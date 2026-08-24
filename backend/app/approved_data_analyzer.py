"""Analyze teacher-approved MAHIR question and student score data."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

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

_DEFAULT_MAHIR_RAG_REMOTE_URL = "https://hakanergul--turkish-rag-system-raginference-web-query.modal.run"
# Varsayılan, deploy edilmiş RAG servisinin adresi olarak koda gömülü - terminalde
# her seferinde MAHIR_RAG_REMOTE_URL ayarlamaya gerek yok. Farklı bir deploy'a
# (ör. test ortamı) işaret etmek gerekirse env var yine de bunu geçersiz kılar.
MAHIR_RAG_REMOTE_URL = os.environ.get("MAHIR_RAG_REMOTE_URL", _DEFAULT_MAHIR_RAG_REMOTE_URL)
_RAG_WEAK_THRESHOLD = 0.70  # assets/js/mahir-report-export-common.js:buildDevelopmentNeedsBlock ile aynı eşik
_RAG_NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."

# ragContext'in boş kalmasının SEKİZ farklı sebebi var ve hepsi aynı boş stringi
# üretiyor - raporda "bazı satırlar boş" görüntüsünün hangisinden kaynaklandığı
# aksi hâlde ayırt edilemiyor. Her dal sunucu loguna tek satır sebep kodu yazar;
# API yanıtı ve rapor bilinçli olarak değişmez (öğretmen teknik mesaj görmemeli).
_logger = logging.getLogger(__name__)


def analyze_approved_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate approved browser data and return deterministic analysis results.

    İmza kasıtlı olarak değişmedi: hattın "sayıları değiştirmiyoruz" güvencesini
    koruyan eşdeğerlik ve altın değer testlerinin tamamı buna bağlı. Ajan izine
    de ihtiyacı olan çağıran (`file_receiver`) `analyze_approved_data_traced`
    kullanır.
    """

    return analyze_approved_data_traced(payload)[0]


def empty_trace() -> dict[str, Any]:
    """Hattın koşmadığı yollar için boş iz - alanın varlığı her zaman öngörülebilir."""

    return {"agents": [], "issues": []}


def analyze_approved_data_traced(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Analizi ve onu ÜRETEN ajan izini birlikte döndürür.

    İz `analysis`in içine değil KARDEŞİNE konuyor: `analysis` öğretmenin rapor
    sözleşmesi, iz ise "bu raporu kim üretti"nin cevabı - taşıma katmanı
    üstverisi. Ayrı tutmak rapor sözleşmesini teknik alanlarla kirletmiyor ve
    kaydedilmiş eski çalışmaları geçerli bırakıyor.

    İze `totalMs` de yazılıyor: ajan süreleri milisaniye mertebesinde, ortak
    LLM turu ise saniyeler sürüyor - toplamı ayrıca taşımak, tarayıcının
    "zaman nerede geçti"yi ek bir alan olmadan gösterebilmesini sağlıyor.
    Ölçüm hatalı yolda YAPILMIYOR: doğrulama hatası istisna olarak çıkıyor ve
    zaten ölçülecek bir iş yapılmamış oluyor.
    """

    began = time.monotonic()
    analysis, trace = _analyze_and_trace(payload)
    measured_total = (time.monotonic() - began) * 1000
    # Tek tek ajan süreleri ayrı ayrı ölçülüp yuvarlandığından çok hızlı yerel
    # koşularda bunların toplamı, duvar saati ölçümünün yuvarlanmış değerini
    # birkaç onda milisaniye aşabilir. İzde matematiksel olarak imkânsız bir
    # görünüm oluşmaması için toplam süre en az ajan sürelerinin toplamıdır.
    agent_total = sum(float(item.get("durationMs") or 0) for item in trace.get("agents", []))
    trace["totalMs"] = round(max(measured_total, agent_total), 1)
    return analysis, trace


def _analyze_and_trace(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        # Genel dil değerlendirmesi hattı koşturmuyor - bileşen analizleri zaten
        # üretilmiş, burada yalnız ağırlıklandırılıyorlar. İz boş döner ve yüzey
        # bunu bugünkü davranışa düşerek karşılar.
        return build_general_evaluation(course_profile.id, component_analyses), empty_trace()
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
    from .agents.base import trace_of
    from .agents.orchestrator import run_pipeline

    context = run_pipeline(payload, component_type, profile_id)
    return context.analysis, trace_of(context)

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


def _normalize_outcome(item: dict[str, Any], weight: float) -> dict[str, Any]:
    return {
        "outcomeCode": str(item.get("outcomeCode") or "").strip(),
        "outcomeDescription": str(item.get("outcomeDescription") or "").strip(),
        "outcomeTheme": str(item.get("outcomeTheme") or "").strip(),
        "outcomeSkill": str(item.get("outcomeSkill") or "").strip(),
        "parentOutcomeCode": str(item.get("parentOutcomeCode") or "").strip(),
        "parentOutcomeDescription": str(item.get("parentOutcomeDescription") or "").strip(),
        "outcomeKey": str(item.get("outcomeKey") or "").strip(),
        "weight": weight,
    }


def _normalize_question(item: Any, fallback_number: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{fallback_number}. soru verisi geçersiz.")
    number = int(_number(item.get("number"), fallback_number))
    max_score = _number(item.get("maxScore"))
    if max_score <= 0:
        raise ValueError(f"{number}. sorunun azami puanı sıfırdan büyük olmalıdır.")

    raw_outcomes = item.get("outcomes")
    outcome_fields = (
        "outcomeCode",
        "outcomeDescription",
        "outcomeTheme",
        "outcomeSkill",
        "parentOutcomeCode",
        "parentOutcomeDescription",
        "outcomeKey",
    )
    outcome_items = [
        entry
        for entry in raw_outcomes
        if isinstance(entry, dict) and any(entry.get(field) for field in outcome_fields)
    ] if isinstance(raw_outcomes, list) else []
    if not outcome_items and any(item.get(field) for field in ("outcomeCode", "outcomeDescription", "outcomeKey")):
        outcome_items = [item]
    weight = 1.0 / len(outcome_items) if outcome_items else 1.0
    outcomes = [_normalize_outcome(entry, weight) for entry in outcome_items]
    primary = outcomes[0] if outcomes else _normalize_outcome({}, 1.0)
    return {
        "number": number,
        "maxScore": max_score,
        "outcomes": outcomes,
        **{field: primary[field] for field in (
            "outcomeCode",
            "outcomeDescription",
            "outcomeTheme",
            "outcomeSkill",
            "parentOutcomeCode",
            "parentOutcomeDescription",
            "outcomeKey",
        )},
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


# Burada bir `_attach_rag_context` vardı: zayıf çıktıları toplayıp `rag_client`
# üzerinden tek partide sorguluyor, yanıtları `ragContext`e yazıyordu. Faz 3'te
# bu iş ajanın kendisine geçti - prompt'lar `pipeline.py::_enqueue_diagnosis_prompts`
# ile kuyruğa yazılıyor, yanıtlar `PedagogicalAnalysisAgent.apply_llm` içinde
# aynı sonrası-işlemeden geçiyor. Aşağıdaki yardımcılar (`_build_rag_question`,
# `_build_rag_retrieval_query`, `_normalize_theme_for_rag`) hâlâ oradan
# çağrılıyor, bu yüzden burada duruyorlar.



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
    """Tema + alt/ana kod + kazanım metni + beceri - kod TEK BAŞINA asla yeterli değil,
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
            outcome.get("parentOutcomeCode"),
            *unique_descriptions,
            outcome.get("outcomeSkill"),
        )
        if part
    ]


