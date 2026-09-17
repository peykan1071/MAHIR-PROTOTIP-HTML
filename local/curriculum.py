"""MEB öğretim programı belgelerine özgü yapı bilgisi: belge adları, SINIF/TEMA
bölüm tespiti, tema içi bölüm türleri, kazanım kodları, süreç bileşeni
bölücüsü ve beceri anahtarları.

`ingestion_pipeline.py` bu modülle her parçaya `grade`/`theme`/`theme_key`/
`skill_key`/`section_kind`/`outcome_codes` payload alanlarını yazar;
`rag_service.py` aynı anahtarlarla filtreler. İki taraf da AYNI fonksiyonları
kullanmalı - anahtar üretimi iki yerde yazılırsa bir tarafın küçük bir farkı
eşleşmeyi sessizce bozar.

Belge yapısı (docs/tde2026.pdf, 2024 programı, 208 sayfa - 2026-09-16'da dört
9. sınıf temasının ham metni taranarak doğrulandı):
  * s.20-27: TÜM sınıflar için ortak "Öğrenme Çıktıları ve Süreç Bileşenleri"
    listesi - `TDE1.2. Anlam Oluşturabilme` / `a) TDE1.2.1. Ön bilgilerle
    bağlantı kurar.` / göstergeler. Tema sayfalarında bu bileşenler YOK.
  * s.32+: "HAZIRLIK SINIFI TEMALARI", s.65 "9. SINIF TEMALARI" ... her sınıfta
    dört "N. TEMA: AD" bölümü (~7-9 sayfa). Tema içinde sabit sırayla: tema
    girişi, programlar arası bileşenler, öğrenme çıktıları (yalnız üst
    kazanım başlıkları), İÇERİK ÇERÇEVESİ, Anahtar Kavramlar, ÖĞRENME
    KANITLARI, ÖĞRENME-ÖĞRETME YAŞANTILARI (Temel Kabuller, Ön Değerlendirme
    Süreci, Köprü Kurma, Öğrenme-Öğretme Uygulamaları, Süreç Çerçevesi),
    Tema Sonu Değerlendirme, FARKLILAŞTIRMA (Zenginleştirme, Destekleme),
    ÖĞRETMEN YANSITMALARI. Bölüm başlıklarının çoğu SATIR İÇİ ("Destekleme
    Öğrencilere içeriği...") - Docling bunları başlık olarak görmüyor, metnin
    başından desenle okunuyor.

Saf modül: stdlib + tembel `pypdf`; ML bağımlılığı yok, testler ağır kurulum
olmadan koşar.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

# Program kimliği -> referans belgenin RESMÎ adı. Bu ad Qdrant payload'ına
# yazılıyor ve oradan öğretmenin raporuna çıkıyor ("Kaynak: ..., s. 66-67"),
# yani dosya adı ("tdeogr.pdf") değil belgenin kendi kimliği olmalı - resmî
# bir rapor, dayanağını dosya adıyla göstermez.
#
# Neden kayıt, neden elle yazım değil: ad her yeniden indekslemede birebir aynı
# olmalı. Elle yazılsa iki indeksleme arasında farklılaşabilir ve dizinde aynı
# belge iki ayrı adla görünürdü. Kod incelemesinden geçmesi de ayrı bir kazanç.
#
# Neden kapaktan otomatik çıkarılmıyor: TDE9 belgesinin kapağında yıl, metin
# katmanında "2O24" (harf O, sıfır değil) olarak geçiyor ve kapak düzeni her
# belgede farklı - temizleme kuralları her yeni belgede yeniden yazılırdı.
#
# Yeni bir referans belge eklendiğinde buraya tek satır eklenir; kayıtta
# bulunmayan bir program için `--document-title` zorunlu olur.
DOCUMENT_TITLES = {
    "tde-9-tymm": (
        "Ortaöğretim Türk Dili ve Edebiyatı Dersi Öğretim Programı - "
        "Türkiye Yüzyılı Maarif Modeli (2024)"
    ),
}


def resolve_document_title(program_id: str, override: str | None = None) -> str:
    """İndekslenecek belgenin resmî adını çözer; bulunamazsa `ValueError`.

    Sessiz bir geri düşüş (ör. dosya adına dönmek) KASITLI olarak yok: yanlış
    ada sahip parçalar dizine girdikten sonra ancak `--replace` ile yeniden
    indeksleme ile düzelir ve bu, o ana kadar üretilmiş her raporun kaynağını
    yanlış göstermiş olur. Hata, indekslemeden ÖNCE verilmeli.
    """

    # Önce kırp, sonra geri düş: yalnız boşluktan oluşan bir `--document-title`
    # (kabuk tırnak hatası) truthy olduğu için kaydı gölgeler ve "ad tanımlı
    # değil" hatası verirdi - oysa kayıtta ad duruyor.
    title = (override or "").strip() or (DOCUMENT_TITLES.get(program_id) or "").strip()
    if not title:
        raise ValueError(
            f"'{program_id}' için resmî belge adı tanımlı değil. "
            "local/curriculum.py DOCUMENT_TITLES'a ekleyin ya da --document-title ile verin."
        )
    return title


# --- SINIF / TEMA bölümleri --------------------------------------------------------------

# MEB müfredat PDF'lerindeki hiyerarşi başlıkları - tdeogr.pdf üzerinde tüm
# 5 sınıf düzeyi ve 20 sınıf×tema kombinasyonu için elle doğrulandı. Satırın
# TAMAMINI kaplayan bağımsız bir metin satırı arıyoruz (`^...$`, MULTILINE) -
# bu, İçindekiler'deki aynı metni (satır sonunda sayfa numarasıyla birlikte
# geldiği için `$` ile eşleşmiyor) doğal olarak eler. Desenler eşleşmezse
# indeksleme SINIF/tema-bölme adımını atlar - yalnızca bu belge yapısına özgü
# kalır, genel kod bozulmaz.
GRADE_HEADING_PATTERN = re.compile(r"^\s*(HAZIRLIK SINIFI TEMALARI|\d+\.\s*SINIF TEMALARI)\s*$", re.MULTILINE)
TEMA_HEADING_PATTERN = re.compile(r"^\s*\d+\.\s*TEMA\s*:\s*(.+?)\s*$", re.MULTILINE)

Section = tuple[str | None, int, int]
"""`(etiket, başlangıç_sayfa, bitiş_sayfa)` - 1-indeksli, iki uç dahil."""


def find_heading_pages(pdf_bytes: bytes, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """`pattern`'a uyan başlıkları tüm sayfalarda arar; aynı başlık metni
    birden fazla sayfada eşleşirse yalnızca EN SON (en yüksek sayfa numaralı)
    eşleşmeyi tutar - `tdeogr.pdf`'te doğrulandı: hem İçindekiler'deki
    girişler (aynı metin ama satır sonunda sayfa numarasıyla, bu yüzden zaten
    `pattern`'ın `$` çapasıyla elenir) hem de "1.5 Programın Yapısı"
    bölümünün örnek/önizleme amaçlı tekrarladığı bir tema başlığı (s.30, gerçek
    başlangıcı s.32) her zaman gerçek bölümden ÖNCE gelir, bu yüzden "en son
    eşleşme kazanır" kuralı güvenilir. Sonuç, sayfa numarasına göre artan
    sırada `(sayfa, başlık_metni)` listesi olarak döner."""

    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(io.BytesIO(pdf_bytes))
    last_page_for_label: dict[str, int] = {}
    for page_index, page in enumerate(reader.pages):
        match = pattern.search(page.extract_text() or "")
        if match:
            label = (match.group(1) if pattern.groups else match.group(0)).strip()
            last_page_for_label[label] = page_index + 1  # üzerine yaz -> son (en büyük) sayfa kalır

    return sorted(((page, label) for label, page in last_page_for_label.items()), key=lambda item: item[0])


def sections_from_heading_pages(heading_pages: list[tuple[int, str]], total_pages: int) -> list[Section]:
    """`find_heading_pages` çıktısını `(etiket, başlangıç_sayfa, bitiş_sayfa)`
    (1-indeksli/dahil) üçlülerinden oluşan, tüm belgeyi/aralığı kapsayan bir
    listeye çevirir. Hiç başlık bulunamazsa tüm aralığı tek, etiketsiz
    (`None`) bir bölüm olarak döndürür - bölme yalnızca desene uyan
    belgelerde devreye girer, genel davranışı bozmaz."""

    if not heading_pages:
        return [(None, 1, total_pages)]

    sections: list[Section] = []
    for index, (start_page, label) in enumerate(heading_pages):
        end_page = heading_pages[index + 1][0] - 1 if index + 1 < len(heading_pages) else total_pages
        sections.append((label, start_page, end_page))
    return sections


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def detect_theme_sections(pdf_bytes: bytes) -> list[Section]:
    """Verilen PDF baytları içinde `TEMA_HEADING_PATTERN`'a uyan başlıkları
    tarar ve `(tema_adı, başlangıç_sayfa, bitiş_sayfa)` (1-indeksli/dahil)
    üçlülerinden oluşan, tüm belgeyi kapsayan bir liste döndürür."""

    return sections_from_heading_pages(find_heading_pages(pdf_bytes, TEMA_HEADING_PATTERN), _page_count(pdf_bytes))


def normalize_grade_label(raw_heading: str) -> str:
    """`"9. SINIF TEMALARI"` -> `"9"`, `"HAZIRLIK SINIFI TEMALARI"` -> `"hazırlık"` -
    `backend/app/program_catalog.py`'deki `ProgramProfile.grade` biçimiyle
    (düz rakam string'i) doğrudan karşılaştırılabilir olması için."""

    match = re.match(r"\s*(\d+)\.\s*SINIF", raw_heading, re.IGNORECASE)
    return match.group(1) if match else "hazırlık"


def detect_grade_sections(pdf_bytes: bytes) -> list[Section]:
    """Verilen PDF baytları içinde `GRADE_HEADING_PATTERN`'a uyan SINIF
    başlıklarını tarar ve `(normalize_edilmiş_sınıf, başlangıç_sayfa,
    bitiş_sayfa)` (1-indeksli/dahil) üçlülerinden oluşan, tüm belgeyi
    kapsayan bir liste döndürür (etiketler `normalize_grade_label` ile
    `"9"`/`"hazırlık"` biçimine çevrilir)."""

    sections = sections_from_heading_pages(find_heading_pages(pdf_bytes, GRADE_HEADING_PATTERN), _page_count(pdf_bytes))
    return [
        (normalize_grade_label(label) if label is not None else None, start, end)
        for label, start, end in sections
    ]


# --- Tema ve beceri anahtarları ----------------------------------------------------------


def theme_match_key(theme_text: str) -> str:
    """Tüm boşlukları atarak bir eşleştirme anahtarı üretir - pypdf'in bazı
    harf çiftlerinde (örn. "YAPI" -> "Y API", `tdeogr.pdf` s.80'de doğrulandı,
    muhtemelen PDF'in harf aralığı/kerning kodlamasından kaynaklanıyor) sahte
    boşluk eklemesi yüzünden, tema adının kendisi (`theme` alanı, gösterim
    için ham hâliyle saklanır) eşleştirme için güvenilir değil. Hem indeksleme
    hem sorgu tarafında (`backend/app/approved_data_analyzer.py::
    _normalize_theme_for_rag`) aynı fonksiyon kullanılmalı."""

    return re.sub(r"\s+", "", theme_text.upper())


# MEB müfredat belgesinde bir kazanım listesinin hangi BECERİYE ait olduğunu
# söyleyen başlıklar. Aynı tema içinde bu dört liste yalnızca kod önekiyle
# ayrışıyor, metinleri neredeyse birebir aynı:
#     TDE2.2. 'Anlamın Yapı Taşları' temasında ele alınan metinlerde anlam oluşturabilme
#     TDE1.2. 'Anlamın Yapı Taşları' temasında ele alınan metinlerde anlam oluşturabilme
# Hiçbir gömme modeli bunları ayırt edemez (canlı ölçüm: okuma sorgusunda
# Dinleme/İzleme listesi 0,813 alıp top_k'yı doldurdu ve model TDE2.3 teşhisine
# TDE2.1/TDE2.2'yi karıştırdı). Ayrım anlamsal değil YAPISAL olduğu için
# çözümü de yapısal: belgenin kendi başlığından okunur.
#
# Değerler `shared/pilot/*/learning-outcomes-template.json` içindeki `skill`
# alanıyla aynı kaynaktan (MEB programı) geliyor; iki taraf da
# `skill_match_key` altında aynı anahtara düştüğü için eşleşme birebir kalır.
SKILL_HEADINGS = ("Dinleme/İzleme", "Konuşma", "Okuma", "Yazma")

# `casefold()` tek başına "İ"yi "i" + U+0307 yapar ve "I"yı "i"ye çevirir -
# ikisi de Türkçe metinde yanlış anahtar üretir.
_TURKISH_LOWER_MAP = str.maketrans(
    {"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"}
)


def skill_match_key(skill_text: str) -> str:
    """Beceri adı/başlığı -> eşleştirme anahtarı ("Dinleme/İzleme" -> "dinlemeizleme").

    Harf dışındaki her şey atılır: belgedeki başlık ile katalogdaki `skill`
    alanı arasındaki eğik çizgi/boşluk/tire farkları eşleşmeyi kaçırmasın.
    Hem indeksleme hem sorgu tarafında AYNI fonksiyon kullanılmalı.
    """

    folded = skill_text.translate(_TURKISH_LOWER_MAP).casefold()
    return "".join(char for char in folded if char.isalnum())


KNOWN_SKILL_KEYS = frozenset(skill_match_key(name) for name in SKILL_HEADINGS)

# TDE9 kod önekinin BECERİ ile eşlemesi - `tdeogr.pdf`'teki 4 tema × 4 beceri
# üzerinde elle doğrulandı ve ayrıca `shared/pilot/tde9/
# learning-outcomes-template.json`daki TÜM kayıtlarla programatik çapraz
# kontrol edildi (bkz. `tests/test_rag_service_indexing.py::
# SkillRegistryContractTests`): TDE1.x her zaman Dinleme/İzleme, TDE2.x her
# zaman Okuma, TDE3.x her zaman Konuşma, TDE4.x her zaman Yazma. Bu, üst
# başlık tespitinin (aşağıda) kaçırdığı asıl durumu yakalamak için var: alt
# süreç bileşeni başlıkları ("c) TDE1.2.3. Çıkarım yapar.") Docling'in başlık
# zincirinde üst beceri başlığını ("Dinleme/İzleme") TAŞIMIYOR - yalnız kendi
# alt başlığını taşıyor. Üst başlık eşleşmesi bu yüzden TEK BAŞINA yeterli
# değil (canlı ölçüm: Yazma istenen bir sorguda TDE1.2.1-1.2.4 alt bileşenleri
# hiç elenmeden sızdı - başlıkları "Dinleme/İzleme" değil "a) TDE1.2.1. ..."
# idi).
CODE_PREFIX_TO_SKILL = {"1": "Dinleme/İzleme", "2": "Okuma", "3": "Konuşma", "4": "Yazma"}
_CODE_PREFIX_PATTERN = re.compile(r"TDE(\d+)\.")


def detect_skill_key(headings: object, text: str = "") -> str | None:
    """Bir parçanın hangi BECERİYE ait olduğunu iki sinyalle çıkarır, yoksa `None`.

    1) Üst düzey beceri başlığı zincirde birebir geçiyorsa (ör. bir bölümün
       KENDİSİ "Okuma" başlığını taşıyorsa) onu kullan - en güvenilir sinyal.
    2) Yoksa, başlıklardan VEYA gövde metninden bir "TDE{N}." kod öneki çıkar
       ve `CODE_PREFIX_TO_SKILL` ile beceriye çevir - alt süreç bileşeni
       başlıkları (yukarıdaki not) bu yol olmadan hiç yakalanmaz.

    `None` KASITLI bir değer, "bilinmiyor" demek değil: tema tanıtımı ya da
    "Öğrenme-Öğretme Uygulamaları" gibi bölümler hiçbir beceriye ait DEĞİL ve
    her beceri için geçerli. Sorgu tarafındaki filtre bunları eler değil,
    korur - yalnız YANLIŞ beceriye ait olduğu belgeden okunan parçaları atar.
    """

    heading_list = [str(heading) for heading in (headings or [])]
    for heading in heading_list:
        key = skill_match_key(heading)
        if key in KNOWN_SKILL_KEYS:
            return key

    match = _CODE_PREFIX_PATTERN.search(" ".join(heading_list) + " " + str(text or ""))
    if match:
        skill_name = CODE_PREFIX_TO_SKILL.get(match.group(1))
        if skill_name:
            return skill_match_key(skill_name)
    return None


def excluded_skill_keys(requested_skill: str | None) -> frozenset[str]:
    """Sorgu filtresi için ELENECEK beceri anahtarları.

    İstenen beceri bilinen dört beceriden biriyse diğer üçü döner; değilse
    (boş, bilinmeyen) boş küme - eleme yapılmaz, bugünkü davranış korunur.
    `skill_key` alanı OLMAYAN parçalar (`None`) hiçbir zaman elenmez: bu
    `must_not`'ın doğası - alanı olmayan nokta koşula uymaz, korunur.
    """

    key = skill_match_key(requested_skill or "")
    if key not in KNOWN_SKILL_KEYS:
        return frozenset()
    return KNOWN_SKILL_KEYS - {key}


# --- İndeks planı: hangi sayfa aralıkları, hangi türle ----------------------------------------


@dataclass(frozen=True)
class PageRange:
    """İndekslenecek sayfa aralığı (1-indeksli, iki uç dahil).

    `kind="surec_bilesenleri"`: sınıftan bağımsız ortak bileşen listesi - Docling
    yerine satır tabanlı bölücüyle (`split_process_components`) parçalanır ve
    `grade`/`theme` boş yazılır. `kind=None`: normal SINIF×TEMA akışı.
    """

    start_page: int
    end_page: int
    kind: str | None = None


# Program başına varsayılan indeks planı. `--start-page/--end-page` verilmezse
# `ingest_pdf` bu aralıkları sırayla işler. Bileşen listesi bir kez (ilk
# aralık), sonra o sınıfın tema sayfaları. Yeni sınıf/program -> yeni satır.
INDEX_PLANS: dict[str, tuple[PageRange, ...]] = {
    "tde-9-tymm": (PageRange(20, 27, kind="surec_bilesenleri"), PageRange(65, 96)),
}


def resolve_index_plan(program_id: str) -> tuple[PageRange, ...] | None:
    return INDEX_PLANS.get(program_id)


# --- Tema içi bölüm türleri ---------------------------------------------------------------------

SECTION_LABELS: dict[str, str] = {
    "tema_giris": "Tema Girişi",
    "programlar_arasi": "Programlar Arası Bileşenler",
    "ogrenme_ciktilari": "Öğrenme Çıktıları",
    "icerik_cercevesi": "İçerik Çerçevesi",
    "anahtar_kavramlar": "Anahtar Kavramlar",
    "ogrenme_kanitlari": "Öğrenme Kanıtları (Ölçme ve Değerlendirme)",
    "ogrenme_ogretme": "Öğrenme-Öğretme Yaşantıları",
    "tema_sonu": "Tema Sonu Değerlendirme",
    "farklilastirma": "Farklılaştırma",
    "ogretmen_yansitmalari": "Öğretmen Yansıtmaları",
    "surec_bilesenleri": "Öğrenme Çıktıları ve Süreç Bileşenleri",
}
SECTION_KINDS = tuple(SECTION_LABELS)

# Bölüm başlığı -> tür. Başlık ya Docling başlığı olarak ya da parça metninin
# BAŞINDA (satır içi başlık) gelir; ikisi de aynı desenlerle okunur. pypdf'in
# sahte boşluğu ("Y AŞANTILARI") için `Y\s?A`. Beceri başlıkları ("Okuma",
# "Dinleme/İzleme", "Metin Tahlili (Anlama)") KASITLI olarak yok: hem öğrenme
# çıktıları hem öğrenme-öğretme uygulamaları altında geçiyorlar, türü
# değiştirmezler.
SECTION_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^(ALAN\s+BECERİLERİ|KAVRAMSAL\s+BECERİLER|PROGRAMLAR\s+ARASI\s+BİLEŞENLER|DİSİPLİNLER\s+ARASI|"
            r"BECERİLER\s+ARASI\s+İLİŞKİLER|Sosyal-Duygusal\s+Öğrenme\s+Becerileri|Değerler\b|Okuryazarlık\s+Becerileri)"
        ),
        "programlar_arasi",
    ),
    (re.compile(r"^ÖĞRENME\s+ÇIKTILARI\s+VE\s+SÜREÇ\s+BİLEŞENLERİ"), "ogrenme_ciktilari"),
    (re.compile(r"^İÇERİK\s+ÇERÇEVESİ"), "icerik_cercevesi"),
    (re.compile(r"^Anahtar\s+Kavramlar"), "anahtar_kavramlar"),
    (
        re.compile(r"^ÖĞRENME\s+KANITLARI|^\(Ölçme\s+ve\s+Değerlendirme\)|^(Okuma\s+ve\s+Dinleme/İzleme|Konuşma\s+ve\s+Yazma)\s*$"),
        "ogrenme_kanitlari",
    ),
    (
        re.compile(
            r"^ÖĞRENME-ÖĞRETME\s+Y\s?AŞANTILARI|^Temel\s+Kabuller|^Ön\s+Değerlendirme\s+Süreci|^Köprü\s+Kurma|"
            r"^Öğrenme-Öğretme\s+Uygulamaları|^Süreç\s+Çerçevesi"
        ),
        "ogrenme_ogretme",
    ),
    (re.compile(r"^Tema\s+Sonu\s+Değerlendirme"), "tema_sonu"),
    (re.compile(r"^FARKLILAŞTIRMA|^Zenginleştirme|^Destekleme"), "farklilastirma"),
    (re.compile(r"^ÖĞRETMEN\s+Y\s?ANSITMALARI"), "ogretmen_yansitmalari"),
)

