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
import os
import urllib.error
import urllib.request

_REMOTE_TIMEOUT_SECONDS = 300
_SHARED_SECRET_HEADER = "X-MAHIR-RAG-Key"
_DEFAULT_TOP_K = 5


def query_rag_context(
    question: str, program_id: str, remote_url: str, top_k: int = _DEFAULT_TOP_K
) -> tuple[bool, str, dict[str, object] | None]:
    """POST a grounded question to a remote RAG query endpoint and relay its response.

    Returns the same (ok, message, structuredData) tuple shape as
    `run_remote_image_group_ocr`. Never raises for expected failure modes
    (network errors, timeouts, non-2xx responses, malformed JSON) - all of
    those come back as `(False, <Turkish message>, None)` so a caller can
    treat this the same way regardless of failure cause.
    """

    body = json.dumps({"question": question, "programId": program_id, "topK": top_k}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    shared_secret = os.environ.get("MAHIR_RAG_SHARED_SECRET", "")
    if shared_secret:
        headers[_SHARED_SECRET_HEADER] = shared_secret
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
