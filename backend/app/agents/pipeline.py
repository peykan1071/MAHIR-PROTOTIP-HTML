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
from ..charter_guard import strip_recommendation_sentences
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

# Getirimde MODELE gönderilecek NİHAİ parça sayısı - bu, `rag_service.py`nin
# Qdrant'tan çektiği HAM aday sayısı DEĞİL (bkz. orada `_MMR_CANDIDATE_
# MULTIPLIER`/`_MMR_MIN_CANDIDATE_POOL`, o çok daha geniş bir havuz çekip
# `_mmr_select` ile bu sayıya iner). 2026-08-22 önce 8 -> 16 -> 12 arası
# gidip geldi (bkz. git geçmişi): aynı kazanımın birbirine çok benzeyen
# "kazanım tanımlama" satırları düz "en yüksek skorlu top_k" seçiminde tek
# başına tüm slotları doldurup temanın asıl zengin içeriğini dışarıda
# bırakıyordu, ama `top_k`yi büyütmek BAŞKA bir sorguda kalabalık/tekrarlı
# bağlamın modelin dikkatini dağıtmasına yol açtı (ölçüldü: 5/5 -> 0/5).
# Kök sorun bir SAYI ayarıyla çözülemeyen yapısal bir tekrar sorunuydu; asıl
# çözüm `rag_service.py`ye eklenen MMR (Maximal Marginal Relevance)
# yeniden-sıralaması - o artık alaka VE çeşitliliği birlikte gözetiyor, bu
# yüzden nihai sayı tekrar makul/küçük bir değere (8) çekilebildi.
_DIAGNOSIS_TOP_K = 8

# `_compose_grounded_pedagogical_answer`in cümle kalıp havuzları. Model
# BAĞLAM'dan doğrulanmış BİR ya da İKİ terim seçiyor, cümlenin TAMAMINI
# MAHİR kuruyor (kanıt garantisi bundan geliyor) - ama tek bir sabit kalıp
# her satırı birebir aynı iskelete sokup raporu robotik/tek düze gösteriyordu.
# Her varyant aynı zorunlu parçaları taşımak ZORUNDA (tırnaklı tema adı,
# terim(ler), "%<oran> olarak hesaplanmıştır" - `RagContextAttachmentTests`
# bunu doğruluyor); yalnız cümlenin çevresi değişiyor. `{terms}` tek bir
# terimde "X", ikide "X ve Y" olarak önceden birleştirilip veriliyor - ayrı
# `{term1}`/`{term2}` yer tutucuları TEK terimli durumda boş kalırdı.
# Seçim `_pick_template` ile GİRDİYE göre belirlenimci (aynı kazanım aynı
# yeniden üretimde hep aynı kalıbı alır - test edilebilirlik/kararlılık
# için) ama farklı kazanımlar farklı kalıp alır, bu yüzden bir raporun
# tamamı tek tip görünmez.
#
# 2026-08-22 (4. sürüm): TAM OLARAK İKİ zorunluluğu kaldırıldı - dar
# kapsamlı bazı kazanımlarda BAĞLAM'da gerçekten TEK güçlü/somut aday
# bulunuyor, model ikinciyi uydurmak yerine tamamen `not_found` diyip
# öğretmene hiçbir yorum göstermiyordu. Artık BİR terim de kabul ediliyor;
# doğrulama kuralı (`_term_is_grounded`) ve kanıt garantisi DEĞİŞMEDİ.
_OPENING_TEMPLATES = (
    (
        '"{theme}" temasında {terms} kapsamındaki sınıf başarı oranı '
        "%{percent} olarak hesaplanmıştır."
    ),
    (
        '"{theme}" temasındaki {terms} bileşeninde sınıf başarı '
        "oranı %{percent} olarak hesaplanmıştır."
    ),
    (
        'Sınıfın "{theme}" temasında {terms} kapsamındaki başarı oranı '
        "%{percent} olarak hesaplanmıştır."
    ),
    (
        '"{theme}" temasında ölçülen {terms} performansına göre sınıf '
        "başarı oranı %{percent} olarak hesaplanmıştır."
    ),
    (
        '"{theme}" temasına ait {terms} göstergesinde sınıf başarı '
        "oranı %{percent} olarak hesaplanmıştır."
    ),
    (
        'Elde edilen verilere göre "{theme}" temasında {terms} '
        "açısından sınıf başarı oranı %{percent} olarak hesaplanmıştır."
    ),
    (
        '"{theme}" temasında {terms} temel alınarak sınıf '
        "başarı oranı %{percent} olarak hesaplanmıştır."
    ),
    (
        'Değerlendirme sonuçlarına göre "{theme}" temasında {terms} '
        "bakımından sınıf başarı oranı %{percent} olarak hesaplanmıştır."
    ),
)
_WEAK_CLOSING_TEMPLATES = (
    (
        "Eksikliğin şiddeti: {severity}. Bu performans, seçilen öğrenme "
        "çıktısının sonraki süreçleri açısından sarmal risk taşır."
    ),
    (
        "Eksikliğin şiddeti: {severity}. Bu durum, ileri düzey kazanımlar için "
        "sarmal bir risk oluşturmaktadır."
    ),
    (
        "Eksikliğin şiddeti: {severity}. Bu eksiklik, sonraki öğrenme "
        "süreçlerine sarmal biçimde yansıyabilir."
    ),
    (
        "Eksikliğin şiddeti: {severity}. Bu düzey, ilerleyen kazanımların "
        "sağlıklı biçimde oluşması açısından risk taşımaktadır."
    ),
    (
        "Eksikliğin şiddeti: {severity}. Bu tablo, sonraki öğrenme "
        "basamaklarına sarmal biçimde etki edebilir."
    ),
    (
        "Eksikliğin şiddeti: {severity}. Bu sonuç, ileriki kazanımların "
        "temelini oluşturan bir alanda risk işaret etmektedir."
    ),
)
_STRONG_CLOSING_TEMPLATES = (
    "Bu sonuç, seçilen öğrenme çıktısında güçlü bir performans alanını gösterir.",
    "Bu veriler, seçilen öğrenme çıktısında sağlam bir kazanım düzeyine işaret eder.",
    "Sınıf, seçilen öğrenme çıktısında bu alanda belirgin bir başarı sergilemektedir.",
    "Elde edilen veriler, seçilen öğrenme çıktısında yüksek bir yeterlik düzeyine karşılık gelmektedir.",
    "Bu bulgular, seçilen öğrenme çıktısında sınıfın büyük ölçüde başarılı olduğunu göstermektedir.",
    "Seçilen öğrenme çıktısına ilişkin veriler, güçlü bir performans düzeyini yansıtmaktadır.",
)


