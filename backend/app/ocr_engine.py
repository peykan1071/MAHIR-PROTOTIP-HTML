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


def read_exam_document(image_bytes: bytes, extension: str) -> dict[str, object]:
    """Read one photographed exam sheet as one document, never as arbitrary OCR rows.

    The photographed MAHİR forms contain two logical tables: document metadata and
    a score table.  PaddleOCR-VL may return both tables as a single HTML fragment.
    This parser therefore identifies rows by their semantic labels and emits one
    student record per document.  Header, class and maximum-score rows can no
    longer become fake students.
    """

    html_text = _run_ocr(image_bytes, extension)
    rows = _extract_table_rows(html_text)
    # Yetkili MAHİR şablonunda sınav türü onay kutusuyla değil, doğrudan
    # "Sınav Türü" hücresine yazılır. Piksel konumuna veya kutu görüntüsüne
    # dayanarak tür tahmin etmek yanlış bir Konuşma/Dinleme sınavı üretebildiği
    # için tek kanıt etiketli hücrenin açık metnidir.
    return _parse_exam_rows(rows)


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold().translate(str.maketrans("çğıöşü", "cgiosu"))).strip()


def _row_has(row: list[str], *needles: str) -> bool:
    text = " ".join(_normalize_label(cell) for cell in row)
    compact_text = text.replace(" ", "")
    return any(
        (normalized := _normalize_label(needle)) in text
        or normalized.replace(" ", "") in compact_text
        for needle in needles
    )


def _numbers_after_label(row: list[str]) -> list[float | int]:
    values = [_parse_number(cell) for cell in row[1:]]
    return [value for value in values if value is not None]


def _positional_numbers_after_label(row: list[str], count: int) -> list[float | int | None]:
    """Preserve empty OCR cells so a missing S3 value cannot shift S4 into S3."""

    return [_parse_number(cell) for cell in row[1:1 + max(0, count)]]


def _without_repeated_total(values: list[float | int]) -> list[float | int]:
    if len(values) > 1 and abs(float(sum(values[:-1])) - float(values[-1])) < 0.01:
        return values[:-1]
    return values


def _value_after_label(rows: list[list[str]], *labels: str) -> str:
    normalized_labels = {_normalize_label(label) for label in labels}
    for row in rows:
        for index, cell in enumerate(row):
            normalized = _normalize_label(cell)
            if any(label in normalized for label in normalized_labels):
                for candidate in row[index + 1:]:
                    value = candidate.strip()
                    if value and not any(label in _normalize_label(value) for label in normalized_labels):
                        return value
    return ""


def _extract_student_reference(rows: list[list[str]]) -> str:
    """Read the school-number/reference field without ever using the name field.

    The value is intentionally kept as an alphanumeric reference (for example
    ``OGR-003``).  OCR output sometimes inserts spaces around the hyphen, so
    only that harmless formatting variation is normalized.
    """

    value = _value_after_label(
        rows,
        "öğrenci okul no",
        "öğrenci okul numarası",
        "ogrenci okul no",
        "ogrenci okul numarasi",
        "okul no",
    ).strip()
    if not value or _looks_like_tckn(value):
        return ""
    compact = re.sub(r"\s*[-–—]\s*", "-", value)
    compact = re.sub(r"\s+", "", compact)
    return compact[:64] if re.search(r"[A-Za-z0-9]", compact) else ""


def _extract_class_section(rows: list[list[str]]) -> str:
    """Return a canonical class/section such as ``9-A`` from OCR table cells."""

    labelled_value = _value_after_label(rows, "sınıf/şube", "sinif/sube", "sınıf şube")
    labelled_candidates = [labelled_value]
    labelled_candidates.extend(
        cell for row in rows if _row_has(row, "sınıf/şube", "sinif/sube", "sınıf şube") for cell in row
    )
    # Handwriting OCR may keep the separator (``9-A``), replace it with a
    # space (``9 A``), or split grade and section into neighbouring cells.
    pattern = r"(?<!\d)(1[0-2]|[1-9])\s*(?:[-/]\s*|\s+)?([A-Za-zÇĞİÖŞÜçğıöşü])(?![A-Za-z])"
    for candidate in labelled_candidates:
        exact = re.fullmatch(r"\s*(1[0-2]|[1-9])\s*(?:[-/]\s*|\s+)?([A-Za-zÇĞİÖŞÜçğıöşü])\s*", candidate)
        if exact:
            return f"{exact.group(1)}-{exact.group(2).upper()}"
    for row in rows:
        if not _row_has(row, "sınıf/şube", "sinif/sube", "sınıf şube"):
            continue
        joined = " ".join(cell.strip() for cell in row if cell.strip())
        match = re.search(pattern, joined)
        if match:
            return f"{match.group(1)}-{match.group(2).upper()}"
    for candidate in labelled_candidates:
        match = re.search(pattern, candidate)
        if match:
            return f"{match.group(1)}-{match.group(2).upper()}"
    return ""


def _normalize_exam_type(value: str, rows: list[list[str]]) -> str:
    """Accept only an explicit value written in the labelled exam-type cell."""

    normalized = _normalize_label(value)
    accepted = {"yazili": "Yazılı", "dinleme": "Dinleme", "konusma": "Konuşma"}
    return accepted.get(normalized, "")


