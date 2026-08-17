"""Tarayıcı yükünü bellek-içi bir CED belgesine çevirir.

Mevcut CED üreticileri (`program_mapper.build_mapped_ced_document`,
`measurement_engine.load_student_answers`) DOSYA YOLU güdümlü - diskteki bir
CSV/JSON'dan okuyorlar. Canlı akışta ise veri tarayıcıdan gelip bellekte
duruyor. Eksik halka buydu ve çok ajanlı hattın CED üzerinden çalışamamasının
teknik sebebi tam olarak buydu.

Öğrenme çıktısı kimliği (`learning_outcome_ids`) kasıtlı olarak
`approved_data_analyzer`ın bugün kullandığı anahtarla AYNI üretilir
("tema | kod"). Böylece `measurement_engine.calculate_learning_outcome_
success_rates` canlı veriyle de bugünküyle birebir aynı oranları verir -
ölçme mantığının tekilleşmesi buna dayanıyor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import (
    CEDAssessment,
    CEDDocument,
    CEDMetadata,
    CEDQuestion,
    CEDQuestionScore,
    CEDStudentResult,
)

CED_VERSION = "1.0"
SOURCE_TEACHER_APPROVED = "teacher-approved-analysis-payload"


def outcome_key_for_mapping(mapping: dict[str, Any], question_number: Any) -> str:
    """Tek bir öğrenme çıktısı eşleştirmesinin kararlı anahtarı."""

    return str(mapping.get("outcomeKey") or "").strip() or " | ".join(
        value for value in (mapping.get("outcomeTheme"), mapping.get("outcomeCode")) if value
    ) or f"Soru {question_number}"


def outcome_mappings_for(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Sorunun tekli veya çoklu öğrenme çıktısı eşleştirmelerini döndür."""

    outcomes = question.get("outcomes")
    if isinstance(outcomes, list) and outcomes:
        return [item for item in outcomes if isinstance(item, dict)]
    return [{
        "outcomeCode": question.get("outcomeCode") or "",
        "outcomeDescription": question.get("outcomeDescription") or "",
        "outcomeTheme": question.get("outcomeTheme") or "",
        "outcomeSkill": question.get("outcomeSkill") or "",
        "parentOutcomeCode": question.get("parentOutcomeCode") or "",
        "parentOutcomeDescription": question.get("parentOutcomeDescription") or "",
        "outcomeKey": question.get("outcomeKey") or "",
        "weight": 1.0,
    }]


def outcome_key_for(question: dict[str, Any]) -> str:
    """`approved_data_analyzer`ın öğrenme çıktısı gruplama anahtarı.

    Kod TEK BAŞINA yeterli değil: aynı kod (ör. TDE1.2) farklı temalarda
    farklı kazanıma karşılık geliyor, bu yüzden tema anahtarın parçası.
    Hiçbiri yoksa soru kendi başına bir grup olur.
    """

    mapping = outcome_mappings_for(question)[0]
    return outcome_key_for_mapping(mapping, question.get("number"))


def question_id_for(index: int) -> str:
    """Sıra tabanlı kimlik - soru NUMARALARI yinelenebildiği için onlara
    güvenilmiyor; `measurement_engine._find_question_score` eşleşmeyi bu
    kimlikle yapıyor ve iki soru aynı kimliği alırsa puanlar karışır."""

    return f"q{index + 1}"


def build_ced_from_payload(
    exam: dict[str, Any],
    questions: list[dict[str, Any]],
    students: list[dict[str, Any]],
) -> CEDDocument:
    """Normalleştirilmiş soru/öğrenci verisinden CED belgesi üretir.

    `questions` ve `students`, `approved_data_analyzer._normalize_question` /
    `_normalize_student` çıktısıdır - doğrulama orada yapılır, burada yalnız
    biçim dönüşümü var.

    GİZLİLİK: `CEDStudentResult.student_no` alanına oturumluk takma referans
    (`Ö-001`) yazılır, `full_name` BOŞ bırakılır. Analiz katmanı kimlik taşıyan
    alanları zaten reddediyor (`_assert_privacy_safe_students`); CED o kapının
    arkasında gerçek kimliği yeniden doğuran yer olmamalı.
    """

    ced_questions = []
    for index, question in enumerate(questions):
        mappings = outcome_mappings_for(question)
        keys = [outcome_key_for_mapping(item, question.get("number")) for item in mappings]
        weights = {
            key: float(mapping.get("weight") or 1.0)
            for key, mapping in zip(keys, mappings)
        }
        ced_questions.append(CEDQuestion(
            id=question_id_for(index),
            number=int(question["number"]),
            max_score=float(question["maxScore"]),
            learning_outcome_ids=keys,
            learning_outcome_weights=weights,
        ))

    student_results = [
        CEDStudentResult(
            student_no=str(student.get("studentRef") or ""),
            full_name="",
            question_scores=[
                CEDQuestionScore(question_id=ced_questions[index].id, score=float(score))
                for index, score in enumerate(student.get("scores") or [])
                if index < len(ced_questions)
            ],
            total_score=student.get("calculatedTotal"),
        )
        for student in students
    ]

    total_score = sum(question.max_score or 0.0 for question in ced_questions)
    assessment = CEDAssessment(
        id=str(exam.get("assessmentId") or exam.get("documentNo") or "mahir-assessment"),
        title=str(exam.get("examType") or "Sınav"),
        course=str(exam.get("courseName") or exam.get("course") or ""),
        education_level=_optional(exam.get("educationStage")),
        school_type=_optional(exam.get("schoolType")),
        grade=_optional(exam.get("grade")),
        exam_type=_optional(exam.get("examType")),
        exam_date=_optional(exam.get("examDate")),
        question_count=len(ced_questions),
        total_score=total_score,
        component_type=_optional(exam.get("componentType")),
        assessment_group_id=_optional(exam.get("assessmentGroupId")),
        weighting_profile_id=_optional(exam.get("weightingProfileId")),
    )

    return CEDDocument(
        metadata=CEDMetadata(
            ced_version=CED_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
            source=SOURCE_TEACHER_APPROVED,
        ),
        assessment=assessment,
        questions=ced_questions,
        student_results=student_results,
    )


def _optional(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