def _pick_template(templates: tuple[str, ...], *seed_parts: str) -> str:
    """`seed_parts`e göre belirlenimci bir kalıp seçer (rastgele değil - aynı
    girdi her zaman aynı kalıbı almalı, aksi hâlde bir raporu iki kez
    üretmek farklı metin verirdi)."""

    digest = hashlib.md5("|".join(seed_parts).encode("utf-8")).hexdigest()
    return templates[int(digest, 16) % len(templates)]


# LLM/RAG bir kaynak bulsa bile yanıt seçilen sınav becerisine saparsa metni
# rapora taşımayız. Hücreyi sessizce boş bırakmak yerine öğretmene nedenini
# açıklarız; bu cümle kaynak iddiası veya pedagojik içerik üretmez.
_RAG_SCOPE_REJECTED_TEXT = (
    "Seçilen sınav türü ve öğrenme çıktısıyla uyumlu, doğrulanmış bir kaynak bağlamı oluşturulamadı."
)

# 2026-08-23: doğrulama neden başarısız olduğunu tanılamak için sebep kodları.
# `_compose_grounded_pedagogical_answer`/`_answer_matches_outcome_scope`
# çağrılırken opsiyonel `reasons` listesine yazılır, `apply_llm` bunu hem
# loglar hem `AgentResult.outputs["ragRejectReasons"]`a sayar (bkz. o
# fonksiyonun docstring'i). Amaç: `_RAG_SCOPE_REJECTED_TEXT`in GERÇEKTE hangi
# sebeple tetiklendiğini ölçebilmek - önceden yalnızca tek bir genel
# "yanit-sozlesmesi" logu vardı, hangi kontrolün tetiklendiği ayırt
# edilemiyordu. GİZLİLİK: yalnızca bu KOD loglanır, model cevabı/gerekçe
# metni/kaynak alıntısı asla (bkz. `agents/llm.py::trace_entry`deki aynı
# disiplin).
_REASON_STATUS_NOT_SUCCESS = "durum-basarisiz"
_REASON_EVIDENCE_COUNT = "kanit-sayisi"
_REASON_EVIDENCE_ITEM_SHAPE = "kanit-ogesi-bicimsiz"
_REASON_TERM_SHAPE = "terim-bicimsiz"
_REASON_RATIONALE_STRIPPED = "gerekce-charter-bosaltti"
_REASON_DUPLICATE_TERMS = "yinelenen-terim"
_REASON_TERM_UNGROUNDED = "terim-baglamda-yok"
_REASON_THEME_MISSING = "tema-eksik"
_REASON_TOO_LONG = "uzunluk-asimi"
_REASON_CAUSAL_OVERCLAIM = "nedensellik-iddiasi"
_REASON_ACTION_LANGUAGE = "eylem-dili"
_REASON_CODE_LEAK = "kod-sizintisi"
_REASON_CROSS_SKILL_LEAK = "capraz-beceri-sizintisi"
_REASON_UNKNOWN = "bilinmeyen"


def _note_reason(reasons: list[str] | None, code: str) -> None:
    if reasons is not None:
        reasons.append(code)


# `PedagogicalAnalysisAgent._evaluate_diagnosis_result`in "retry" durumu için:
# ilk denemede doğrulanamayan çıktılar, başarısızlığın SEBEBİNE göre seçilen
# bir düzeltici notla AYNI getirime bir kez daha sorulur. Önceden tek bir
# sabit ipucu vardı (yalnızca terim-ayarı sorunundan bahsediyordu) - gerçek
# sebep başka bir şeyse (ör. gerekçe charter filtresiyle boşaldıysa) o ipucu
# alakasızdı ve retry aynı sebeple tekrar başarısız olma ihtimali yüksekti.
_GROUNDING_RETRY_HINT = (
    "\n\nNOT: Önceki denemende seçtiğin en az bir terim BAĞLAM'da BİREBİR "
    "geçmiyordu (eş anlamlı ya da çekim eki değiştirilmiş bir ifade "
    "kullanmıştın) veya yanıtın seçilen öğrenme çıktısının kapsamı dışına "
    "çıkmıştı. Bu kez YALNIZCA BAĞLAM'da harfi harfine geçen kelime veya "
    "kelime öbeklerini seç; hiçbir kelimeyi değiştirme."
)

