"""Minimal local file receiver for MAHIR frontend/backend integration.

The receiver detects that a file reached the Python backend, validates its
filename extension, and triggers the existing backend reporting flow for CSV
uploads. Word, PDF and image documents are accepted by the prototype and
forwarded to the teacher-validation step; DOCX tables are parsed when their
headings can be recognised, and image groups are OCR'd by a remote MAHIR
backend (see `remote_ocr_client.py`) when `MAHIR_OCR_REMOTE_URL` is set - no
OCR pipeline runs on this machine. A fixed MAHIR template is never required.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

from .docx_parser import parse_mahir_docx
from .pdf_parser import parse_score_pdf
from .spreadsheet_parser import parse_score_xlsx
from .approved_data_analyzer import analyze_approved_data_traced
from .timing import stage


UPLOAD_PATH = "/mahir-upload"
ANALYZE_PATH = "/mahir-analyze"
OCR_WARMUP_PATH = "/mahir-ocr-warmup"
RAG_WARMUP_PATH = "/mahir-rag-warmup"
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10
MAX_REQUEST_SIZE = MAX_UPLOAD_SIZE * MAX_FILES_PER_UPLOAD
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
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
_DEFAULT_MAHIR_OCR_REMOTE_URL = "https://hakanergul--mahir-ocr-worker-ocr-worker.modal.run"
# Dağıtılmış OCR işçisinin adresi koda gömülü - `approved_data_analyzer.py`'deki
# `MAHIR_RAG_REMOTE_URL` ile aynı desen. Modal'ın ürettiği URL bir daha dağıtım
# yapılana kadar değişmiyor, bu yüzden sunucuyu her başlatışta aynı pencerede
# env değişkeni ayarlamaya gerek yok - unutulduğunda sunucu hata vermeden
# OCR'sız "pass-through" moduna düşüyordu (bkz. README'deki uyarı). Farklı bir
# dağıtıma (ör. test ortamı) işaret etmek gerekirse env var yine geçersiz kılar;
# boş string vermek OCR'ı bilinçli olarak kapatır.
MAHIR_OCR_REMOTE_URL = os.environ.get("MAHIR_OCR_REMOTE_URL", _DEFAULT_MAHIR_OCR_REMOTE_URL)


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
        # `SimpleHTTPRequestHandler` yalnızca `Last-Modified` gönderiyor,
        # `Cache-Control` göndermiyor. Tarayıcı bu durumda SEZGİSEL önbellekleme
        # uygular: dosyayı sunucuya hiç sormadan kendi kopyasından verir. Bu,
        # rapor katmanını sessizce ikiye bölüyordu - `mahir-report-export-common.js`
        # tazelenirken `mahir-pdf-exporter.js` eski kopyadan geldiği için ekranda
        # görünen dipnot indirilen PDF'e hiç düşmedi. Öğretmenin imzalayacağı
        # resmî çıktı ekranda gördüğünden farklı olamaz; prototipte önbelleğin
        # kazandıracağı hiçbir şey bu riski karşılamıyor.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        """Serve the prototype, but intercept the warm-up pings first.

        The browser can't call the remote services itself (it never learns
        their URLs, and they are on another origin), so both pings are proxied
        here. They must return *immediately*: a remote call blocks for 30-110 s
        while a cold container loads its models, and the teacher is meanwhile
        picking files or reviewing scores - nothing may wait on it.
        """

        request_path = urlparse(self.path).path
        if request_path == OCR_WARMUP_PATH:
            # OCR ısıtması dosyalar seçilir seçilmez tetikleniyor; soğuk
            # başlangıcı (~30-50 sn) "Verileri Oku"nun beklemesinden çıkarır.
            from .remote_ocr_client import warm_up_remote_ocr

            self._start_warm_up(MAHIR_OCR_REMOTE_URL, warm_up_remote_ocr)
            return
        if request_path == RAG_WARMUP_PATH:
            # RAG ısıtması doğrulama ekranı açılınca tetikleniyor; öğretmen
            # puanları incelerken ~110 sn'lik soğuk başlangıç biter ve
            # scaledown_window=300 sayesinde analize kadar sıcak kalır. URL
            # burada değil analiz modülünde tanımlı - modül üzerinden okunuyor
            # ki testler onu yamalayabilsin.
            from . import approved_data_analyzer
            from .rag_client import warm_up_remote_rag

            self._start_warm_up(approved_data_analyzer.MAHIR_RAG_REMOTE_URL, warm_up_remote_rag)
            return
        super().do_GET()

    def _start_warm_up(self, remote_url: str, warm_up) -> None:
        """Uzak ısıtmayı daemon thread'e atıp anında yanıt döner."""

        if not remote_url:
            # Uzak servis yapılandırılmamış (ör. OCR'sız yerel geliştirme):
            # ısıtılacak bir şey yok, sessizce başarılı dön.
            self._send_json(200, {"ok": True, "started": False})
            return

        threading.Thread(
            target=warm_up, args=(remote_url,), name=warm_up.__name__, daemon=True
        ).start()
        self._send_json(200, {"ok": True, "started": True})

    def do_POST(self) -> None:
        request_path = urlparse(self.path).path
        if request_path == ANALYZE_PATH:
            self._handle_analysis_request()
            return
        if request_path != UPLOAD_PATH:
            self._send_json(404, {"ok": False, "message": "Bilinmeyen alıcı yolu."})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        content_type = self.headers.get("Content-Type", "")

        if content_length <= 0:
            self._send_json(400, {"ok": False, "message": "Dosya verisi alınamadı."})
            return
        if content_length > MAX_REQUEST_SIZE:
            self._send_json(413, {"ok": False, "message": "Dosya 20 MB sınırını aşıyor."})
            return

        body = self.rfile.read(content_length)
        uploaded_files = extract_uploaded_files(body, content_type)

        if not uploaded_files:
            self._send_json(400, {"ok": False, "message": "Dosya verisi alınamadı."})
            return
        if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
            self._send_json(400, {"ok": False, "message": "Bir görsel grubunda en fazla 10 dosya seçebilirsiniz."})
            return

        oversized = next((f for f in uploaded_files if len(f.content) > MAX_UPLOAD_SIZE), None)
        if oversized is not None:
            self._send_json(
                413,
                {"ok": False, "fileName": oversized.file_name, "message": "Dosya 20 MB sınırını aşıyor."},
            )
            return

        results = [validate_file_name(f.file_name) for f in uploaded_files]
        invalid = next((r for r in results if not r.is_allowed), None)

        if invalid is None:
            print(
                f"[MAHIR] {len(uploaded_files)} dosya alındı: "
                + ", ".join(f"{r.file_name} ({r.extension})" for r in results),
                flush=True,
            )
            # Yerel toplam: isteğin alınmasından yanıtın hazır olmasına kadar.
            # `remote_ocr_client` kendi satırını ayrıca basıyor; aradaki fark
            # yerel ayrıştırma, uzak satırdaki büyük süre ise soğuk başlangıç.
            with stage(
                "ocr-yerel",
                dosya=len(uploaded_files),
                bayt=sum(len(f.content) for f in uploaded_files),
            ) as measured:
                flow_ok, flow_message, structured_data = run_existing_backend_flow(
                    uploaded_files, results
                )
                measured["ogrenci"] = len((structured_data or {}).get("students") or [])
                measured["sonuc"] = "tamam" if flow_ok else "basarisiz"

            if flow_ok:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "fileName": results[0].file_name,
                        "extension": results[0].extension,
                        "fileCount": len(uploaded_files),
                        "message": flow_message,
                        "structuredData": structured_data,
                    },
                )
                return

            print(f"[MAHIR] Backend akışı tamamlanamadı: {flow_message}", flush=True)
            self._send_json(
                500,
                {
                    "ok": False,
                    "fileName": results[0].file_name,
                    "extension": results[0].extension,
                    "message": flow_message,
                },
            )
            return

        print(
            f"[MAHIR] Dosya reddedildi: {invalid.file_name or 'adsız dosya'} | Uzantı: {invalid.extension or 'yok'}",
            flush=True,
        )
        self._send_json(
            400,
            {
                "ok": False,
                "fileName": invalid.file_name,
                "extension": invalid.extension,
                "message": "Dosya uzantısı desteklenen biçimlerle eşleşmedi.",
            },
        )

    def _handle_analysis_request(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0 or content_length > MAX_UPLOAD_SIZE:
            self._send_json(400, {"ok": False, "message": "Onaylanan veri alınamadı."})
            return

        from .agents.base import trace_of
        from .agents.orchestrator import PipelineError

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            with stage("analiz-rota", soru=len(payload.get("questions") or [])) as measured:
                result, trace = analyze_approved_data_traced(payload)
                measured["ogrenci"] = len(payload.get("students") or [])
                measured["istem"] = (trace.get("llmRound") or {}).get("promptCount", 0)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._send_json(422, {"ok": False, "message": str(error)})
            return
        except PipelineError as error:
            # Zorunlu bir ajan düştü. İzi de göndermek kasıtlı: hangi ajanın
            # düştüğü, hangilerinin atlandığı ve öncekilerin ne ürettiği,
            # hatanın kendisi kadar değerli - `PipelineError` bu kısmi bağlamı
            # tam da bunun için taşıyor.
            self._send_json(
                500,
                {"ok": False, "message": str(error), "trace": trace_of(error.context)},
            )
            return

        self._send_json(
            200,
            {
                "ok": True,
                "message": "Öğretmen onaylı veriler analiz motoruna aktarıldı.",
                "analysis": result,
                # Analizi ÜRETEN ajanların izi: hangi ajan ne kadar sürdü, ne
                # üretti, LLM'i kaç kez kullandı. `analysis`in kardeşi, içinde
                # değil - rapor sözleşmesi teknik alanlarla kirlenmemeli.
                "trace": trace,
            },
        )

    def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_existing_backend_flow(
    uploaded_files: list[UploadedFile], file_checks: list[FileCheckResult]
) -> tuple[bool, str, dict[str, object] | None]:
    """Accept supported documents and forward their data for teacher validation."""

    if all(check.extension in IMAGE_EXTENSIONS for check in file_checks):
        return run_image_group_ocr(uploaded_files)

    if len(uploaded_files) > 1:
        # No field-merge parsing exists across a group of non-image documents -
        # forward the whole group the same way a single unrecognised document
        # is accepted today, and let the teacher complete the validation screen
        # manually.
        return True, f"{len(uploaded_files)} görsel alındı ve öğretmen kontrolüne hazırlandı.", None

    uploaded_file = uploaded_files[0]
    file_check = file_checks[0]

    if file_check.extension == ".docx":
        try:
            structured_data = parse_mahir_docx(uploaded_file.content)
            summary = structured_data["summary"]
            return (
                True,
                f"Word belgesi okundu: {summary['questionCount']} soru ve "
                f"{summary['studentCount']} öğrenci satırı öğretmen kontrolüne aktarıldı.",
                structured_data,
            )
        except ValueError as error:
            # A readable Word package may still contain an unfamiliar teacher-made
            # layout. Do not reject it merely because it is not a MAHIR template.
            return (
                True,
                "Word belgesi alındı. Alanlar otomatik okunamadığı için bilgiler "
                "öğretmen kontrol ekranında tamamlanacaktır.",
                {
                    "exam": {},
                    "questions": [],
                    "students": [],
                    "warnings": [str(error)],
                    "summary": {"questionCount": 0, "studentCount": 0, "warningCount": 1},
                },
            )

    if file_check.extension == ".pdf":
        try:
            structured_data = parse_score_pdf(uploaded_file.content)
            summary = structured_data["summary"]
            return (
                True,
                f"PDF tablosu okundu: {summary['questionCount']} soru ve "
                f"{summary['studentCount']} öğrenci satırı öğretmen kontrolüne aktarıldı.",
                structured_data,
            )
        except ValueError as error:
            return (
                True,
                "PDF belgesi alındı; tablo otomatik okunamadığı için bilgiler öğretmen kontrol ekranında tamamlanacaktır.",
                {
                    "exam": {}, "questions": [], "students": [], "warnings": [str(error)],
                    "summary": {"questionCount": 0, "studentCount": 0, "warningCount": 1},
                },
            )

    if file_check.extension == ".xlsx":
        try:
            structured_data = parse_score_xlsx(uploaded_file.content)
            summary = structured_data["summary"]
            return (
                True,
                f"Excel tablosu okundu: {summary['questionCount']} soru ve "
                f"{summary['studentCount']} öğrenci satırı öğretmen kontrolüne aktarıldı.",
                structured_data,
            )
        except ValueError as error:
            return (
                True,
                "Excel belgesi alındı; tablo otomatik okunamadığı için bilgiler öğretmen kontrol ekranında tamamlanacaktır.",
                {
                    "exam": {}, "questions": [], "students": [], "warnings": [str(error)],
                    "summary": {"questionCount": 0, "studentCount": 0, "warningCount": 1},
                },
            )

    if file_check.extension == ".xls":
        return (
            True,
            "Eski .xls biçimi alındı; otomatik okuma için dosyayı Excel'de .xlsx olarak kaydediniz.",
            {
                "exam": {}, "questions": [], "students": [],
                "warnings": ["Eski .xls biçimi doğrudan okunmuyor. Dosyayı .xlsx biçiminde kaydedip yeniden yükleyiniz."],
                "summary": {"questionCount": 0, "studentCount": 0, "warningCount": 1},
            },
        )

    # Buraya kadar tanınmayan her biçim öğretmen kontrol ekranına düşer.
    #
    # Eskiden burada bir `.csv` dalı vardı: yüklenen dosyayı diske yazıp
    # `measurement_engine`/`pedagogical_analysis`/`reporting_engine` zincirini
    # koşturuyor, sonucu `shared/report-example.txt`e yazıp konsola basıyordu.
    # Üç sebeple kaldırıldı: (1) arayüzdeki dosya girişi `.csv` kabul etmiyor,
    # yani öğretmen bu dalı hiç tetikleyemiyordu; (2) tetiklense bile yüklenen
    # içeriği kullanmayıp sabit `shared/sample-*.json` dosyalarını okuyordu;
    # (3) tarayıcıya `None` döndüğü için öğretmen sonucu zaten göremiyordu.
    # O zincirin gerçek karşılığı artık canlı akışta: `analyze_approved_data`
    # beş uzman ajanı koşturuyor (bkz. backend/app/agents/).
    return True, "Belge alındı ve öğretmen kontrolüne hazırlandı.", None


def run_image_group_ocr(uploaded_files: list[UploadedFile]) -> tuple[bool, str, dict[str, object] | None]:
    """Send an all-image upload group to the remote MAHIR OCR backend, if configured."""

    if not MAHIR_OCR_REMOTE_URL:
        return True, f"{len(uploaded_files)} görsel alındı ve öğretmen kontrolüne hazırlandı.", None

    from .remote_ocr_client import run_remote_image_group_ocr

    return run_remote_image_group_ocr(uploaded_files, MAHIR_OCR_REMOTE_URL)


def extract_uploaded_files(body: bytes, content_type: str) -> list[UploadedFile]:
    """Extract every browser-supplied file from multipart form data."""

    boundary = _extract_boundary(content_type)

    if not boundary:
        return []

    files: list[UploadedFile] = []
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition:" not in part:
            continue

        headers, _, content = part.partition(b"\r\n\r\n")
        header_text = headers.decode("utf-8", errors="replace")
        match = re.search(r'filename="([^"]*)"', header_text)

        if match:
            files.append(UploadedFile(file_name=_clean_filename(match.group(1)), content=content.rstrip(b"\r\n")))

    return files


def extract_uploaded_file(body: bytes, content_type: str) -> UploadedFile:
    """Extract the first browser-supplied file from multipart form data."""

    files = extract_uploaded_files(body, content_type)
    return files[0] if files else UploadedFile(file_name="", content=b"")


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
