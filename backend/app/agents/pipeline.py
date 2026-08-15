"""Beş uzman ajanın çalışan karşılığı.

Her ajan `docs/architecture/` altındaki kendi şartnamesine sadık kalır ve
şartnamedeki "bu ajan şunu YAPMAZ" sınırına uyar: Belge Anlama analiz etmez,
Ölçme yorum yapmaz, Pedagojik Analiz hesap yapmaz, Raporlama yeniden
hesaplamaz.

Faz 1'de hepsi deterministik: mevcut, test edilmiş mantık sarmalanıyor -
yeniden yazılmıyor. LLM rolleri sonraki fazda bu iskeletin üzerine eklenecek
ve her çağrı `AgentTrace.llm_calls`'a düşecek.
"""

from __future__ import annotations

from typing import Any

from .. import measurement_engine
from ..models import CEDValidationIssue
from ..program_catalog import validate_question_program_context
from .base import AgentContext, AgentIssue, AgentResult
from .ced_builder import build_ced_from_payload, outcome_key_for


class DocumentUnderstandingAgent:
    """Belge Anlama Ajanı - yükü doğrulanmış bir CED nesnesine çevirir.

    Şartname: "Bu ajan analiz, program eşleştirme, pedagojik değerlendirme
    veya raporlama yapmaz." Burada da yalnız normalleştirme + CED üretimi var.

    Doğrulama hataları (eksik puan, aralık dışı değer) `ValueError` olarak
    yukarı gider: bunlar öğretmenin düzeltmesi gereken şeyler, sessizce
    geçilecek uyarılar değil - bugünkü davranış birebir korunuyor.
    """

    name = "belge-anlama"
    description = "Öğretmen onaylı yükü Canonical Education Document'e çevirir."
    # CED yoksa sonraki hiçbir adımın anlamı yok.
    required = True

    def run(self, context: AgentContext) -> AgentResult:
        from ..approved_data_analyzer import _normalize_question, _normalize_student

        raw_questions = context.payload.get("questions") or []
        raw_students = context.payload.get("students") or []

        questions = [
            _normalize_question(item, index) for index, item in enumerate(raw_questions, 1)
        ]
        students = [
            _normalize_student(item, questions, index)
            for index, item in enumerate(raw_students, 1)
        ]
        if not students:
            raise ValueError("Sınava katılan öğrenci bulunmadığı için analiz oluşturulamadı.")

        context.scratch["questions"] = questions
        context.scratch["students"] = students
        context.ced = build_ced_from_payload(
            context.payload.get("exam") or {}, questions, students
        )

        return AgentResult(
            outputs={
                "questionCount": len(questions),
                "studentCount": len(students),
                "cedVersion": context.ced.metadata.ced_version,
            }
        )


class ProgramMappingAgent:
    """Program Eşleştirme Ajanı - soruları resmî öğretim programına bağlar.

    Şartname: "Bu ajan yalnız resmî öğretim programlarını kullanır. Analiz,
    puanlama veya raporlama yapmaz."

    `validate_question_program_context` yanlış ders/sınıf kodlarını reddeder
    (ör. TDE kodları kayıtlı olmayan bir ders-sınıf profilinde kullanılamaz).
    Program çözülemezse bu bir hata DEĞİL: MAHİR 60+ dersi kapsıyor, yalnız
    kayıtlı programların referans materyali var - o derslerde hat çalışmaya
    devam eder, sonraki ajan RAG'i atlar.
    """

    name = "program-eslestirme"
    description = "Her soruyu Türkiye Yüzyılı Maarif Modeli öğrenme çıktısıyla eşleştirir."
    # Program çözülemezse yalnız müfredat temelli teşhis düşer; ölçme sürer.
    required = False

    def run(self, context: AgentContext) -> AgentResult:
        exam = context.payload.get("exam") or {}
        course_name = str(exam.get("courseName") or exam.get("course") or "").strip()
        questions = context.scratch["questions"]

        program = validate_question_program_context(course_name, exam.get("grade"), questions)
        context.scratch["program"] = program

        outcome_keys = {outcome_key_for(question) for question in questions}
        unmapped = [
            question["number"] for question in questions if not question.get("outcomeCode")
        ]

        issues: list[AgentIssue] = []
        if unmapped:
            # Öğrenme çıktısı seçilmemiş sorular soru bazında analiz edilir;
            # bu bir arıza değil, öğretmenin bilinçli seçimi olabilir.
            issues.append(
                AgentIssue(
                    agent=self.name,
                    code="cikti-secilmemis",
                    message=(
                        f"{len(unmapped)} soru için öğrenme çıktısı seçilmediğinden "
                        "bu sorular yalnız soru bazında değerlendirildi."
                    ),
                    severity="info",
                )
            )

        return AgentResult(
            outputs={
                "programId": program.id if program else None,
                "outcomeCount": len(outcome_keys),
                "unmappedQuestionCount": len(unmapped),
            },
            issues=issues,
        )


