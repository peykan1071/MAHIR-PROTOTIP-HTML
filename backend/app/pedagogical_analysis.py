"""Pedagogical Analysis Engine for the MAHIR backend skeleton.

This module consumes Measurement Engine success rates and produces simple
pedagogical decision notes. It does not use AI, OCR, API, or a database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .measurement_engine import build_measured_ced_document
from .program_mapper import load_learning_outcomes


STRONG_THRESHOLD = 0.80
DEVELOPMENT_THRESHOLD = 0.50


def analyze_learning_outcomes(
    outcome_rates: dict[str, float],
    learning_outcomes: list[dict[str, Any]],
) -> list[dict[str, str | float]]:
    """Categorize learning outcomes and create pedagogical decision notes."""

    titles_by_id = {
        str(outcome["id"]): str(outcome.get("title", outcome["id"]))
        for outcome in learning_outcomes
    }

    return [
        {
            "learning_outcome_id": outcome_id,
            "title": titles_by_id.get(outcome_id, outcome_id),
            "success_rate": rate,
            "category": _categorize_rate(rate),
            "decision": _build_decision_note(rate),
        }
        for outcome_id, rate in sorted(outcome_rates.items())
    ]


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "shared" / "sample-exam.csv"
    outcomes_path = project_root / "shared" / "sample-learning-outcomes.json"
    student_results_path = project_root / "shared" / "sample-student-results.json"

    try:
        _document, _question_rates, outcome_rates = build_measured_ced_document(
            csv_path,
            outcomes_path,
            student_results_path,
        )
        learning_outcomes = load_learning_outcomes(outcomes_path)
        analysis_results = analyze_learning_outcomes(outcome_rates, learning_outcomes)
    except (OSError, ValueError) as error:
        print(f"Pedagojik analiz tamamlanamadı: {error}")
        return 1

    print("Pedagojik analiz sonuçları:")
    for result in analysis_results:
        print(
            f"- {result['learning_outcome_id']}: "
            f"{_format_rate(float(result['success_rate']))} | {result['category']}"
        )
        print(f"  Karar: {result['decision']}")

    return 0


def _categorize_rate(rate: float) -> str:
    if rate >= STRONG_THRESHOLD:
        return "Güçlü"
    if rate >= DEVELOPMENT_THRESHOLD:
        return "Geliştirilmeli"
    return "Kritik"


def _build_decision_note(rate: float) -> str:
    category = _categorize_rate(rate)

    if category == "Güçlü":
        return "Öğrenme çıktısı güçlü düzeydedir; pekiştirme etkinlikleriyle sürdürülmelidir."
    if category == "Geliştirilmeli":
        return "Öğrenme çıktısı kısmen kazanılmıştır; hedefli tekrar ve ek örneklerle desteklenmelidir."
    return "Öğrenme çıktısı kritik düzeydedir; yeniden öğretim ve yakın izleme planlanmalıdır."


def _format_rate(rate: float) -> str:
    return f"%{rate * 100:.2f}"


if __name__ == "__main__":
    sys.exit(main())
