"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

# Charter süzgeci `charter_guard`a taşındı: kısıt tek bir ajanın değil, LLM
# üreten her ajanın sorunu. Takma ad, mevcut çağrı yerlerini ve testleri
# değiştirmeden bırakmak için.
from .charter_guard import strip_recommendation_sentences as _strip_recommendation_sentences
from .assessment_profiles import (
    COMPONENT_LABELS,
    GENERAL,
    PROFILES,
    WRITTEN,
    build_general_evaluation,
    profile_for_course,
)
# `defaultdict` ve `validate_question_program_context` artık burada değil:
# ölçme toplamları `measurement_engine`e, program eşleştirme ise
# `agents/pipeline.py::ProgramMappingAgent`a taşındı.
from .program_catalog import ProgramProfile

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

    _assert_privacy_safe_students(payload.get("students"))
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

    # Buradan sonrası beş uzman ajanın işi (bkz. backend/app/agents/): Belge
    # Anlama -> Program Eşleştirme -> Ölçme -> Pedagojik Analiz -> Raporlama.
    # Yukarıdaki kontroller İSTEK düzeyinde (bileşen türü, ağırlık profili,
    # gizlilik kapısı) ve ajanların işi değil, bu yüzden burada kalıyor.
    #
    # Import fonksiyon içinde: `agents` paketi bu modülden normalleştirme ve
    # eşik yardımcılarını alıyor, modül seviyesinde import döngü kurardı.
    from .agents.orchestrator import run_pipeline

    return run_pipeline(payload, component_type, profile_id).analysis


def _normalize_corrected_cells(raw: Any) -> dict[int, int]:
    """`{"0": 2, "3": 1}` -> `{0: 2, 3: 1}` (soru indeksi -> düzeltilen hücre sayısı).

    Öğretmenin kaç puan hücresini düzelttiği yalnız tarayıcıda bilinebiliyor
    (bkz. `assets/js/mahir-score-corrections.js`), bu yüzden analiz yüküyle
    birlikte geliyor. Sayıya güvenilmiyor: bozuk, negatif veya sayı olmayan
    girdiler sessizce elenir - bu alan yalnız bir açıklanabilirlik göstergesi,
    hiçbir puanı veya oranı etkilemediği için bir doğrulama hatası fırlatıp
    öğretmenin analizini engellemesi orantısız olurdu.
    """

    if not isinstance(raw, dict):
        return {}
    normalized: dict[int, int] = {}
    for key, value in raw.items():
        try:
            index = int(key)
            count = int(value)
        except (TypeError, ValueError):
            continue
        if index >= 0 and count > 0:
            normalized[index] = count
    return normalized


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
    student_ref = str(item.get("studentRef") or "").strip()
    if not re.fullmatch(r"Ö-\d{3,}", student_ref):
        raise ValueError(
            f"{fallback_row}. öğrenci için oturumluk takma referans oluşturulamadı."
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
        "studentRef": student_ref,
        "scores": normalized_scores,
        "calculatedTotal": calculated_total,
        "attendance": "",
    }