class MeasurementAgent:
    """Ölçme ve Değerlendirme Ajanı - tüm nicel sonuçları üretir.

    Şartname: "Bu ajan yalnız hesaplama ve ölçme-değerlendirme işlemlerini
    gerçekleştirir. Pedagojik yorum veya raporlama yapmaz."

    Aritmetiğin tamamı `measurement_engine`de: bu hat kurulmadan önce aynı
    hesap hem orada hem `approved_data_analyzer` içinde ayrı ayrı yazılıydı
    ve ikisi sessizce ayrışabilirdi. Artık tek ev var.

    Bu ajan ileride LLM alsa bile SAYILAR modelden gelmeyecek - LLM yalnız
    anomali işaretleyecek. Gösterilen yüzdenin gösterilen puanlardan yeniden
    üretilebilmesi ("Kanıtları Gör") buna bağlı.
    """

    name = "olcme-degerlendirme"
    description = "Soru ve öğrenme çıktısı düzeyinde başarı oranlarını hesaplar."
    # Sayılar raporun kendisi; yoksa gösterilecek bir şey yok.
    required = True

    def run(self, context: AgentContext) -> AgentResult:
        from ..approved_data_analyzer import _normalize_corrected_cells

        questions = context.scratch["questions"]
        students = context.scratch["students"]
        corrected_cells = _normalize_corrected_cells(context.payload.get("correctedCells"))

        question_totals = measurement_engine.calculate_question_totals(context.ced)
        outcome_totals = measurement_engine.calculate_learning_outcome_totals(context.ced)

        question_results = []
        # Öğrenme çıktısı başına kanıt: hangi soru, hangi oranla katkı verdi.
        evidence_questions: dict[str, list[dict[str, Any]]] = {}
        outcome_meta: dict[str, dict[str, Any]] = {}

        for index, question in enumerate(questions):
            ced_question = context.ced.questions[index]
            totals = question_totals[ced_question.id]
            earned, possible = totals["earned"], totals["possible"]
            rate = earned / possible if possible else 0.0
            question_results.append({
                **question,
                "earnedScore": earned,
                "possibleScore": possible,
                "realizationRate": rate,
                "successRate": rate,
            })

            key = outcome_key_for(question)
            evidence_questions.setdefault(key, []).append({
                "number": question["number"],
                "maxScore": question["maxScore"],
                "earnedScore": earned,
                "possibleScore": possible,
                "successRate": rate,
                "correctedCellCount": corrected_cells.get(index, 0),
            })
            # Son soru kazanır - bugünkü davranış birebir aynı.
            outcome_meta[key] = {
                "skill": question["outcomeSkill"],
                "description": question["outcomeDescription"],
                "parentDescription": question["parentOutcomeDescription"],
            }

        context.scratch["questionResults"] = question_results
        context.scratch["outcomeTotals"] = outcome_totals
        context.scratch["evidenceQuestions"] = evidence_questions
        context.scratch["outcomeMeta"] = outcome_meta
        context.scratch["participatingStudentCount"] = len(students)

        return AgentResult(
            outputs={
                "measuredQuestionCount": len(question_results),
                "measuredOutcomeCount": len(outcome_totals),
                "correctedCellTotal": sum(corrected_cells.values()),
            }
        )


