"""Ajanların paylaştığı LLM katmanı.

Bir turda kaç ajan LLM'e ihtiyaç duyarsa duysun, hepsinin prompt'u TEK istekte
ve TEK vLLM partisinde gider. Sebep ölçüldü: vLLM'de N dizinin birlikte
çözülmesi neredeyse tek dizi kadar sürüyor (darboğaz GPU'nun bellek bant
genişliği, hesap gücü değil). Mevcut prototipte Ölçme ve Pedagojik Analiz
ajanlarının istemleri bu ortak turda birleştirilir. Katman daha fazla uzman
rolü aynı turda taşıyabilecek biçimde kurulmuştur; bu, bütün ajanların LLM
kullandığı anlamına gelmez.

Bu modül `rag_client` ile aynı sözleşmeyi taşır: **asla istisna fırlatmaz**.
LLM arızası isteğe bağlı bir ajanı düşürür, öğretmenin analizini değil
(bkz. `agents/orchestrator.py`, zorunlu/isteğe bağlı ayrımı).
"""

from __future__ import annotations

import time
from typing import Any

# Uzak uç noktanın sınırlarıyla aynı olmalı (bkz. rag_service.py MAX_AGENT_*).
# Burada da kontrol ediliyor ki ağ turu boşa harcanmasın ve hata mesajı
# çağırana yakın yerde üretilsin.
MAX_PROMPTS_PER_REQUEST = 16

# Uzak uç noktanın anladığı alanlar. Kuyruktaki sözlük bunlardan fazlasını
# taşıyabiliyor (ör. `agent`: LLM kaydının hangi ajanın izine düşeceği) ve o
# alanlar yerel - beyaz liste, çağıran tarafın iç alanlarının sessizce ağa
# sızmasını yapısal olarak engelliyor.
_WIRE_KEYS = ("name", "system", "user", "maxTokens", "retrieval")


def build_prompt(agent: str, system: str, user: str, max_tokens: int | None = None) -> dict[str, Any]:
    """Uzak uç noktanın beklediği tek prompt sözlüğünü kurar."""

    item: dict[str, Any] = {"name": agent, "system": system, "user": user}
    if max_tokens:
        item["maxTokens"] = int(max_tokens)
    return item


def run_agent_prompts(
    items: list[dict[str, Any]],
    remote_url: str,
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

    # `rag_client._post` yeniden kullanılıyor: HTTPError gövdesinden Türkçe
    # mesaj çıkarmayı ve zaman aşımını zaten doğru yapıyor. İkinci bir HTTP
    # istemcisi yazmak bunu kopyalamak olurdu.
    from ..rag_client import _post

    wire = [{key: item[key] for key in _WIRE_KEYS if key in item} for item in items]

    began = time.monotonic()
    ok, message, structured_data = _post(remote_url, {"agents": wire})
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
