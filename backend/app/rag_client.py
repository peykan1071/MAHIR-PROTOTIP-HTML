"""HTTP client for the MAHİR RAG service running out of process
(`local/rag_service.py`, `POST /agents`) - no embedding/LLM code runs here.

The service speaks the same `{"ok", "message", "structuredData"}` response
envelope as `remote_ocr_client.py`, so callers need no special-casing. Unlike
`remote_ocr_client.py`, no path is appended to `remote_url`: the configured URL
(`approved_data_analyzer.MAHIR_RAG_REMOTE_URL`, default
`http://127.0.0.1:8001/agents`) *is* the route; warm-up and the agent round
both go there, distinguished by the request body.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# llama-server bir turun N prompt'unu ARDIŞIK çözer (--parallel 1): prompt
# başına ~10 s LLM + reranker açıksa ~20 s CPU. 8 zayıf öğrenme çıktısı ≈ 4 dk;
# 300 s yetmiyordu. Bu istek analiz sırasında tek bir kez gidiyor.
_REMOTE_TIMEOUT_SECONDS = 600


def warm_up_remote_rag(remote_url: str) -> bool:
    """Ask the RAG service to load its models now (idempotent on the service side).

    Embedder + reranker take tens of seconds to come into memory on first use;
    calling this while the teacher is still reviewing scores moves that wait
    out of the "approve and analyse" click. Never raises - a failed warm-up
    must stay invisible, the analysis that follows works exactly as before,
    just slower.
    """

    return _post(remote_url, {"warmup": True})[0]


def _post(remote_url: str, body_payload: dict[str, object]) -> tuple[bool, str, object | None]:
    """Isıtma ve ajan turunun ortak HTTP gövdesi - ikisi de aynı uç noktaya
    gider, ayrım gövdedeki bayraktadır (`{"warmup": true}` / `{"agents": [...]}`).

    Beklenen arıza kipleri (ağ hatası, zaman aşımı, 2xx dışı yanıt, bozuk
    JSON) istisna değil `(False, <Türkçe mesaj>, None)` döndürür; `agents/llm.py`
    bu sözleşmeye dayanır.
    """

    body = json.dumps(body_payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(remote_url.rstrip("/"), data=body, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=_REMOTE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # The service still answers with its usual {"ok", "message", ...} JSON body even on a
        # non-2xx status - surface that message instead of the generic "HTTP Error 500" text.
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return False, str(payload.get("message") or error), None
        except (ValueError, UnicodeDecodeError):
            return False, f"Uzak RAG sunucusuna ulaşılamadı: {error}", None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return False, f"Uzak RAG sunucusuna ulaşılamadı: {error}", None

    return (
        bool(payload.get("ok")),
        str(payload.get("message", "")),
        payload.get("structuredData"),
    )
