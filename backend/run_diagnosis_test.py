"""Pedagojik Analiz Ajanı'nın müfredat teşhisini (RAG + LLM) tek bir öğrenme
çıktısı için, tüm MAHİR akışını (yükleme/OCR/onay/analiz) çalıştırmadan test
eder.

Üretim kodunu KOPYALAMAZ, doğrudan çağırır - `agents/pipeline.py`'nin gerçekte
kurduğu prompt'u, gerçek Modal uç noktasına gönderir ve öğretmenin göreceği
metni üreten aynı doğrulama fonksiyonlarından geçirir. Böylece bu script'in
sonucu her zaman canlı davranışla birebir aynı kalır.

Kullanım (backend/ dizininden) - yalnız kazanım kodu ve başarı yüzdesi:
    python run_diagnosis_test.py --outcome-code TDE1.2 --rate 35

Tema, açıklama, beceri, üst kazanım ve ders/sınıf `shared/pilot/*/
learning-outcomes-template.json` kataloğundan otomatik çözülür (aynı katalog
`assets/js/mahir-program-catalog.js`nin tarayıcıda kullandığı ile birebir
aynı dosya). Katalogda bulunamayan bir kod için (ör. henüz pilot dışı bir
ders) `--course`/`--grade`/`--theme` gibi alanlar elle verilebilir ve
otomatik çözümü geçersiz kılar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.agents.base import AgentContext
from app.agents.llm import run_agent_prompts
from app.agents.pipeline import (
    _RAG_SCOPE_REJECTED_TEXT,
    _answer_matches_outcome_scope,
    _compose_grounded_pedagogical_answer,
    _enqueue_diagnosis_prompts,
)
from app.approved_data_analyzer import (
    MAHIR_RAG_REMOTE_URL,
    _RAG_NO_ANSWER_TEXT,
    _RAG_WEAK_THRESHOLD,
    _normalize_theme_for_rag,
)
from app.models import CEDAssessment, CEDDocument, CEDMetadata
from app.program_catalog import PROGRAMS, ProgramProfile, validate_question_program_context

# `assets/js/mahir-program-catalog.js::programs[].dataUrl` ile AYNI kalmalı -
# tarayıcı ve bu script aynı kazanım kataloğunu okuyor, elle senkron tutuluyor
# (program_catalog.py'nin Python tarafı `dataUrl` taşımıyor, yalnız kod
# öneki/ders/sınıf biliyor).
_PROGRAM_DATA_URLS: dict[str, str] = {
    "tde-9-tymm": "shared/pilot/tde9/learning-outcomes-template.json",
}

# `mahir-program-catalog.js::skillsForComponent`in tersi: beceriden bileşen
# türüne dönüş, kullanıcı --component vermese bile doğru sınav türünü seçsin.
_COMPONENT_FOR_SKILL = {
    "okuma": "written",
    "yazma": "written",
    "dinleme/izleme": "listening",
    "konuşma": "speaking",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _normalize_tr(value: str) -> str:
    translated = str(value or "").translate(str.maketrans({"I": "ı", "İ": "i"}))
    return " ".join(translated.casefold().split())


def _resolve_program_for_code(outcome_code: str) -> ProgramProfile | None:
    upper = outcome_code.strip().upper()
    for program in PROGRAMS:
        if upper.startswith(program.outcome_prefix):
            return program
    return None


def _load_catalog(program: ProgramProfile) -> list[dict]:
    data_url = _PROGRAM_DATA_URLS.get(program.id)
    if not data_url:
        return []
    path = _REPO_ROOT / data_url
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return payload.get("learning_outcomes") or []


def _lookup_outcome(
    program: ProgramProfile, outcome_code: str, theme_hint: str | None = None
) -> dict[str, str] | None:
    """Kazanım kodunu katalogda ara; süreç bileşeni kodlarını da tanır.

    `mahir-program-catalog.js::filterOutcomes`in yaptığı üst kazanım/süreç
    bileşeni ayrımıyla aynı: bir süreç bileşeni bulunursa `parentCode`/
    `parentDescription` üst kazanıma, `outcomeDescription` bileşenin kendi
    başlığına işaret eder - üretimde soruya seçilen kazanımın taşıdığı
    alanlarla birebir aynı şekil.

    `theme_hint` verilmişse (kullanıcı `--theme` geçtiyse) yalnız O temadaki
    kayıt eşleşir. TDE9'da neredeyse her kod (TDE1.1, TDE2.2, TDE3.3 ...) 4
    temanın HEPSİNDE tekrar ediyor ve kazanım METNİ temaya göre değişiyor
    ("'Sözün İnceliği' temasında ele alınan ..." / "'Anlam Arayışı'
    temasında ele alınan ..."). `theme_hint` yoksayılırsa `--theme` yalnızca
    getirim filtresini değiştirir, `outcomeDescription` katalogdaki İLK
    (dosya sırasına göre 1. Tema) kayıttan gelmeye devam eder - kullanıcının
    seçtiği temayla TUTARSIZ bir kazanım metni prompt'a girer. Karşılaştırma
    `_normalize_theme_for_rag` ile yapılır: aynı fonksiyon getirim tarafında
    da kullanıldığı için "1. Tema: Sözün İnceliği" ile salt "Sözün İnceliği"
    burada da orada da aynı şeyi ifade eder.
    """

    target = outcome_code.strip().upper()
    normalized_hint = _normalize_theme_for_rag(theme_hint) if theme_hint else ""
    for outcome in _load_catalog(program):
        if normalized_hint and _normalize_theme_for_rag(str(outcome.get("theme") or "")) != normalized_hint:
            continue
        if str(outcome.get("code") or "").upper() == target:
            return {
                "theme": str(outcome.get("theme") or ""),
                "outcomeDescription": str(outcome.get("title") or ""),
                "skill": str(outcome.get("skill") or ""),
                "parentCode": "",
                "parentDescription": "",
            }
        for component in outcome.get("processComponents") or []:
            if str(component.get("code") or "").upper() == target:
                return {
                    "theme": str(outcome.get("theme") or ""),
                    "outcomeDescription": str(component.get("title") or ""),
                    "skill": str(outcome.get("skill") or ""),
                    "parentCode": str(outcome.get("code") or ""),
                    "parentDescription": str(outcome.get("title") or ""),
                }
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--outcome-code", required=True, help="Kazanım kodu, ör. TDE1.2")
    parser.add_argument("--rate", type=float, required=True, help="Başarı yüzdesi, 0-100 arası")
    parser.add_argument("--course", default=None, help="Ders adı - verilmezse katalogdan çözülür")
    parser.add_argument("--grade", default=None, help="Sınıf - verilmezse katalogdan çözülür")
    parser.add_argument("--theme", default=None, help="Tema adı - verilmezse katalogdan çözülür")
    parser.add_argument("--outcome-desc", default=None, help="Kazanım açıklaması - verilmezse katalogdan çözülür")
    parser.add_argument("--skill", default=None, help="Beceri alanı - verilmezse katalogdan çözülür")
    parser.add_argument("--component", default=None, help="written/listening/speaking - verilmezse beceriden çözülür")
    parser.add_argument("--parent-code", default=None, help="Üst kazanım kodu - verilmezse katalogdan çözülür")
    parser.add_argument("--parent-desc", default=None, help="Üst kazanım açıklaması - verilmezse katalogdan çözülür")
    parser.add_argument("--exam-type", default="", help="Sınav türü metni (opsiyonel, prompt'a gider)")
    return parser.parse_args()


def _empty_ced() -> CEDDocument:
    return CEDDocument(
        metadata=CEDMetadata(ced_version="1.0", created_at="", source="run_diagnosis_test"),
        assessment=CEDAssessment(id="", title="", course=""),
    )


def main() -> int:
    args = _parse_args()

    program = _resolve_program_for_code(args.outcome_code)
    catalog_entry = _lookup_outcome(program, args.outcome_code, args.theme) if program else None

    course = args.course or (program.course_names[0] if program else None)
    grade = args.grade or (program.grade if program else None)
    theme = args.theme if args.theme is not None else (catalog_entry or {}).get("theme", "")
    outcome_desc = args.outcome_desc if args.outcome_desc is not None else (catalog_entry or {}).get("outcomeDescription", "")
    skill = args.skill if args.skill is not None else (catalog_entry or {}).get("skill", "")
    parent_code = args.parent_code if args.parent_code is not None else (catalog_entry or {}).get("parentCode", "")
    parent_desc = args.parent_desc if args.parent_desc is not None else (catalog_entry or {}).get("parentDescription", "")
    component = args.component or _COMPONENT_FOR_SKILL.get(_normalize_tr(skill), "written")

    if not course or not grade or not theme:
        print(
            f"UYARI: '{args.outcome_code}' katalogda bulunamadı ve --course/--grade/--theme "
            "elle verilmedi. Pilot dışı bir kod için bu üçünü elle girin."
        )
        return 1
    if program is not None and catalog_entry is None and args.theme is not None and not outcome_desc:
        # program çözüldü (kod tanıdık bir önekle başlıyor) ama --theme ile
        # istenen KOMBİNASYON (bu kod + bu tema) katalogda yok - kodun
        # kendisi başka temalarda var olabilir. Sessizce devam etmek --theme'i
        # yoksayıp yanlış temanın kazanım metnini prompt'a sokardı.
        print(
            f"UYARI: '{args.outcome_code}' kodu \"{theme}\" temasında katalogda bulunamadı "
            "(başka bir temada var olabilir). --outcome-desc ile elle de girilebilir."
        )
        return 1

    print(f"Çözülen bağlam: {course} / {grade}. sınıf / \"{theme}\" / bileşen={component}")
    if outcome_desc:
        print(f"Kazanım açıklaması: {outcome_desc}")
    if parent_code:
        print(f"Üst kazanım: {parent_code} — {parent_desc}")

    # Program çözümü gerçek fonksiyonla: kayıtsız ders/sınıfta RAG hiç
    # denenmez, tıpkı üretimde ProgramMappingAgent'ta olduğu gibi.
    questions = [{
        "number": 1,
        "outcomeCode": args.outcome_code,
        "outcomeDescription": outcome_desc,
        "outcomeTheme": theme,
        "outcomeSkill": skill,
    }]
    resolved_program = validate_question_program_context(course, grade, questions)
    if resolved_program is None:
        print(f"UYARI: '{course}' / {grade}. sınıf kayıtlı bir programa çözülemedi; RAG denenmez.")
        return 1

    outcome = {
        "outcomeCode": args.outcome_code,
        "outcomeDescription": outcome_desc,
        "outcomeTheme": theme,
        "outcomeSkill": skill,
        "parentOutcomeCode": parent_code,
        "parentOutcomeDescription": parent_desc,
        "successRate": args.rate / 100,
        "componentType": component,
    }
    is_weak = outcome["successRate"] < _RAG_WEAK_THRESHOLD
    print(f"Kazanım {'ZAYIF (< %{:.0f})'.format(_RAG_WEAK_THRESHOLD * 100) if is_weak else 'GÜÇLÜ'} olarak değerlendirilecek (oran: %{args.rate:g}).")

    context = AgentContext(
        payload={"exam": {"examType": args.exam_type, "courseName": course}},
        ced=_empty_ced(),
    )
    targets = _enqueue_diagnosis_prompts(context, [outcome], resolved_program)
    if not targets:
        print("UYARI: prompt kuyruğa yazılmadı (tema çözülemedi ya da soru boş kaldı).")
        return 1

    print(f"\nUzak RAG/LLM servisine istek atılıyor: {MAHIR_RAG_REMOTE_URL}")
    ok, message, results = run_agent_prompts(context.llm_queue, MAHIR_RAG_REMOTE_URL)
    if not ok or not results:
        print(f"LLM turu başarısız: {message}")
        return 1

    result = results[0]
    answer = str(result.get("answer") or "")
    sources = result.get("sources") or []

    print("\n=== HAM MODEL YANITI ===")
    print(answer or "(boş)")
    print(f"\nGetirilen kaynak sayısı: {len(sources)}")
    for index, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            continue
        score = source.get("score")
        score_text = f", skor: {score:.3f}" if isinstance(score, (int, float)) else ""
        print(f"  [{index}] {source.get('documentName')} (sayfa: {source.get('pages')}{score_text})")
        headings = source.get("headings")
        if headings:
            print(f"      Başlık: {headings}")
        excerpt = str(source.get("excerpt") or "").strip()
        print(f"      İçerik: {excerpt or '(boş)'}")

    print("\n=== ÖĞRETMENİN GÖRECEĞİ METİN ===")
    if answer.startswith(_RAG_NO_ANSWER_TEXT):
        print("(Model kaynak yetersizliğini bildirdi; hücre boş kalır.)")
        return 0
    if not answer:
        print("(Boş yanıt; hücre boş kalır.)")
        return 0

    # Ret sebepleri toplanıyor: aksi hâlde her başarısız üretimde ham çıktıya
    # bakıp hangi kuralın tetiklendiğini elle tahmin etmek gerekiyor.
    reasons: list[str] = []
    if any(str(source.get("excerpt") or "").strip() for source in sources if isinstance(source, dict)):
        composed = _compose_grounded_pedagogical_answer(answer, outcome, sources, reasons)
    else:
        composed = answer

    accepted = bool(composed) and _answer_matches_outcome_scope(composed, outcome, reasons)
    if accepted:
        print(composed)
    else:
        print(f"REDDEDİLDİ - öğretmene şu gösterilirdi: \"{_RAG_SCOPE_REJECTED_TEXT}\"")

    if reasons:
        print("\n=== DOĞRULAMA KAYDI ===")
        for reason in reasons:
            print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
