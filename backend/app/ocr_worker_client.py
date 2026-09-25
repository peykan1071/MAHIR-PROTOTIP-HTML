"""Forward an image group to the MAHİR OCR worker process instead of loading
PaddleOCR-VL into the web backend.

The other side is `ocr_worker.py` started by `backend/run_ocr_worker.py`
(default `http://127.0.0.1:8002`, configured through `file_receiver.MAHIR_OCR_URL`).
It speaks the same `/mahir-upload` request/response shape as the local file
receiver. This module is stdlib-only so the web backend never imports paddle.
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
from .timing import stage

# İşçi ile paylaşılan yol: `ocr_worker.py` aynı sabiti buradan alır.
UPLOAD_PATH = "/mahir-upload"

# Paylaşılan parola başlığı. İşçi 127.0.0.1 dışına açıldığında (RunPod pod'u)
# bu uç, kimlik doğrulaması olmadan dosya kabul eden açık bir yükleme noktası
# olurdu. Bu katman depoda vardı ve servisler yerele dönünce kaldırılmıştı
# (7189aba); uzak dağıtım geri geldiği için aynı desenle geri geliyor.
# `ocr_worker.py` aynı sabiti buradan alır - iki taraf tek yerden okusun.
#
# Parola BOŞSA doğrulama tümüyle atlanır: yerelde (varsayılan kurulum)
# hiçbir şey değişmez, yalnız uzak dağıtımda ayarlanır.
SHARED_SECRET_HEADER = "X-MAHIR-OCR-Key"
SHARED_SECRET_ENV = "MAHIR_OCR_SHARED_SECRET"

_WORKER_TIMEOUT_SECONDS = 300
# Canlıda ölçüldü: WinError 10053 tek bir anlık blip değil, aynı yükleme
# içinde birden fazla denemeyi arka arkaya vurabilen tekrarlayan bir yerel
# ağ/rota kesintisi olabiliyor (bkz. `_post_to_worker_with_retry`). Yerel
# işçide de aynı yeniden deneme işe yarar: işçi modeli yüklerken bağlantı
# reddedilebilir. Artan beklemeyle 2 yeniden deneme (toplam 3 deneme, ~7 sn).
_CONNECTION_RETRY_DELAYS_SECONDS = (2, 5)
_UNREACHABLE_MESSAGE = "OCR işçisine ulaşılamadı (backend/run_ocr_worker.py çalışıyor mu?)"


def _post_to_worker(request: urllib.request.Request) -> dict[str, object]:
    with urllib.request.urlopen(request, timeout=_WORKER_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_to_worker_with_retry(request: urllib.request.Request) -> dict[str, object]:
    """Post once, then retry on connection-level failures only.

    `HTTPError` is a real answer from the worker (500/...) and is re-raised
    immediately - retrying it would not change the outcome. Only
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


def request_image_group_ocr(
    uploaded_files: list[UploadedFile], worker_url: str
) -> tuple[bool, str, dict[str, object] | None]:
    """POST an image group to the worker's /mahir-upload endpoint and relay its response."""

    boundary = uuid.uuid4().hex
    body = _build_multipart_body(uploaded_files, boundary)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    secret = os.environ.get(SHARED_SECRET_ENV, "")
    if secret:
        headers[SHARED_SECRET_HEADER] = secret
    request = urllib.request.Request(
        worker_url.rstrip("/") + UPLOAD_PATH,
        data=body,
        method="POST",
        headers=headers,
    )

    # İşçi çağrısının kendi süresi ayrı ölçülüyor: yerel toplamla arasındaki
    # fark yerel ayrıştırma, buradaki büyük süre ise işçinin model yüklemesi
    # (ilk istekte) + gerçek OCR. Süreyi dönüş tipine eklemek yerine burada
    # basmak kasıtlı: 3'lü demet `run_image_group_ocr` -> `run_existing_backend_flow`
    # -> `do_POST` boyunca akıyor ve testler ona bağlı; her katmanın kendi
    # satırını basması `ocr_engine`in bugün yaptığının aynısı.
    try:
        with stage("ocr-isci", dosya=len(uploaded_files), bayt=len(body)):
            payload = _post_to_worker_with_retry(request)
    except urllib.error.HTTPError as error:
        # The worker still answers with its usual {"ok", "message", ...} JSON body even on a
        # non-2xx status - surface that message instead of the generic "HTTP Error 500" text.
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return False, str(payload.get("message") or error), None
        except (ValueError, UnicodeDecodeError, http.client.IncompleteRead):
            return False, f"{_UNREACHABLE_MESSAGE}: {error}", None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return False, f"{_UNREACHABLE_MESSAGE}: {error}", None

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
