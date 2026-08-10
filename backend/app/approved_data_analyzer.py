"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

from .assessment_profiles import (
    COMPONENT_LABELS,
    GENERAL,
    PROFILES,
    WRITTEN,
    build_general_evaluation,
    profile_for_course,
)
from .program_catalog import ProgramProfile, validate_question_program_context

_DEFAULT_MAHIR_RAG_REMOTE_URL = "https://hakanergul--turkish-rag-system-raginference-web-query.modal.run"
# Varsayılan, deploy edilmiş RAG servisinin adresi olarak koda gömülü - terminalde
# her seferinde MAHIR_RAG_REMOTE_URL ayarlamaya gerek yok. Farklı bir deploy'a
# (ör. test ortamı) işaret etmek gerekirse env var yine de bunu geçersiz kılar.
MAHIR_RAG_REMOTE_URL = os.environ.get("MAHIR_RAG_REMOTE_URL", _DEFAULT_MAHIR_RAG_REMOTE_URL)
_RAG_WEAK_THRESHOLD = 0.70  # assets/js/mahir-report-export-common.js:buildDevelopmentNeedsBlock ile aynı eşik
_RAG_NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."


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
    if component_type == GENERAL:
        if course_profile is None:
            raise ValueError("Genel dil değerlendirmesi yalnız dil dersi profilinde kullanılabilir.")
        component_analyses = payload.get("componentAnalyses")
        if not isinstance(component_analyses, dict):
            raise ValueError(
                "Genel değerlendirme için yazılı, dinleme/izleme ve konuşma bileşenlerine ait "
                "onaylanmış öğrenme kanıtları gereklidir."
            )
        return build_general_evaluation(course_profile.id, component_analyses)
    if not isinstance(questions, list) or not questions:
        raise ValueError("Analiz için en az bir soru bulunmalıdır.")
    if not isinstance(students, list) or not students:
        raise ValueError("Analiz için en az bir öğrenci bulunmalıdır.")

    program = validate_question_program_context(course_name, exam.get("grade"), questions)

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
        question_results.append({
            **question,
            "earnedScore": earned,
            "possibleScore": possible,
            "realizationRate": rate,
            "successRate": rate,
        })
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
                "realizationRate": rate,
                "developmentLevel": _category(rate),
                "category": _category(rate),
                "decision": _decision(rate),
            }
        )

    _attach_rag_context(outcome_results, program)

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
            "classLearningLevel": average / exam_max if exam_max else 0.0,
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
        "parentOutcomeCode": str(item.get("parentOutcomeCode") or "").strip(),
        "parentOutcomeDescription": str(item.get("parentOutcomeDescription") or "").strip(),
        "outcomeKey": str(item.get("outcomeKey") or "").strip(),
    }


