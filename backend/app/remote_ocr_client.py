"""Forward an image group to a remote MAHIR OCR worker instead of running
PaddleOCR-VL locally.

The remote side is expected to be `ocr_worker.py` (see `modal_app.py` for
how it's deployed). It speaks the same `/mahir-upload` request/response
shape as the local file receiver.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

from .file_receiver import UploadedFile

_REMOTE_TIMEOUT_SECONDS = 300
_SHARED_SECRET_HEADER = "X-MAHIR-OCR-Key"


def run_remote_image_group_ocr(
    uploaded_files: list[UploadedFile], remote_url: str
) -> tuple[bool, str, dict[str, object] | None]:
    """POST an image group to a remote /mahir-upload endpoint and relay its response."""

    boundary = uuid.uuid4().hex
    body = _build_multipart_body(uploaded_files, boundary)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    shared_secret = os.environ.get("MAHIR_OCR_SHARED_SECRET", "")
    if shared_secret:
        headers[_SHARED_SECRET_HEADER] = shared_secret
    request = urllib.request.Request(
        remote_url.rstrip("/") + "/mahir-upload",
        data=body,
        method="POST",
        headers=headers,
    )

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
            return False, f"Uzak OCR sunucusuna ulaşılamadı: {error}", None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return False, f"Uzak OCR sunucusuna ulaşılamadı: {error}", None

    return (
        bool(payload.get("ok")),
        str(payload.get("message", "")),
        payload.get("structuredData"),
    )


def _build_multipart_body(uploaded_files: list[UploadedFile], boundary: str) -> bytes:
    parts: list[bytes] = []
    for uploaded_file in uploaded_files:
        content_type = mimetypes.guess_type(uploaded_file.file_name)[0] or "application/octet-stream"
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="exam-file"; filename="{uploaded_file.file_name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        )
        parts.append(header.encode("utf-8") + uploaded_file.content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)
