"""MEB öğretim programı belgelerine özgü yapı bilgisi: belge adları, SINIF/TEMA
bölüm tespiti ve beceri anahtarları.

`ingestion_pipeline.py` bu modülle her parçaya `grade`/`theme`/`theme_key`/
`skill_key` payload alanlarını yazar; `rag_service.py` aynı anahtarlarla filtreler.
İki taraf da AYNI fonksiyonları kullanmalı - anahtar üretimi iki yerde
yazılırsa bir tarafın küçük bir farkı eşleşmeyi sessizce bozar.

Saf modül: stdlib + tembel `pypdf`; ML bağımlılığı yok, testler ağır kurulum
olmadan koşar.
"""

from __future__ import annotations

import io
import re

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