class PedagogicalAnalysisAgent:
    """Pedagojik Analiz Ajanı - nicel sonuçları pedagojik olarak yorumlar.

    Şartname: "Bu ajan istatistiksel hesaplama yapmaz ve rapor oluşturmaz."
    Buradaki tek "hesap" eşik karşılaştırması (düzey/karar etiketi); oranlar
    olduğu gibi Ölçme Ajanı'ndan devralınır.

    Müfredat temelli teşhis (RAG) da buraya ait ve şartnamedeki "öğretim
    sürecini destekleyecek pedagojik çıkarım" tam olarak budur. RAG bir
    ARAÇ (tool) olarak kullanılıyor: ajan onu çağırır, arıza hâlinde
    `ragContext` boş kalır ve analiz kesilmez.
    """

    name = "pedagojik-analiz"
    description = "Başarı oranlarını düzey, karar ve müfredat temelli teşhise dönüştürür."
    # Yorumsuz bir rapor hâlâ işe yarar; rapor YOKLUĞU yaramaz.
    required = False

    def run(self, context: AgentContext) -> AgentResult:
        from ..approved_data_analyzer import _attach_rag_context, _category, _decision

        outcome_totals = context.scratch["outcomeTotals"]
        evidence_questions = context.scratch["evidenceQuestions"]
        outcome_meta = context.scratch["outcomeMeta"]
        participating = context.scratch["participatingStudentCount"]

        outcome_results = []
        for outcome_key, totals in outcome_totals.items():
            earned, possible = totals["earned"], totals["possible"]
            rate = earned / possible if possible else 0.0
            theme, separator, code = outcome_key.rpartition(" | ")
            meta = outcome_meta.get(outcome_key, {})
            questions = evidence_questions.get(outcome_key, [])
            outcome_results.append({
                "outcomeCode": code if separator else outcome_key,
                "outcomeTheme": theme if separator else "",
                "outcomeSkill": meta.get("skill", ""),
                "outcomeDescription": meta.get("description", ""),
                "parentOutcomeDescription": meta.get("parentDescription", ""),
                "earnedScore": earned,
                "possibleScore": possible,
                "successRate": rate,
                "realizationRate": rate,
                "developmentLevel": _category(rate),
                "category": _category(rate),
                "decision": _decision(rate),
                "evidence": {
                    "questionNumbers": [item["number"] for item in questions],
                    "questionCount": len(questions),
                    "participatingStudentCount": participating,
                    "earnedScore": earned,
                    "possibleScore": possible,
                    "correctedCellCount": sum(item["correctedCellCount"] for item in questions),
                    "questions": questions,
                },
            })

        _attach_rag_context(outcome_results, context.scratch.get("program"))

        context.scratch["outcomeResults"] = outcome_results
        grounded = sum(1 for item in outcome_results if item.get("ragContext"))
        weak = sum(1 for item in outcome_results if item["successRate"] < 0.70)

        return AgentResult(
            outputs={
                "outcomeCount": len(outcome_results),
                "weakOutcomeCount": weak,
                "curriculumGroundedCount": grounded,
            }
        )


class ReportingAgent:
    """Raporlama Ajanı - öğretmenin gördüğü analiz sözleşmesini kurar.

    Şartname: "Bu ajan yalnız rapor üretir. Ölçme ve değerlendirme analizi,
    pedagojik yorum veya program eşleştirmesi yapmaz." Buradaki tek aritmetik
    sınıf ortalaması ve sınav azami puanı - ikisi de rapor başlığına ait özet
    değerler, öğrenme çıktısı hesabına girmiyor.
    """

    name = "raporlama"
    description = "Ölçme ve pedagojik sonuçları MAHİR analiz raporu sözleşmesine dönüştürür."
    required = True

    def run(self, context: AgentContext) -> AgentResult:
        from ..assessment_profiles import COMPONENT_LABELS, PROFILES

        exam = context.payload.get("exam") or {}
        questions = context.scratch["questions"]
        students = context.scratch["students"]
        component_type = context.scratch["componentType"]
        profile_id = context.scratch["profileId"]

        average = sum(student["calculatedTotal"] for student in students) / len(students)
        exam_max = sum(question["maxScore"] for question in questions)

        context.analysis = {
            "exam": {
                **exam,
                "componentType": component_type,
                "componentLabel": COMPONENT_LABELS[component_type],
                "weightingProfileId": profile_id or None,
                "componentWeight": (
                    PROFILES[profile_id].weights.get(component_type) if profile_id else None
                ),
            },
            "summary": {
                "questionCount": len(questions),
                "studentCount": len(context.payload.get("students") or []),
                "participatingStudentCount": len(students),
                "absentStudentCount": 0,
                "examMaxScore": exam_max,
                "classAverage": round(average, 2),
                "classLearningLevel": average / exam_max if exam_max else 0.0,
                "classSuccessRate": average / exam_max if exam_max else 0.0,
            },
            "questions": context.scratch["questionResults"],
            # `.get`: Pedagojik Analiz isteğe bağlı, düşerse rapor yorumsuz
            # ama geçerli kalır - bu ajanın onun arızasında çökmemesi şart.
            "outcomes": context.scratch.get("outcomeResults", []),
            "students": students,
        }

        return AgentResult(
            outputs={
                "sectionCount": len(context.analysis),
                "classAverage": context.analysis["summary"]["classAverage"],
            }
        )


def issues_to_ced_validation(issues: list[AgentIssue]) -> list[CEDValidationIssue]:
    """Ajan bulgularını CED doğrulama bulgusu biçimine çevirir - iki ayrı
    bulgu listesi tutmamak için."""

    return [
        CEDValidationIssue(code=issue.code, message=issue.message, field=issue.agent, severity=issue.severity)
        for issue in issues
    ]
