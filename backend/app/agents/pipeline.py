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


def _compose_grounded_pedagogical_answer(
    answer: str,
    outcome: dict[str, Any],
    sources: list[dict[str, Any]],
) -> str:
    """LLM'nin seçtiği iki kaynak teriminden güvenli rapor paragrafı kurar.

    Terimler kaynak alıntılarında birebir bulunmuyorsa hiçbir metin üretilmez.
    Başarı oranı ve şiddet modelden değil, ölçme motorunun sonucundan alınır.
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
        return ""
    terms = payload.get("evidenceTerms") if isinstance(payload, dict) else None
    if not isinstance(terms, list) or len(terms) != 2:
        return ""
    terms = [" ".join(str(term).split()).strip(" .,:;\"'") for term in terms]
    if any(not term or len(term) > 90 for term in terms) or terms[0].casefold() == terms[1].casefold():
        return ""

    evidence = " ".join(str(source.get("excerpt") or "") for source in sources if isinstance(source, dict))
    normalized_evidence = _normalize_evidence_text(evidence)
    if any(_normalize_evidence_text(term) not in normalized_evidence for term in terms):
        return ""

    rate = float(outcome.get("successRate") or 0.0)
    percent = round(rate * 100)
    theme = re.sub(r"^\s*\d+\.\s*Tema\s*:\s*", "", str(outcome.get("outcomeTheme") or ""), flags=re.IGNORECASE).strip()
    if not theme:
        return ""
    first = (
        f'"{theme}" temasında {terms[0]} ve {terms[1]} kapsamındaki '
        f"sınıf başarı oranı %{percent} olarak hesaplanmıştır."
    )
    if rate < 0.70:
        severity = "Kritik" if rate < 0.50 else "Orta"
        return (
            f"{first} Eksikliğin şiddeti: {severity}. "
            "Bu performans, seçilen öğrenme çıktısının sonraki süreçleri açısından sarmal risk taşır."
        )
    return f"{first} Bu sonuç, seçilen öğrenme çıktısında güçlü bir performans alanını gösterir."


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
                    "\n\nYANIT SÖZLEŞMESİ: Paragraf yazma. Yalnız geçerli JSON döndür: "
                    "{\"evidenceTerms\":[\"BAĞLAMDA AYNEN GEÇEN TERİM 1\",\"BAĞLAMDA AYNEN GEÇEN TERİM 2\"]}. "
                    "Her terim BAĞLAM içinde kesintisiz ve birebir geçen kısa bir ifade olmalı; sözcük türetme, "
                    "ek değiştirme, özetleme veya iki ayrı parçayı birleştirme. "
                    "Kod, oran, şiddet, neden, yorum, risk, etkinlik, çözüm veya öneri ekleme. Markdown kullanma."
                    if is_weak else
                    "\n\nYANIT SÖZLEŞMESİ: Paragraf yazma. Yalnız geçerli JSON döndür: "
                    "{\"evidenceTerms\":[\"BAĞLAMDA AYNEN GEÇEN TERİM 1\",\"BAĞLAMDA AYNEN GEÇEN TERİM 2\"]}. "
                    "Her terim BAĞLAM içinde kesintisiz ve birebir geçen kısa bir ifade olmalı; sözcük türetme, "
                    "ek değiştirme, özetleme veya iki ayrı parçayı birleştirme. "
                    "Kod, oran, neden, yorum, etkinlik, çözüm veya öneri ekleme. Markdown kullanma."
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


def _answer_matches_outcome_scope(answer: str, outcome: dict[str, Any]) -> bool:
    """Pedagojik LLM yanıtının güvenli yayın sözleşmesine uyduğunu doğrula.

    Model metni burada düzeltilmez. Uzunluk, öneri/etkinlik dili, başarı
    oranından kanıtlanamayacak nedensellik veya kapsam sapması varsa yanıtın
    tamamı elenir. Böylece akıcı görünen fakat kanıtı aşan bir metin rapora
    taşınmaz.
    """

    normalized = " ".join(answer.casefold().split())
    word_count = len(re.findall(r"\b[\wÇĞİÖŞÜçğıöşü]+(?:['’][\wÇĞİÖŞÜçğıöşü]+)?\b", answer))
    is_weak = float(outcome.get("successRate") or 0.0) < 0.70
    if word_count > (70 if is_weak else 60):
        return False

    # Toplu başarı oranı performans düzeyini gösterir; hatanın nedenini,
    # öğrenci niyetini veya öğrenci sayısını kanıtlamaz.
    unsupported_claims = (
        "temel neden", "temel sebep", "nedeni", "sebebi", "kaynaklan",
        "öğrencilerin say", "öğrenci say", "yetersiz bilgi",
    )
    # MAHİR tanı koyabilir fakat öğretmene etkinlik/telafi işi yazamaz.
    action_language = (
        "etkinlik", "aktivite", "alıştırma", "uygulama çalış",
        "telafi", "önerilir", "tavsiye", "yapılmalı", "verilmeli",
        "geliştirilmeli", "desteklenmeli", "gerekmektedir", "gereklidir",
        "ihtiyaç duyul",
    )
    if any(term in normalized for term in unsupported_claims + action_language):
        return False

    allowed_codes = {
        str(value).upper() for value in (outcome.get("outcomeCode"), outcome.get("parentOutcomeCode")) if value
    }
    mentioned_codes = {code.upper() for code in re.findall(r"\bTDE\d+(?:\.\d+)+\b", answer, re.IGNORECASE)}
    if mentioned_codes - allowed_codes:
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
    return not any(term in normalized and term not in selected_text for term in forbidden)


def issues_to_ced_validation(issues: list[AgentIssue]) -> list[CEDValidationIssue]:
    """Ajan bulgularını CED doğrulama bulgusu biçimine çevirir - iki ayrı
    bulgu listesi tutmamak için."""

    return [
        CEDValidationIssue(code=issue.code, message=issue.message, field=issue.agent, severity=issue.severity)
        for issue in issues
    ]