# Parça metninin ORTASINDA (satır başında) başlayan satır içi başlıklar: parça
# burada bölünür ki "Yazma" kazanım listesi ile "İÇERİK ÇERÇEVESİ" aynı parçada
# kalmasın.
_INLINE_TITLE_PATTERN = re.compile(
    r"(?<=\n)(?=(?:ÖĞRENME\s+ÇIKTILARI\s+VE\s+SÜREÇ\s+BİLEŞENLERİ|İÇERİK\s+ÇERÇEVESİ|Anahtar\s+Kavramlar|ÖĞRENME\s+KANITLARI|"
    r"\(Ölçme\s+ve\s+Değerlendirme\)|ÖĞRENME-ÖĞRETME\s+Y\s?AŞANTILARI|"
    r"Temel\s+Kabuller|Ön\s+Değerlendirme\s+Süreci|Köprü\s+Kurma|Öğrenme-Öğretme\s+Uygulamaları|Süreç\s+Çerçevesi|"
    r"Tema\s+Sonu\s+Değerlendirme|FARKLILAŞTIRMA|Zenginleştirme|Destekleme\s|ÖĞRETMEN\s+Y\s?ANSITMALARI))"
)
_OUTCOME_LINE_PATTERN = re.compile(r"^\s*-?\s*TDE\d+\.\d+\.\s")
_OUTCOME_CODE_PATTERN = re.compile(r"\bTDE(\d+)\.(\d+)(?:\.\d+)*\b")