def _parse_exam_rows(rows: list[list[str]]) -> dict[str, object]:
    """Pure parser used by the OCR worker and unit tests."""

    if not rows:
        raise ValueError("Görselde tablo tespit edilemedi.")

    privacy_findings: set[str] = set()
    for row in rows:
        for cell in row:
            if _looks_like_tckn(cell):
                privacy_findings.add("TCKN")
        if _row_has(row, "öğrencinin adı", "ogrencinin adi", "öğrencinin adı soyadı"):
            candidate = _value_after_label([row], "öğrencinin adı", "ogrencinin adi", "öğrencinin adı soyadı")
            if _looks_like_full_name(candidate):
                privacy_findings.add("AD_SOYAD")

    class_section = _extract_class_section(rows)
    course = _value_after_label(rows, "dersin adı", "dersin adi", "ders adı")
    exam_type = _normalize_exam_type(_value_after_label(rows, "sınav türü", "sinav turu"), rows)
    exam_date = _value_after_label(rows, "sınav tarihi", "sinav tarihi")
    student_reference = _extract_student_reference(rows)
    exam = {
        "course": course,
        "courseName": course,
        "classSection": class_section,
        "grade": re.match(r"\d+", class_section or "").group(0) if re.match(r"\d+", class_section or "") else "",
        "examType": exam_type,
        "examDate": exam_date,
        "metadataSource": "labeled-template",
        "verifiedMetadataFields": [
            field
            for field, value in (
                ("classSection", class_section),
                ("course", course),
                ("examType", exam_type),
                ("examDate", exam_date),
            )
            if value
        ],
    }

    max_row = next((row for row in rows if _row_has(row, "azami puan")), None)
    score_row = next((row for row in rows if _row_has(row, "öğrencinin aldığı puan", "ogrencinin aldigi puan")), None)
    if max_row is None or score_row is None:
        return {
            "exam": exam,
            "questions": [],
            "student": {"studentNo": student_reference, "scores": [], "totalScore": None, "calculatedTotal": 0, "control": "question-count-required"},
            "privacyFindings": sorted(privacy_findings),
            "requiresQuestionCount": True,
        }

    question_header = next((row for row in rows if _row_has(row, "sorular")), None)
    header_question_count = sum(
        1 for cell in (question_header or [])[1:]
        if re.fullmatch(r"s\s*\d{1,2}", _normalize_label(cell).replace(" ", ""))
    )
    if header_question_count:
        question_count = min(15, header_question_count)
        max_scores = _positional_numbers_after_label(max_row, question_count)
        student_scores = _positional_numbers_after_label(score_row, question_count)
        total_score = _parse_number(score_row[question_count + 1]) if len(score_row) > question_count + 1 else None
    else:
        readable_max_scores = _without_repeated_total(_numbers_after_label(max_row))
        question_count = min(15, len(readable_max_scores))
        max_scores = readable_max_scores[:question_count]
        raw_student_values = [_parse_number(cell) for cell in score_row[1:]]
        student_scores = raw_student_values[:question_count]
        total_score = raw_student_values[question_count] if len(raw_student_values) > question_count else None
    if not max_scores:
        raise ValueError("Soruların azami puanları okunamadı.")

    questions = [
        {"number": index + 1, "maxScore": score}
        for index, score in enumerate(max_scores)
    ]
    return {
        "exam": exam,
        "questions": questions,
        "student": {
            "studentNo": student_reference,
            "scores": student_scores + [None] * max(0, len(max_scores) - len(student_scores)),
            "totalScore": total_score,
            "calculatedTotal": round(sum(score or 0 for score in student_scores), 2),
            "control": "",
        },
        "privacyFindings": sorted(privacy_findings),
    }


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


def _looks_like_tckn(value: str) -> bool:
    """Return True only for values matching the Turkish identity-number checksum."""

    digits = re.sub(r"\D", "", value)
    if len(digits) != 11 or digits[0] == "0":
        return False
    numbers = [int(digit) for digit in digits]
    tenth = ((sum(numbers[0:9:2]) * 7) - sum(numbers[1:8:2])) % 10
    eleventh = sum(numbers[:10]) % 10
    return numbers[9] == tenth and numbers[10] == eleventh


def _looks_like_full_name(value: str) -> bool:
    normalized = " ".join(value.strip().split())
    if any(character.isdigit() for character in normalized):
        return False
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", normalized)
    return len(words) >= 2 and len("".join(words)) >= 5


def _parse_positional_row(row: list[str]) -> dict[str, object] | None:
    if len(row) < 2:
        return None

    privacy_findings: list[str] = []
    safe_cells: list[str] = []
    for cell in row:
        if _looks_like_tckn(cell):
            if "TCKN" not in privacy_findings:
                privacy_findings.append("TCKN")
            continue
        if _looks_like_full_name(cell):
            if "AD_SOYAD" not in privacy_findings:
                privacy_findings.append("AD_SOYAD")
            continue
        safe_cells.append(cell)

    if len(safe_cells) < 2:
        return None

    student_no = safe_cells[0].strip()
    total_score = _parse_number(safe_cells[-1])
    scores = [_parse_number(cell) for cell in safe_cells[1:-1]]

    if not student_no and total_score is None and all(score is None for score in scores):
        return None

    return {
        "studentNo": student_no,
        "scores": scores,
        "totalScore": total_score,
        "calculatedTotal": round(sum(score or 0 for score in scores), 2),
        "control": "",
        "privacyFindings": privacy_findings,
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