_RATIONALE_RETRY_HINT = (
    "\n\nNOT: Önceki denemende gerekçe (gapRationale/strengthRationale) "
    "zorunluluk kipiyle yazılmıştı (ör. '...gerekir', '...gereklidir', "
    "'...yapılmalıdır', '...önerilir') ve bu yüzden tamamen elendi. Bu kez "
    "gerekçeyi DOĞRUDAN GÖZLEMSEL bir cümleyle yaz - ne yapılması "
    "GEREKTİĞİNİ değil, öğrencide NE EKSİK/NE GÜÇLÜ olduğunu anlat. Örnek "
    "kalıplar: '...net biçimde kurulamamaktadır.', '...sınırlı düzeyde "
    "kalmaktadır.', '...başarıyla uygulanmaktadır.'"
)

_SCOPE_RETRY_HINT = (
    "\n\nNOT: Önceki denemen ya çok uzundu, ya kanıtlanamayacak bir "
    "nedensellik/öğrenci sayısı iddiası içeriyordu, ya öneri/etkinlik dili "
    "kullanmıştı ya da izin verilmeyen bir kazanım kodu/beceri alanı "
    "sızdırmıştı. Bu kez YALNIZCA seçilen öğrenme çıktısının kapsamında "
    "kal, kısa ve tanı-odaklı yaz; hiçbir öneri, etkinlik veya nedensellik "
    "iddiası ekleme."
)

# Sebep kodu -> retry ipucu. Eşlenmeyen sebepler (ör. kanıt sayısı/biçim
# sorunları - bunlar zaten JSON şemasının kendisiyle ilgili, prompttaki
# ÇIKTI FORMATI zaten bunu anlatıyor) varsayılan (terim-ayarı) ipucuna düşer.
_RETRY_HINTS_BY_REASON: dict[str, str] = {
    _REASON_TERM_UNGROUNDED: _GROUNDING_RETRY_HINT,
    _REASON_RATIONALE_STRIPPED: _RATIONALE_RETRY_HINT,
    _REASON_TOO_LONG: _SCOPE_RETRY_HINT,
    _REASON_CAUSAL_OVERCLAIM: _SCOPE_RETRY_HINT,
    _REASON_ACTION_LANGUAGE: _SCOPE_RETRY_HINT,
    _REASON_CODE_LEAK: _SCOPE_RETRY_HINT,
    _REASON_CROSS_SKILL_LEAK: _SCOPE_RETRY_HINT,
}

_logger = logging.getLogger(__name__)


def _grounding_retry_hint_for(reason: str | None) -> str:
    """Sebep koduna göre düzeltici ipucu seçer; eşlenmeyen/`None` sebep
    varsayılan (terim-ayarı) ipucuna düşer - bkz. `_RETRY_HINTS_BY_REASON`."""

    if reason is None:
        return _GROUNDING_RETRY_HINT
    return _RETRY_HINTS_BY_REASON.get(reason, _GROUNDING_RETRY_HINT)


