"""Reporting Engine for the MAHIR backend skeleton.

This module creates the first standard text-based MAHIR analysis report from
Pedagogical Analysis Engine results. It does not use AI, OCR, API, or a
database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .measurement_engine import build_measured_ced_document
from .pedagogical_analysis import analyze_learning_outcomes
from .program_mapper import load_learning_outcomes


def generate_report(
    document: Any,
    question_rates: dict[str, float],
    outcome_rates: dict[str, float],
    analysis_results: list[dict[str, str | float]],
    learning_outcomes: list[dict[str, Any]],
) -> str:
    """Generate a standard text-based MAHIR analysis report."""

    outcome_titles = {
        str(outcome["id"]): str(outcome.get("title", outcome["id"]))
        for outcome in learning_outcomes
    }

    lines = [
        "MAHİR ANALİZ RAPORU",
        "",
        "1. Sınav Özeti",
        f"- Sınav adı: {document.assessment.title}",
        f"- Soru sayısı: {len(document.questions)}",
        f"- Toplam puan: {_format_number(document.assessment.total_score)}",
        f"- Öğrenci sayısı: {len(document.student_results)}",
        "",
        "2. Soru Bazlı Başarı",
    ]

    for question in document.questions:
        rate = question_rates.get(question.id, 0.0)
        lines.append(f"- Soru {question.number} ({question.id}): {_format_rate(rate)}")

    lines.extend(["", "3. Öğrenme Çıktısı Bazlı Başarı"])

    for outcome_id, rate in sorted(outcome_rates.items()):
        title = outcome_titles.get(outcome_id, outcome_id)
        lines.append(f"- {outcome_id}: {_format_rate(rate)}")
        lines.append(f"  {title}")

    lines.extend(["", "4. Pedagojik Kararlar"])

    for result in analysis_results:
        outcome_id = str(result["learning_outcome_id"])
        category = str(result["category"])
        decision = str(result["decision"])
        rate = float(result["success_rate"])
        lines.append(f"- {outcome_id}: {_format_rate(rate)} | {category}")
        lines.append(f"  Karar: {decision}")

    return "\n".join(lines) + "\n"


def write_report(report_text: str, path: str | Path) -> None:
    """Write the generated report as UTF-8 text."""

    Path(path).write_text(report_text, encoding="utf-8")


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "shared" / "sample-exam.csv"
    outcomes_path = project_root / "shared" / "sample-learning-outcomes.json"
    student_results_path = project_root / "shared" / "sample-student-results.json"
    report_path = project_root / "shared" / "report-example.txt"

    try:
        document, question_rates, outcome_rates = build_measured_ced_document(
            csv_path,
            outcomes_path,
            student_results_path,
        )
        learning_outcomes = load_learning_outcomes(outcomes_path)
        analysis_results = analyze_learning_outcomes(outcome_rates, learning_outcomes)
        report_text = generate_report(
            document,
            question_rates,
            outcome_rates,
            analysis_results,
            learning_outcomes,
        )
        write_report(report_text, report_path)
    except (OSError, ValueError) as error:
        print(f"Rapor oluşturulamadı: {error}")
        return 1

    print(report_text, end="")
    return 0


def _format_rate(rate: float) -> str:
    return f"%{rate * 100:.2f}"


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "Belirtilmedi"
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.2f}"


if __name__ == "__main__":
    sys.exit(main())
