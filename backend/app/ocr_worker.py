"""Dedicated OCR worker server (PaddleOCR-VL on the local GPU), run as its own
process by `backend/run_ocr_worker.py` on 127.0.0.1:8002 - separate from the
MAHIR file receiver (`file_receiver.py`), which has no PaddleOCR dependency
and simply forwards image groups here over HTTP (see `ocr_worker_client.py`).

Speaks the same request/response shape as `file_receiver.py`'s
`/mahir-upload` (`{"ok", "message", "structuredData"}`) so `ocr_worker_client.py`
needs no special-casing for what it's talking to.
"""

from __future__ import annotations

import json
import re
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
from .ocr_worker_client import UPLOAD_PATH


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

    def do_POST(self) -> None:
        if self.path != UPLOAD_PATH:
            self._send_json(404, {"ok": False, "message": "Bilinmeyen alıcı yolu."})
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
            self._send_json(413, {"ok": False, "message": "Dosya 20 MB sınırını aşıyor."})
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

    documents: list[dict[str, object]] = []
    warnings: list[str] = []

    for uploaded_file, file_check in zip(uploaded_files, file_checks):
        # Kaynak görsel adı öğretmenin yüklediği gerçek dosya adıdır. Bu ad
        # yalnız izlenebilirlik içindir; hiçbir OCR veya sınıflandırma kararına
        # katılmaz.
        document_ref = uploaded_file.file_name
        try:
            document = ocr_engine.read_exam_document(uploaded_file.content, file_check.extension)
        except Exception as error:  # noqa: BLE001 - OCR is a third-party ML pipeline; one bad/unreadable
            # image must not drop the whole batch or crash the request thread.
            warnings.append(f"{document_ref}: Alanlar boş bırakıldı; görseli kontrol ederek manuel doldurunuz.")
            document = {
                "exam": {}, "questions": [],
                "student": {"studentNo": "", "scores": [], "totalScore": None, "calculatedTotal": 0, "control": ""},
                "privacyFindings": [],
            }
        privacy_findings = set(document.pop("privacyFindings", []) or [])
        if privacy_findings:
            warnings.append(f"{document_ref}: Kişisel bilgi algılandı; kimlik alanları OCR çıktısına alınmadı.")
        student = dict(document.pop("student", {}) or {})
        # Öğrenci adı hiçbir zaman aktarılmaz. Öğretmenin kontrol ekranında
        # evraktaki "Öğrenci Okul No" gösterilir. Analiz katmanına ise okul
        # numarası yerine yalnızca bu oturuma ait takma teknik kimlik gider.
        student_reference = str(student.get("studentNo") or "").strip()
        student["studentNo"] = student_reference
        student["technicalId"] = f"Ö-{len(documents) + 1:03d}"
        student["rowNumber"] = len(documents) + 1
        student["sourceFile"] = document_ref
        documents.append({**document, "student": student, "documentRef": document_ref})

    def normalize_class_section(value: object) -> str:
        match = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*(?:[-/]\s*|\s+)?([A-Za-zÇĞİÖŞÜçğıöşü])(?![A-Za-z])", str(value or ""))
        return f"{int(match.group(1))}-{match.group(2).upper()}" if match else ""

    def student_sort_key(student: dict[str, object]) -> tuple[object, ...]:
        reference = str(student.get("studentNo") or "").strip()
        numbers = re.findall(r"\d+", reference)
        return (0, int(numbers[-1]), reference.casefold()) if numbers else (1, 0, reference.casefold())

    def group_key(document: dict[str, object]) -> str:
        exam = document.get("exam") or {}
        # OCR sınıflandırmasının tek anahtarı açık etiketli Sınıf/Şube
        # hücresidir. Sınav türü okunmuş olsa bile ayrı grup oluşturmaz.
        return normalize_class_section(exam.get("classSection"))

    grouped: dict[str, dict[str, object]] = {}
    for document in documents:
        key = group_key(document)
        group = grouped.setdefault(key, {
            "exam": document.get("exam") or {}, "questions": document.get("questions") or [],
            "students": [], "documentRefs": [],
            "requiresQuestionCount": not bool(document.get("questions")),
        })
        document_questions = document.get("questions") or []
        if not group.get("questions") and document_questions:
            group["questions"] = document_questions
        group["requiresQuestionCount"] = not bool(group.get("questions"))
        group["students"].append(document["student"])
        group["documentRefs"].append(document["documentRef"])

    for group in grouped.values():
        group["students"].sort(key=student_sort_key)
        for row_number, student in enumerate(group["students"], start=1):
            student["rowNumber"] = row_number
            student["technicalId"] = f"Ö-{row_number:03d}"

    groups = list(grouped.values())
    first = groups[0] if len(groups) == 1 else {"exam": {}, "questions": [], "students": []}

    return (
        True,
        f"{len(uploaded_files)} görsel OCR ile okundu ve öğretmen kontrolüne hazırlandı.",
        {
            "exam": first.get("exam") or {},
            "questions": first.get("questions") or [],
            "students": first.get("students") or [],
            "documents": documents,
            "groups": groups,
            "warnings": warnings,
            "summary": {
                "questionCount": len(first.get("questions") or []),
                "studentCount": len(documents),
                "groupCount": len(groups),
                "warningCount": len(warnings),
            },
        },
    )


def create_server(host: str = "127.0.0.1", port: int = 8002) -> ThreadingHTTPServer:
    """Yalnız loopback, 8002: web backend 8000'de aynı makinede koşuyor."""

    return ThreadingHTTPServer((host, port), OCRWorkerHandler)
