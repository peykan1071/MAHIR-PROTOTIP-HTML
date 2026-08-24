"""Read MAHIR Veri Giriş Şablonu tables from a DOCX document."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from .parsing_utils import (
    TOTAL_MISMATCH_TOLERANCE,
    calculate_total,
    normalise_label,
    parse_integer,
    parse_number,
    question_number,
)

WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_mahir_docx(content: bytes) -> dict[str, object]:
    """Return teacher-reviewable data from a DOCX without requiring a template."""

    tables = _read_tables(content)
    exam_table = _find_exam_table(tables)
    question_table = _find_question_table(tables)
    student_table = _find_student_table(tables)
    single_student_table = _find_single_student_score_table(tables)

    exam = _parse_exam(exam_table or [])
    questions = _parse_questions(question_table or [])
    document_type = "unclassified-docx"
    if student_table:
        document_type = "mahir-class-score-template"
        if not questions:
            questions = _questions_from_student_headings(student_table)
        students = _parse_students_flexible(student_table, questions)
    elif single_student_table:
        document_type = "single-student-score-sheet"
        if not questions:
            questions = _parse_single_student_questions(single_student_table)
        students = _parse_single_student_scores(exam_table or [], single_student_table)
    else:
        students = []
    warnings = _build_warnings(exam, questions, students)

    identity_cells = []
    if student_table:
        identity_cells.extend(student_table[0])
    if exam_table:
        identity_cells.extend(cell for row in exam_table for cell in row)
    if identity_cells:
        headings = {normalise_label(cell) for cell in identity_cells}
        identity_columns = []
        if headings & {"tc kimlik no", "t c kimlik no", "tc kimlik numarasi", "t c kimlik numarasi", "tckn"}:
            identity_columns.append("T.C. kimlik numarası")
        if headings & {
            "ad soyad", "adi soyadi", "ogrenci ad soyad", "ogrenci adi soyadi",
            "ogrencinin adi soyadi",
        }:
            identity_columns.append("ad-soyad")
        if identity_columns:
            warnings.append(
                f"Word belgesi: KVKK uyarısı - {' ve '.join(identity_columns)} sütunu algılandı "
                "ve öğrenci analiz verisinden çıkarıldı."
            )

    if not student_table and not single_student_table:
        warnings.append(
            "Word belgesindeki öğrenci ve puan alanları otomatik olarak ayırt edilemedi. "
            "Bilgileri öğretmen kontrol ekranında tamamlayınız."
        )

    return {
        "documentType": document_type,
        "exam": exam,
        "questions": questions,
        "students": students,
        "warnings": warnings,
        "summary": {
            "questionCount": len(questions),
            "studentCount": len(students),
            "warningCount": len(warnings),
        },
    }


def _find_table(
    tables: list[list[list[str]]], required_labels: set[str]
) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        labels = {normalise_label(cell) for cell in table[0]}
        if required_labels.issubset(labels):
            return table
    return None


def _find_exam_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    metadata_labels = {
        "il", "ilce", "okul adi", "ders", "dersin adi", "sinif sube",
        "sinav turu", "sinav tarihi", "ogrenci okul no", "ogrencinin adi soyadi",
        "il ilce", "okul", "egitim yili", "sinif ders",
    }
    for table in tables:
        labels = {normalise_label(cell) for row in table for cell in row}
        if len(labels & metadata_labels) >= 2:
            return table
    return None


def _find_student_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        labels = {normalise_label(cell) for cell in table[0]}
        has_number = any(label in {"okul no", "ogrenci no", "numara", "no"} for label in labels)
        has_score = any(question_number(label) is not None for label in labels)
        if has_number and has_score:
            return table
    return None


def _find_question_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    """Find both the official template and compact simulation question tables."""

    number_labels = {"soru", "soru no"}
    maximum_labels = {"azami", "azami puan"}
    for table in tables:
        if not table:
            continue
        labels = {_normalise_label(cell) for cell in table[0]}
        if labels & number_labels and labels & maximum_labels:
            return table
    return None


def _find_single_student_score_table(
    tables: list[list[list[str]]],
) -> list[list[str]] | None:
    """Find the Ministry-style three-row score matrix for one student."""

    for table in tables:
        if len(table) < 3:
            continue
        row_labels = {normalise_label(row[0]) for row in table if row}
        if {"sorular", "azami puan", "ogrencinin aldigi puan"}.issubset(row_labels):
            return table
    return None


def _read_tables(content: bytes) -> list[list[list[str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("Word belgesi açılamadı veya geçerli bir .docx dosyası değil.") from error

    root = ElementTree.fromstring(document_xml)
    tables: list[list[list[str]]] = []

    for table in root.findall(".//w:tbl", WORD_NAMESPACE):
        rows: list[list[str]] = []
        for row in table.findall("./w:tr", WORD_NAMESPACE):
            cells: list[str] = []
            for cell in row.findall("./w:tc", WORD_NAMESPACE):
                paragraphs = []
                for paragraph in cell.findall(".//w:p", WORD_NAMESPACE):
                    text = "".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NAMESPACE))
                    if text.strip():
                        paragraphs.append(text.strip())
                cells.append(" ".join(paragraphs).strip())
            rows.append(cells)
        tables.append(rows)

    return tables


def _parse_exam(rows: list[list[str]]) -> dict[str, object]:
    values = _labeled_values(rows)

    province = values.get("il", "")
    district = values.get("ilce", "")
    if not (province or district):
        province, district = _split_combined_value(values.get("il ilce", ""))

    class_section = values.get("sinif sube", "")
    course = values.get("ders", "") or values.get("dersin adi", "")
    if not (class_section or course):
        class_section, course = _split_combined_value(values.get("sinif ders", ""))

    exam = {
        "province": province,
        "district": district,
        "schoolName": values.get("okul adi", "") or values.get("okul", ""),
        "academicYear": values.get("egitim ogretim yili", "") or values.get("egitim yili", ""),
        "course": course,
        "classSection": class_section,
        "term": _selected_option(values.get("donem", "")),
        "examType": _normalise_exam_type(_selected_option(values.get("sinav turu", ""))),
        "examDate": values.get("sinav tarihi", ""),
        "totalMaxScore": parse_number(values.get("toplam puan", "")),
        "teacherName": values.get("ogretmenin adi soyadi", ""),
        "teachingProgram": values.get("ogretim programi", ""),
        "assessmentBasis": values.get("olcme ve degerlendirme dayanagi", ""),
        "scenarioInfo": values.get("senaryo ornek evrak", ""),
        "otherSources": values.get("diger dayanaklar", ""),
        "documentNo": values.get("belge rapor no", "") or values.get("belge sayfa no", ""),
        "approvalInfo": values.get("iletim onay bilgisi", ""),
        "documentPage": values.get("belge sayfa no", ""),
    }
    verified_labels = {
        "province": "il", "district": "ilce", "schoolName": "okul adi",
        "teacherName": "ogretmenin adi soyadi", "academicYear": "egitim ogretim yili",
        "classSection": "sinif sube", "teachingProgram": "ogretim programi",
        "assessmentBasis": "olcme ve degerlendirme dayanagi",
    }
    exam["verifiedMetadataFields"] = [
        field for field, label in verified_labels.items() if values.get(label, "").strip()
    ]
    if exam["verifiedMetadataFields"]:
        exam["metadataSource"] = "labeled-template"
    return exam


def _labeled_values(rows: list[list[str]]) -> dict[str, str]:
    """Return adjacent label/value pairs from a metadata table."""

    values: dict[str, str] = {}
    for row in rows:
        for index in range(0, len(row) - 1, 2):
            label = normalise_label(row[index])
            if label:
                values[label] = row[index + 1].strip()
    return values


def _parse_questions(rows: list[list[str]]) -> list[dict[str, object]]:
    if not rows:
        return []

    headings = [_normalise_label(cell) for cell in rows[0]]

    def heading_index(*labels: str) -> int | None:
        return next((index for index, label in enumerate(headings) if label in labels), None)

    number_index = heading_index("soru", "soru no")
    maximum_index = heading_index("azami", "azami puan")
    code_index = heading_index("kod", "ogrenme ciktisi kodu", "cikti kodu")
    description_index = heading_index(
        "ogrenme ciktisi", "ogrenme ciktisi aciklamasi", "cikti aciklamasi"
    )
    questions = []
    for row in rows[1:]:
        padded = row + [""] * max(0, len(headings) - len(row))
        number = _integer(padded[number_index]) if number_index is not None else None
        outcome_code = padded[code_index].strip() if code_index is not None else ""
        outcome_description = (
            padded[description_index].strip() if description_index is not None else ""
        )
        max_score = _number(padded[maximum_index]) if maximum_index is not None else None
        if not (outcome_code or outcome_description or max_score is not None):
            continue
        questions.append(
            {
                "number": number or len(questions) + 1,
                "outcomeCode": outcome_code,
                "outcomeDescription": outcome_description,
                "maxScore": max_score,
            }
        )
    return questions


def _questions_from_student_headings(rows: list[list[str]]) -> list[dict[str, object]]:
    """Create a question skeleton from Soru 1..N columns without inventing outcomes."""

    if not rows:
        return []
    questions = []
    for cell in rows[0]:
        label = normalise_label(cell)
        number = question_number(label)
        if number is None:
            continue
        questions.append(
            {
                "number": number,
                "outcomeCode": "",
                "outcomeDescription": "",
                "maxScore": None,
                "source": "score-column-heading",
            }
        )
    return questions


def _parse_single_student_questions(rows: list[list[str]]) -> list[dict[str, object]]:
    """Read question numbers and maximum scores from a three-row score matrix."""

    if not rows:
        return []
    question_row = next(
        (row for row in rows if row and normalise_label(row[0]) == "sorular"), []
    )
    max_row = next(
        (row for row in rows if row and normalise_label(row[0]) == "azami puan"), []
    )
    questions = []
    for index, cell in enumerate(question_row[1:], start=1):
        label = normalise_label(cell)
        number = question_number(label)
        if number is None:
            continue
        max_score = parse_number(max_row[index]) if index < len(max_row) else None
        questions.append(
            {
                "number": number,
                "outcomeCode": "",
                "outcomeDescription": "",
                "maxScore": max_score,
                "source": "single-student-score-sheet",
            }
        )
    return questions


def _parse_single_student_scores(
    exam_rows: list[list[str]], score_rows: list[list[str]]
) -> list[dict[str, object]]:
    """Read one student without carrying name/surname into the analysis model."""

    values = _labeled_values(exam_rows)
    student_no = values.get("ogrenci okul no", "") or values.get("okul no", "")
    score_row = next(
        (
            row
            for row in score_rows
            if row and normalise_label(row[0]) == "ogrencinin aldigi puan"
        ),
        [],
    )
    if not score_row:
        return []
    question_count = len(_parse_single_student_questions(score_rows))
    scores = [parse_number(value) for value in score_row[1 : 1 + question_count]]
    total_score = (
        parse_number(score_row[1 + question_count])
        if len(score_row) > 1 + question_count
        else None
    )
    if not (student_no or any(score is not None for score in scores) or total_score is not None):
        return []
    return [
        {
            "rowNumber": 1,
            "studentNo": student_no.strip(),
            "scores": scores,
            "totalScore": total_score,
            "calculatedTotal": calculate_total(scores),
            "control": "",
        }
    ]


def _parse_students(
    rows: list[list[str]], questions: list[dict[str, object]]
) -> list[dict[str, object]]:
    question_count = max((int(question["number"]) for question in questions), default=10)
    students = []

    for row in rows[1:]:
        padded = row + [""] * (16 - len(row))
        scores = [_number(value) for value in padded[3 : 3 + question_count]]
        student_no = padded[1].strip()
        # Ad-soyad, veri minimizasyonu gereği öğrenci analiz modeline alınmaz.
        total_score = _number(padded[13])
        attendance = padded[14].strip()
        control = padded[15].strip()

        if not (student_no or any(score is not None for score in scores) or attendance):
            continue

        students.append(
            {
                "rowNumber": _integer(padded[0]) or len(students) + 1,
                "studentNo": student_no,
                "scores": scores,
                "totalScore": total_score,
                "calculatedTotal": round(sum(score or 0 for score in scores), 2),
                "attendance": attendance or "Girdi",
                "control": control,
            }
        )

    return students


def _parse_students_flexible(
    rows: list[list[str]], questions: list[dict[str, object]] | None = None
) -> list[dict[str, object]]:
    """Read a student-score table by its headings rather than column positions."""

    if not rows:
        return []
    headings = [normalise_label(cell) for cell in rows[0]]

    def find_index(predicate) -> int | None:
        return next((index for index, label in enumerate(headings) if predicate(label)), None)

    row_index = find_index(lambda label: label in {"sira", "sira no"})
    number_index = find_index(lambda label: label in {"okul no", "ogrenci no", "numara", "no"})
    total_index = find_index(lambda label: label == "puan" or label.startswith("toplam"))
    score_indexes = [
        index for index, label in enumerate(headings)
        if question_number(label) is not None
    ]
    explicit_question_numbers = {
        int(question["number"])
        for question in (questions or [])
        if question.get("number") is not None
    }
    if explicit_question_numbers:
        score_indexes = [
            index for index in score_indexes
            if (match := re.match(r"^(?:s|soru) ?(\d+)\b", headings[index]))
            and int(match.group(1)) in explicit_question_numbers
        ]
    students = []

    for source_row in rows[1:]:
        row = source_row + [""] * max(0, len(headings) - len(source_row))
        scores = [parse_number(row[index]) for index in score_indexes]
        student_no = row[number_index].strip() if number_index is not None else ""
        total_score = _number(row[total_index]) if total_index is not None else None
        first_cell = _normalise_label(row[0]) if row else ""
        if first_cell in {"azami", "maksimum", "azami puan"}:
            continue
        if not (student_no or any(score is not None for score in scores) or total_score is not None):
            continue
        students.append(
            {
                "rowNumber": parse_integer(row[row_index]) if row_index is not None else len(students) + 1,
                "studentNo": student_no,
                "scores": scores,
                "totalScore": total_score,
                "calculatedTotal": calculate_total(scores),
                "control": "",
            }
        )
    return students


def _build_warnings(
    exam: dict[str, object],
    questions: list[dict[str, object]],
    students: list[dict[str, object]],
) -> list[str]:
    warnings = []
    if not exam.get("course"):
        warnings.append("Ders alanı boş.")
    if not questions:
        warnings.append("Doldurulmuş soru–öğrenme çıktısı satırı bulunamadı.")
    if not students:
        warnings.append("Doldurulmuş öğrenci satırı bulunamadı.")

    inferred_questions = [question for question in questions if question.get("source")]
    if inferred_questions:
        if any(
            not question["outcomeCode"] and not question["outcomeDescription"]
            for question in inferred_questions
        ):
            warnings.append(
                "Öğrenme çıktıları puan çizelgesinde yer almıyor; sınav senaryosu veya "
                "öğretmenin onaylı eşleştirmesi kullanılmalıdır."
            )
        if any(question["maxScore"] is None for question in inferred_questions):
            warnings.append(
                "Soru azami puanları bu çizelgede yer almıyor; öğretmen kontrol ekranında "
                "onaylanmalıdır."
            )
    else:
        for question in questions:
            if not question["outcomeCode"] and not question["outcomeDescription"]:
                warnings.append(f"{question['number']}. sorunun öğrenme çıktısı boş.")
            if question["maxScore"] is None:
                warnings.append(f"{question['number']}. sorunun azami puanı boş.")

    for student in students:
        if (
            student["totalScore"] is not None
            and abs(float(student["totalScore"]) - float(student["calculatedTotal"])) > TOTAL_MISMATCH_TOLERANCE
        ):
            warnings.append(
                f"{student['rowNumber']}. satırında yazılan toplam "
                f"({student['totalScore']}) ile hesaplanan toplam ({student['calculatedTotal']}) farklı."
            )
    return warnings


def _selected_option(value: str) -> str:
    checked = re.search(r"(?:☒|☑|■|✓)\s*([^☐☒☑■✓]+)", value)
    return checked.group(1).strip() if checked else value.strip()


def _split_combined_value(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split("/", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0], "") if parts else ("", "")


def _normalise_exam_type(value: str) -> str:
    cleaned = re.sub(r"^\s*\d+\s*[.\-)]?\s*", "", value).strip()
    token = _normalise_label(cleaned)
    for canonical, candidate in (
        ("Yazılı", "yazili"),
        ("Dinleme", "dinleme"),
        ("Konuşma", "konusma"),
    ):
        if candidate in token:
            return canonical
    return cleaned


def _number(value: str) -> float | int | None:
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def _integer(value: str) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None
