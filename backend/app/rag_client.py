"""Send a document-grounded question to the remote MAHIR RAG worker instead of
running any embedding/LLM pipeline locally.

The remote side is expected to be `rag_service.py`'s `RAGInference.web_query`
HTTP endpoint (see `rag_service.py` for how it's deployed). It speaks the same
`{"ok", "message", "structuredData"}` response shape as `remote_ocr_client.py`,
so callers need no special-casing.

Unlike `remote_ocr_client.py`, no path is appended to `remote_url`: OCR's
remote is a hand-rolled server behind `@modal.web_server` that forwards any
path, while `RAGInference.web_query` is a `@modal.fastapi_endpoint` - Modal
generates one full URL per method, and that URL's root *is* the route.
`remote_url` must be the exact URL `modal deploy rag_service.py` printed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

_REMOTE_TIMEOUT_SECONDS = 300
# Parçalar 512 token ve getirim zaten tek bir temaya (≈8-9 PDF sayfası)
# kısıtlı olduğundan, daha büyük bir k konu dışına çıkma riski getirmeden
# modele kazanımın kendi metninden daha fazlasını verir.
_DEFAULT_TOP_K = 8


def warm_up_remote_rag(remote_url: str) -> bool:
    """Ask the remote RAG service to boot and load its models now.

    Its cold start is ~110 s (container + bge-m3 + vLLM/Qwen2.5-7B, measured -
    see `modal app logs turkish-rag-system`), and today that whole wait lands on
    the teacher pressing "approve and analyse". Calling this while they are
    still reviewing scores moves it out of the way; `scaledown_window=300` in
    `rag_service.py` keeps the container up long enough to cover that review.

    Never raises - a failed warm-up must stay invisible, the analysis that
    follows works exactly as before, just slower.
    """

    return _post(remote_url, {"warmup": True})[0]


def query_rag_contexts(
    items: list[dict[str, object]],
    program_id: str,
    remote_url: str,
    top_k: int = _DEFAULT_TOP_K,
) -> tuple[bool, str, list[dict[str, object]] | None]:
    """POST several grounded questions in ONE request; results come back in order.

    CANLI AKIŞTA ÇAĞRILMIYOR (bu ve `query_rag_context`): Faz 3'te getirim ajan
    kuyruğuna taşındı, teşhis artık `agents/llm.py` üzerinden birleşik `agents`
    biçimiyle gidiyor. İkisi burada duruyor çünkü `rag_service.py`nin eski
    `queries` biçiminin tek istemcisi onlar ve o sunucu dalı geriye dönük uyum
    için bilinçli olarak korunuyor. İstemci ile sunucu dalı BİRLİKTE kaldırılmalı
    - yalnız birini silmek diğerini test edilemez hâle getirir.

    Each item is `{"question", "retrievalQuery", "grade", "theme"}` - the same
    fields `query_rag_context` sends for a single question. The remote answers
    them in a single vLLM batch, which is why this exists: measured warm, one
    question costs ~10 s of which 7-8.6 s is generation at ~29 output tokens/s,
    i.e. single-sequence decode speed. Decoding several sequences together
    barely costs more than one, so N weak outcomes cost ~10 s instead of N×10 s.

    Same never-raises contract as `query_rag_context`; on any failure the caller
    can fall back to calling `query_rag_context` per outcome.
    """

    body_payload: dict[str, object] = {"queries": items, "programId": program_id, "topK": top_k}
    ok, message, structured_data = _post(remote_url, body_payload)
    if not ok or not isinstance(structured_data, dict):
        return ok, message, None
    results = structured_data.get("results")
    if not isinstance(results, list) or len(results) != len(items):
        return False, "Toplu RAG yanıtı sorgu sayısıyla eşleşmedi.", None
    return True, message, results


def query_rag_context(
    question: str,
    program_id: str,
    remote_url: str,
    top_k: int = _DEFAULT_TOP_K,
    grade: str | None = None,
    theme: str | None = None,
    retrieval_query: str | None = None,
) -> tuple[bool, str, dict[str, object] | None]:
    """POST a grounded question to a remote RAG query endpoint and relay its response.

    `grade`/`theme`, if given, are forwarded as extra (AND) retrieval filters
    alongside `program_id` - see `rag_service.py::_run_query`. `grade` is the
    high-confidence filter (matches `program_catalog.ProgramProfile.grade`
    directly, no normalization risk); `theme` is best-effort (the exam's
    `outcomeTheme` text must be normalized to match the indexed theme label -
    see `approved_data_analyzer.py::_normalize_theme_for_rag`).

    `retrieval_query`, if given, is what gets embedded for the vector search
    while `question` still goes to the LLM. They are separated on purpose:
    `question` carries the success rate and a "diagnose this" imperative, and
    neither has any counterpart in the curriculum PDF - embedding them drags
    the query vector away from the curriculum prose. Omit it and the remote
    embeds `question`, i.e. exactly the previous behaviour.

    Returns the same (ok, message, structuredData) tuple shape as
    `run_remote_image_group_ocr`. Never raises for expected failure modes
    (network errors, timeouts, non-2xx responses, malformed JSON) - all of
    those come back as `(False, <Turkish message>, None)` so a caller can
    treat this the same way regardless of failure cause.
    """

    body_payload: dict[str, object] = {"question": question, "programId": program_id, "topK": top_k}
    if grade:
        body_payload["grade"] = grade
    if theme:
        body_payload["theme"] = theme
    if retrieval_query:
        body_payload["retrievalQuery"] = retrieval_query
    return _post(remote_url, body_payload)


def _post(remote_url: str, body_payload: dict[str, object]) -> tuple[bool, str, object | None]:
    """Tek/toplu sorgu ve ısıtmanın ortak HTTP gövdesi - hepsi aynı uç noktaya
    gidiyor (Modal her `@modal.fastapi_endpoint` metoduna TEK bir URL üretiyor,
    bu yüzden ayrı bir ısıtma URL'si yapılandırmak yerine gövdeye bir bayrak
    koyuyoruz)."""

    body = json.dumps(body_payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(remote_url.rstrip("/"), data=body, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=_REMOTE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # The worker still answers with its usual {"ok", "message", ...} JSON body even on a
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
