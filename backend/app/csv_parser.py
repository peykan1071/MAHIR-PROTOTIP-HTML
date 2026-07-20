"""Create a CED document from the Sprint 3 sample exam CSV file.

Expected CSV format:

question_no,question_text,correct_answer,points
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import CEDAssessment, CEDDocument, CEDMetadata, CEDQuestion, CEDValidation
from .validator import validate_ced_payload


EXPECTED_HEADERS = ["question_no", "question_text", "correct_answer", "points"]


def read_sample_exam(csv_path: str | Path) -> list[CEDQuestion]:
    """Read sample-exam.csv rows and convert each row into CEDQuestion."""

    path = Path(csv_path)

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != EXPECTED_HEADERS:
            expected = ", ".join(EXPECTED_HEADERS)
            actual = ", ".join(reader.fieldnames or [])
            raise ValueError(f"CSV başlıkları beklenen formatla uyumlu değil. Beklenen: {expected}. Gelen: {actual}.")

        questions: list[CEDQuestion] = []
        for row_index, row in enumerate(reader, start=2):
            question_no = _parse_int(row["question_no"], row_index, "question_no")
            points = _parse_float(row["points"], row_index, "points")
            question_text = row["question_text"].strip()
            correct_answer = row["correct_answer"].strip()

            if not question_text:
                raise ValueError(f"{row_index}. satır: question_text boş olamaz.")
            if not correct_answer:
                raise ValueError(f"{row_index}. satır: correct_answer boş olamaz.")

            questions.append(
                CEDQuestion(
                    id=f"q{question_no}",
                    number=question_no,
                    text=question_text,
                    max_score=points,
                    learning_outcome_ids=[],
                    answer_key=correct_answer,
                )
            )

    return questions


def build_ced_document(csv_path: str | Path) -> CEDDocument:
    """Build a complete CEDDocument from sample-exam.csv."""

    path = Path(csv_path)
    questions = read_sample_exam(path)
    total_score = sum(question.max_score or 0 for question in questions)

    return CEDDocument(
        metadata=CEDMetadata(
            ced_version="0.1.0",
            created_at=datetime.now(timezone.utc).isoformat(),
            source=path.name,
            language="tr",
        ),
        assessment=CEDAssessment(
            id="sample-exam",
            title="Sample Exam CSV",
            course="Belirtilmedi",
            question_count=len(questions),
            total_score=total_score,
        ),
        questions=questions,
        student_results=[],
        validation=CEDValidation(valid=True, issues=[], warnings=[]),
    )


def validate_document(document: CEDDocument) -> tuple[bool, list[str]]:
    """Validate a generated CEDDocument with the existing validator."""

    is_valid, errors, _model = validate_ced_payload(document.to_dict())
    return is_valid, errors


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "shared" / "sample-exam.csv"

    try:
        document = build_ced_document(csv_path)
        is_valid, errors = validate_document(document)
    except (OSError, ValueError) as error:
        print(f"CED oluşturulamadı: {error}")
        return 1

    if not is_valid:
        print("CED doğrulama başarısız.")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CED oluşturuldu.")
    return 0


def _parse_int(value: str, row_index: int, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{row_index}. satır: {field_name} tam sayı olmalıdır.") from error


def _parse_float(value: str, row_index: int, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{row_index}. satır: {field_name} sayı olmalıdır.") from error


if __name__ == "__main__":
    sys.exit(main())
