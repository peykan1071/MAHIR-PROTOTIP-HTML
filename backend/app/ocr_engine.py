"""Read a single-student exam score table from a photographed image via PaddleOCR-VL.

This module only runs on the remote OCR worker (see `ocr_worker.py`, meant to
be started on a machine with a real GPU - see `modal_app.py`). The local
MAHIR file receiver never imports this module; it forwards image uploads
over HTTP instead (see `remote_ocr_client.py`), so a teacher's machine
never needs PaddleOCR installed.

Each uploaded image is expected to show one handwritten score table per the
MAHIR paper template: a student-number column, one column per question, and
a total column (see `AA.jpg` at the repo root for a reference photo). OCR on
handwritten, skewed, glare-affected photos misreads header text often (e.g.
"Öğrenci No" -> "Openci No", "Soru 1" -> "Sonu 1") even when the numeric
values are read correctly, so rows are interpreted positionally (first
column = student number, last column = total, everything between = scores)
rather than by matching header text.

The pipeline is only ever created and called from one dedicated worker
thread (via `_EXECUTOR`, a single-worker `ThreadPoolExecutor`): calling it
from whichever thread happens to be handling a given HTTP request (the
server is a `ThreadingHTTPServer`) crashes an internal PaddleX worker with
"int(Tensor) is not supported in static graph mode" on the second call from
a different thread, even though repeated calls from the *same* thread work
fine - so every call is funneled onto that one worker thread instead.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

_pipeline = None
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddleocr-vl")
    return _executor


def _get_pipeline():
    """Create (once) or return the shared PaddleOCR-VL pipeline. Must only run on the OCR worker thread."""

    global _pipeline
    if _pipeline is None:
        # Model dosyaları zaten önbellekte (bkz. Dockerfile) olsa bile PaddleX, her
        # pipeline kurulumunda uzak model kaynaklarına (BOS/HuggingFace/ModelScope/
        # AIStudio) bir bağlantı kontrolü yapıp dakikalarca bekletebiliyor. Bu
        # kontrolü kapatıyoruz.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        from paddleocr import PaddleOCRVL
        from paddlex.utils import deps as paddlex_deps

        # paddlex.utils.deps.is_dep_available("paddlepaddle") is @lru_cache'd; if
        # anything calls it before paddlepaddle-gpu is fully importable, the
        # negative result sticks for the rest of the process and every engine
        # ("paddle_static", "paddle_dynamic") reports itself unavailable forever
        # after. Clear it right before use so this process's first real check
        # reflects the truth.
        paddlex_deps.is_dep_available.cache_clear()

        device = os.environ.get("MAHIR_OCR_DEVICE", "gpu")
        # paddle_dynamic (eager) her adımı Python üzerinden dispatch ediyor - token
        # token üretim yapan bir VLM için bu çok yavaş. PaddleOCR-VL-1.6-0.9B
        # yalnızca paddle_dynamic/transformers/genai_client destekliyor
        # (paddle_static desteklenmiyor - denendi, ValueError verdi);
        # transformers'ın KV-cache'li generate() yolu daha hızlı olabilir.
        # MAHIR_OCR_ENGINE ile eskiye dönülebilir.
        engine = os.environ.get("MAHIR_OCR_ENGINE", "transformers")
        _pipeline = PaddleOCRVL(device=device, engine=engine)
    return _pipeline


def ensure_available() -> None:
    """Create the pipeline on the OCR worker thread now, raising RuntimeError if paddleocr isn't installed."""

    try:
        _get_executor().submit(_get_pipeline).result()
    except ImportError as error:
        raise RuntimeError("PaddleOCR bu Python ortamında kurulu değil.") from error


def read_student_rows(image_bytes: bytes, extension: str) -> list[dict[str, object]]:
    """OCR one exam-score image and return the student row(s) found in its table."""

    html_text = _run_ocr(image_bytes, extension)
    rows = _extract_table_rows(html_text)
    if not rows:
        raise ValueError("Görselde tablo tespit edilemedi.")

    data_rows = rows[1:] if len(rows) > 1 else rows
    students = [row for row in (_parse_positional_row(row) for row in data_rows) if row is not None]
    if not students:
        raise ValueError("Görseldeki tablo satırından öğrenci bilgisi okunamadı.")
    return students


def _run_ocr(image_bytes: bytes, extension: str) -> str:
    suffix = extension if extension else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        tmp_file.write(image_bytes)
        tmp_path = tmp_file.name

    try:
        return _get_executor().submit(_predict_on_worker, tmp_path).result()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _predict_on_worker(tmp_path: str) -> str:
    """Runs on the OCR worker thread: the only place `pipeline.predict` may be called from."""

    started = time.monotonic()
    print(f"[ocr_engine] predict başlıyor: {tmp_path}", flush=True)

    pipeline = _get_pipeline()
    print(f"[ocr_engine] pipeline hazır (+{time.monotonic() - started:.1f}s), predict() çağrılıyor", flush=True)
    results = list(pipeline.predict(tmp_path))
    print(f"[ocr_engine] predict() bitti (+{time.monotonic() - started:.1f}s)", flush=True)
    if not results:
        raise ValueError("OCR sonucu alınamadı.")

    markdown = results[0].markdown
    return markdown.get("markdown_texts", "") if isinstance(markdown, dict) else str(markdown)


def _parse_number(value: str) -> float | int | None:
    cleaned = value.strip().replace(",", ".")
    if not cleaned or not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None
    number = float(cleaned)
    return int(number) if number.is_integer() else number


def _parse_positional_row(row: list[str]) -> dict[str, object] | None:
    if len(row) < 2:
        return None

    student_no = row[0].strip()
    total_score = _parse_number(row[-1])
    scores = [_parse_number(cell) for cell in row[1:-1]]

    if not student_no and total_score is None and all(score is None for score in scores):
        return None

    return {
        "studentNo": student_no,
        "fullName": "",
        "scores": scores,
        "totalScore": total_score,
        "calculatedTotal": round(sum(score or 0 for score in scores), 2),
        "control": "",
    }


class _TableRowsExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None
        elif tag in ("td", "th") and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)


def _extract_table_rows(html_text: str) -> list[list[str]]:
    parser = _TableRowsExtractor()
    parser.feed(html_text)
    return [row for row in parser.rows if row]
