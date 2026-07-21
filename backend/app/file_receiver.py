"""Minimal local file receiver for MAHIR frontend/backend integration.

The receiver detects that a file reached the Python backend, validates its
filename extension, and triggers the existing backend reporting flow for CSV
uploads. It does not add AI, OCR, API, database, or user-system behavior.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

from .measurement_engine import build_measured_ced_document
from .pedagogical_analysis import analyze_learning_outcomes
from .program_mapper import load_learning_outcomes
from .reporting_engine import generate_report, write_report


UPLOAD_PATH = "/mahir-upload"
ALLOWED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".webp",
    ".xls",
    ".xlsx",
}


@dataclass(frozen=True)
class FileCheckResult:
    """Filename and extension validation result."""

    file_name: str
    extension: str
    is_allowed: bool


@dataclass(frozen=True)
class UploadedFile:
    """Uploaded browser file captured from multipart form data."""

    file_name: str
    content: bytes


class MAHIRFileReceiverHandler(SimpleHTTPRequestHandler):
    """Serve the prototype and receive a selected file from the browser."""

    server_version = "MAHIRFileReceiver/0.1"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_POST(self) -> None:
        if urlparse(self.path).path != UPLOAD_PATH:
            self._send_json(404, {"ok": False, "message": "Bilinmeyen alıcı yolu."})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        content_type = self.headers.get("Content-Type", "")

        if content_length <= 0:
            self._send_json(400, {"ok": False, "message": "Dosya verisi alınamadı."})
            return

        body = self.rfile.read(content_length)
        uploaded_file = extract_uploaded_file(body, content_type)
        result = validate_file_name(uploaded_file.file_name)

        if result.is_allowed:
            print(
                f"[MAHIR] Dosya alındı: {result.file_name} | Uzantı: {result.extension}",
                flush=True,
            )
            flow_ok, flow_message = run_existing_backend_flow(uploaded_file, result)

            if flow_ok:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "fileName": result.file_name,
                        "extension": result.extension,
                        "message": "Dosya başarıyla işlendi.",
                    },
                )
                return

            print(f"[MAHIR] Backend akışı tamamlanamadı: {flow_message}", flush=True)
            self._send_json(
                500,
                {
                    "ok": False,
                    "fileName": result.file_name,
                    "extension": result.extension,
                    "message": flow_message,
                },
            )
            return

        print(
            f"[MAHIR] Dosya reddedildi: {result.file_name or 'adsız dosya'} | Uzantı: {result.extension or 'yok'}",
            flush=True,
        )
        self._send_json(
            400,
            {
                "ok": False,
                "fileName": result.file_name,
                "extension": result.extension,
                "message": "Dosya uzantısı desteklenen biçimlerle eşleşmedi.",
            },
        )

    def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_existing_backend_flow(uploaded_file: UploadedFile, file_check: FileCheckResult) -> tuple[bool, str]:
    """Run the current CSV -> CED -> report backend flow for an uploaded CSV."""

    if file_check.extension != ".csv":
        return False, "Mevcut backend akışı yalnız CSV dosyasıyla çalışır."

    project_root = Path(__file__).resolve().parents[2]
    temporary_dir = project_root / "backend" / ".tmp"
    temporary_dir.mkdir(exist_ok=True)
    uploaded_csv_path = temporary_dir / "uploaded-sample-exam.csv"

    try:
        uploaded_csv_path.write_bytes(uploaded_file.content)
        outcomes_path = project_root / "shared" / "sample-learning-outcomes.json"
        student_results_path = project_root / "shared" / "sample-student-results.json"
        report_path = project_root / "shared" / "report-example.txt"
        document, question_rates, outcome_rates = build_measured_ced_document(
            uploaded_csv_path,
            outcomes_path,
            student_results_path,
        )
        learning_outcomes = load_learning_outcomes(outcomes_path)
        analysis_results = analyze_learning_outcomes(outcome_rates, learning_outcomes)
        report_text = generate_report(
            document,
            question_rates,
            outcome_rates,
            analysis_results,
            learning_outcomes,
        )
        write_report(report_text, report_path)
        print(report_text, end="", flush=True)
        return True, "Dosya başarıyla işlendi."
    except (OSError, ValueError) as error:
        return False, str(error)
    finally:
        if uploaded_csv_path.exists():
            uploaded_csv_path.unlink()
        try:
            temporary_dir.rmdir()
        except OSError:
            pass


def extract_uploaded_file(body: bytes, content_type: str) -> UploadedFile:
    """Extract browser-supplied filename and content from multipart form data."""

    boundary = _extract_boundary(content_type)

    if not boundary:
        return UploadedFile(file_name="", content=b"")

    for part in body.split(b"--" + boundary):
        if b"Content-Disposition:" not in part:
            continue

        headers, _, content = part.partition(b"\r\n\r\n")
        header_text = headers.decode("utf-8", errors="replace")
        match = re.search(r'filename="([^"]*)"', header_text)

        if match:
            return UploadedFile(file_name=_clean_filename(match.group(1)), content=content.rstrip(b"\r\n"))

    return UploadedFile(file_name="", content=b"")


def extract_filename(body: bytes, content_type: str) -> str:
    """Extract a browser-supplied filename from multipart form data."""

    return extract_uploaded_file(body, content_type).file_name


def validate_file_name(file_name: str) -> FileCheckResult:
    """Validate only the filename extension."""

    clean_name = _clean_filename(file_name)
    extension = Path(clean_name).suffix.lower()
    return FileCheckResult(
        file_name=clean_name,
        extension=extension,
        is_allowed=bool(clean_name and extension in ALLOWED_EXTENSIONS),
    )


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Create a local server rooted at the project directory."""

    project_root = Path(__file__).resolve().parents[2]

    class ProjectHandler(MAHIRFileReceiverHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(project_root), **kwargs)

    return ThreadingHTTPServer((host, port), ProjectHandler)


def _extract_boundary(content_type: str) -> bytes:
    match = re.search(r"boundary=([^;]+)", content_type)

    if not match:
        return b""

    return match.group(1).strip().strip('"').encode("utf-8")


def _clean_filename(file_name: str) -> str:
    windows_name = PureWindowsPath(file_name or "").name
    return PurePosixPath(windows_name).name