"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

import logging
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
_RAG_CRITICAL_THRESHOLD = 0.50  # aynı dosyadaki "Öncelikli" / Kritik eşiği
_RAG_NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."

# ragContext'in boş kalmasının SEKİZ farklı sebebi var ve hepsi aynı boş stringi
# üretiyor - raporda "bazı satırlar boş" görüntüsünün hangisinden kaynaklandığı
# aksi hâlde ayırt edilemiyor. Her dal sunucu loguna tek satır sebep kodu yazar;
# API yanıtı ve rapor bilinçli olarak değişmez (öğretmen teknik mesaj görmemeli).
_logger = logging.getLogger(__name__)


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
        lambda: {"earned": 0.0, "possible": 0.0, "skill": "", "description": "", "parentDescription": ""}
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
        # Kazanımın tam metni (ör. "«Sözün İnceliği» temasında ele alınan
        # metinlerde dinlemeyi/izlemeyi yönetebilme") RAG için iki açıdan
        # kritik: müfredat PDF'iyle aynı dilde yazıldığı için çıplak bir koddan
        # çok daha iyi bir getirim anahtarı, ve kazanımın bilişsel fiilinin
        # ("yönetebilme", "değerlendirebilme") geçtiği tek yer - rag_service.py'nin
        # SYSTEM_PROMPT'u modelden tam olarak bu düzeyi sınıflandırmasını istiyor.
        # Süreç bileşeni seçildiyse (bkz. assets/js/mahir-program-catalog.js
        # filterOutcomes) üst kazanımın metni de taşınır; ikisi birlikte tek bir
        # bileşenin dar ifadesinden daha eksiksiz bir bağlam veriyor.
        outcome_totals[outcome_key]["description"] = question["outcomeDescription"]
        outcome_totals[outcome_key]["parentDescription"] = question["parentOutcomeDescription"]

    outcome_results = []
    for outcome_key, totals in outcome_totals.items():
        rate = totals["earned"] / totals["possible"] if totals["possible"] else 0.0
        theme, separator, code = outcome_key.rpartition(" | ")
        outcome_results.append(
            {
                "outcomeCode": code if separator else outcome_key,
                "outcomeTheme": theme if separator else "",
                "outcomeSkill": totals["skill"],
                "outcomeDescription": totals["description"],
                "parentOutcomeDescription": totals["parentDescription"],
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

    if not MAHIR_RAG_REMOTE_URL:
        _logger.info("RAG atlandı: sebep=yapilandirilmamis")
        return
    if program is None:
        _logger.info("RAG atlandı: sebep=program-yok")
        return

    from .rag_client import query_rag_context

    for outcome in outcome_results:
        code = str(outcome.get("outcomeCode") or "?")
        if float(outcome.get("successRate") or 0.0) >= _RAG_WEAK_THRESHOLD:
            continue
        question = _build_rag_question(outcome)
        if not question:
            _logger.info("RAG atlandı: cikti=%s sebep=soru-bos", code)
            continue
        theme = _normalize_theme_for_rag(str(outcome.get("outcomeTheme") or ""))
        if not theme:
            # Tema çözülemezse (ör. kazanım kataloğunda seçim yapılmamış) grade-only
            # bir aramaya düşmüyoruz: bu, 9. sınıfın 4 farklı temasından herhangi
            # birinin içeriğini getirebilir - aynı çıktı kodu her temada farklı bir
            # kazanıma karşılık geldiği için (bkz. rag_service.py index_pdf
            # docstring'i) yanlış temadan "kaynaklı" görünen bir teşhis vermek,
            # hiç teşhis vermemekten daha kötü.
            _logger.info("RAG atlandı: cikti=%s sebep=tema-cozulemedi", code)
            continue
        try:
            ok, message, data = query_rag_context(
                question,
                program.id,
                MAHIR_RAG_REMOTE_URL,
                grade=program.grade,
                theme=theme,
                retrieval_query=_build_rag_retrieval_query(outcome),
            )
        except Exception:  # noqa: BLE001 - bir RAG/ağ sorunu analiz yanıtını asla kesmemeli.
            _logger.exception("RAG atlandı: cikti=%s sebep=istisna", code)
            continue
        if not ok or not data:
            _logger.info("RAG atlandı: cikti=%s sebep=uzak-hata mesaj=%s", code, message)
            continue
        answer = str(data.get("answer") or "").strip()
        sources = data.get("sources") or []
        if not answer or not sources:
            # Kaynak listesi boşsa getirim hiç isabet vermemiştir (bkz.
            # rag_service.py::_run_query'nin `no_answer` dönüşü) - filtrelerden
            # (program_id/grade/theme_key) biri tutmamış demektir.
            _logger.info("RAG atlandı: cikti=%s sebep=kaynak-yok tema=%s", code, theme)
            continue
        # startswith + kırpma, tam eşleşme değil: gerçek dizin karşısında
        # doğrulandı (bkz. proje hafızası) - model doğru bağlamla beslendiğinde
        # bile CEVABI neredeyse HER ZAMAN "Bu bilgi belgede bulunmuyor." ile
        # başlatıp ardından gerçek, bağlama dayalı bir teşhisle devam ediyor.
        # Önceki sürüm bu ön ek varsa cevabın TAMAMINI atıyordu - bu da
        # kaynakları dolu gelen, geçerli çoğu yanıtın sessizce boş kalmasına
        # yol açıyordu. Yalnızca ön eki kırpıp gerçekten hiçbir şey kalmıyorsa
        # (modelin GERÇEKTEN hiçbir şey bulamadığı durum) atlanır.
        if answer.startswith(_RAG_NO_ANSWER_TEXT):
            answer = answer[len(_RAG_NO_ANSWER_TEXT):].strip()
        if not answer:
            _logger.info("RAG atlandı: cikti=%s sebep=model-reddetti tema=%s", code, theme)
            continue
        answer, dropped = _strip_recommendation_sentences(answer)
        if dropped:
            _logger.warning("RAG önerisi kırpıldı: cikti=%s cumle=%d", code, dropped)
        if not answer:
            _logger.info("RAG atlandı: cikti=%s sebep=tamami-oneri tema=%s", code, theme)
            continue
        _logger.info(
            "RAG dolduruldu: cikti=%s sebep=basarili kaynak=%d",
            code,
            len(sources) if isinstance(sources, list) else -1,
        )
        outcome["ragContext"] = answer


# DEVELOPMENT_CHARTER.md: "MAHİR ... öğretim yöntemi veya telafi programı
# önermez". Bu kısıt rag_service.py'nin SYSTEM_PROMPT'unda (madde 5) yazılı ama
# 7B'lik bir modelde prompt tek başına güvence değil - canlı ölçümde 8 yanıtın
# 2'si "... programları önerilir" / "... eğitim verilmesi gerekmektedir" gibi
# öneri cümleleriyle bitti. Bu yüzden kod tarafında da cümle düzeyinde bir
# emniyet ağı var. Tetikleyiciler kasıtlı olarak dar tutuldu - teşhis dilinde
# meşru olan biçimler elenmemeli: "gerektirir" ("bu kazanım analiz becerisi
# gerektirir") ve "gerekli olan" ("gerekli olan yeteneklerin kazandırılmadığı")
# kalmalı; yalnızca reçete yazan biçimler ("gerekir", "gerekmektedir",
# "gereklidir", zorunluluk kipi "-malıdır") elenmeli.
_RECOMMENDATION_PATTERN = re.compile(
    r"öneri|tavsiye|telafi|gerekmekte|gerekiyor|\bgerekir\b|gereklid[ıi]r"
    r"|ihtiyaç duyul|şartt[ıi]r|mal[ıi]d[ıi]r\b|melid[ıi]r\b",
    re.IGNORECASE,
)


def _strip_recommendation_sentences(answer: str) -> tuple[str, int]:
    """Öneri içeren cümleleri at; (kalan metin, atılan cümle sayısı) döndür.

    Yanıt tek bir akıcı paragraf olduğundan (bkz. SYSTEM_PROMPT çıktı biçimi)
    cümleler birbirinden büyük ölçüde bağımsız - bir cümleyi düşürmek kalan
    teşhisi bozmuyor. Hepsi öneriyse boş string döner ve çağıran taraf çıktıyı
    tamamen atar; charter ihlali içeren bir metni raporlamaktansa hücreyi boş
    bırakmak doğrusu.
    """

    sentences = re.split(r"(?<=[.!?])\s+", answer)
    kept = [sentence for sentence in sentences if not _RECOMMENDATION_PATTERN.search(sentence)]
    return " ".join(kept).strip(), len(sentences) - len(kept)


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


def _outcome_identity_parts(outcome: dict[str, Any]) -> list[str]:
    """Tema + kod + kazanım metni + beceri - kod TEK BAŞINA asla yeterli değil,
    aynı kod (ör. TDE1.2) dört TDE9 temasının her birinde farklı bir kazanıma
    karşılık geliyor. Kazanım metni (`outcomeDescription`, süreç bileşeni
    seçilmişse ayrıca üst kazanımın metni) müfredat PDF'iyle aynı dilde yazıldığı
    için hem getirimin hem de bilişsel düzey teşhisinin asıl dayanağı."""

    descriptions = [
        str(value)
        for value in (outcome.get("outcomeDescription"), outcome.get("parentOutcomeDescription"))
        if value
    ]
    # Süreç bileşeni seçilmemişse script.js parentOutcomeDescription'ı kazanım
    # metninin kendisiyle dolduruyor - aynı cümleyi iki kez göndermeyelim.
    unique_descriptions = list(dict.fromkeys(descriptions))
    return [
        str(part)
        for part in (
            outcome.get("outcomeTheme"),
            outcome.get("outcomeCode"),
            *unique_descriptions,
            outcome.get("outcomeSkill"),
        )
        if part
    ]


def _build_rag_retrieval_query(outcome: dict[str, Any]) -> str:
    """Vektör getiriminde gömülecek metin - üretim talimatından KASITLI olarak
    ayrı tutuluyor (bkz. `_build_rag_question`). Başarı oranı ve "teşhis et"
    emri müfredat PDF'inde hiçbir karşılığı olmayan, sorgu vektörünü müfredat
    düzyazısından uzaklaştıran gürültü; getirim sorgusu yalnızca kazanımın
    kendi içeriğini taşır."""

    return " - ".join(_outcome_identity_parts(outcome))


def _build_rag_question(outcome: dict[str, Any]) -> str:
    """LLM'e sorulan soru (getirim sorgusu değil - o `_build_rag_retrieval_query`).
    Kazanımın kimliğine ek olarak gerçek başarı oranını da taşır ki
    rag_service.py'nin SYSTEM_PROMPT'u kazanımın Bloom bilişsel düzeyini bu
    oranla kıyaslayabilsin. Kasıtlı olarak TEŞHİS ister, asla "bu nasıl
    öğretilmeli" demez - MAHİR etkinlik, yöntem veya telafi programı önermez
    (DEVELOPMENT_CHARTER.md); bu kısıtın fiilen uygulandığı yer bu ifade."""

    parts = _outcome_identity_parts(outcome)
    if not parts:
        return ""
    success_rate = float(outcome.get("successRate") or 0.0)
    percent_text = f"%{round(success_rate * 100)}"
    # Şiddet etiketi eşiğe dayalı, tamamen belirlenimci bir karar - modele
    # bıraktığımızda %55'lik vakaların yarısına "Kritik" dediği ölçüldü.
    # Burada hesaplayıp soruya gömüyoruz; rag_service.py'nin SYSTEM_PROMPT'u
    # (madde 4) bu etiketi aynen kullanmakla yükümlü.
    severity = "Kritik" if success_rate < _RAG_CRITICAL_THRESHOLD else "Orta"
    return (
        f"{' - '.join(parts)} öğrenme çıktısında öğrenciler {percent_text} "
        f"başarı oranı gösterdi. Bu oran için şiddet etiketi: {severity}. "
        "Bu kazanımın bilişsel düzeyini bu başarı oranıyla kıyaslayarak teşhis et."
    )
