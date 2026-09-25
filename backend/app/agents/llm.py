"""Ajanların paylaştığı LLM katmanı.

Bir turda kaç ajan LLM'e ihtiyaç duyarsa duysun, hepsinin prompt'u TEK
istekte yerel RAG servisine (`local/rag_service.py`, `/agents`) gider; servis
getirimi yapar ve yanıtları llama-server'dan ardışık üretip giriş sırasıyla
döndürür. Tek istek: bir tur = bir ağ çağrısı, bir hata noktası, bir iz kaydı.
Mevcut prototipte Ölçme ve Pedagojik Analiz ajanlarının istemleri bu ortak
turda birleştirilir. Katman daha fazla uzman rolü aynı turda taşıyabilecek
biçimde kurulmuştur; bu, bütün ajanların LLM kullandığı anlamına gelmez.

Servis adresi `approved_data_analyzer.MAHIR_RAG_URL` (varsayılan
http://127.0.0.1:8001/agents; boş string LLM turunu kapatır). HTTP istemcisi de
burada (`_post_json`) - `ocr_worker_client.py` ile aynı `{"ok", "message",
"structuredData"}` zarfı. Bu modül **asla istisna fırlatmaz**: LLM arızası
isteğe bağlı bir ajanı düşürür, öğretmenin analizini değil (bkz.
`agents/orchestrator.py`, zorunlu/isteğe bağlı ayrımı).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

# Servisin sınırlarıyla aynı olmalı (bkz. local/rag_service.py MAX_AGENT_*).
# Burada da kontrol ediliyor ki ağ turu boşa harcanmasın ve hata mesajı
# çağırana yakın yerde üretilsin.
MAX_PROMPTS_PER_REQUEST = 16

# Servisin anladığı alanlar. Kuyruktaki sözlük bunlardan fazlasını
# taşıyabiliyor (ör. `agent`: LLM kaydının hangi ajanın izine düşeceği) ve o
# alanlar yerel - beyaz liste, çağıran tarafın iç alanlarının sessizce ağa
# sızmasını yapısal olarak engelliyor.
_WIRE_KEYS = ("name", "system", "user", "maxTokens", "retrieval")

# llama-server bir turun N prompt'unu ARDIŞIK çözer (--parallel 1): prompt
# başına ~10 s LLM + reranker açıksa ~20 s CPU. 8 zayıf öğrenme çıktısı ≈ 4 dk.
# Bu istek analiz sırasında tek bir kez gidiyor.
_SERVICE_TIMEOUT_SECONDS = 600
_UNREACHABLE_MESSAGE = "RAG servisine ulaşılamadı (local/rag_service.py çalışıyor mu?)"

# Paylaşılan parola başlığı - `local/rag_service.py` aynı adı bekler.
# Servis 127.0.0.1 dışına açıldığında (RunPod pod'u) `/agents` ucu GPU'yu
# meşgul eden açık bir üretim noktası olurdu. Parola BOŞSA başlık hiç
# gönderilmez ve servis de doğrulama yapmaz - yerel kurulumda davranış aynı.
SHARED_SECRET_HEADER = "X-MAHIR-RAG-Key"
SHARED_SECRET_ENV = "MAHIR_RAG_SHARED_SECRET"


def build_prompt(agent: str, system: str, user: str, max_tokens: int | None = None) -> dict[str, Any]:
    """Servisin beklediği tek prompt sözlüğünü kurar."""

    item: dict[str, Any] = {"name": agent, "system": system, "user": user}
    if max_tokens:
        item["maxTokens"] = int(max_tokens)
    return item


def _post_json(service_url: str, body_payload: dict[str, object]) -> tuple[bool, str, object | None]:
    """Ajan turunun HTTP gövdesi: `POST <service_url>` JSON -> `(ok, mesaj, structuredData)`.

    Servis (`local/rag_service.py` `/agents`) `{"ok", "message", "structuredData"}`
    zarfını 2xx dışı durumda da döndürür; o Türkçe mesaj öne çıkarılır.
    Beklenen arıza kipleri (ağ hatası, zaman aşımı, bozuk JSON) istisna değil
    `(False, <Türkçe mesaj>, None)` döndürür - bu modül asla istisna fırlatmaz.
    """

    body = json.dumps(body_payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = os.environ.get(SHARED_SECRET_ENV, "")
    if secret:
        headers[SHARED_SECRET_HEADER] = secret
    request = urllib.request.Request(service_url.rstrip("/"), data=body, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=_SERVICE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return False, str(payload.get("message") or error), None
        except (ValueError, UnicodeDecodeError):
            return False, f"{_UNREACHABLE_MESSAGE}: {error}", None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return False, f"{_UNREACHABLE_MESSAGE}: {error}", None

    return (
        bool(payload.get("ok")),
        str(payload.get("message", "")),
        payload.get("structuredData"),
    )


def run_agent_prompts(
    items: list[dict[str, Any]],
    service_url: str,
) -> tuple[bool, str, list[dict[str, Any]] | None]:
    """Prompt'ları tek partide çalıştırır; sonuçlar giriş sırasıyla döner.

    Dönen her öğe: `{"name", "answer", "sources", "promptChars",
    "answerChars", "durationMs", "strippedSentences"}`.

    `strippedSentences` her zaman 0: bu katman yanıt METNİNE hiç dokunmaz -
    cümle düzeyinde kırpma JSON alan sınırlarını tanımadan çalışıp
    yapılandırılmış yanıtları bozardı (bkz. `test_json_shaped_answers_are_
    exempt_from_sentence_stripping`). Charter süzgeci artık ayrıştırılmış
    `diagnosis` alanı üzerinde, `pipeline.py::_compose_grounded_pedagogical_
    answer` içindeki `_strip_scope_violations`de uygulanır - alan hâlâ
    burada taşınıyor çünkü `PedagogicalAnalysisAgent._evaluate_diagnosis_
    result` onu okuyor.
    """

    if not items:
        return False, "Gönderilecek ajan prompt'u yok.", None
    if len(items) > MAX_PROMPTS_PER_REQUEST:
        return False, f"Tek istekte en çok {MAX_PROMPTS_PER_REQUEST} prompt gönderilebilir.", None

    wire = [{key: item[key] for key in _WIRE_KEYS if key in item} for item in items]

    began = time.monotonic()
    ok, message, structured_data = _post_json(service_url, {"agents": wire})
    duration_ms = (time.monotonic() - began) * 1000
    if not ok or not isinstance(structured_data, dict):
        return ok, message, None

    results = structured_data.get("results")
    if not isinstance(results, list) or len(results) != len(items):
        # Sıraya göre eşleştirme yapıldığı için sayı tutmuyorsa hiçbir sonuca
        # güvenilemez - yanlış ajana yanlış yanıt bağlamaktansa hepsini düşür.
        return False, "Ajan yanıt sayısı istek sayısıyla eşleşmedi.", None

    enriched: list[dict[str, Any]] = []
    for item, result in zip(items, results):
        answer = str((result or {}).get("answer") or "")
        enriched.append({
            "name": str(item.get("name") or ""),
            "answer": answer,
            # Getirim isabetleri: çağıran taraf bunlara bakıp "kaynak yoksa
            # teşhis yazma" diyor (bkz. PedagogicalAnalysisAgent.apply_llm).
            # Düşürülürse getirim çalışsa bile her teşhis sessizce elenir.
            "sources": (result or {}).get("sources") or [],
            "promptChars": len(str(item.get("system") or "")) + len(str(item.get("user") or "")),
            "answerChars": len(answer),
            # Parti tek istek olduğu için süre partinin tamamına ait; öğe
            # başına ayrıştırmak mümkün değil ve yanıltıcı olurdu.
            "durationMs": round(duration_ms, 1),
            "strippedSentences": 0,
        })
    return True, message, enriched


def trace_entry(result: dict[str, Any]) -> dict[str, Any]:
    """`AgentTrace.llm_calls`e yazılacak kaydı üretir.

    Prompt ve yanıt METNİ kasıtlı olarak dışarıda: iz yalnız sayım ve özet
    taşıyor (bkz. `tests/test_agent_pipeline.py::test_trace_carries_no_student_rows`)
    ve bu kural, öğrenci verisinin ize sızmasını yapısal olarak engelliyor.
    """

    return {
        "agent": result.get("name", ""),
        "promptChars": result.get("promptChars", 0),
        "answerChars": result.get("answerChars", 0),
        "durationMs": result.get("durationMs", 0.0),
    }
