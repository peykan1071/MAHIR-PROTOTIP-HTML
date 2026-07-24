"""Read MAHIR Veri Giriş Şablonu tables from a DOCX document."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree


WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_mahir_docx(content: bytes) -> dict[str, object]:
    """Return exam, question and student data found in a MAHIR DOCX template."""

    tables = _read_tables(content)
    if len(tables) < 5:
        raise ValueError("Belge, MAHİR Veri Giriş Şablonu tablo yapısıyla eşleşmiyor.")

    exam = _parse_exam(tables[1])
    questions = _parse_questions(tables[3])
    students = _parse_students(tables[4], questions)
    warnings = _build_warnings(exam, questions, students)

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
        full_name = padded[2].strip()
        total_score = _number(padded[13])
        attendance = padded[14].strip()
        control = padded[15].strip()

        if not (student_no or full_name or any(score is not None for score in scores) or attendance):
            continue

        students.append(
            {
                "rowNumber": _integer(padded[0]) or len(students) + 1,
                "studentNo": student_no,
                "fullName": full_name,
                "scores": scores,
                "totalScore": total_score,
                "calculatedTotal": round(sum(score or 0 for score in scores), 2),
                "attendance": attendance or "Girdi",
                "control": control,
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
        if not student["fullName"]:
            warnings.append(f"{student['rowNumber']}. öğrenci satırında ad soyad boş.")
        if (
            student["totalScore"] is not None
            and student["attendance"].casefold() not in {"g", "girmedi", "katilmadi"}
            and abs(float(student["totalScore"]) - float(student["calculatedTotal"])) > 0.01
        ):
            warnings.append(
                f"{student['fullName'] or student['rowNumber']}. satırında yazılan toplam "
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
