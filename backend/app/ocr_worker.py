"""Dedicated OCR worker server - meant to run where a real GPU is available
(e.g. a Google Colab notebook, see `colab/mahir_ocr_colab.ipynb`), separate
from the local MAHIR file receiver (`file_receiver.py`), which has no
PaddleOCR dependency and simply forwards image groups here over HTTP (see
`remote_ocr_client.py`).

Speaks the same request/response shape as `file_receiver.py`'s
`/mahir-upload` (`{"ok", "message", "structuredData"}`) so `remote_ocr_client.py`
needs no special-casing for what it's talking to.
"""

from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ocr_engine
from .file_receiver import (
    IMAGE_EXTENSIONS,
    MAX_FILES_PER_UPLOAD,
    MAX_REQUEST_SIZE,
    MAX_UPLOAD_SIZE,
    extract_uploaded_files,
    validate_file_name,
)
from .ocr_protocol import SHARED_SECRET_HEADER, UPLOAD_PATH, WARMUP_PATH


class OCRWorkerHandler(BaseHTTPRequestHandler):
    server_version = "MAHIROCRWorker/0.1"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        """Ön-ısıtma: konteyneri ayağa kaldırıp modelleri GPU'ya yükletir.

        Ölçüldü (bkz. `modal app logs mahir-ocr-worker`): bir isteğin 50-57
        saniyesinin 30-50'si konteyner açılışı + model yükleme, yalnızca 7-12
        saniyesi gerçek OCR. Bu uç nokta o hazırlığı, öğretmen daha dosyalarını
        seçerken tetiklemek için var - hiç predict çalıştırmaz.

        `ensure_available()` idempotenttir (`ocr_engine._get_pipeline` tek
        seferlik kurulum yapar), bu yüzden sıcak bir konteynerde anında döner.
        Paylaşılan parola doğrulaması bilinçli olarak uygulanmıyor: uç nokta
        hiçbir veri kabul etmiyor ve hiçbir şey döndürmüyor, tek etkisi bu
        konteyneri hazırlamak.
        """

        if self.path != WARMUP_PATH:
            self._send_json(404, {"ok": False, "message": "Bilinmeyen alıcı yolu."})
            return

        try:
            ocr_engine.ensure_available()
        except RuntimeError as error:
            self._send_json(503, {"ok": False, "ready": False, "message": str(error)})
            return
        self._send_json(200, {"ok": True, "ready": True, "message": "OCR hattı hazır."})

    def do_POST(self) -> None:
        if self.path != UPLOAD_PATH:
            self._send_json(404, {"ok": False, "message": "Bilinmeyen alıcı yolu."})
            return

        expected_secret = os.environ.get("MAHIR_OCR_SHARED_SECRET", "")
        if expected_secret and not hmac.compare_digest(
            self.headers.get(SHARED_SECRET_HEADER, ""), expected_secret
        ):
            self._send_json(401, {"ok": False, "message": "Yetkisiz istek."})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        content_type = self.headers.get("Content-Type", "")

        if content_length <= 0 or content_length > MAX_REQUEST_SIZE:
            self._send_json(400, {"ok": False, "message": "Dosya verisi alınamadı."})
            return

        body = self.rfile.read(content_length)
        uploaded_files = extract_uploaded_files(body, content_type)

        if not uploaded_files or len(uploaded_files) > MAX_FILES_PER_UPLOAD:
            self._send_json(400, {"ok": False, "message": "Dosya verisi alınamadı."})
            return

        checks = [validate_file_name(f.file_name) for f in uploaded_files]
        invalid = next((c for c in checks if not c.is_allowed or c.extension not in IMAGE_EXTENSIONS), None)
        if invalid is not None:
            self._send_json(400, {"ok": False, "message": "Yalnızca görsel dosyalar OCR ile okunabilir."})
            return
        oversized = next((f for f in uploaded_files if len(f.content) > MAX_UPLOAD_SIZE), None)
        if oversized is not None:
            limit_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
            self._send_json(413, {"ok": False, "message": f"Dosya {limit_mb} MB sınırını aşıyor."})
            return

        ok, message, structured_data = _run_image_group_ocr(uploaded_files, checks)
        self._send_json(200 if ok else 500, {"ok": ok, "message": message, "structuredData": structured_data})

    def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _run_image_group_ocr(uploaded_files, file_checks) -> tuple[bool, str, dict[str, object] | None]:
    try:
        ocr_engine.ensure_available()
    except RuntimeError as error:
        return False, str(error), None

    students: list[dict[str, object]] = []
    warnings: list[str] = []

    for uploaded_file, file_check in zip(uploaded_files, file_checks):
        try:
            rows = ocr_engine.read_student_rows(uploaded_file.content, file_check.extension)
        except Exception as error:  # noqa: BLE001 - OCR is a third-party ML pipeline; one bad/unreadable
            # image must not drop the whole batch or crash the request thread.
            warnings.append(f"{uploaded_file.file_name}: {error}")
            rows = [
                {
                    "studentNo": "Okunamadı",
                    "scores": [],
                    "totalScore": None,
                    "calculatedTotal": 0,
                    "control": "",
                }
            ]
        for row in rows:
            privacy_findings = set(row.pop("privacyFindings", []) or [])
            labels = _translate_privacy_findings(privacy_findings)
            if labels:
                warnings.append(
                    f"{uploaded_file.file_name}: KVKK uyarısı — {' ve '.join(labels)} "
                    "algılandı ve öğrenci analiz verisinden çıkarıldı."
                )
            row["rowNumber"] = len(students) + 1
            students.append(row)

    return (
        True,
        f"{len(uploaded_files)} görsel OCR ile okundu ve öğretmen kontrolüne hazırlandı.",
        {
            "exam": {},
            "questions": [],
            "students": students,
            "warnings": warnings,
            "summary": {
                "questionCount": 0,
                "studentCount": len(students),
                "warningCount": len(warnings),
            },
        },
    )


def _translate_privacy_findings(findings: set[str]) -> list[str]:
    """OCR sınırındaki gizlilik bulgu kodlarını öğretmene gösterilecek Türkçe etikete çevir."""

    labels = []
    if "TCKN" in findings:
        labels.append("T.C. kimlik numarası")
    if "AD_SOYAD" in findings:
        labels.append("ad-soyad")
    return labels


def create_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), OCRWorkerHandler)