def _build_grounding_retry_prompt(original: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    """Doğrulama başarısız olduğunda AYNI getirimle (aynı BAĞLAM) tek seferlik
    yeniden deneme prompt'u kurar - `system`/`retrieval` aynı kalır, yalnız
    `user`e, başarısızlığın SEBEBİNE göre seçilen düzeltici bir not eklenir
    (bkz. `_grounding_retry_hint_for`). Aynı `retrieval` kasıtlı: getirim
    zaten deterministik, sorun modelin BAĞLAM'ı yanlış kullanmasıydı, hangi
    BAĞLAM'ın getirildiği değil.
    """

    retry = dict(original)
    retry["user"] = str(original.get("user") or "") + _grounding_retry_hint_for(reason)
    return retry


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
        return AgentResult(outputs={"anomalyFindings": finding.count("-") if finding else 0})


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

    def _evaluate_diagnosis_result(
        self, code: str, result: dict[str, Any] | None, outcome: dict[str, Any]
    ) -> tuple[str, int, str | None]:
        """Tek bir teşhis denemesini değerlendirir; başarılıysa `outcome`u yazar.

        Döner: `(durum, kırpılan_cümle_sayısı, sebep)`. `durum` üçünden biri:
        - `"grounded"`: rapora yazıldı.
        - `"retry"`: model bir cevap ÜRETTİ ama doğrulanamadı (BAĞLAM'da
          birebir geçmeyen terim, kapsam dışı yanıt vb.) - yeniden denemeye
          değer, çünkü üretim stokastik ve aynı soru ikinci seferde farklı
          (ve doğrulanabilir) bir terim seçebilir.
        - `"skip"`: kaynak/cevap hiç yok ya da model dürüstçe "bu kazanıma
          BAĞLAM'da içerik yok" dedi - yeniden denemek sonucu değiştirmez.

        `sebep` yalnızca `"retry"` durumunda dolu (bkz. `_REASON_*`
        sabitleri) - `apply_llm` bunu hem loglamak hem retry ipucunu
        seçmek (`_grounding_retry_hint_for`) için kullanır.
        """

        from ..approved_data_analyzer import _RAG_NO_ANSWER_TEXT

        if not result:
            _logger.info("RAG atlandı: cikti=%s sebep=sonuc-yok", code)
            return "skip", 0, None
        if not result.get("sources"):
            # Kaynak yoksa getirim hiç isabet vermemiştir - filtrelerden
            # (program/sınıf/tema) biri tutmamış demektir.
            _logger.info("RAG atlandı: cikti=%s sebep=kaynak-yok", code)
            return "skip", 0, None
        answer = str(result.get("answer") or "").strip()
        # startswith + kırpma, tam eşleşme değil: model doğru bağlamla
        # beslendiğinde bile cevabı sık sık bu cümleyle başlatıp ardından
        # gerçek teşhisle devam ediyor (gerçek dizin karşısında ölçüldü).
        # `_is_not_found_response`, 2026-08-22 (2. sürüm) şemasının
        # `{"status":"not_found"}` biçimini AYNI şekilde ele alır - ikisi
        # de "BAĞLAM'da içerik yok" demenin dürüst bir yolu, sözleşme
        # ihlali değil; ikisi de görünür ret mesajı OLMADAN sessizce
        # atlanmalı (aksi hâlde meşru "bu konuda içerik yok" durumları
        # öğretmene sanki model hata yapmış gibi görünürdü).
        if answer.startswith(_RAG_NO_ANSWER_TEXT) or _is_not_found_response(answer):
            # Model kaynak yetersizliğini bildirdiyse devamına eklediği
            # metin güvenilir kabul edilemez. Ret cümlesini kırpıp kalan
            # olası halüsinasyonu rapora taşımak yerine yanıtın tamamı
            # elenir.
            answer = ""
        if not answer:
            _logger.info("RAG atlandı: cikti=%s sebep=model-reddetti", code)
            return "skip", 0, None
        stripped = int(result.get("strippedSentences") or 0)
        raw_sources = result.get("sources") or []
        reasons: list[str] = []
        # Güncel RAG uç noktası kaynak parçalarının kısa alıntılarını da
        # döndürür. Bu durumda model nihai raporu yazmaz; yalnız kaynakta
        # birebir doğrulanabilen iki kanıt terimi seçer ve paragrafı MAHİR
        # belirlenimci olarak kurar. Eski/aletsiz uçların alıntısız kaynak
        # biçimi geriye uyumluluk için mevcut sözleşmeyle denetlenir.
        if any(str(source.get("excerpt") or "").strip() for source in raw_sources if isinstance(source, dict)):
            answer = _compose_grounded_pedagogical_answer(answer, outcome, raw_sources, reasons)
        if not answer or not _answer_matches_outcome_scope(answer, outcome, reasons):
            # `reasons`a en fazla BİR kod yazılır: `_compose_grounded_
            # pedagogical_answer` reddederse `answer` boşalır ve `or`
            # `_answer_matches_outcome_scope`i hiç ÇAĞIRMAZ (kısa devre) -
            # iki fonksiyon aynı anda kendi sebebini eklemez.
            reason = reasons[0] if reasons else _REASON_UNKNOWN
            _logger.info("RAG doğrulanamadı: cikti=%s sebep=yanit-sozlesmesi ayrinti=%s", code, reason)
            return "retry", stripped, reason
        merged_sources = _merge_rag_sources(raw_sources)
        if not merged_sources:
            _logger.info("RAG atlandı: cikti=%s sebep=gecersiz-kaynak", code)
            return "skip", stripped, None
        outcome["ragContext"] = answer
        outcome["ragSources"] = merged_sources
        _logger.info(
            "RAG dolduruldu: cikti=%s sebep=basarili kaynak=%d", code, len(outcome["ragSources"])
        )
        return "grounded", stripped, None

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

        2026-08-22 (3. sürüm): canlı ölçümde ilk üretimde ~%40 doğrulanamama
        oranı görüldü (dominant sebep: model BAĞLAM'daki terimi birebir
        değil, eş anlamlısıyla seçiyor). Üretim stokastik olduğundan aynı
        soruyu bir kez daha sormak makul bir düzeltme - bu yüzden `"retry"`
        durumundaki çıktılar TEK bir ek tur için toplanıp aynı getirimle
        (aynı BAĞLAM) yeniden sorulur. Toleransı gevşetmek yerine bu yol
        seçildi çünkü doğrulama kuralının kendisine DOKUNMUYOR - charter
        garantisini zayıflatmadan modele ikinci bir şans veriyor.

        2026-08-23: retry artık SEBEBE göre farklı bir düzeltici ipucu
        kullanıyor (bkz. `_grounding_retry_hint_for`) - önceden tek sabit
        ipucu vardı ve gerçek sebep başkaysa (ör. gerekçe charter
        filtresiyle boşaldıysa) alakasızdı. `outputs["ragRejectReasons"]`
        (sebep→sayı) da eklendi - `_RAG_SCOPE_REJECTED_TEXT`in ne sıklıkta
        hangi sebeple tetiklendiğini ölçmek için (loglama YAPILANDIRILMIŞSA
        - bkz. `run_file_receiver.py::_configure_logging`).
        """

        targets = context.scratch.get("diagnosisTargets", {})
        prompts_by_name = {
            str(item.get("name")): item
            for item in context.llm_queue
            if item.get("agent") == self.name
        }

        grounded = 0
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

        return AgentResult(outputs={"curriculumGroundedCount": grounded})


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
    # Müfredat metninin kendi kalıp ifadeleri: her kazanım satırında geçtikleri
    # için ("... temasında ELE ALINAN metinlerden HAREKETLE ...") kaynakla
    # örtüşmeleri hiçbir şey kanıtlamaz.
    "alınan", "hareketle", "ilişkin", "yönelik", "üzerinde", "belirlenen",
)

# Grounding eşiği: teşhis metni ile kaynak arasında paylaşılması gereken
# AYIRT EDİCİ sözcük sayısı.
#
# 2026-08-24: 3 -> 2. Eşik ilk olarak tema adının VE müfredat kalıp
# sözcüklerinin ("ele alınan", "hareketle") de sayıldığı bir ölçümle
# belirlenmişti. O "bedava" eşleşmeler elendikten sonra 3, fiilen çok daha
# yüksek bir bar hâline geldi ve canlı ölçümde iyi bir teşhis 2/3 ile
# reddedildi (bulunan sözcükler: "kural", "içerik" - ikisi de TDE3.2/TDE3.3
# kazanım metninden gelen gerçek müfredat terimleri). Ölçüm sıkılaşınca eşik
# de yeniden ayarlanmalıydı; iki AYIRT EDİCİ terim, tesadüf olmadığını
# gösterecek kadar güçlü bir kanıt.
_MIN_GROUNDED_WORDS = 2

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


# Türkçe ünsüz yumuşaması: sözcük ünlüyle başlayan bir ek aldığında sondaki
# sert ünsüz yumuşar (içeriK -> içeriĞi, kitaP -> kitaBı, amaÇ -> amaCı,
# kanaT -> kanaDı). Düz önek karşılaştırması bunu KAÇIRIYORDU - canlı ölçümde
# "içerik" (teşhis) ile "içeriği" (müfredat) eşleşmedi ve kanıt sayısı bir
# eksik çıktı. Her iki tarafı da aynı kanonik biçime çevirerek karşılaştırmak
# sorunu kökten çözer; dönüşüm simetrik olduğu için yanlış eşleşme üretmez.
_CONSONANT_ALTERNATIONS = str.maketrans({"ğ": "k", "b": "p", "c": "ç", "d": "t"})


# İki sözcüğün ortak önekinin, "aynı kök" sayılması için en az kaç karakter
# olması gerektiği - bkz. `_shares_root`. Canlı ölçüm: "oluşturmayı" (teşhis)
# ile "oluşturabilme" (kaynak) aynı "oluştur" kökünden ama biri diğerinin TAM
# öneki DEĞİL - ikisi de kökten (7 harf) sonra farklı eklerle ayrışıyor
# ("-mayı" / "-abilme"). Salt "biri diğerinin öneki mi" testi bunu kaçırdı ve
# gerçekten kaynaklı bir teşhis 0 kanıt sözcüğüyle reddedildi. 5, "içerik" /
# "inceleme" gibi yalnız ilk harfi ortak sözcükleri (ortak önek 1) hâlâ
# eleyecek kadar sıkı, "oluştur" gibi 7 harflik gerçek kökleri hâlâ
# yakalayacak kadar gevşek.
_MIN_SHARED_STEM_LENGTH = 5


def _shares_root(left: str, right: str) -> bool:
    """İki sözcüğün aynı kökten geldiğini gevşek biçimde kabul eder.

    Türkçe eklemeli olduğundan tam eşleşme aranmaz. İki ayrı durum aynı kök
    sayılır: (1) biri diğerinin öneki (ör. "unsurları" / "unsurlarını",
    "çözümleyebilme" / "çözümleyebilmek"), (2) ikisi de en az
    `_MIN_SHARED_STEM_LENGTH` karakterlik ortak bir kökten sonra FARKLI
    eklerle ayrışıyor (ör. "oluşturmayı" / "oluşturabilme" - "oluştur"
    kökünden sonra biri "-mayı", biri "-abilme" alıyor; ikisi de birbirinin
    TAM öneki değil ama aynı fiilin çekimleri). Ünsüz yumuşaması da hesaba
    katılır (bkz. `_CONSONANT_ALTERNATIONS`). En az dört karakter şartı, kısa
    tesadüfi örtüşmeleri engeller.
    """

    if min(len(left), len(right)) < 4:
        return False
    left_key = left.translate(_CONSONANT_ALTERNATIONS)
    right_key = right.translate(_CONSONANT_ALTERNATIONS)
    if left_key.startswith(right_key) or right_key.startswith(left_key):
        return True
    common_prefix_length = 0
    for left_char, right_char in zip(left_key, right_key):
        if left_char != right_char:
            break
        common_prefix_length += 1
    return common_prefix_length >= _MIN_SHARED_STEM_LENGTH


def _grounded_word_overlap(diagnosis: str, evidence: str, theme: str = "") -> list[str]:
    """Teşhis metninin kaynakla paylaştığı ayırt edici sözcükleri döndürür.

    Kanıt garantisinin ÖLÇÜLDÜĞÜ yer burası. Önceki tasarımda model kendi
    kullandığı terimleri `groundedTerms` alanında BEYAN ediyor, MAHİR de o
    beyanı doğruluyordu; canlı ölçümde model beyanı defalarca yanlış
    doldurdu (kendi cümlesinden aldığı, hatta olumsuz çekimli ifadeler
    yazdı - müfredatta böyle geçmesi imkânsız) ve aslında kaynağa dayalı
    olan iyi teşhisler bu yüzden elendi. Artık beyan istenmiyor: MAHİR
    doğrudan metnin kendisini ölçüyor, yani garanti modelin uyumuna hiç
    bağlı değil.

    `theme` verilirse tema adının sözcükleri sayılmaz: getirim zaten TEMA
    filtresiyle yapıldığından tema adı GETİRİLEN HER parçada geçer, yani
    modelin onu tekrarlaması hiçbir şey kanıtlamaz (canlı ölçümde kanıt
    listesi "sözün"/"inceliği" ile şişiyordu).
    """

    theme_words = _content_words(theme)
    evidence_words = _content_words(evidence)
    matched: list[str] = []
    for word in _content_words(diagnosis):
        if any(_shares_root(word, theme_word) for theme_word in theme_words):
            continue
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
    # Model prompttaki yasağa rağmen kendi yazdığı yüzdeyi tekrar edebiliyor
    # (canlı ölçümde görüldü) - MAHİR oranı zaten kendi açılış cümlesinde
    # söylediğinden bu ya gereksiz tekrar ya da modelin uydurduğu FARKLI bir
    # sayı olur; tüm yanıtı atmak yerine yalnız o cümleyi kırp, geri kalan
    # (genelde iyi) içeriği koru.
    diagnosis, stripped_scope_sentences = _strip_scope_violations(diagnosis, reasons)
    if not diagnosis:
        _note_reason(reasons, "kapsam-kirpmasi-bosaltti (tüm cümleler oran tekrarı içeriyordu)")
        return ""
    if stripped_scope_sentences:
        _note_reason(reasons, f"bilgi: {stripped_scope_sentences} cümle oran tekrarı nedeniyle kırpıldı")

    theme = re.sub(r"^\s*\d+\.\s*Tema\s*:\s*", "", str(outcome.get("outcomeTheme") or ""), flags=re.IGNORECASE).strip()
    if not theme:
        _note_reason(reasons, "tema-cozulemedi")
        return ""

    # Model, prompttaki açık yasağa rağmen paragrafa tema adını yazabiliyor
    # (canlı ölçümde görüldü). MAHİR tema adını zaten açılış cümlesinde
    # söylediğinden bu, öğretmene tema adını iki kez okutuyordu - baştaki
    # "<tema> temasında ..." girişini at.
    diagnosis = _drop_theme_lead_in(diagnosis, theme)

    # KANIT GARANTİSİ: teşhis metninin kendisi kaynakla yeterince örtüşüyor mu.
    # Tema adı sayılmaz - getirim zaten tema filtresiyle yapıldığı için her
    # parçada geçer ve tekrarlanması hiçbir şey kanıtlamaz.
    evidence = " ".join(str(source.get("excerpt") or "") for source in sources if isinstance(source, dict))
    grounded_words = _grounded_word_overlap(diagnosis, evidence, theme)
    if len(grounded_words) < _MIN_GROUNDED_WORDS:
        _note_reason(
            reasons,
            f"kaynak-ortusmesi-yetersiz ({len(grounded_words)}/{_MIN_GROUNDED_WORDS} "
            f"ayırt edici sözcük; bulunan: {grounded_words})",
        )
        return ""
    _note_reason(reasons, f"bilgi: kaynakla örtüşen ayırt edici sözcükler: {grounded_words}")

    rate = float(outcome.get("successRate") or 0.0)
    percent = round(rate * 100)
    code = str(outcome.get("outcomeCode") or "")
    opening = _pick_template(_OPENING_TEMPLATES, code, theme).format(theme=theme, percent=percent)

    if rate < 0.70:
        severity = "Kritik" if rate < 0.50 else "Orta"
        closing = _pick_template(_WEAK_CLOSING_TEMPLATES, code, theme, "weak").format(severity=severity)
    else:
        closing = _pick_template(_STRONG_CLOSING_TEMPLATES, code, theme, "strong")

    return f"{opening} {_as_standalone_sentence(diagnosis)} {closing}"


def _as_standalone_sentence(text: str) -> str:
    """Model paragrafını, MAHİR'in cümleleri arasına konmaya hazır hâle getirir.

    İki canlı kusuru kapatır: (1) bir giriş öbeği atıldıktan sonra metin küçük
    harfle başlayabiliyor, (2) model cümlesini noktalama olmadan bitirince
    kapanış cümlesi ona yapışıyordu ("...zorlanıyor Eksikliğin şiddeti:").
    """

    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


# Türkçe'ye özgü küçültme: `str.casefold()` "İ"yi "i" + BİRLEŞİK NOKTA
# (U+0307) çiftine çeviriyor ve o nokta hiçbir sözcük sınıfına girmediği için
# "İnceliği" -> "i" + "nceliği" diye İKİYE bölünüyordu (canlı ölçümde kanıt
# listesinde "nceliği" gibi kırık bir token olarak görüldü). Çeviri tablosu
# casefold'dan ÖNCE uygulanmalı.
_TURKISH_LOWER_MAP = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})


def _normalize_evidence_text(value: str) -> str:
    """PDF satır sonu ve hece tirelerini kaynak-terim karşılaştırması için düzelt."""

    value = re.sub(r"\s*-\s*", "", value.translate(_TURKISH_LOWER_MAP).casefold())
    return " ".join(value.split())


# 2026-08-22: bir terim BAĞLAM'da geçiyor mu kontrolü, önceden birebir
# alt-dize (`in` operatörü) ile yapılıyordu. Bu ÇOK katıydı: model doğru,
# BAĞLAM'daki gerçek bir ifadeyi seçse bile Türkçe'nin çekim ekleri
# ("görsellerden"/"görsellerinden", "ön bilgileri ile"/"ön bilgilerle",
# "metni"/"metinleri") yüzünden karakter karakter eşleşmiyordu - gerçek
# sorgularla ölçüldü, bu halüsinasyon değil, yalnızca yazım farkıydı.
# Bunun yerine terim SÖZCÜK SÖZCÜK BAĞLAM'daki en yakın sözcükle
# karşılaştırılır (`difflib.SequenceMatcher`, eşik aşağıda). 3 karakter ve
# altı sözcükler ("ile", "ve", "bir"...) işlevsel kabul edilip her zaman
# geçer. Eşik (0,80) dört gerçek uydurma örneğiyle (model SORU'nun kendi
# cümlesini veya kendi "BAĞLAM" etiketini içeriğe sızdırdığında - ör.
# "sarmal risk", "%30 başarı oranı", "bağlamanın kontrol listesi",
# "kısaltma") kalibre edildi; bkz. `tests/test_agent_llm_round.py`daki
# kalibrasyon testleri - dördü de bu eşikte doğru reddediliyor.
_TERM_WORD_SIMILARITY_THRESHOLD = 0.80
_WORD_PATTERN = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+")


def _word_is_grounded(word: str, evidence_words: list[str]) -> bool:
    """Tek bir sözcüğün BAĞLAM'da (çekim eki farklı olsa bile) karşılığı var mı."""

    if len(word) <= 3:
        return True
    return any(
        difflib.SequenceMatcher(None, word, evidence_word).ratio() >= _TERM_WORD_SIMILARITY_THRESHOLD
        for evidence_word in evidence_words
    )


def _term_is_grounded(term: str, evidence: str) -> bool:
    """`term`in BAĞLAM'da (`evidence`) - Türkçe çekim eki farklılıklarına
    tolerans tanıyarak - gerçekten geçtiğini doğrular. Bkz. yukarıdaki
    modül notu."""

    evidence_words = _WORD_PATTERN.findall(_normalize_evidence_text(evidence))
    term_words = _WORD_PATTERN.findall(_normalize_evidence_text(term))
    if not term_words:
        return False
    return all(_word_is_grounded(word, evidence_words) for word in term_words)


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
        # Başarı oranı KASITLI OLARAK burada yok (bkz. _build_rag_question'ın
        # 2026-08-22 notu) - model artık paragraf yazmıyor, yalnız BAĞLAM'dan
        # iki terim seçiyor; oranı sorguya gömmek modelin SORU'nun kendi
        # cümlesini (ör. "%90") "evidenceTerms" diye seçmesine yol açıyordu.
        question = _build_rag_question(outcome) if is_weak else (
            f"{' - '.join(str(part) for part in (outcome.get('outcomeTheme'), outcome.get('outcomeCode'), outcome.get('outcomeDescription'), outcome.get('outcomeSkill')) if part)} "
            "öğrenme çıktısı için BAĞLAM'daki somut süreç bileşenlerine dayanarak güçlü "
            "performansı kanıtlayan iki somut terimi adıyla anarak seç."
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
                # Eskiden burada ayrıca bir "YANIT SÖZLEŞMESİ" bloğu vardı
                # (evidenceTerms'e özgü JSON talimatı) - 2026-08-22 (2. sürüm)
                # yeni sistem promptu kendi ÇIKTI FORMATI'nı zaten tam
                # taşıdığından KALDIRILDI; o eski blok bırakılsaydı yeni
                # şemayla ("evidence"/"gapRationale") ÇELİŞİRDİ - tam olarak
                # bu oturumun daha önce düzelttiği "sistem promptu ile
                # kullanıcı mesajı çelişiyor" hatasının aynısını geri
                # getirirdi.
                + f"SORU: {question}\n\nYalnızca bu sınav türü, seçilmiş öğrenme çıktısı ve yukarıdaki BAĞLAM'a dayanarak Türkçe yanıtla."
                + (
                    "\n\nYANIT SÖZLEŞMESİ: Yalnız geçerli JSON döndür: "
                    "{\"diagnosis\":\"tema/yüzde/şiddet İÇERMEYEN, yalnız nitel teşhis paragrafı\"}. "
                    "Tema adı, yüzde sayısı veya şiddet kelimesi yazma - bunlar ayrıca ekleniyor. "
                    "BAĞLAM'daki müfredat sözcüklerini kendi sözcüklerinle değiştirmeden "
                    "kullan. Markdown kullanma."
                    if is_weak else
                    "\n\nYANIT SÖZLEŞMESİ: Yalnız geçerli JSON döndür: "
                    "{\"diagnosis\":\"tema/yüzde İÇERMEYEN, yalnız nitel teşhis paragrafı\"}. Tema "
                    "adı veya yüzde sayısı yazma - bunlar ayrıca ekleniyor. "
                    "BAĞLAM'daki müfredat sözcüklerini kendi sözcüklerinle değiştirmeden kullan. "
                    "Markdown kullanma."
                )
            ),
            "retrieval": {
                "programId": program.id,
                "grade": program.grade,
                "theme": theme,
                # Aynı tema içinde dört beceri listesi (Dinleme/İzleme, Konuşma,
                # Okuma, Yazma) yalnız kod önekiyle ayrışıyor, metinleri
                # neredeyse birebir aynı - gömme onları ayırt EDEMEZ. Beceri
                # adı getirim tarafına bu yüzden gidiyor: sunucu yanlış
                # beceriye ait parçaları eliyor (bkz. rag_service
                # `_detect_skill_key`). Boş bırakılırsa eleme yapılmaz,
                # bugünkü davranış korunur.
                "skill": outcome.get("outcomeSkill") or "",
                # Getirimde gömülen metin, üretim talimatından KASITLI ayrı:
                # başarı oranı ve "teşhis et" emri müfredat düzyazısında
                # karşılığı olmayan, sorgu vektörünü uzaklaştıran gürültü.
                "query": _build_rag_retrieval_query(outcome),
                "topK": _DIAGNOSIS_TOP_K,
            },
        })
        targets[name] = outcome

    return targets


