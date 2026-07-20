"""Program Mapping Engine for the MAHIR backend skeleton.

This module maps questions in a generated CED document to sample learning
outcomes by deterministic keyword matching. It does not use AI, OCR, API, or a
database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .csv_parser import build_ced_document, validate_document
from .models import CEDDocument, CEDQuestion


def load_learning_outcomes(path: str | Path) -> list[dict[str, Any]]:
    """Load sample learning outcomes from JSON."""

    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)

    outcomes = payload.get("learning_outcomes")

    if not isinstance(outcomes, list):
        raise ValueError("sample-learning-outcomes.json içinde learning_outcomes listesi bulunmalıdır.")

    for index, outcome in enumerate(outcomes, start=1):
        if not isinstance(outcome, dict):
            raise ValueError(f"{index}. öğrenme çıktısı nesne olmalıdır.")
        if not outcome.get("id"):
            raise ValueError(f"{index}. öğrenme çıktısında id bulunmalıdır.")
        if not isinstance(outcome.get("keywords", []), list):
            raise ValueError(f"{index}. öğrenme çıktısında keywords liste olmalıdır.")

    return outcomes


def map_program_outcomes(document: CEDDocument, learning_outcomes: list[dict[str, Any]]) -> CEDDocument:
    """Add learning_outcome_ids to each question in the CED document."""

    fallback_id = _get_fallback_outcome_id(learning_outcomes)

    for question in document.questions:
        question.learning_outcome_ids = _match_question(question, learning_outcomes, fallback_id)

    return document


def build_mapped_ced_document(csv_path: str | Path, outcomes_path: str | Path) -> CEDDocument:
    """Create a CED document from CSV and map questions to learning outcomes."""

    document = build_ced_document(csv_path)
    outcomes = load_learning_outcomes(outcomes_path)
    return map_program_outcomes(document, outcomes)


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "shared" / "sample-exam.csv"
    outcomes_path = project_root / "shared" / "sample-learning-outcomes.json"

    try:
        document = build_mapped_ced_document(csv_path, outcomes_path)
        is_valid, errors = validate_document(document)
    except (OSError, ValueError) as error:
        print(f"Program Mapping tamamlanamadı: {error}")
        return 1

    if not is_valid:
        print("Program Mapping doğrulama başarısız.")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Program Mapping tamamlandı.")
    return 0


def _match_question(
    question: CEDQuestion,
    learning_outcomes: list[dict[str, Any]],
    fallback_id: str,
) -> list[str]:
    question_text = (question.text or "").casefold()
    matched_ids: list[str] = []

    for outcome in learning_outcomes:
        outcome_id = str(outcome["id"])
        keywords = outcome.get("keywords", [])

        if any(str(keyword).casefold() in question_text for keyword in keywords):
            matched_ids.append(outcome_id)

    return matched_ids or [fallback_id]


def _get_fallback_outcome_id(learning_outcomes: list[dict[str, Any]]) -> str:
    for outcome in learning_outcomes:
        if outcome.get("id") == "GEN.1":
            return "GEN.1"

    if not learning_outcomes:
        raise ValueError("En az bir öğrenme çıktısı tanımlanmalıdır.")

    return str(learning_outcomes[0]["id"])


if __name__ == "__main__":
    sys.exit(main())