# Docling'in run-in (kalın, satır içi) etiketleri metinden DÜŞÜRDÜĞÜ görüldü
# (canlı: "İÇERİK ÇERÇEVESİ “Sözün İnceliği” temasının..." satırı etiketsiz,
# "Anahtar Kavramlar açık ve örtük ileti" -> yalnız liste). pypdf metni etiketi
# korur; `recover_inline_titles` Docling satırını pypdf akışında bulup hemen
# önündeki etiketi ayrı satır olarak geri yerleştirir. En uzun önce: "Ön
# Değerlendirme Süreci" "Süreci"nin altına düşmesin.
INLINE_TITLES: tuple[str, ...] = (
    "ÖĞRENME ÇIKTILARI VE SÜREÇ BİLEŞENLERİ",
    "ÖĞRENME-ÖĞRETME YAŞANTILARI",
    "Öğrenme-Öğretme Uygulamaları",
    "Ön Değerlendirme Süreci",
    "Tema Sonu Değerlendirme",
    "(Ölçme ve Değerlendirme)",
    "ÖĞRETMEN YANSITMALARI",
    "ÖĞRENME KANITLARI",
    "İÇERİK ÇERÇEVESİ",
    "Anahtar Kavramlar",
    "Süreç Çerçevesi",
    "FARKLILAŞTIRMA",
    "Temel Kabuller",
    "Zenginleştirme",
    "Destekleme",
    "Köprü Kurma",
)
# Harf/rakam dışı her şey atılır: boşluk, tire, iki nokta VE tırnaklar - Docling
# düz tırnak ('Sözün'), pypdf kıvrımlı tırnak (“Sözün”) üretiyor.
_SQUASH_PATTERN = re.compile(r"[^\w]+")


