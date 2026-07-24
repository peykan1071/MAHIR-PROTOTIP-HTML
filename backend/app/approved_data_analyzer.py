"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def analyze_approved_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate approved browser data and return deterministic analysis results."""

    questions = payload.get("questions")
    students = payload.get("students")
    exam = payload.get("exam") or {}
    if not isinstance(questions, list) or not questions:
        raise ValueError("Analiz için en az bir soru bulunmalıdır.")
    if not isinstance(students, list) or not students:
        raise ValueError("Analiz için en az bir öğrenci bulunmalıdır.")

    normalized_questions = [_normalize_question(item, index) for index, item in enumerate(questions, 1)]
    participating = [
        _normalize_student(item, normalized_questions, index)
        for index, item in enumerate(students, 1)
        if _is_participating(item)
    ]
    if not participating:
        raise ValueError("Sınava katılan öğrenci bulunmadığı için analiz oluşturulamadı.")

    question_results = []
    outcome_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"earned": 0.0, "possible": 0.0}
    )
    for question_index, question in enumerate(normalized_questions):
        earned = sum(student["scores"][question_index] for student in participating)
        possible = question["maxScore"] * len(participating)
        rate = earned / possible if possible else 0.0
        question_results.append({**question, "earnedScore": earned, "possibleScore": possible, "successRate": rate})
        outcome_code = question["outcomeCode"] or f"Soru {question['number']}"
        outcome_totals[outcome_code]["earned"] += earned
        outcome_totals[outcome_code]["possible"] += possible

    outcome_results = []
    for code, totals in outcome_totals.items():
        rate = totals["earned"] / totals["possible"] if totals["possible"] else 0.0
        outcome_results.append(
            {
                "outcomeCode": code,
                "earnedScore": totals["earned"],
                "possibleScore": totals["possible"],
                "successRate": rate,
                "category": _category(rate),
                "decision": _decision(rate),
            }
        )

    average = sum(student["calculatedTotal"] for student in participating) / len(participating)
    exam_max = sum(question["maxScore"] for question in normalized_questions)
    return {
        "exam": exam,
        "summary": {
            "questionCount": len(normalized_questions),
            "studentCount": len(students),
            "participatingStudentCount": len(participating),
            "absentStudentCount": len(students) - len(participating),
            "examMaxScore": exam_max,
            "classAverage": round(average, 2),
            "classSuccessRate": average / exam_max if exam_max else 0.0,
        },
        "questions": question_results,
        "outcomes": outcome_results,
        "students": participating,
    }


def _normalize_question(item: Any, fallback_number: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{fallback_number}. soru verisi geçersiz.")
    number = int(_number(item.get("number"), fallback_number))
    max_score = _number(item.get("maxScore"))
    if max_score <= 0:
        raise ValueError(f"{number}. sorunun azami puanı sıfırdan büyük olmalıdır.")
    return {
        "number": number,
        "maxScore": max_score,
        "outcomeCode": str(item.get("outcomeCode") or "").strip(),
        "outcomeDescription": str(item.get("outcomeDescription") or "").strip(),
    }


def _normalize_student(
    item: Any, questions: list[dict[str, Any]], fallback_row: int
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{fallback_row}. öğrenci verisi geçersiz.")
    scores = item.get("scores")
    if not isinstance(scores, list) or len(scores) != len(questions):
        raise ValueError(f"{fallback_row}. öğrenci için soru puanları eksik.")

    normalized_scores = []
    for question, score in zip(questions, scores):
        value = _number(score)
        if value < 0 or value > question["maxScore"]:
            raise ValueError(
                f"{fallback_row}. öğrencinin {question['number']}. soru puanı "
                f"0–{question['maxScore']:g} aralığında olmalıdır."
            )
        normalized_scores.append(value)

    calculated_total = round(sum(normalized_scores), 2)
    supplied_total = _number(item.get("totalScore"), calculated_total)
    if abs(supplied_total - calculated_total) > 0.01:
        raise ValueError(
            f"{fallback_row}. öğrencinin toplam puanı {calculated_total:g} olmalıdır; "
            f"onay ekranındaki toplamı düzeltiniz."
        )
    return {
        "rowNumber": item.get("rowNumber") or fallback_row,
        "studentNo": str(item.get("studentNo") or "").strip(),
        "fullName": str(item.get("fullName") or "").strip(),
        "scores": normalized_scores,
        "calculatedTotal": calculated_total,
        "attendance": str(item.get("attendance") or "Girdi").strip(),
    }


def _is_participating(item: Any) -> bool:
    if not isinstance(item, dict):
        return True
    attendance = str(item.get("attendance") or "Girdi").strip().casefold()
    return attendance not in {"g", "girmedi", "katılmadı", "katilmadi", "yok"}


def _number(value: Any, default: float | int | None = None) -> float:
    if value is None or value == "":
        if default is not None:
            return float(default)
        raise ValueError("Boş bırakılan sayısal alanlar düzeltilmelidir.")
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError) as error:
        raise ValueError(f"“{value}” geçerli bir sayı değildir.") from error


def _category(rate: float) -> str:
    if rate >= 0.85:
        return "Çok güçlü"
    if rate >= 0.70:
        return "Güçlü"
    if rate >= 0.50:
        return "Gelişmekte"
    return "Destek gerekli"


def _decision(rate: float) -> str:
    if rate >= 0.85:
        return "Öğrenme çıktısındaki başarı korunmalı ve zenginleştirici çalışmalarla sürdürülmelidir."
    if rate >= 0.70:
        return "Kısa pekiştirme çalışmalarıyla öğrenmenin kalıcılığı desteklenmelidir."
    if rate >= 0.50:
        return "Hedefe yönelik ek etkinlik ve biçimlendirici değerlendirme uygulanmalıdır."
    return "Öğrenme eksikleri yeniden öğretim ve yakın izleme yoluyla öncelikli olarak desteklenmelidir."
