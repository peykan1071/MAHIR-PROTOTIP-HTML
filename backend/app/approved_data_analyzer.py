"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .assessment_profiles import COMPONENT_LABELS, PROFILES, WRITTEN, profile_for_course


def analyze_approved_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate approved browser data and return deterministic analysis results."""

    questions = payload.get("questions")
    students = payload.get("students")
    exam = payload.get("exam") or {}
    component_type = str(exam.get("componentType") or WRITTEN).strip()
    if component_type not in COMPONENT_LABELS:
        raise ValueError("Sınav türü yazılı, dinleme/izleme veya konuşma olmalıdır.")
    profile_id = str(exam.get("weightingProfileId") or "").strip()
    if profile_id and profile_id not in PROFILES:
        raise ValueError("Seçilen değerlendirme ağırlık profili tanınmıyor.")
    course_name = str(exam.get("courseName") or exam.get("course") or "").strip()
    course_profile = profile_for_course(course_name)
    if profile_id and (course_profile is None or course_profile.id != profile_id):
        raise ValueError("Seçilen ağırlık profili bu ders için kullanılamaz.")
    if course_profile is None and component_type != WRITTEN:
        raise ValueError("Dinleme/izleme ve konuşma sınavları yalnız dil dersi profilinde kullanılabilir.")
    if not isinstance(questions, list) or not questions:
        raise ValueError("Analiz için en az bir soru bulunmalıdır.")
    if not isinstance(students, list) or not students:
        raise ValueError("Analiz için en az bir öğrenci bulunmalıdır.")

    normalized_questions = [_normalize_question(item, index) for index, item in enumerate(questions, 1)]
    participating = [
        _normalize_student(item, normalized_questions, index)
        for index, item in enumerate(students, 1)
    ]
    if not participating:
        raise ValueError("Sınava katılan öğrenci bulunmadığı için analiz oluşturulamadı.")

    question_results = []
    outcome_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"earned": 0.0, "possible": 0.0, "skill": ""}
    )
    for question_index, question in enumerate(normalized_questions):
        earned = sum(student["scores"][question_index] for student in participating)
        possible = question["maxScore"] * len(participating)
        rate = earned / possible if possible else 0.0
        question_results.append({**question, "earnedScore": earned, "possibleScore": possible, "successRate": rate})
        outcome_key = " | ".join(
            value for value in (question["outcomeTheme"], question["outcomeCode"]) if value
        ) or f"Soru {question['number']}"
        outcome_totals[outcome_key]["earned"] += earned
        outcome_totals[outcome_key]["possible"] += possible
        outcome_totals[outcome_key]["skill"] = question["outcomeSkill"]

    outcome_results = []
    for outcome_key, totals in outcome_totals.items():
        rate = totals["earned"] / totals["possible"] if totals["possible"] else 0.0
        theme, separator, code = outcome_key.rpartition(" | ")
        outcome_results.append(
            {
                "outcomeCode": code if separator else outcome_key,
                "outcomeTheme": theme if separator else "",
                "outcomeSkill": totals["skill"],
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
        "exam": {
            **exam,
            "componentType": component_type,
            "componentLabel": COMPONENT_LABELS[component_type],
            "weightingProfileId": profile_id or None,
            "componentWeight": PROFILES[profile_id].weights.get(component_type) if profile_id else None,
        },
        "summary": {
            "questionCount": len(normalized_questions),
            "studentCount": len(students),
            "participatingStudentCount": len(participating),
            "absentStudentCount": 0,
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
        "outcomeTheme": str(item.get("outcomeTheme") or "").strip(),
        "outcomeSkill": str(item.get("outcomeSkill") or "").strip(),
    }


def _normalize_student(
    item: Any, questions: list[dict[str, Any]], fallback_row: int
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{fallback_row}. öğrenci verisi geçersiz.")
    student_no = str(item.get("studentNo") or "").strip()
    full_name = str(item.get("fullName") or "").strip()
    if not student_no or not full_name or "okunamadı" in {student_no.casefold(), full_name.casefold()}:
        raise ValueError(
            f"{fallback_row}. öğrenci satırındaki okunamayan veya boş kimlik alanlarını düzeltiniz."
        )
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
        "studentNo": student_no,
        "fullName": full_name,
        "scores": normalized_scores,
        "calculatedTotal": calculated_total,
        "attendance": "",
    }


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
        return "Öğrenme çıktısında güçlü yeterlilik düzeyi tespit edilmiştir."
    if rate >= 0.70:
        return "Öğrenme çıktısında yeterlilik sağlanmış, gelişimin izlenmesine ihtiyaç bulunduğu değerlendirilmiştir."
    if rate >= 0.50:
        return "Öğrenme çıktısında gelişim ihtiyacı bulunduğu tespit edilmiştir."
    return "Öğrenme çıktısında öncelikli gelişim ihtiyacı bulunduğu tespit edilmiştir."