def squash(text: str) -> str:
    """Harf ve rakam dışındaki her şeyi atar - Docling ile pypdf metnini hizalamak için."""

    return _SQUASH_PATTERN.sub("", text)


_SQUASHED_TITLES = tuple((squash(title), title) for title in INLINE_TITLES)
_LINE_KEY_CHARS = 24
_LINE_KEY_MIN_CHARS = 12


def locate_line(line: str, reference_squashed: str, cursor: int = 0) -> int:
    """Satırın (ilk ~24 sıkıştırılmış karakteri) pypdf akışındaki konumu; bulunamazsa -1.

    Önce `cursor`'dan itibaren (belge sırası), bulunamazsa baştan aranır.
    """

    key = squash(line)[:_LINE_KEY_CHARS]
    if len(key) < _LINE_KEY_MIN_CHARS:
        return -1
    position = reference_squashed.find(key, cursor)
    return position if position >= 0 else reference_squashed.find(key)


def first_locatable_position(text: str, reference_squashed: str, cursor: int = 0) -> int:
    """Parçanın akışta bulunabilen ilk satırının konumu; hiçbiri bulunamazsa -1."""

    for line in text.split("\n"):
        position = locate_line(line, reference_squashed, cursor)
        if position >= 0:
            return position
    return -1