def _assert_privacy_safe_students(students: Any) -> None:
    """Reject identity-bearing fields at the analysis/LLM boundary."""

    if not isinstance(students, list):
        return
    forbidden = {
        "studentNo": "okul numarası",
        "fullName": "ad-soyad",
        "name": "ad-soyad",
        "surname": "soyad",
        "tckn": "T.C. kimlik numarası",
        "tcKimlikNo": "T.C. kimlik numarası",
        "sourceFile": "kaynak dosya adı",
    }
    for index, student in enumerate(students, 1):
        if not isinstance(student, dict):
            continue
        found = [label for key, label in forbidden.items() if key in student]
        if found:
            raise ValueError(
                f"{index}. öğrenci verisi analiz güvenlik kapısından geçirilemedi: "
                f"{', '.join(dict.fromkeys(found))} analiz/LLM katmanına gönderilemez."
            )


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
    always predictable regardless of which path was taken. Never raises: any
    failure, timeout, or "not found in the document" answer just leaves
    `ragContext` empty, so a RAG problem can never block the teacher's
    analysis response. Only attempted for a resolved program (`program is
    not None`) - MAHİR covers 60+ courses but only registered programs have
    any indexed reference material, so unregistered courses would otherwise
    pay a ~110s cold-start wait for a query guaranteed to return nothing.

    All weak outcomes go out in ONE request (`query_rag_contexts`) so the
    remote can answer them in a single vLLM batch. Measured warm, one question
    costs ~10 s of which 7-8.6 s is generation at ~29 output tokens/s - that is
    single-sequence decode speed on an A10G, bounded by memory bandwidth, so
    decoding several sequences together costs barely more than one. The
    earlier design issued them sequentially (parallel HTTP calls were rejected
    because RAGInference has no @modal.concurrent and each call would spin up
    its own cold container); batching gets the speed without that problem.

    If the batch call fails for any reason the code falls back to the old
    per-outcome sequential path: one request carrying everything means one
    failure would otherwise blank every cell, where before it blanked one.
    """

    for outcome in outcome_results:
        outcome["ragContext"] = ""

    if not MAHIR_RAG_REMOTE_URL:
        _logger.info("RAG atlandı: sebep=yapilandirilmamis")
        return
    if program is None:
        _logger.info("RAG atlandı: sebep=program-yok")
        return

    from .rag_client import query_rag_context, query_rag_contexts

    # Partiye girecek zayıf çıktıları topla. Sorusu üretilemeyen veya teması
    # çözülemeyen çıktılar partiye HİÇ girmez - eskisi gibi sebep koduyla
    # loglanıp boş bırakılırlar.
    batch: list[tuple[dict[str, Any], str, dict[str, object]]] = []
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
        batch.append((
            outcome,
            theme,
            {
                "question": question,
                "retrievalQuery": _build_rag_retrieval_query(outcome),
                "grade": program.grade,
                "theme": theme,
            },
        ))

    if not batch:
        return

    items = [item for _outcome, _theme, item in batch]
    try:
        ok, message, results = query_rag_contexts(items, program.id, MAHIR_RAG_REMOTE_URL)
    except Exception:  # noqa: BLE001 - bir RAG/ağ sorunu analiz yanıtını asla kesmemeli.
        _logger.exception("Toplu RAG çağrısı istisna verdi")
        ok, message, results = False, "istisna", None

    if not ok or results is None:
        # Tek istekte her şeyi göndermenin bedeli: bir arıza TÜM hücreleri
        # boşaltırdı. Eski sıralı yol bu yüzden geri çekilme yolu olarak duruyor.
        _logger.warning("Toplu RAG çağrısı başarısız (%s), tek tek sorgulanıyor", message)
        results = []
        for _outcome, _theme, item in batch:
            try:
                single_ok, _message, data = query_rag_context(
                    str(item["question"]),
                    program.id,
                    MAHIR_RAG_REMOTE_URL,
                    grade=program.grade,
                    theme=str(item["theme"]),
                    retrieval_query=str(item["retrievalQuery"]),
                )
            except Exception:  # noqa: BLE001 - tek bir çıktının hatası kalanları düşürmemeli.
                _logger.exception("RAG atlandı: sebep=istisna")
                single_ok, data = False, None
            results.append(data if single_ok and data else None)

    for (outcome, theme, _item), data in zip(batch, results):
        code = str(outcome.get("outcomeCode") or "?")
        if not isinstance(data, dict):
            _logger.info("RAG atlandı: cikti=%s sebep=uzak-hata", code)
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




# Standart Unicode .upper() Türkçe 'i'/'ı' ayrımını kaybediyor (ikisi de düz
# "I"ya dönüşüyor) - rag_service.py'nin PDF'ten çıkardığı tema etiketleri
# (ör. "SÖZÜN İNCELİĞİ") zaten belgedeki doğru büyük/küçük harfle saklanıyor,
# bu yüzden yalnızca burada, sınavın karışık-case "outcomeTheme" alanını o
# etikete eşleştirmek için Türkçe-doğru büyütme uygulanıyor.
_TURKISH_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})
# Ters yön: str.lower() "İ" için birleşik noktalı bir "i̇" üretip fiil
# eşleşmesini bozuyor (bkz. _bloom_level_for).
_TURKISH_LOWER_MAP = str.maketrans({"İ": "i", "I": "ı"})


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


# TDE9 kataloğundaki (shared/pilot/tde9/learning-outcomes-template.json) 55
# kazanımın TAMAMI yalnızca şu beş fiille bitiyor: oluşturabilme (17),
# yönetebilme (16), yansıtabilme (10), uygulayabilme (8), çözümleyebilme (4).
# Küme kapalı ve küçük olduğu için bilişsel basamağı modele tahmin ettirmek
# yerine burada, tek ve gözden geçirilebilir bir yerde sabitliyoruz: canlı
# ölçümde model kazanım fiilinin kendisini ("Yönetebilme") basamak adı sanıp
# "altı Bloom basamağından en yüksek düzey" diye niteleyebiliyordu. Eşleşme
# bulunamazsa (yeni bir ders/program eklendiğinde) alan hiç gönderilmez ve
# basamağı model kendi seçer - eski davranış korunur.
_BLOOM_LEVELS_BY_VERB = (
    ("çözümleyebilme", "Analiz"),        # tahlil etme, ögeler arası ilişki kurma
    ("yansıtabilme", "Değerlendirme"),   # öğrendiğini gözden geçirme, öz değerlendirme
    ("yönetebilme", "Uygulama"),         # strateji seçip süreci izleme/denetleme
    ("uygulayabilme", "Uygulama"),
    ("oluşturabilme", "Anlama"),         # metinden anlam kurma, yorumlama, çıkarım
)


def _bloom_level_for(description: str) -> str:
    """Kazanım metnindeki fiilden Bloom basamağını çöz; bulunamazsa boş string."""

    lowered = description.translate(_TURKISH_LOWER_MAP).lower()
    for verb, level in _BLOOM_LEVELS_BY_VERB:
        if verb in lowered:
            return level
    return ""


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
    bloom_level = _bloom_level_for(" ".join(parts))
    bloom_text = f"Bu kazanımın bilişsel düzeyi: {bloom_level}. " if bloom_level else ""
    return (
        f"{' - '.join(parts)} öğrenme çıktısında öğrenciler {percent_text} "
        f"başarı oranı gösterdi. {bloom_text}"
        f"Bu oran için şiddet etiketi: {severity}. "
        "Bu kazanımın bilişsel düzeyini bu başarı oranıyla kıyaslayarak teşhis et."
    )