# Burada bir `_BLOOM_LEVELS_BY_VERB` haritası ve `_bloom_level_for` vardı:
# kazanım fiilinden Bloom basamağını çözüp prompt'a gömüyorlardı. Bloom analizi
# tamamen kaldırıldı çünkü ölçüm, teşhisin değerini AZALTTIĞINI gösterdi -
# sekiz yanıtın tamamı Bloom cümlesiyle açılıyor, yanıt başına 2-8 kez basamak
# adı geçiyor, buna karşılık temanın adı 0/8 yanıtta geçiyor ve yalnız 2/8
# yanıt müfredattan somut bir öğe anıyordu. Model, ona zaten söylediğimiz şeyi
# tekrarlamaya harcanıyordu. Teşhisin yeni ekseni müfredata demirleme
# (bkz. rag_service.py::SYSTEM_PROMPT madde 2).


def _build_rag_retrieval_query(outcome: dict[str, Any]) -> str:
    """Vektör getiriminde gömülecek metin - üretim talimatından KASITLI olarak
    ayrı tutuluyor (bkz. `_build_rag_question`). Başarı oranı ve "teşhis et"
    emri müfredat PDF'inde hiçbir karşılığı olmayan, sorgu vektörünü müfredat
    düzyazısından uzaklaştıran gürültü; getirim sorgusu yalnızca kazanımın
    kendi içeriğini taşır."""

    return " - ".join(_outcome_identity_parts(outcome))


def _build_rag_question(outcome: dict[str, Any]) -> str:
    """LLM'e sorulan soru (getirim sorgusu değil - o `_build_rag_retrieval_query`).

    2026-08-22: Başarı oranı ve şiddet etiketi buradan KALDIRILDI. Eskiden
    model paragrafın kendisini yazdığı için bunlara ihtiyacı vardı; artık
    yalnızca BAĞLAM'dan bir ila üç terim SEÇİYOR (`{"evidenceTerms":[...]}`,
    `pipeline.py::_compose_grounded_pedagogical_answer`) ve oranı/şiddeti
    MAHİR kendi hesaplıyor - modelin bunlara erişimi gerekmiyor. Canlı
    ölçümde bu sayılar sorudayken model tekrar tekrar "%30 başarı oranı"
    veya "Kritik" gibi SORU'nun kendi cümlesini "evidenceTerms" olarak
    seçip BAĞLAM'daki gerçek müfredat metnini hiç kullanmadı - kaldırılması
    bu tuzağı ortadan kaldırıyor.
    """

    parts = _outcome_identity_parts(outcome)
    if not parts:
        return ""
    return (
        f"{' - '.join(parts)} öğrenme çıktısı için BAĞLAM'daki öğretim "
        "programı metninden bu çıktıyla doğrudan ilgili bir ila üç somut "
        "terimi adıyla anarak yanıtla. Eksikliğin nedenini, öğrenci "
        "sayısını veya öğrencinin bilgisini tahmin etme."
    )