def heading_precedes(heading: str, reference_squashed: str, position: int) -> bool:
    """Docling başlığı pypdf akışında parçadan ÖNCE geçiyor mu?

    Sayfa geçişinde Docling bir sonraki sayfanın etiketini ("Destekleme")
    önceki paragrafın devamına başlık yapabiliyor; akışta etiket paragraftan
    sonra geliyorsa o başlık bu parçaya ait değildir. Akışta hiç bulunmayan
    başlık (Docling'in kendi ürettiği/OCR) güvenilir sayılır.
    """

    key = squash(heading)
    if not key or position < 0:
        return True
    first = reference_squashed.find(key)
    return first < 0 or first <= position


def recover_inline_titles(text: str, reference_squashed: str, cursor: int = 0) -> tuple[str, int]:
    """Docling parçasındaki her satırın pypdf akışında hemen önünde duran etiketi geri koyar.

    `reference_squashed`: bölüm sayfalarının pypdf metni, `squash` ile
    sıkıştırılmış. Satır akışta `cursor`'dan itibaren aranır (bulunamazsa
    baştan); bulunduğu yerin hemen öncesi bir `INLINE_TITLES` etiketiyle
    bitiyorsa, satır o etiketle başlamıyorsa ve bir önceki çıktı satırı zaten
    o etiket değilse, etiket ayrı satır olarak öne eklenir. Dönüş
    `(yeni_metin, cursor)` - aynı bölümün sonraki parçaları için imleç
    ilerletilir (belge sırası).
    """

    lines_out: list[str] = []
    for line in text.split("\n"):
        position = locate_line(line, reference_squashed, cursor)
        if position >= 0:
            before = reference_squashed[max(0, position - 48):position]
            squashed_line = squash(line)
            previous = squash(lines_out[-1]) if lines_out else ""
            for squashed_title, title in _SQUASHED_TITLES:
                if (
                    before.endswith(squashed_title)
                    and not squashed_line.startswith(squashed_title)
                    and previous != squashed_title
                ):
                    lines_out.append(title)
                    break
            cursor = position
        lines_out.append(line)
    return "\n".join(lines_out), cursor