# Modelin yazdığı yüzde ifadesi ("%35", "yüzde 35"). Oranı MAHİR söylüyor.
_RATE_MENTION_PATTERN = re.compile(r"%\s*\d|yüzde\s+\d", re.IGNORECASE)


def _sentence_violation(sentence: str) -> str:
    """Cümleyi eleyen kuralı döndürür; temizse boş string.

    Sebebi METİN olarak döndürmek kasıtlı: `run_diagnosis_test.py`in
    doğrulama kaydı, hangi cümlenin HANGİ kalıp yüzünden atıldığını
    yazabilsin diye - aksi hâlde "hepsi kırpıldı" gibi bir sonuçta ham
    çıktıyı elle inceleyip kalıbı tahmin etmek gerekiyor.
    """

    # Modele yüzdeyi yazmaması söylendi ama yine de yazabiliyor (canlı
    # ölçümde görüldü). MAHİR oranı zaten kendi açılış cümlesinde
    # söylediğinden böyle bir cümle en iyi ihtimalle gereksiz tekrar, en
    # kötü ihtimalle modelin uydurduğu FARKLI bir sayı olur - ikisi de
    # rapora girmemeli.
    if _RATE_MENTION_PATTERN.search(sentence):
        return "oran-tekrari"
    return ""


def _strip_scope_violations(text: str, reasons: list[str] | None = None) -> tuple[str, int]:
    """Oran tekrarı taşıyan cümleleri paragraftan çıkarır; geri kalanı korur.

    `_answer_matches_outcome_scope`nin ikili ret/kabulüne bırakılsaydı, aksi
    hâlde iyi olan tüm teşhis TEK kötü cümle yüzünden kaybedilirdi; bunun
    yerine yalnız o cümle atılır."""

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        violation = _sentence_violation(sentence)
        if violation:
            _note_reason(reasons, f"bilgi: kırpılan cümle [{violation}]: {sentence.strip()[:120]}")
        else:
            kept.append(sentence)
    dropped = len(sentences) - len(kept)
    if kept and dropped and sentences and sentences[0] not in kept:
        # İLK cümle atıldıysa, hayatta kalan metin ona geri gönderme yapan bir
        # işaret sözcüğüyle başlayabilir ("Bu eksiklik, ...") - canlı ölçümde
        # tam olarak bu görüldü ve öğretmene artık var olmayan bir cümleye
        # atıf yapan, havada kalan bir paragraf gitti. O bağlayıcı öbeği
        # atıp cümleyi kendi başına ayakta duracak hâle getiriyoruz.
        kept[0] = _drop_dangling_reference(kept[0])
    return " ".join(kept).strip(), dropped


