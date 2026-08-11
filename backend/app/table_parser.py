"""Parse teacher-made score tables by semantic column headings.

The parser is shared by Word, text-based PDF and Excel readers. Identity
columns are recognised and excluded before student rows are returned.
"""

from __future__ import annotations

import re
from typing import Iterable


def parse_tabular_document(
    tables: Iterable[list[list[object]]], *, source_label: str
) -> dict[str, object]:
    """Return the best student-score table found in a document."""

    candidates = []
    for table in tables:
        cleaned = _clean_table(table)
        if not cleaned:
            continue
        parsed = _parse_student_table(cleaned, source_label=source_label)
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        raise ValueError(
            f"{source_label} belgesinde Okul No ve Soru sütunları bulunan okunabilir bir puan tablosu bulunamadı."
        )

    result = max(candidates, key=lambda item: len(item["students"]))
    return {
        "exam": {},
        "questions": result["questions"],
        "students": result["students"],
        "warnings": result["warnings"],
        "summary": {
            "questionCount": len(result["questions"]),
            "studentCount": len(result["students"]),
            "warningCount": len(result["warnings"]),
        },
    }


def _parse_student_table(rows: list[list[str]], *, source_label: str) -> dict[str, object] | None:
    headings = [_normalise_label(cell) for cell in rows[0]]
    number_index = _find_index(headings, _is_student_number_heading)
    total_index = _find_index(headings, _is_total_heading)
    row_index = _find_index(headings, lambda label: label in {"sira", "sira no"})
    name_indexes = [index for index, label in enumerate(headings) if _is_name_heading(label)]
    tckn_indexes = [index for index, label in enumerate(headings) if _is_tckn_heading(label)]
    score_columns = sorted(
        (
            (_question_number(label), index, _max_score_from_heading(rows[0][index]))
            for index, label in enumerate(headings)
            if _question_number(label) is not None
        ),
        key=lambda item: item[0],
    )

    if number_index is None or not score_columns:
        return None

    questions = [
        {"number": number, "outcomeCode": "", "outcomeDescription": "", "maxScore": max_score}
        for number, _, max_score in score_columns
    ]
    students = []
    for source_row in rows[1:]:
        row = source_row + [""] * max(0, len(headings) - len(source_row))
        student_no = row[number_index].strip()
        scores = [_number(row[index]) for _, index, _ in score_columns]
        total_score = _number(row[total_index]) if total_index is not None else None
        if not (student_no or any(score is not None for score in scores) or total_score is not None):
            continue
        privacy_findings = []
        if any(row[index].strip() for index in tckn_indexes):
            privacy_findings.append("TCKN")
        if any(row[index].strip() for index in name_indexes):
            privacy_findings.append("AD_SOYAD")
        students.append(
            {
                "rowNumber": _integer(row[row_index]) if row_index is not None else len(students) + 1,
                "studentNo": student_no,
                "scores": scores,
                "totalScore": total_score,
                "calculatedTotal": round(sum(score or 0 for score in scores), 2),
                "control": "",
                "privacyFindings": privacy_findings,
            }
        )

    if not students:
        return None

    warnings = []
    detected_identity_labels = []
    if tckn_indexes:
        detected_identity_labels.append("T.C. kimlik numarası")
    if name_indexes:
        detected_identity_labels.append("ad-soyad")
    if detected_identity_labels:
        warnings.append(
            f"{source_label}: KVKK uyarısı - {' ve '.join(detected_identity_labels)} sütunu algılandı "
            "ve öğrenci analiz verisinden çıkarıldı."
        )
    for student in students:
        if student["totalScore"] is not None and abs(
            float(student["totalScore"]) - float(student["calculatedTotal"])
        ) > 0.01:
            warnings.append(
                f"{student['rowNumber']}. satırda yazılan toplam ({student['totalScore']}) ile "
                f"hesaplanan toplam ({student['calculatedTotal']}) farklı."
            )
        student.pop("privacyFindings", None)

    return {"questions": questions, "students": students, "warnings": warnings}


def _clean_table(table: list[list[object]]) -> list[list[str]]:
    rows = [["" if cell is None else str(cell).strip() for cell in row] for row in table]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    nonempty_columns = [index for index in range(width) if any(row[index] for row in rows)]
    return [[row[index] for index in nonempty_columns] for row in rows]


def _find_index(headings: list[str], predicate) -> int | None:
    return next((index for index, label in enumerate(headings) if predicate(label)), None)


def _normalise_label(value: object) -> str:
    translation = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")
    return re.sub(r"[^a-z0-9]+", " ", str(value).translate(translation).casefold()).strip()


def _is_student_number_heading(label: str) -> bool:
    return label in {"okul no", "okul numarasi", "ogrenci no", "ogrenci numarasi", "numara", "no"}


def _is_name_heading(label: str) -> bool:
    return label in {"ad soyad", "adi soyadi", "ogrenci ad soyad", "ogrenci adi soyadi"}


def _is_tckn_heading(label: str) -> bool:
    return label in {
        "tc kimlik no", "t c kimlik no", "tc kimlik numarasi", "t c kimlik numarasi", "tckn"
    }


def _is_total_heading(label: str) -> bool:
    return label == "puan" or label.startswith("toplam") or label == "genel toplam"


def _question_number(label: str) -> int | None:
    match = re.match(r"^(?:s|soru)\s*(\d+)\b", label)
    return int(match.group(1)) if match else None


def _max_score_from_heading(value: object) -> float | int | None:
    text = str(value)
    match = re.search(r"(?:\(|\b)(\d+(?:[.,]\d+)?)\s*(?:p|puan)\b", text, flags=re.IGNORECASE)
    return _number(match.group(1)) if match else None


def _number(value: object) -> float | int | None:
    cleaned = str(value).strip().replace(",", ".")
    if not cleaned:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None