# Tek başına anlam taşımayan bant/başlık satırları: yalnız bunlardan oluşan
# parça (ör. "(Ölçme ve Değerlendirme)\nMetin Tahlili (Anlama)") dizine girmez.
_BANNER_LINE_PATTERN = re.compile(
    r"^\s*(Metin\s+Tahlili\s*\(Anlama\)|Edebiyat\s+Atölyesi\s*\(Anlatma\)|Dinleme/İzleme|Okuma|Konuşma|Yazma|"
    r"Okuma\s+ve\s+Dinleme/İzleme|Konuşma\s+ve\s+Yazma)\s*$"
)


def is_boilerplate_piece(text: str) -> bool:
    """Parça yalnız bölüm etiketi/beceri bandı satırlarından mı oluşuyor?"""

    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return True
    for line in lines:
        squashed = squash(line)
        if _BANNER_LINE_PATTERN.match(line) or any(squashed == title for title, _ in _SQUASHED_TITLES):
            continue
        return False
    return True


def section_kind_of_title(title: str) -> str | None:
    """Bir başlık/satır başı metnini bölüm türüne çevirir; eşleşmezse `None`."""

    stripped = title.strip()
    for pattern, kind in SECTION_TITLE_PATTERNS:
        if pattern.search(stripped):
            return kind
    return None


def split_at_inline_titles(text: str) -> list[str]:
    """Metni satır içi bölüm başlıklarından böler (ilk parça başlıksız olabilir).

    Yalnız etiketten oluşan bir parça (ör. geri yerleştirilmiş "ÖĞRENME KANITLARI"
    satırının hemen ardından "(Ölçme ve Değerlendirme)" gelmesi) tek başına
    kalmaz, bir sonraki parçanın başına yapıştırılır.
    """

    pieces = [piece.strip() for piece in _INLINE_TITLE_PATTERN.split(text)]
    pieces = [piece for piece in pieces if piece]
    glued: list[str] = []
    carry = ""
    for piece in pieces:
        if any(squash(piece) == squashed for squashed, _ in _SQUASHED_TITLES):
            carry = f"{carry}\n{piece}".strip() if carry else piece
            continue
        glued.append(f"{carry}\n{piece}" if carry else piece)
        carry = ""
    if carry:
        glued.append(carry)
    return glued


def looks_like_outcome_list(text: str) -> bool:
    """Metin ağırlıkla `TDE1.2. ...` kazanım başlığı satırlarından mı oluşuyor?"""

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    outcome_lines = sum(1 for line in lines if _OUTCOME_LINE_PATTERN.match(line))
    return outcome_lines >= 1 and outcome_lines / len(lines) >= 0.6


def is_continuation(text: str) -> bool:
    """Küçük harfle başlayan metin: önceki sayfadan sarkan paragraf devamı."""

    stripped = text.lstrip()
    return bool(stripped) and stripped[0].islower()


