"""Beş uzman ajanın çalışan karşılığı.

Her ajan `docs/architecture/` altındaki kendi şartnamesine sadık kalır ve
şartnamedeki "bu ajan şunu YAPMAZ" sınırına uyar: Belge Anlama analiz etmez,
Ölçme yorum yapmaz, Pedagojik Analiz hesap yapmaz, Raporlama yeniden
hesaplamaz.

Belge Anlama, Program Eşleştirme ve Raporlama deterministik çalışır. Ölçme
Ajanı yalnız sayı üretmeyen anomali açıklamasını, Pedagojik Analiz Ajanı ise
kaynaklı program yorumunu ortak LLM kuyruğuna ekleyebilir. Nicel sonuçların
hiçbiri LLM tarafından üretilmez veya değiştirilmez; her çağrı ilgili ajanın
`AgentTrace.llm_calls` kaydına düşer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from .. import measurement_engine
from ..models import CEDValidationIssue
from ..program_catalog import validate_question_program_context
from .base import AgentContext, AgentIssue, AgentResult
from .ced_builder import (
    build_ced_from_payload,
    outcome_key_for,
    outcome_key_for_mapping,
    outcome_mappings_for,
)
from .prompts import DIAGNOSIS_SYSTEM_PROMPT, STRENGTH_SYSTEM_PROMPT, build_anomaly_prompt

# Anomali yoksa modelin yazması istenen cümle (bkz. prompts.ANOMALY_SYSTEM_PROMPT
# madde 4). Bu hâlde alan boş bırakılır - rapora "bir şey yok" satırı eklemek
# gürültüden başka bir şey olmaz.
_NO_ANOMALY_TEXT = "Belirgin bir tutarsızlık görülmedi"

# Getirimde çekilecek parça sayısı - backend/app/rag_client.py ile aynı
# gerekçe: parçalar 512 token ve getirim zaten tek temaya kısıtlı.
_DIAGNOSIS_TOP_K = 8

# LLM/RAG bir kaynak bulsa bile yanıt seçilen sınav becerisine saparsa metni
# rapora taşımayız. Hücreyi sessizce boş bırakmak yerine öğretmene nedenini
# açıklarız; bu cümle kaynak iddiası veya pedagojik içerik üretmez.
_RAG_SCOPE_REJECTED_TEXT = (
    "Seçilen sınav türü ve öğrenme çıktısıyla uyumlu, doğrulanmış bir kaynak bağlamı oluşturulamadı."
)

_logger = logging.getLogger(__name__)


class DocumentUnderstandingAgent:
    """Belge Anlama Ajanı - yükü doğrulanmış bir CED nesnesine çevirir.

    Şartname: "Bu ajan analiz, program eşleştirme, pedagojik değerlendirme
    veya raporlama yapmaz." Burada da yalnız normalleştirme + CED üretimi var.

    Doğrulama hataları (eksik puan, aralık dışı değer) `ValueError` olarak
    yukarı gider: bunlar öğretmenin düzeltmesi gereken şeyler, sessizce
    geçilecek uyarılar değil - bugünkü davranış birebir korunuyor.
    """

    name = "belge-anlama"
    label = "Belge Anlama"
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
    label = "Program Eşleştirme"
    description = "Her soruyu Türkiye Yüzyılı Maarif Modeli öğrenme çıktısıyla eşleştirir."
    # Program çözülemezse yalnız müfredat temelli teşhis düşer; ölçme sürer.
    required = False

    def run(self, context: AgentContext) -> AgentResult:
        exam = context.payload.get("exam") or {}
        course_name = str(exam.get("courseName") or exam.get("course") or "").strip()
        questions = context.scratch["questions"]

        program = validate_question_program_context(course_name, exam.get("grade"), questions)
        context.scratch["program"] = program

        outcome_keys = {
            outcome_key_for_mapping(mapping, question.get("number"))
            for question in questions
            for mapping in outcome_mappings_for(question)
        }
        unmapped = [
            question["number"]
            for question in questions
            if not any(mapping.get("outcomeCode") for mapping in outcome_mappings_for(question))
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
    label = "Ölçme ve Değerlendirme"
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

            for mapping in outcome_mappings_for(question):
                key = outcome_key_for_mapping(mapping, question.get("number"))
                weight = float(mapping.get("weight") or 1.0)
                evidence_questions.setdefault(key, []).append({
                    "number": question["number"],
                    "maxScore": question["maxScore"],
                    "earnedScore": earned * weight,
                    "possibleScore": possible * weight,
                    "successRate": rate,
                    "weight": weight,
                    "correctedCellCount": corrected_cells.get(index, 0),
                })
                # Son soru kazanır - tekli eşleştirmenin mevcut davranışı korunur.
                outcome_meta[key] = {
                    "code": mapping.get("outcomeCode") or "",
                    "theme": mapping.get("outcomeTheme") or "",
                    "skill": mapping.get("outcomeSkill") or "",
                    "description": mapping.get("outcomeDescription") or "",
                    "parentCode": mapping.get("parentOutcomeCode") or "",
                    "parentDescription": mapping.get("parentOutcomeDescription") or "",
                }

        context.scratch["questionResults"] = question_results
        context.scratch["outcomeTotals"] = outcome_totals
        context.scratch["evidenceQuestions"] = evidence_questions
        context.scratch["outcomeMeta"] = outcome_meta
        context.scratch["participatingStudentCount"] = len(students)

        # Anomali rolü: LLM burada ÇAĞRILMAZ, yalnız prompt kuyruğa yazılır.
        # Tüm ajanların prompt'ları tek istekte gidiyor (bkz. orchestrator
        # `_flush_llm_queue`) - bu ajanın LLM alması analize ek bir HTTP turu
        # eklemiyor.
        # Anomali istemi öğrenme çıktısı kanıtlarından kurulmaz: aynı soru
        # birden fazla çıktıya bağlıysa o listede yinelenir ve model bunu
        # sahte bir "aynı oran" örüntüsü sanabilir. Her fiziksel soru burada
        # tam bir kez bulunur.
        anomaly_rows = [
            {
                **row,
                "correctedCellCount": corrected_cells.get(index, 0),
            }
            for index, row in enumerate(question_results)
        ]
        prompt = build_anomaly_prompt(anomaly_rows)
        if prompt:
            # Sahiplik AÇIK yazılıyor: orkestratör LLM kaydını bu alana bakarak
            # doğru ajanın izine düşürüyor. Prompt ADINDAN çıkarmak kırılgan
            # olurdu - bu ajanınki ajan adıyla aynı, Pedagojik'inkiler
            # "pedagoji/..." biçiminde ve ajan adı "pedagojik-analiz".
            prompt["agent"] = self.name
            exam = context.payload.get("exam") or {}
            prompt["user"] = (
                f"SINAV TÜRÜ: {exam.get('examType') or context.scratch.get('componentType')}\n"
                f"SINAV SIRASI: {exam.get('examSequence') or 'Belirtilmedi'}\n"
                + str(prompt.get("user") or "")
            )
            context.enqueue_prompt(prompt)

        return AgentResult(
            outputs={
                "measuredQuestionCount": len(question_results),
                "measuredOutcomeCount": len(outcome_totals),
                "correctedCellTotal": sum(corrected_cells.values()),
                "anomalyCheckQueued": bool(prompt),
            }
        )

    def apply_llm(self, context: AgentContext) -> AgentResult:
        """Anomali bulgularını bağlama yazar - hiçbir SAYIYA dokunmaz.

        Sonuç gelmemişse (LLM yapılandırılmamış, tur başarısız ya da soru
        sayısı üçten az) alan boş kalır; rapor bugünküyle aynı görünür.
        """

        result = context.llm_result(self.name)
        if not result:
            context.scratch["anomalies"] = ""
            return AgentResult(outputs={"anomalyFindings": 0})

        finding = _sanitize_anomaly_finding(
            str(result.get("answer") or ""),
            {int(item["number"]) for item in context.scratch.get("questionResults", [])},
        )
        if finding.startswith(_NO_ANOMALY_TEXT):
            finding = ""
        context.scratch["anomalies"] = finding
        return AgentResult(
            outputs={
                "anomalyFindings": finding.count("-") if finding else 0,
                "llmStrippedSentences": result.get("strippedSentences", 0),
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
    label = "Pedagojik Analiz"
    description = "Başarı oranlarını düzey, karar ve müfredat temelli teşhise dönüştürür."
    # Yorumsuz bir rapor hâlâ işe yarar; rapor YOKLUĞU yaramaz.
    required = False

    def run(self, context: AgentContext) -> AgentResult:
        from ..approved_data_analyzer import _category, _decision

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
                "componentType": context.scratch["componentType"],
                "componentLabel": str((context.payload.get("exam") or {}).get("examType") or ""),
                "outcomeCode": meta.get("code") or (code if separator else outcome_key),
                "outcomeTheme": meta.get("theme") or (theme if separator else ""),
                "outcomeSkill": meta.get("skill", ""),
                "outcomeDescription": meta.get("description", ""),
                "parentOutcomeCode": meta.get("parentCode", ""),
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

        context.scratch["outcomeResults"] = outcome_results

        # Müfredat temelli teşhis: LLM burada ÇAĞRILMAZ, zayıf her çıktı için
        # getirimli bir prompt kuyruğa yazılır. Kuyruk Ölçme Ajanı'nın anomali
        # prompt'uyla birlikte TEK istekte gidiyor - ajan başına ayrı HTTP turu
        # atsaydık her LLM'li ajan analize ~3 sn eklerdi.
        from ..approved_data_analyzer import _RAG_WEAK_THRESHOLD

        queued = _enqueue_diagnosis_prompts(
            context, outcome_results, context.scratch.get("program")
        )
        context.scratch["diagnosisTargets"] = queued
        weak = sum(1 for item in outcome_results if item["successRate"] < _RAG_WEAK_THRESHOLD)

        return AgentResult(
            outputs={
                "outcomeCount": len(outcome_results),
                "weakOutcomeCount": weak,
                "diagnosisQueued": len(queued),
            }
        )

    def apply_llm(self, context: AgentContext) -> AgentResult:
        """Teşhis yanıtlarını `ragContext`e, dayandığı kaynakları `ragSources`a yazar.

        Sonrası-işleme bugünküyle birebir aynı: reddetme ön eki kırpılır,
        kaynak yoksa çıktı boş bırakılır, charter süzgeci zaten `agents/llm.py`
        içinde uygulanmıştır. Sonuç gelmemişse (LLM yapılandırılmamış, tur
        başarısız) `ragContext` boş kalır - RAG arızası öğretmenin analizini
        asla kesmez.

        `ragSources` Faz 4'ün açıklanabilirlik çizgisini müfredat teşhisine
        taşıyor: D bölümündeki "Kanıtları Gör" bir oranın hangi PUANLARDAN
        geldiğini söylüyordu; bu da bir teşhisin hangi BELGE SAYFASINDAN
        geldiğini söylüyor. Veri zaten uçtan geliyordu (`sources`) ve yalnız
        "boş mu" diye bakılıp atılıyordu.
        """

        from ..approved_data_analyzer import _RAG_NO_ANSWER_TEXT

        grounded = 0
        stripped = 0
        for name, outcome in context.scratch.get("diagnosisTargets", {}).items():
            code = str(outcome.get("outcomeCode") or "?")
            result = context.llm_result(name)
            if not result:
                _logger.info("RAG atlandı: cikti=%s sebep=sonuc-yok", code)
                continue
            if not result.get("sources"):
                # Kaynak yoksa getirim hiç isabet vermemiştir - filtrelerden
                # (program/sınıf/tema) biri tutmamış demektir.
                _logger.info("RAG atlandı: cikti=%s sebep=kaynak-yok", code)
                continue
            answer = str(result.get("answer") or "").strip()
            # startswith + kırpma, tam eşleşme değil: model doğru bağlamla
            # beslendiğinde bile cevabı sık sık bu cümleyle başlatıp ardından
            # gerçek teşhisle devam ediyor (gerçek dizin karşısında ölçüldü).
            if answer.startswith(_RAG_NO_ANSWER_TEXT):
                # Model kaynak yetersizliğini bildirdiyse devamına eklediği
                # metin güvenilir kabul edilemez. Ret cümlesini kırpıp kalan
                # olası halüsinasyonu rapora taşımak yerine yanıtın tamamı
                # elenir.
                answer = ""
            if not answer:
                _logger.info("RAG atlandı: cikti=%s sebep=model-reddetti", code)
                continue
            stripped += int(result.get("strippedSentences") or 0)
            raw_sources = result.get("sources") or []
            # Güncel RAG uç noktası kaynak parçalarının kısa alıntılarını da
            # döndürür. Bu durumda model nihai raporu yazmaz; yalnız kaynakta
            # birebir doğrulanabilen iki kanıt terimi seçer ve paragrafı MAHİR
            # belirlenimci olarak kurar. Eski/aletsiz uçların alıntısız kaynak
            # biçimi geriye uyumluluk için mevcut sözleşmeyle denetlenir.
            if any(str(source.get("excerpt") or "").strip() for source in raw_sources if isinstance(source, dict)):
                answer = _compose_grounded_pedagogical_answer(answer, outcome, raw_sources)
            if not answer or not _answer_matches_outcome_scope(answer, outcome):
                _logger.info("RAG atlandı: cikti=%s sebep=yanit-sozlesmesi", code)
                outcome["ragContext"] = _RAG_SCOPE_REJECTED_TEXT
                outcome["ragSources"] = []
                continue
            merged_sources = _merge_rag_sources(raw_sources)
            if not merged_sources:
                _logger.info("RAG atlandı: cikti=%s sebep=gecersiz-kaynak", code)
                continue
            outcome["ragContext"] = answer
            outcome["ragSources"] = merged_sources
            grounded += 1
            _logger.info(
                "RAG dolduruldu: cikti=%s sebep=basarili kaynak=%d",
                code,
                len(outcome["ragSources"]),
            )

        return AgentResult(
            outputs={"curriculumGroundedCount": grounded, "llmStrippedSentences": stripped}
        )


class ReportingAgent:
    """Raporlama Ajanı - öğretmenin gördüğü analiz sözleşmesini kurar.

    Şartname: "Bu ajan yalnız rapor üretir. Ölçme ve değerlendirme analizi,
    pedagojik yorum veya program eşleştirmesi yapmaz." Buradaki tek aritmetik
    sınıf ortalaması ve sınav azami puanı - ikisi de rapor başlığına ait özet
    değerler, öğrenme çıktısı hesabına girmiyor.
    """

    name = "raporlama"
    label = "Raporlama"
    description = "Ölçme ve pedagojik sonuçları MAHİR analiz raporu sözleşmesine dönüştürür."
    required = True
    # LLM turundan SONRA koşar: rapor, ajanların LLM sonuçlarını da içermeli ve
    # bu, önceden üretilmiş sözlüklerin yerinde değiştirilmesi tesadüfüne
    # bağlı kalmamalı (bkz. orchestrator.run_pipeline üç aşama).
    after_llm = True

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
                # Ölçme Ajanı'nın anomali bulgusu; hiçbir sayıyı etkilemez,
                # bulgu yoksa boş string kalır.
                "anomalies": context.scratch.get("anomalies", ""),
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


def _merge_rag_sources(sources: Any) -> list[dict[str, Any]]:
    """Getirim isabetlerini belge başına tek satıra indirger.

    Uçtan sekize kadar isabet dönüyor ve çoğu AYNI belgenin komşu
    sayfalarından; hepsini olduğu gibi göstermek raporu kaynak listesiyle
    doldururdu. Belge başına birleştirip sayfaları tekilleştiriyoruz -
    öğretmenin ihtiyacı "hangi belgenin hangi sayfası", kaç parça çekildiği
    değil.

    Sayfa numaraları ORİJİNAL PDF'e göre (bkz. rag_service.py
    `_extract_original_pages`): müfredat PDF'i sınıf/tema aralıklarına
    bölünerek indeksleniyor ve o düzeltme yapılmasa numaralar her dilimde
    1'den başlardı.
    """

    if not isinstance(sources, list):
        return []

    pages_by_document: dict[str, set[int]] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        name = str(source.get("documentName") or "").strip()
        if not name:
            continue
        pages = pages_by_document.setdefault(name, set())
        for page in source.get("pages") or []:
            if isinstance(page, int) and page > 0:
                pages.add(page)

    return [
        {"documentName": name, "pages": sorted(pages)}
        for name, pages in pages_by_document.items()
    ]


def _sanitize_anomaly_finding(answer: str, valid_question_numbers: set[int]) -> str:
    """Yalnız mevcut sorulara bağlı, en çok üç anomali maddesini kabul et.

    Anomali LLM'i sayısal sonuç üretmez; yine de model var olmayan bir soru
    numarası veya serbest bir genel hüküm yazabilir. Rapor yalnız biçimi doğru
    ve sınavda gerçekten bulunan soru numarasına bağlı gözlemleri taşır.
    """

    cleaned = answer.strip()
    if cleaned.startswith(_NO_ANOMALY_TEXT):
        return ""

    accepted: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        match = re.fullmatch(r"-\s*Soru\s+(\d+)\s*:\s*(.+)", line, re.IGNORECASE)
        if not match:
            continue
        if int(match.group(1)) not in valid_question_numbers:
            continue
        accepted.append(f"- Soru {int(match.group(1))}: {match.group(2).strip()}")
        if len(accepted) == 3:
            break
    return "\n".join(accepted)


# Model artık tema/yüzde/şiddeti hiç yazmıyor (canlı ölçümde yer tutucu
# talimatını izlemediği, gerçek değerleri kendi uydurduğu görüldü - küçük bir
# modelin "burada literal {TEMA} yaz" gibi alışılmadık bir talimatı güvenilir
# biçimde izlemesi beklenemez). Bunun yerine MAHIR, modelin yalnız NİTEL
# içerik ürettiği paragrafı DEĞİŞKEN bir açılış/kapanış kalıbıyla sarar - tema
# adı, yüzde ve şiddet etiketi HİÇBİR ZAMAN modelden gelmez.
_OPENING_TEMPLATES = (
    '"{theme}" temasında sınıfın başarı oranı %{percent} olarak hesaplanmıştır.',
    '"{theme}" temasındaki başarı oranı %{percent} olarak hesaplanmıştır.',
    'Sınıfın "{theme}" temasındaki başarı oranı %{percent} olarak hesaplanmıştır.',
    '"{theme}" temasında ölçülen başarı oranı %{percent} olarak hesaplanmıştır.',
)
_WEAK_CLOSING_TEMPLATES = (
    "Eksikliğin şiddeti: {severity}. Bu performans, seçilen öğrenme çıktısının sonraki süreçleri açısından sarmal risk taşır.",
    "Eksikliğin şiddeti: {severity}. Bu durum, ileri düzey kazanımlar için sarmal bir risk oluşturmaktadır.",
    "Eksikliğin şiddeti: {severity}. Bu eksiklik, sonraki öğrenme süreçlerine sarmal biçimde yansıyabilir.",
)
_STRONG_CLOSING_TEMPLATES = (
    "Bu sonuç, seçilen öğrenme çıktısında güçlü bir performans alanını gösterir.",
    "Bu veriler, seçilen öğrenme çıktısında sağlam bir kazanım düzeyine işaret eder.",
    "Sınıf, seçilen öğrenme çıktısında bu alanda belirgin bir başarı sergilemektedir.",
)


def _pick_template(templates: tuple[str, ...], *seed_parts: str) -> str:
    """`seed_parts`e göre belirlenimci bir kalıp seçer - aynı girdi her zaman
    aynı kalıbı almalı, aksi hâlde bir raporu iki kez üretmek farklı metin
    verirdi. `hash()` kasıtlı olarak kullanılmıyor: Python'da string hash'i
    çalışmalar arası rastgele tohumlanır, `md5` deterministiktir."""

    digest = hashlib.md5("|".join(seed_parts).encode("utf-8")).hexdigest()
    return templates[int(digest, 16) % len(templates)]


# Grounding ölçümünde SAYILMAYAN sözcükler: her pedagojik cümlede geçtikleri
# için kaynakla örtüşmeleri hiçbir şey kanıtlamaz. Önek olarak eşleştirilir
# (Türkçe çekim ekleri yüzünden), bu yüzden liste kökleri taşır.
_GENERIC_WORD_PREFIXES = (
    # Her pedagojik cümlede geçen alan sözcükleri.
    "öğrenc", "öğretm", "metin", "metni", "metne", "beceri", "başar", "oran",
    "düzey", "durum", "süreç", "sınıf", "kazanım", "öğrenme", "eksik", "performans",
    "ilgili", "şekil", "bakım", "göster", "belirt", "bulun", "yapıl",
    "gerçekleş", "önemli", "temas", "tema", "konus", "konu", "veril", "edilm",
    "değerlend", "çalışma", "yeterl", "gelişim", "sonuç", "alan",
    # Dört harf ve üzeri işlev sözcükleri: uzunluk süzgecinden geçerler ama
    # kaynakla örtüşmeleri hiçbir şey kanıtlamaz.
    "gibi", "için", "olarak", "olan", "olup", "daha", "ancak", "fakat", "veya",
    "kadar", "sonra", "önce", "üzere", "ayrıca", "yani", "birlikte", "böyle",
    "şöyle", "bunun", "bunlar", "onlar", "hangi", "diğer", "tüm",
)

# Grounding eşiği: teşhis metni ile kaynak arasında paylaşılması gereken
# AYIRT EDİCİ sözcük sayısı. Üç, bir cümlenin tesadüfen değil gerçekten
# müfredat metninden beslendiğini gösterecek kadar; iyi teşhisleri elemeyecek
# kadar da düşük (ölçülen gerçek örneklerde 7+ örtüşme görüldü).
_MIN_GROUNDED_WORDS = 3

_WORD_PATTERN = re.compile(r"[\wÇĞİÖŞÜçğıöşü]+", re.UNICODE)


def _content_words(text: str) -> list[str]:
    """Metnin grounding ölçümünde sayılan sözcüklerini döndürür.

    Dört karakterden kısa sözcükler (bağlaç/edat) ve `_GENERIC_WORD_PREFIXES`
    ile başlayanlar elenir - geriye yalnız o kazanıma özgü olabilecek
    içerik sözcükleri kalır.
    """

    words = _WORD_PATTERN.findall(_normalize_evidence_text(text))
    return [
        word for word in words
        if len(word) >= 4
        and not word.isdigit()
        and not any(word.startswith(prefix) for prefix in _GENERIC_WORD_PREFIXES)
    ]


def _shares_root(left: str, right: str) -> bool:
    """İki sözcüğün aynı kökten geldiğini gevşek biçimde kabul eder.

    Türkçe eklemeli olduğundan tam eşleşme aranmaz: biri diğerinin öneki
    ise (ör. "unsurları" / "unsurlarını", "çözümleyebilme" /
    "çözümleyebilmek") aynı kök sayılır. En az dört karakter şartı, kısa
    tesadüfi örtüşmeleri engeller.
    """

    return min(len(left), len(right)) >= 4 and (left.startswith(right) or right.startswith(left))


def _grounded_word_overlap(diagnosis: str, evidence: str) -> list[str]:
    """Teşhis metninin kaynakla paylaştığı ayırt edici sözcükleri döndürür.

    Kanıt garantisinin ÖLÇÜLDÜĞÜ yer burası. Önceki tasarımda model kendi
    kullandığı terimleri `groundedTerms` alanında BEYAN ediyor, MAHİR de o
    beyanı doğruluyordu; canlı ölçümde model beyanı defalarca yanlış
    doldurdu (kendi cümlesinden aldığı, hatta olumsuz çekimli ifadeler
    yazdı - müfredatta böyle geçmesi imkânsız) ve aslında kaynağa dayalı
    olan iyi teşhisler bu yüzden elendi. Artık beyan istenmiyor: MAHİR
    doğrudan metnin kendisini ölçüyor, yani garanti modelin uyumuna hiç
    bağlı değil.
    """

    evidence_words = _content_words(evidence)
    matched: list[str] = []
    for word in _content_words(diagnosis):
        if any(_shares_root(word, evidence_word) for evidence_word in evidence_words):
            if not any(_shares_root(word, seen) for seen in matched):
                matched.append(word)
    return matched


def _note_reason(reasons: list[str] | None, code: str) -> None:
    """Ret sebebini (varsa) çağıranın listesine düşürür.

    `backend/run_diagnosis_test.py` bunu kullanarak "neden reddedildi"yi
    doğrudan terminale yazar - aksi hâlde her başarısız üretim, ham çıktıyı
    elle inceleyip hangi kuralın tetiklendiğini tahmin etmeyi gerektiriyor.
    Üretim yolunda çağıranlar `None` geçer ve hiçbir maliyeti olmaz.
    """

    if reasons is not None:
        reasons.append(code)


def _compose_grounded_pedagogical_answer(
    answer: str,
    outcome: dict[str, Any],
    sources: list[dict[str, Any]],
    reasons: list[str] | None = None,
) -> str:
    """Modelin yazdığı nitel teşhis paragrafını, MAHİR'in ürettiği tema/oran/
    şiddet cümleleriyle sarıp nihai rapor metnini kurar.

    Model yalnız NİTEL teşhisi yazar: tema adı, başarı oranı ve şiddet
    etiketi HİÇBİR ZAMAN modelden gelmez - MAHIR tarafından, kazanıma göre
    belirlenimci seçilen bir kalıptan üretilir.

    Kanıt garantisi `_grounded_word_overlap` ile ÖLÇÜLÜR: teşhis metninin
    kendisi, getirilen müfredat alıntılarıyla en az `_MIN_GROUNDED_WORDS`
    ayırt edici sözcük paylaşmak zorunda. Modelden "hangi terimleri
    kullandım" beyanı istenmez - o tasarım canlı ölçümde defalarca yanlış
    dolduruldu ve iyi teşhisleri eledi.

    `reasons` verilirse her ret dalı oraya bir sebep kodu yazar (bkz.
    `_note_reason`); üretim yolu bunu kullanmaz.
    """

    candidate = answer.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        # Küçük modeller, "yalnız JSON" talimatına rağmen geçerli nesnenin
        # arkasına açıklama ekleyebiliyor. İlk JSON nesnesi güvenle ayrıştırılır;
        # devamındaki serbest metin rapora hiçbir koşulda taşınmaz.
        payload, _unused_tail = json.JSONDecoder().raw_decode(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        _note_reason(reasons, "json-ayristirilamadi (model geçerli JSON döndürmedi)")
        return ""
    if not isinstance(payload, dict):
        _note_reason(reasons, "json-nesne-degil")
        return ""

    diagnosis = " ".join(str(payload.get("diagnosis") or "").split()).strip()
    if not diagnosis:
        _note_reason(reasons, "diagnosis-alani-bos")
        return ""
    # Canlı ölçümde model eski bir yer tutucu tasarımının kalıntısı olarak
    # "{TEMA}" gibi süslü parantezli metin yazmayı denedi (bkz. `prompts.py`
    # DIAGNOSIS_SYSTEM_PROMPT'un tarihçesi). Doğal Türkçe düzyazıda süslü
    # parantezin hiçbir meşru kullanımı yok - varlığı öğretmene giden metinde
    # çirkin bir kalıntı bırakır, bu yüzden tüm yanıt reddedilir.
    if "{" in diagnosis or "}" in diagnosis:
        _note_reason(reasons, "susulu-parantez-kalintisi (model yer tutucu yazdı)")
        return ""
    # Promptun açık yasağına rağmen canlı ölçümde model tekrar tekrar
    # nedensellik iddiası kurdu (ör. "...nedeniyle %3 başarı oranı elde
    # ediyorlar") - tüm yanıtı atmak yerine yalnız o cümleyi kırp, geri
    # kalan (genelde iyi) içeriği koru.
    diagnosis, stripped_scope_sentences = _strip_scope_violations(diagnosis)
    if not diagnosis:
        _note_reason(reasons, "kapsam-kirpmasi-bosaltti (tüm cümleler nedensellik/öneri dili içeriyordu)")
        return ""
    if stripped_scope_sentences:
        _note_reason(reasons, f"bilgi: {stripped_scope_sentences} cümle nedensellik/öneri dili nedeniyle kırpıldı")

    # KANIT GARANTİSİ: teşhis metninin kendisi kaynakla yeterince örtüşüyor mu.
    evidence = " ".join(str(source.get("excerpt") or "") for source in sources if isinstance(source, dict))
    grounded_words = _grounded_word_overlap(diagnosis, evidence)
    if len(grounded_words) < _MIN_GROUNDED_WORDS:
        _note_reason(
            reasons,
            f"kaynak-ortusmesi-yetersiz ({len(grounded_words)}/{_MIN_GROUNDED_WORDS} "
            f"ayırt edici sözcük; bulunan: {grounded_words})",
        )
        return ""
    _note_reason(reasons, f"bilgi: kaynakla örtüşen ayırt edici sözcükler: {grounded_words}")

    theme = re.sub(r"^\s*\d+\.\s*Tema\s*:\s*", "", str(outcome.get("outcomeTheme") or ""), flags=re.IGNORECASE).strip()
    if not theme:
        _note_reason(reasons, "tema-cozulemedi")
        return ""

    rate = float(outcome.get("successRate") or 0.0)
    percent = round(rate * 100)
    code = str(outcome.get("outcomeCode") or "")
    opening = _pick_template(_OPENING_TEMPLATES, code, theme).format(theme=theme, percent=percent)

    if rate < 0.70:
        severity = "Kritik" if rate < 0.50 else "Orta"
        closing = _pick_template(_WEAK_CLOSING_TEMPLATES, code, theme, "weak").format(severity=severity)
    else:
        closing = _pick_template(_STRONG_CLOSING_TEMPLATES, code, theme, "strong")

    return f"{opening} {diagnosis} {closing}"


def _normalize_evidence_text(value: str) -> str:
    """PDF satır sonu ve hece tirelerini kaynak-terim karşılaştırması için düzelt."""

    value = re.sub(r"\s*-\s*", "", value.casefold())
    return " ".join(value.split())


def _enqueue_diagnosis_prompts(
    context: AgentContext, outcome_results: list[dict[str, Any]], program: Any
) -> dict[str, dict[str, Any]]:
    """Seçilmiş her öğrenme çıktısı için getirimli pedagojik prompt kuyruğa yazar.

    Dönen sözlük: prompt adı -> ilgili çıktı sözlüğü. `apply_llm` yanıtları bu
    eşlemeyle sahibine bağlıyor; ada göre eşleştirme, sıraya göre eşleştirmenin
    aksine partiye giren/girmeyen öğe olduğunda da güvenli.

    Program çözülemediyse hiç prompt üretilmez: MAHİR 60+ dersi kapsıyor ama
    yalnız kayıtlı programların indekslenmiş referans materyali var - kayıtsız
    bir derste getirim garantili biçimde boş dönerdi.
    """

    from ..approved_data_analyzer import (
        _RAG_WEAK_THRESHOLD,
        _build_rag_question,
        _build_rag_retrieval_query,
        _normalize_theme_for_rag,
    )

    # Alanların varlığı HER ZAMAN öngörülebilir olmalı - hangi yoldan geçilirse
    # geçilsin (program yok, getirim boş, LLM kapalı) tarayıcı aynı şekli görür.
    for outcome in outcome_results:
        outcome["ragContext"] = ""
        outcome["ragSources"] = []

    if program is None:
        _logger.info("RAG atlandı: sebep=program-yok")
        return {}

    targets: dict[str, dict[str, Any]] = {}
    for outcome in outcome_results:
        code = str(outcome.get("outcomeCode") or "?")
        is_weak = float(outcome.get("successRate") or 0.0) < _RAG_WEAK_THRESHOLD
        question = _build_rag_question(outcome) if is_weak else (
            f"{' - '.join(str(part) for part in (outcome.get('outcomeTheme'), outcome.get('outcomeCode'), outcome.get('outcomeDescription'), outcome.get('outcomeSkill')) if part)} "
            f"öğrenme çıktısında başarı oranı %{round(float(outcome.get('successRate') or 0.0) * 100)}. "
            "BAĞLAM'daki somut süreç bileşenlerine dayanarak güçlü alanı ve başarının sürdürülme odağını açıkla."
        )
        if not question:
            _logger.info("RAG atlandı: cikti=%s sebep=soru-bos", code)
            continue
        theme = _normalize_theme_for_rag(str(outcome.get("outcomeTheme") or ""))
        if not theme:
            # Tema çözülemezse sınıf-geneli aramaya DÜŞÜLMEZ: aynı çıktı kodu
            # her temada farklı bir kazanıma karşılık geliyor, yanlış temadan
            # "kaynaklı" görünen bir teşhis hiç teşhis vermemekten kötüdür.
            _logger.info("RAG atlandı: cikti=%s sebep=tema-cozulemedi", code)
            continue

        name = f"pedagoji/{outcome.get('outcomeTheme')}|{code}"
        context.enqueue_prompt({
            "name": name,
            # LLM kaydının hangi ajanın izine düşeceği (bkz. orchestrator
            # `_flush_llm_queue`). Ağa çıkmaz: `llm.run_agent_prompts` gövdeyi
            # beyaz listeyle kuruyor.
            "agent": PedagogicalAnalysisAgent.name,
            "system": DIAGNOSIS_SYSTEM_PROMPT if is_weak else STRENGTH_SYSTEM_PROMPT,
            "user": (
                f"SINAV TÜRÜ: {(context.payload.get('exam') or {}).get('examType') or context.scratch.get('componentType')}\n"
                f"SINAV SIRASI: {(context.payload.get('exam') or {}).get('examSequence') or 'Belirtilmedi'}\n"
                f"SEÇİLMİŞ ÖĞRENME ÇIKTISI: {outcome.get('outcomeCode')} — {outcome.get('outcomeDescription')}\n"
                + (
                    f"ÜST ÖĞRENME ÇIKTISI: {outcome.get('parentOutcomeCode')} — {outcome.get('parentOutcomeDescription')}\n"
                    if outcome.get("parentOutcomeCode")
                    and outcome.get("parentOutcomeCode") != outcome.get("outcomeCode")
                    else ""
                )
                + f"SORU: {question}\n\nYalnızca bu sınav türü, seçilmiş öğrenme çıktısı ve yukarıdaki BAĞLAM'a dayanarak Türkçe yanıtla."
                + (
                    "\n\nYANIT SÖZLEŞMESİ: Yalnız geçerli JSON döndür: "
                    "{\"diagnosis\":\"tema/yüzde/şiddet İÇERMEYEN, yalnız nitel teşhis paragrafı\"}. "
                    "Tema adı, yüzde sayısı veya şiddet kelimesi yazma - bunlar ayrıca ekleniyor. "
                    "Eksikliği orana \"nedeniyle\", \"bu yüzden\", \"dolayısıyla\" gibi bağlaçlarla "
                    "BAĞLAMA. BAĞLAM'daki müfredat sözcüklerini kendi sözcüklerinle değiştirmeden "
                    "kullan. Markdown kullanma."
                    if is_weak else
                    "\n\nYANIT SÖZLEŞMESİ: Yalnız geçerli JSON döndür: "
                    "{\"diagnosis\":\"tema/yüzde İÇERMEYEN, yalnız nitel teşhis paragrafı\"}. Tema "
                    "adı veya yüzde sayısı yazma - bunlar ayrıca ekleniyor. Anlattığın başarıyı orana "
                    "\"nedeniyle\", \"bu yüzden\", \"dolayısıyla\" gibi bağlaçlarla BAĞLAMA. "
                    "BAĞLAM'daki müfredat sözcüklerini kendi sözcüklerinle değiştirmeden kullan. "
                    "Markdown kullanma."
                )
            ),
            "retrieval": {
                "programId": program.id,
                "grade": program.grade,
                "theme": theme,
                # Getirimde gömülen metin, üretim talimatından KASITLI ayrı:
                # başarı oranı ve "teşhis et" emri müfredat düzyazısında
                # karşılığı olmayan, sorgu vektörünü uzaklaştıran gürültü.
                "query": _build_rag_retrieval_query(outcome),
                "topK": _DIAGNOSIS_TOP_K,
            },
        })
        targets[name] = outcome

    return targets


# Toplu başarı oranı performans düzeyini gösterir; hatanın nedenini,
# öğrenci niyetini veya öğrenci sayısını kanıtlamaz.
_UNSUPPORTED_CLAIM_PATTERNS = (
    "temel neden", "temel sebep", "nedeni", "sebebi", "kaynaklan",
    "öğrencilerin say", "öğrenci say", "yetersiz bilgi",
)
# MAHİR tanı koyabilir fakat öğretmene etkinlik/telafi işi yazamaz.
_ACTION_LANGUAGE_PATTERNS = (
    "etkinlik", "aktivite", "alıştırma", "uygulama çalış",
    "telafi", "önerilir", "tavsiye", "yapılmalı", "verilmeli",
    "geliştirilmeli", "desteklenmeli", "gerekmektedir", "gereklidir",
    "ihtiyaç duyul",
)


def _strip_scope_violations(text: str) -> tuple[str, int]:
    """Nedensellik iddiası veya öneri/etkinlik dili taşıyan cümleleri
    paragraftan çıkarır; geri kalanı korur.

    Aynı `charter_guard.strip_recommendation_sentences` tekniği: canlı
    ölçümde model, prompttaki açık yasağa (bkz. DIAGNOSIS_SYSTEM_PROMPT
    madde 3) rağmen "...nedeniyle %3 başarı oranı elde ediyorlar" gibi
    nedensellik iddiası kurmaya devam etti - küçük bir modelin bir OLUMSUZ
    talimatı güvenilir biçimde izlemesi beklenemez. `_answer_matches_
    outcome_scope`nin ikili ret/kabulüne bırakılsaydı, aksi hâlde iyi olan
    tüm teşhis TEK kötü cümle yüzünden kaybedilirdi; bunun yerine yalnız o
    cümle atılır."""

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [
        sentence for sentence in sentences
        if not any(term in sentence.casefold() for term in _UNSUPPORTED_CLAIM_PATTERNS + _ACTION_LANGUAGE_PATTERNS)
    ]
    return " ".join(kept).strip(), len(sentences) - len(kept)


def _answer_matches_outcome_scope(
    answer: str, outcome: dict[str, Any], reasons: list[str] | None = None
) -> bool:
    """Pedagojik LLM yanıtının güvenli yayın sözleşmesine uyduğunu doğrula.

    Model metni burada düzeltilmez (bkz. `_strip_scope_violations` - o adım
    burada değil, `_compose_grounded_pedagogical_answer` içinde, sarmadan
    ÖNCE çalışır). Bu fonksiyon yalnız SON bir güvenlik ağı: uzunluk, kalan
    öneri/etkinlik dili, nedensellik iddiası veya kapsam sapması varsa
    yanıtın tamamı elenir.

    `reasons` verilirse ret sebebi oraya yazılır (bkz. `_note_reason`).
    """

    normalized = " ".join(answer.casefold().split())
    word_count = len(re.findall(r"\b[\wÇĞİÖŞÜçğıöşü]+(?:['’][\wÇĞİÖŞÜçğıöşü]+)?\b", answer))
    is_weak = float(outcome.get("successRate") or 0.0) < 0.70
    # Modelin kendi paragrafı (en çok 45/35 kelime, bkz. DIAGNOSIS_SYSTEM_
    # PROMPT/STRENGTH_SYSTEM_PROMPT) artık MAHİR'in ürettiği açılış+kapanış
    # cümleleriyle sarılıyor (bkz. `_compose_grounded_pedagogical_answer`) -
    # sınır o toplamı karşılayacak kadar geniş tutulur.
    limit = 90 if is_weak else 70
    if word_count > limit:
        _note_reason(reasons, f"uzunluk-asimi ({word_count} kelime, sınır {limit})")
        return False

    hits = [term for term in _UNSUPPORTED_CLAIM_PATTERNS + _ACTION_LANGUAGE_PATTERNS if term in normalized]
    if hits:
        _note_reason(reasons, f"nedensellik-veya-eylem-dili: {hits}")
        return False

    allowed_codes = {
        str(value).upper() for value in (outcome.get("outcomeCode"), outcome.get("parentOutcomeCode")) if value
    }
    mentioned_codes = {code.upper() for code in re.findall(r"\bTDE\d+(?:\.\d+)+\b", answer, re.IGNORECASE)}
    leaked_codes = mentioned_codes - allowed_codes
    if leaked_codes:
        _note_reason(reasons, f"kod-sizintisi: {sorted(leaked_codes)} (izinli: {sorted(allowed_codes)})")
        return False
    component = str(outcome.get("componentType") or "").lower()
    forbidden = {
        "listening": (
            "okuma beceri", "okuma strateji", "yazma beceri", "konuşma beceri",
            "mülakat yap", "mülakatta konuş", "söyleşi yap", "sözlü anlatım",
        ),
        "speaking": ("okuma beceri", "yazma beceri", "dinleme/izleme beceri", "dinleme beceri"),
    }.get(component, ())
    selected_text = " ".join(str(outcome.get(key) or "") for key in ("outcomeDescription", "parentOutcomeDescription")).casefold()
    drifted = [term for term in forbidden if term in normalized and term not in selected_text]
    if drifted:
        _note_reason(reasons, f"capraz-beceri-sizintisi: {drifted} (bileşen: {component})")
        return False
    return True


def issues_to_ced_validation(issues: list[AgentIssue]) -> list[CEDValidationIssue]:
    """Ajan bulgularını CED doğrulama bulgusu biçimine çevirir - iki ayrı
    bulgu listesi tutmamak için."""

    return [
        CEDValidationIssue(code=issue.code, message=issue.message, field=issue.agent, severity=issue.severity)
        for issue in issues
    ]
