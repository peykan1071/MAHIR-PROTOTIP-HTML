"""Measurement Engine — soru ve öğrenme çıktısı düzeyinde ham puan toplamları.

Dosya-yolu güdümlü eski akış (`load_student_answers`, `apply_student_results`,
`build_measured_ced_document`, CLI `main`) buradan kaldırıldı: canlı istek
yolu artık `backend/app/agents/pipeline.py::MeasurementAgent`, CED'i
bellek-içi bir yükten kuruyor (bkz. `agents/ced_builder.py`) ve buradaki
toplam fonksiyonlarını doğrudan çağırıyor.
"""

from __future__ import annotations

from collections import defaultdict

from .models import CEDDocument, CEDStudentResult


def calculate_question_totals(document: CEDDocument) -> dict[str, dict[str, float]]:
    """Return raw earned/possible totals per question id.

    Ham toplamlar oranın kendisinden ayrı olarak gerekiyor: rapordaki
    "Kanıtları Gör" bloğu, öğretmenin gösterilen yüzdeyi gösterilen
    puanlardan yeniden üretebilmesini istiyor (bkz.
    `approved_data_analyzer` evidence alanı). Oran fonksiyonu da bunu
    kullanır - hesap tek yerde kalsın diye.
    """

    student_count = len(document.student_results)
    totals: dict[str, dict[str, float]] = {}

    for question in document.questions:
        max_score = question.max_score or 0
        earned = sum(
            _find_question_score(student, question.id) for student in document.student_results
        )
        totals[question.id] = {"earned": earned, "possible": max_score * student_count}

    return totals


def calculate_learning_outcome_totals(document: CEDDocument) -> dict[str, dict[str, float]]:
    """Return raw earned/possible totals per learning outcome id.

    Bir öğrenme çıktısı birden çok soruyu kapsayabildiği için toplamlar soru
    bazında hesaplanıp çıktıya eklenir; sıralama soru sırasıdır, yani aynı
    girdi her zaman aynı kayan nokta toplamını verir.
    """

    question_totals = calculate_question_totals(document)
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"earned": 0.0, "possible": 0.0})

    for question in document.questions:
        values = question_totals[question.id]
        for outcome_id in question.learning_outcome_ids:
            weight = question.learning_outcome_weights.get(outcome_id, 1.0)
            totals[outcome_id]["earned"] += values["earned"] * weight
            totals[outcome_id]["possible"] += values["possible"] * weight

    return dict(totals)


def _find_question_score(student: CEDStudentResult, question_id: str) -> float:
    for question_score in student.question_scores:
        if question_score.question_id == question_id:
            return float(question_score.score or 0)

    return 0.0