def extract_outcome_codes(headings: object, text: str = "") -> list[str]:
    """Başlıklar + metindeki üst kazanım kodları (`TDE1.2.3` -> `TDE1.2`), sıralı ve tekrarsız."""

    source = " ".join(str(heading) for heading in (headings or [])) + " " + str(text or "")
    codes = {f"TDE{major}.{minor}" for major, minor in _OUTCOME_CODE_PATTERN.findall(source)}
    return sorted(codes, key=lambda code: tuple(int(part) for part in code[3:].split(".")))


@dataclass
class SectionPiece:
    """Bölüm türü ve kodlarıyla etiketlenmiş parça metni (bir Docling parçası birden çok üretebilir)."""

    text: str
    section_kind: str | None
    outcome_codes: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    source_index: int = 0  # hangi girdi parçasından türedi (sayfa bilgisi oradan alınır)


def classify_sections(chunks: list[tuple[list[str], str]], initial_kind: str = "tema_giris") -> list[SectionPiece]:
    """Belge sırasındaki `(başlıklar, metin)` parçalarını bölüm türüyle etiketler.

    Durum makinesi: bir bölüm başlığı görülene kadar önceki tür sürer. Sinyal
    önceliği (1) metnin başındaki satır içi başlık, (2) Docling başlıkları -
    ama metin küçük harfle başlıyorsa (sayfa geçişi devamı) Docling başlığı
    GÜVENİLMEZ sayılır ve tür/kodlar önceki parçadan miras alınır (canlı
    bulgu: s.70'ten sarkan TDE3.x metni s.71'de "Destekleme" başlığını almıştı).
    Ağırlıkla `TDE1.2. ...` satırlarından oluşan parça, açık başlık yoksa
    "öğrenme çıktıları" sayılır (Docling o başlığı düşürüyor). Satır içi
    başlıkla başlayan alt metinler ayrı parça olur.
    """

    state = initial_kind
    last_codes: list[str] = []
    pieces: list[SectionPiece] = []
    for source_index, (headings, text) in enumerate(chunks):
        continuation = is_continuation(text)
        for index, piece_text in enumerate(split_at_inline_titles(text)):
            first_line = piece_text.split("\n", 1)[0]
            kind = section_kind_of_title(first_line)
            # Devam parçasının Docling başlığı yanlış sayfaya ait olabilir - taşınmaz.
            piece_headings = list(headings) if (index == 0 and not continuation) else []
            if kind is None and index == 0 and not continuation:
                for heading in headings:
                    kind = section_kind_of_title(str(heading))
                    if kind:
                        break
            if kind is None and looks_like_outcome_list(piece_text) and state in ("tema_giris", "programlar_arasi"):
                kind = "ogrenme_ciktilari"
            if kind is not None:
                state = kind
            codes = extract_outcome_codes([] if (continuation and index == 0) else piece_headings, piece_text)
            if continuation and index == 0 and not codes:
                codes = list(last_codes)
            pieces.append(
                SectionPiece(text=piece_text, section_kind=state, outcome_codes=codes, headings=piece_headings, source_index=source_index)
            )
            last_codes = codes
    return pieces


# --- Metin temizliği: satır sonu tiresi ve sahte boşluk ---------------------------------------

_WORD_CHARS = "A-Za-zÇĞİÖŞÜçğıöşüâîû"
_HYPHEN_BREAK_PATTERN = re.compile(rf"([{_WORD_CHARS}]{{2,}})\s*-\s*\n?\s*([a-zçğıöşüâîû][{_WORD_CHARS}]*)")
# Yalnız BÜYÜK harfli başlıklarda ("Y API", "HAY ATIN", "DÜNY ASI" - pypdf kerning
# artığı, tdeogr.pdf'te yalnız başlıklarda görüldü); sol parça en çok 4 harf.
# Küçük harfli düzyazıya dokunulmaz ("ve ya" -> "veya" gibi yanlış birleşme olmasın).
_UPPER_CHARS = "A-ZÇĞİÖŞÜ"
_SPURIOUS_SPACE_PATTERN = re.compile(rf"\b([{_UPPER_CHARS}]{{1,4}}) ([{_UPPER_CHARS}]{{2,}})\b")
_VOCAB_WORD_PATTERN = re.compile(rf"[{_WORD_CHARS}]{{3,}}")


def build_vocabulary(*texts: str) -> frozenset[str]:
    """Metinlerdeki (tiresiz) kelimelerin küçük harfli kümesi - birleştirme kararlarının sözlüğü."""

    words: set[str] = set()
    for text in texts:
        for word in _VOCAB_WORD_PATTERN.findall(text or ""):
            words.add(word.translate(_TURKISH_LOWER_MAP).lower())
    return frozenset(words)


