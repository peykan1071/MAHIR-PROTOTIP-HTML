"""Forward an image group to a remote MAHIR backend for OCR instead of
running PaddleOCR-VL locally.

The remote side is expected to be the same `run_file_receiver.py` server
(e.g. running in a Google Colab notebook with GPU support), reached through
a tunnel such as cloudflared. Requests mimic exactly what the browser
already sends to `/mahir-upload`, so the remote server needs no special
code path - it is the same app, just running somewhere with more VRAM.
"""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
import uuid

from .file_receiver import UploadedFile

_REMOTE_TIMEOUT_SECONDS = 300


def run_remote_image_group_ocr(
    uploaded_files: list[UploadedFile], remote_url: str
) -> tuple[bool, str, dict[str, object] | None]:
    """POST an image group to a remote /mahir-upload endpoint and relay its response."""

    boundary = uuid.uuid4().hex
    body = _build_multipart_body(uploaded_files, boundary)
    request = urllib.request.Request(
        remote_url.rstrip("/") + "/mahir-upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    try:
        with urllib.request.urlopen(request, timeout=_REMOTE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
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
