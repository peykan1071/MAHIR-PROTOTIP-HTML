"""Read MAHIR Veri Giriş Şablonu tables from a DOCX document."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree


WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_mahir_docx(content: bytes) -> dict[str, object]:
    """Return teacher-reviewable data from a DOCX without requiring a template."""

    tables = _read_tables(content)
    exam_table = _find_exam_table(tables)
    question_table = _find_table(tables, {"soru no", "azami puan"})
    student_table = _find_student_table(tables)

    exam = _parse_exam(exam_table or [])
    questions = _parse_questions(question_table or [])
    students = _parse_students_flexible(student_table or [])
    warnings = _build_warnings(exam, questions, students)

    if student_table:
        headings = {_normalise_label(cell) for cell in student_table[0]}
        identity_columns = []
        if headings & {"tc kimlik no", "t c kimlik no", "tc kimlik numarasi", "t c kimlik numarasi", "tckn"}:
            identity_columns.append("T.C. kimlik numarası")
        if headings & {"ad soyad", "adi soyadi", "ogrenci ad soyad", "ogrenci adi soyadi"}:
            identity_columns.append("ad-soyad")
        if identity_columns:
            warnings.append(
                f"Word belgesi: KVKK uyarısı - {' ve '.join(identity_columns)} sütunu algılandı "
                "ve öğrenci analiz verisinden çıkarıldı."
            )

    if not student_table:
        warnings.append(
            "Word belgesindeki öğrenci ve puan alanları otomatik olarak ayırt edilemedi. "
            "Bilgileri öğretmen kontrol ekranında tamamlayınız."
        )

    return {
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
        labels = {_normalise_label(cell) for cell in table[0]}
        if required_labels.issubset(labels):
            return table
    return None


def _find_exam_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        labels = {_normalise_label(cell) for row in table for cell in row}
        if len(labels & {"il", "ilce", "okul adi", "ders", "sinif sube"}) >= 2:
            return table
    return None


def _find_student_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        labels = {_normalise_label(cell) for cell in table[0]}
        has_number = any(label in {"okul no", "ogrenci no", "numara", "no"} for label in labels)
        has_score = any(re.match(r"^(?:s|soru) ?\d+\b", label) for label in labels)
        if has_number and has_score:
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
    values: dict[str, str] = {}
    for row in rows:
        for index in range(0, len(row) - 1, 2):
            values[_normalise_label(row[index])] = row[index + 1].strip()

    return {
        "province": values.get("il", ""),
        "district": values.get("ilce", ""),
        "schoolName": values.get("okul adi", ""),
        "academicYear": values.get("egitim ogretim yili", ""),
        "course": values.get("ders", ""),
        "classSection": values.get("sinif sube", ""),
        "term": _selected_option(values.get("donem", "")),
        "examType": _selected_option(values.get("sinav turu", "")),
        "examDate": values.get("sinav tarihi", ""),
        "totalMaxScore": _number(values.get("toplam puan", "")),
        "teacherName": values.get("ogretmenin adi soyadi", ""),
        "teachingProgram": values.get("ogretim programi", ""),
        "assessmentBasis": values.get("olcme ve degerlendirme dayanagi", ""),
        "scenarioInfo": values.get("senaryo ornek evrak", ""),
        "otherSources": values.get("diger dayanaklar", ""),
        "documentNo": values.get("belge rapor no", "") or values.get("belge sayfa no", ""),
        "approvalInfo": values.get("iletim onay bilgisi", ""),
        "documentPage": values.get("belge sayfa no", ""),
    }


def _parse_questions(rows: list[list[str]]) -> list[dict[str, object]]:
    questions = []
    for row in rows[1:]:
        padded = row + [""] * (4 - len(row))
        number = _integer(padded[0])
        outcome_code = padded[1].strip()
        outcome_description = padded[2].strip()
        max_score = _number(padded[3])
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


def _parse_students_flexible(rows: list[list[str]]) -> list[dict[str, object]]:
    """Read a student-score table by its headings rather than column positions."""

    if not rows:
        return []
    headings = [_normalise_label(cell) for cell in rows[0]]

    def find_index(predicate) -> int | None:
        return next((index for index, label in enumerate(headings) if predicate(label)), None)

    row_index = find_index(lambda label: label in {"sira", "sira no"})
    number_index = find_index(lambda label: label in {"okul no", "ogrenci no", "numara", "no"})
    total_index = find_index(lambda label: label == "puan" or label.startswith("toplam"))
    score_indexes = [
        index for index, label in enumerate(headings)
        if re.match(r"^(?:s|soru) ?\d+\b", label)
    ]
    students = []

    for source_row in rows[1:]:
        row = source_row + [""] * max(0, len(headings) - len(source_row))
        scores = [_number(row[index]) for index in score_indexes]
        student_no = row[number_index].strip() if number_index is not None else ""
        total_score = _number(row[total_index]) if total_index is not None else None
        if not (student_no or any(score is not None for score in scores) or total_score is not None):
            continue
        students.append(
            {
                "rowNumber": _integer(row[row_index]) if row_index is not None else len(students) + 1,
                "studentNo": student_no,
                "scores": scores,
                "totalScore": total_score,
                "calculatedTotal": round(sum(score or 0 for score in scores), 2),
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

    for question in questions:
        if not question["outcomeCode"] and not question["outcomeDescription"]:
            warnings.append(f"{question['number']}. sorunun öğrenme çıktısı boş.")
        if question["maxScore"] is None:
            warnings.append(f"{question['number']}. sorunun azami puanı boş.")

    for student in students:
        if (
            student["totalScore"] is not None
            and abs(float(student["totalScore"]) - float(student["calculatedTotal"])) > 0.01
        ):
            warnings.append(
                f"{student['rowNumber']}. satırında yazılan toplam "
                f"({student['totalScore']}) ile hesaplanan toplam ({student['calculatedTotal']}) farklı."
            )
    return warnings


def _normalise_label(value: str) -> str:
    translation = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")
    return re.sub(r"[^a-z0-9]+", " ", value.translate(translation).casefold()).strip()


def _selected_option(value: str) -> str:
    checked = re.search(r"(?:☒|☑|■|✓)\s*([^☐☒☑■✓]+)", value)
    return checked.group(1).strip() if checked else value.strip()


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