def dehyphenate(text: str, vocabulary: frozenset[str]) -> str:
    """"sü - reci" / "düzen-⏎ledikleri" -> "süreci" / "düzenledikleri", YALNIZ birleşim sözlükteyse.

    Docling satır sonu tiresini metne taşıyor; gömme, reranker ve modelin
    birebir alıntısı için gürültü. Gerçek tireler ("sözlü - yazılı",
    "TDE3.1 - TDE3.2") korunur: sağ taraf küçük harfle başlamalı ve birleşik
    kelime belgede/katalogda başka yerde geçmeli.
    """

    def _join(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        joined = left + right
        if joined.translate(_TURKISH_LOWER_MAP).lower() in vocabulary:
            return joined
        return match.group(0)

    return _HYPHEN_BREAK_PATTERN.sub(_join, text)


def fix_spurious_spaces(text: str, vocabulary: frozenset[str]) -> str:
    """pypdf'in "Y API TAŞLARI" / "HAY ATIN" boşluğunu sözlük onayıyla kapatır."""

    def _join(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        joined = left + right
        lowered = joined.translate(_TURKISH_LOWER_MAP).lower()
        if lowered in vocabulary and left.translate(_TURKISH_LOWER_MAP).lower() not in vocabulary:
            return joined
        return match.group(0)

    return _SPURIOUS_SPACE_PATTERN.sub(_join, text)


# --- Süreç bileşenleri (s.20-27): kazanım başına parça -----------------------------------------

_RUNNING_HEADER_PATTERN = re.compile(
    r"^\s*(\d+|TÜRK DİLİ VE EDEBİYATI DERSİ ÖĞRETİM PROGRAMI|METİN TAHLİLİ|EDEBİYAT ATÖLYESİ|"
    r"DİNLEME/İZLEME|OKUMA|KONUŞMA|YAZMA)\s*$"
)
_OUTCOME_TITLE_PATTERN = re.compile(r"^\s*(TDE\d+\.\d+)\.\s+\S")
_COMPONENT_LINE_PATTERN = re.compile(r"^\s*[a-zçğıöşü]\)\s*TDE\d+\.\d+\.\d+\.")


@dataclass
class ComponentBlock:
    """Bir üst kazanımın süreç bileşenleri + göstergeleri (gerekirse bileşen sınırından bölünmüş)."""

    code: str
    title: str
    text: str
    pages: list[int]


def split_process_components(
    page_texts: list[tuple[int, str]], vocabulary: frozenset[str], max_chars: int = 1400
) -> list[ComponentBlock]:
    """Bileşen sayfalarının ham metnini (`[(sayfa, metin)]`) kazanım başına bloklara böler.

    Blok `TDE1.2. Anlam Oluşturabilme` başlığıyla açılır, sonraki başlığa kadar
    sürer; sayfa üstbilgileri ve beceri bant başlıkları atılır. `max_chars`
    aşılırsa blok `a) TDE1.2.1.` bileşen sınırlarından bölünür ve her alt
    bloğa kazanım başlığı yeniden yazılır (parça tek başına anlaşılır kalsın).
    """

    blocks: list[ComponentBlock] = []
    current: list[tuple[int, str]] = []
    current_code = ""

    def _close() -> None:
        if not current or not current_code:
            return
        title_line = current[0]
        groups: list[list[tuple[int, str]]] = [[]]
        for item in current[1:]:
            if _COMPONENT_LINE_PATTERN.match(item[1]) and groups[-1]:
                groups.append([])
            groups[-1].append(item)
        merged: list[list[tuple[int, str]]] = []
        for group in groups:
            if merged and sum(len(line) + 1 for _, line in merged[-1] + group) <= max_chars:
                merged[-1].extend(group)
            else:
                merged.append(list(group))
        for group in merged:
            lines = [title_line, *group]
            text = dehyphenate("\n".join(line for _, line in lines), vocabulary)
            blocks.append(
                ComponentBlock(code=current_code, title=title_line[1], text=text, pages=sorted({page for page, _ in lines}))
            )

    for page, page_text in page_texts:
        for raw_line in (page_text or "").splitlines():
            line = raw_line.strip()
            if not line or _RUNNING_HEADER_PATTERN.match(line):
                continue
            title_match = _OUTCOME_TITLE_PATTERN.match(line)
            if title_match:
                _close()
                current = [(page, line)]
                current_code = title_match.group(1)
                continue
            if current:
                current.append((page, line))
    _close()
    return blocks


# --- Gömme/bağlam ön eki ------------------------------------------------------------------------


def context_prefix(
    grade: str | None,
    theme_no: int | None,
    theme: str | None,
    section_kind: str | None,
    outcome_codes: list[str],
    skill_key: str | None,
    headings: list[str],
) -> str:
    """Parçanın gömülen/LLM'e giden hâlinin ilk satırı.

    Örnek: "9. Sınıf | 1. Tema: Sözün İnceliği | Öğrenme-Öğretme Yaşantıları | TDE2.2 | Okuma".
    Docling'in tek seviyeli başlık zinciri yerine belge yapısını taşır; ham
    `text` değişmez (doğrulayıcı `excerpt` hamdan gelir). Docling başlıkları
    ön ekte zaten geçen parçaları tekrar etmez.
    """

    parts: list[str] = []
    if grade:
        parts.append(f"{grade}. Sınıf" if grade.isdigit() else f"{grade.capitalize()} Sınıfı")
    if theme:
        parts.append(f"{theme_no}. Tema: {theme}" if theme_no else f"Tema: {theme}")
    if section_kind:
        parts.append(SECTION_LABELS.get(section_kind, section_kind))
    if outcome_codes:
        parts.append(", ".join(outcome_codes))
    skill_name = next((name for name in SKILL_HEADINGS if skill_match_key(name) == skill_key), None)
    if skill_name:
        parts.append(skill_name)
    seen = " | ".join(parts).translate(_TURKISH_LOWER_MAP).lower()
    for heading in headings:
        text = str(heading).strip()
        lowered = text.translate(_TURKISH_LOWER_MAP).lower()
        if text and lowered not in seen and not _OUTCOME_CODE_PATTERN.fullmatch(text):
            parts.append(text)
            seen += " | " + lowered
    return " | ".join(parts)
