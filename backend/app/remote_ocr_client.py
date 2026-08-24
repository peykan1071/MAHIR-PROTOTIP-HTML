"""Forward an image group to a remote MAHIR OCR worker instead of running
PaddleOCR-VL locally.

The remote side is expected to be `ocr_worker.py` (see `modal_app.py` for
how it's deployed). It speaks the same `/mahir-upload` request/response
shape as the local file receiver.
"""

from __future__ import annotations

import json
import http.client
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid

from .file_receiver import UploadedFile
from .ocr_protocol import SHARED_SECRET_HEADER, UPLOAD_PATH, WARMUP_PATH
from .timing import stage

_REMOTE_TIMEOUT_SECONDS = 300
# Canlıda ölçüldü: WinError 10053 tek bir anlık blip değil, aynı yükleme
# içinde birden fazla denemeyi arka arkaya vurabilen tekrarlayan bir yerel
# ağ/rota kesintisi olabiliyor (bkz. `_post_to_worker_with_retry`). Artan
# beklemeyle 2 yeniden deneme (toplam 3 deneme, ~7 sn ek bekleme) bu tür
# kesintilere tek seferlik bir denemeden daha dayanıklı.
_CONNECTION_RETRY_DELAYS_SECONDS = (2, 5)
_SHARED_SECRET_HEADER = "X-MAHIR-OCR-Key"
# `ocr_worker.WARMUP_PATH` ile aynı olmalı - burada elle tekrarlanıyor çünkü bu
# modül öğretmenin makinesinde çalışıyor ve PaddleOCR bağımlısı `ocr_worker`i
# import edemez (modül docstring'i).
WARMUP_PATH = "/mahir-warmup"


def _post_to_worker(request: urllib.request.Request) -> dict[str, object]:
    with urllib.request.urlopen(request, timeout=_REMOTE_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_to_worker_with_retry(request: urllib.request.Request) -> dict[str, object]:
    """Post once, then retry on connection-level failures only.

    `HTTPError` is a real answer from the server (401/500/...) and is
    re-raised immediately - retrying it would not change the outcome. Only
    `URLError`/`TimeoutError`/`OSError` (the request never reaching the
    worker at all, e.g. WinError 10053) gets retried, backing off across
    `_CONNECTION_RETRY_DELAYS_SECONDS`.
    """
    last_error: Exception | None = None
    for delay in (0, *_CONNECTION_RETRY_DELAYS_SECONDS):
        if delay:
            time.sleep(delay)
        try:
            return _post_to_worker(request)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
    raise last_error


def run_remote_image_group_ocr(
    uploaded_files: list[UploadedFile], remote_url: str
) -> tuple[bool, str, dict[str, object] | None]:
    """POST an image group to a remote /mahir-upload endpoint and relay its response."""

    boundary = uuid.uuid4().hex
    body = _build_multipart_body(uploaded_files, boundary)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    shared_secret = os.environ.get("MAHIR_OCR_SHARED_SECRET", "")
    if shared_secret:
        headers[SHARED_SECRET_HEADER] = shared_secret
    request = urllib.request.Request(
        remote_url.rstrip("/") + UPLOAD_PATH,
        data=body,
        method="POST",
        headers=headers,
    )

    # Uzak çağrının kendi süresi ayrı ölçülüyor: yerel toplamla arasındaki fark
    # yerel ayrıştırma, buradaki büyük süre ise uzak konteynerin soğuk
    # başlangıcı (ölçülen 30-50 sn, gerçek OCR yalnız 7-12 sn). Süreyi dönüş
    # tipine eklemek yerine burada basmak kasıtlı: 3'lü demet
    # `run_image_group_ocr` -> `run_existing_backend_flow` -> `do_POST` boyunca
    # akıyor ve testler ona bağlı; her katmanın kendi satırını basması
    # `ocr_engine`in bugün yaptığının aynısı.
    try:
        with stage("ocr-uzak", dosya=len(uploaded_files), bayt=len(body)):
            payload = _post_to_worker_with_retry(request)
    except urllib.error.HTTPError as error:
        # The worker still answers with its usual {"ok", "message", ...} JSON body even on a
        # non-2xx status - surface that message instead of the generic "HTTP Error 500" text.
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return False, str(payload.get("message") or error), None
        except (ValueError, UnicodeDecodeError, http.client.IncompleteRead):
            if error.code == 401:
                return (
                    False,
                    "Uzak OCR yetkilendirmesi başarısız. Yerel ve Modal OCR anahtarlarını eşitleyiniz.",
                    None,
                )
            return False, f"Uzak OCR sunucusuna ulaşılamadı: {error}", None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return False, f"Uzak OCR sunucusuna ulaşılamadı: {error}", None

    return (
        bool(payload.get("ok")),
        str(payload.get("message", "")),
        payload.get("structuredData"),
    )


def warm_up_remote_ocr(remote_url: str) -> bool:
    """Ask the remote worker to load its models now, before any real upload.

    A cold Modal container spends 30-50 s booting and loading PaddleOCR-VL onto
    the GPU, against only 7-12 s of actual OCR (measured, see `modal app logs
    mahir-ocr-worker`). Calling this the moment the teacher picks files moves
    that preparation off the wait that follows "Verileri Oku ve Kontrol Et".

    Never raises: a warm-up is best-effort by definition, and a failed one must
    stay invisible - the upload that follows works exactly as before, just
    slower. Returns whether the remote reported itself ready, for tests/logs.
    """

    request = urllib.request.Request(remote_url.rstrip("/") + WARMUP_PATH, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=_REMOTE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - ısıtma en iyi çaba; hiçbir hata dışarı sızmamalı.
        return False
    return bool(payload.get("ok"))


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