# "Bu eksiklik," / "Bu durum," gibi, kendinden ÖNCEKİ cümleye gönderme yapan
# açılış öbekleri. Yalnız virgülle biten kısa bir öbek olarak aranır - cümlenin
# asıl yüklemine dokunulmaz.
_DANGLING_REFERENCE_PATTERN = re.compile(
    r"^(bu|bunlar|bunun|böylece|dolayısıyla|ayrıca|bu durum|bu eksiklik|bu sonuç|bu performans)\b[^,]{0,40},\s*",
    re.IGNORECASE,
)


def _drop_dangling_reference(sentence: str) -> str:
    """Cümle başındaki, kaldırılmış bir cümleye gönderme yapan öbeği atar."""

    trimmed = _DANGLING_REFERENCE_PATTERN.sub("", sentence, count=1)
    if not trimmed or trimmed == sentence:
        return sentence
    return trimmed[0].upper() + trimmed[1:]


def _drop_theme_lead_in(diagnosis: str, theme: str) -> str:
    """Paragrafın başındaki `<tema> temasında[ki] ...` girişini atar.

    MAHİR tema adını kendi açılış cümlesinde zaten söylüyor; model de yazınca
    öğretmen aynı adı iki kez okuyor. Yalnız BAŞTAKİ giriş atılır - metnin
    ortasında geçen tema adına dokunulmaz, çünkü orada cümlenin anlamını
    taşıyor olabilir.
    """

    if not theme:
        return diagnosis
    # `(?:ki)?` - `ki?` DEĞİL: ikincisi zorunlu bir "k" arar ve düz
    # "temasında" ile başlayan metni hiç yakalamaz (canlı ölçümde tema adı
    # bu yüzden iki kez göründü).
    pattern = re.compile(
        r"^[\"'“”]?" + re.escape(theme) + r"[\"'“”]?\s+temasınd[ae](?:ki)?\s+(?:ele\s+alınan\s+)?",
        re.IGNORECASE,
    )
    trimmed = pattern.sub("", diagnosis, count=1)
    if not trimmed or trimmed == diagnosis:
        return diagnosis
    return trimmed[0].upper() + trimmed[1:]


def _answer_matches_outcome_scope(
    answer: str, outcome: dict[str, Any], reasons: list[str] | None = None
) -> bool:
    """Pedagojik LLM yanıtının güvenli yayın sözleşmesine uyduğunu doğrula.

    Model metni burada düzeltilmez (bkz. `_strip_scope_violations` - o adım
    burada değil, `_compose_grounded_pedagogical_answer` içinde, sarmadan
    ÖNCE çalışır - oran tekrarı orada, HAM teşhis üzerinde temizlenir). Bu
    fonksiyon SARILMIŞ (opening+diagnosis+closing) tam metni görür - MAHİR'in
    kendi açılış cümlesi zaten oranı söylediği için burada oran ARAMAZ. Bu
    fonksiyon yalnız SON bir güvenlik ağı: uzunluk veya kapsam sapması
    (kod sızıntısı, beceri/bileşen uyuşmazlığı) varsa yanıtın tamamı elenir.

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