def _normalize_student(
    item: Any, questions: list[dict[str, Any]], fallback_row: int
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{fallback_row}. öğrenci verisi geçersiz.")
    student_no = str(item.get("studentNo") or "").strip()
    if not student_no or student_no.casefold() == "okunamadı":
        raise ValueError(
            f"{fallback_row}. öğrenci satırındaki okunamayan veya boş okul numarasını düzeltiniz."
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
        return "Beklenen düzeyin üzerinde gelişmiş"
    if rate >= 0.70:
        return "Beklenen düzeyde gelişmiş"
    if rate >= 0.50:
        return "Gelişimi sürmekte"
    return "İlave destek gerektiriyor"


def _decision(rate: float) -> str:
    if rate >= 0.85:
        return "Öğrenme çıktısına ilişkin kanıtlar beklenen düzeyin üzerinde gelişim göstermektedir."
    if rate >= 0.70:
        return "Öğrenme çıktısına ilişkin kanıtlar beklenen düzeydedir; gelişim izlenmelidir."
    if rate >= 0.50:
        return "Öğrenme çıktısının gerçekleşme düzeyini geliştirecek öğrenme yaşantılarına ihtiyaç vardır."
    return "Öğrenme çıktısına ilişkin öğrenme kanıtları ilave desteğe ihtiyaç olduğunu göstermektedir."


def _attach_rag_context(outcome_results: list[dict[str, Any]], program: ProgramProfile | None) -> None:
    """Attach a short RAG-grounded conceptual explanation to each weak outcome.

    Mutates `outcome_results` in place, adding a `ragContext` field (empty
    string when unavailable) to every outcome so the field's presence is
    always predictable regardless of which path was taken. Calls
    `rag_client.query_rag_context` sequentially, once per weak outcome (see
    module docstring history / rag_service.py for why not parallel: RAGInference
    has no @modal.concurrent, so simultaneous calls would spin up separate
    cold containers instead of reusing one warm one). Never raises: any
    failure, timeout, or "not found in the document" answer just leaves
    `ragContext` empty, so a RAG problem can never block the teacher's
    analysis response. Only attempted for a resolved program (`program is
    not None`) - MAHİR covers 60+ courses but only registered programs have
    any indexed reference material, so unregistered courses would otherwise
    pay a ~112s cold-start wait for a query guaranteed to return nothing.
    """

    for outcome in outcome_results:
        outcome["ragContext"] = ""

    if not MAHIR_RAG_REMOTE_URL or program is None:
        return

    from .rag_client import query_rag_context

    for outcome in outcome_results:
        if float(outcome.get("successRate") or 0.0) >= _RAG_WEAK_THRESHOLD:
            continue
        question = _build_rag_question(outcome)
        if not question:
            continue
        theme = _normalize_theme_for_rag(str(outcome.get("outcomeTheme") or ""))
        try:
            ok, _message, data = query_rag_context(
                question, program.id, MAHIR_RAG_REMOTE_URL, grade=program.grade, theme=theme
            )
        except Exception:  # noqa: BLE001 - bir RAG/ağ sorunu analiz yanıtını asla kesmemeli.
            continue
        if not ok or not data:
            continue
        answer = str(data.get("answer") or "").strip()
        # startswith, tam eşleşme değil: model bazen "Bu bilgi belgede
        # bulunmuyor." ile başlayıp çelişkili şekilde devam edip teşhis
        # yazmaya devam edebiliyor (gerçek deploy'da görüldü) - böyle
        # kendiyle çelişen bir yanıtı göstermek yerine tamamen atlanır.
        if not answer or not data.get("sources") or answer.startswith(_RAG_NO_ANSWER_TEXT):
            continue
        outcome["ragContext"] = answer


# Standart Unicode .upper() Türkçe 'i'/'ı' ayrımını kaybediyor (ikisi de düz
# "I"ya dönüşüyor) - rag_service.py'nin PDF'ten çıkardığı tema etiketleri
# (ör. "SÖZÜN İNCELİĞİ") zaten belgedeki doğru büyük/küçük harfle saklanıyor,
# bu yüzden yalnızca burada, sınavın karışık-case "outcomeTheme" alanını o
# etikete eşleştirmek için Türkçe-doğru büyütme uygulanıyor.
_TURKISH_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})


def _normalize_theme_for_rag(raw_theme: str) -> str:
    """`"1. Tema: Sözün İnceliği"` -> `"SÖZÜN İNCELİĞİ"` - rag_service.py'nin
    `index_pdf`'in PDF'ten çıkardığı ham tema etiketiyle (bkz. `_run_query`'nin
    `theme` filtresi) eşleşmesi için "N. Tema:" önekini atıp Türkçe-doğru
    büyük harfe çevirir."""

    without_prefix = re.sub(r"^\s*\d+\.\s*Tema\s*:\s*", "", raw_theme, flags=re.IGNORECASE).strip()
    return without_prefix.translate(_TURKISH_UPPER_MAP).upper()


def _build_rag_question(outcome: dict[str, Any]) -> str:
    """Build a RAG question from theme + code + skill together - never code
    alone, since the same code (e.g. TDE1.2) means a different learning
    outcome in each of the four TDE9 themes. Includes the actual success
    rate so the RAG system prompt (rag_service.py) can compare the outcome's
    Bloom's-taxonomy cognitive level against the score, per the analyst-style
    diagnostic framing. Deliberately asks for a diagnosis, never "how should
    this be taught" - MAHİR does not suggest activities, methods, or
    remedial programs (DEVELOPMENT_CHARTER.md), this question wording is the
    point where that constraint is actually enforced."""

    parts = [
        str(part)
        for part in (outcome.get("outcomeTheme"), outcome.get("outcomeCode"), outcome.get("outcomeSkill"))
        if part
    ]
    if not parts:
        return ""
    success_rate = float(outcome.get("successRate") or 0.0)
    percent_text = f"%{round(success_rate * 100)}"
    return (
        f"{' - '.join(parts)} öğrenme çıktısında öğrenciler {percent_text} "
        "başarı oranı gösterdi. Bu kazanımın bilişsel düzeyini bu başarı "
        "oranıyla kıyaslayarak teşhis et."
    )
