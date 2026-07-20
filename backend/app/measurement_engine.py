"""Measurement Engine for the MAHIR backend skeleton.

This module calculates question-level and learning-outcome-level success rates
from a program-mapped CED document and sample student answers. It does not use
AI, OCR, API, or a database.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .csv_parser import validate_document
from .models import CEDDocument, CEDQuestionScore, CEDStudentResult
from .program_mapper import build_mapped_ced_document


def load_student_answers(path: str | Path) -> list[dict[str, Any]]:
    """Load sample student answers from JSON."""

    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)

    student_results = payload.get("student_results")

    if not isinstance(student_results, list):
        raise ValueError("sample-student-results.json içinde student_results listesi bulunmalıdır.")

    for index, student in enumerate(student_results, start=1):
        if not isinstance(student, dict):
            raise ValueError(f"{index}. öğrenci sonucu nesne olmalıdır.")
        if not student.get("student_no"):
            raise ValueError(f"{index}. öğrenci sonucunda student_no bulunmalıdır.")
        if not student.get("full_name"):
            raise ValueError(f"{index}. öğrenci sonucunda full_name bulunmalıdır.")
        if not isinstance(student.get("answers"), list):
            raise ValueError(f"{index}. öğrenci sonucunda answers listesi bulunmalıdır.")

    return student_results


def apply_student_results(document: CEDDocument, student_answers: list[dict[str, Any]]) -> CEDDocument:
    """Match student answers to CED questions and update CED student_results."""

    questions_by_id = {question.id: question for question in document.questions}
    document.student_results = []

    for student in student_answers:
        answer_items = student["answers"]
        answers_by_question = {
            str(item.get("question_id")): str(item.get("answer", "")).strip()
            for item in answer_items
            if isinstance(item, dict)
        }
        question_scores: list[CEDQuestionScore] = []
        total_score = 0.0

        for question in document.questions:
            answer = answers_by_question.get(question.id, "")
            score = _score_answer(answer, question.answer_key, question.max_score)
            total_score += score
            question_scores.append(CEDQuestionScore(question_id=question.id, score=score))

        document.student_results.append(
            CEDStudentResult(
                student_no=str(student["student_no"]),
                full_name=str(student["full_name"]),
                answers=answer_items,
                question_scores=question_scores,
                total_score=total_score,
            )
        )

    return document


def calculate_question_success_rates(document: CEDDocument) -> dict[str, float]:
    """Calculate success rate for each question."""

    student_count = len(document.student_results)
    rates: dict[str, float] = {}

    if student_count == 0:
        return {question.id: 0.0 for question in document.questions}

    for question in document.questions:
        max_score = question.max_score or 0
        if max_score <= 0:
            rates[question.id] = 0.0
            continue

        earned_score = 0.0
        for student in document.student_results:
            score = _find_question_score(student, question.id)
            earned_score += score

        rates[question.id] = earned_score / (max_score * student_count)

    return rates


def calculate_learning_outcome_success_rates(document: CEDDocument) -> dict[str, float]:
    """Calculate weighted success rate for each learning outcome."""

    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"earned": 0.0, "possible": 0.0})
    student_count = len(document.student_results)

    if student_count == 0:
        return {}

    for question in document.questions:
        possible_score = (question.max_score or 0) * student_count
        earned_score = sum(_find_question_score(student, question.id) for student in document.student_results)

        for outcome_id in question.learning_outcome_ids:
            totals[outcome_id]["earned"] += earned_score
            totals[outcome_id]["possible"] += possible_score

    return {
        outcome_id: values["earned"] / values["possible"] if values["possible"] else 0.0
        for outcome_id, values in totals.items()
    }


def build_measured_ced_document(
    csv_path: str | Path,
    outcomes_path: str | Path,
    student_results_path: str | Path,
) -> tuple[CEDDocument, dict[str, float], dict[str, float]]:
    """Build mapped CED, apply student answers, and calculate measurements."""

    document = build_mapped_ced_document(csv_path, outcomes_path)
    student_answers = load_student_answers(student_results_path)
    document = apply_student_results(document, student_answers)
    question_rates = calculate_question_success_rates(document)
    outcome_rates = calculate_learning_outcome_success_rates(document)
    return document, question_rates, outcome_rates


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "shared" / "sample-exam.csv"
    outcomes_path = project_root / "shared" / "sample-learning-outcomes.json"
    student_results_path = project_root / "shared" / "sample-student-results.json"

    try:
        document, question_rates, outcome_rates = build_measured_ced_document(
            csv_path,
            outcomes_path,
            student_results_path,
        )
        is_valid, errors = validate_document(document)
    except (OSError, ValueError) as error:
        print(f"Measurement Engine tamamlanamadı: {error}")
        return 1

    if not is_valid:
        print("Measurement Engine doğrulama başarısız.")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Soru bazlı başarı oranları:")
    for question in document.questions:
        print(f"- {question.id}: {_format_rate(question_rates[question.id])}")

    print("Öğrenme çıktısı bazlı başarı oranları:")
    for outcome_id, rate in sorted(outcome_rates.items()):
        print(f"- {outcome_id}: {_format_rate(rate)}")

    return 0


def _score_answer(answer: str, answer_key: str | None, max_score: float | None) -> float:
    if not answer_key or max_score is None:
        return 0.0

    return float(max_score) if answer.casefold() == answer_key.strip().casefold() else 0.0


def _find_question_score(student: CEDStudentResult, question_id: str) -> float:
    for question_score in student.question_scores:
        if question_score.question_id == question_id:
            return float(question_score.score or 0)

    return 0.0


def _format_rate(rate: float) -> str:
    return f"%{rate * 100:.2f}"


if __name__ == "__main__":
    sys.exit(main())
