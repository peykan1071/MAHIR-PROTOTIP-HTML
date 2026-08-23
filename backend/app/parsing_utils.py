"""Belge tablosu ayrıştırıcılarının (docx_parser, table_parser) paylaştığı yardımcılar.

Word ve PDF/Excel okuyucuları aynı Türkçe başlık normalizasyonu, sayı ayrıştırma
ve soru-numarası tanıma mantığını birbirinden bağımsız olarak taşıyordu; bu
modül o tekrarı tek yere indirger. Davranış değişmedi - fonksiyonlar iki
dosyadaki karşılıklarıyla birebir aynı.
"""

from __future__ import annotations

import re

# Rapor edilen toplam ile hesaplanan toplam arasındaki kabul edilebilir fark.
# docx_parser ve table_parser'da ayrı ayrı tanımlıydı, aynı değeri taşıyordu.
TOTAL_MISMATCH_TOLERANCE = 0.01


def normalise_label(value: object) -> str:
    """Türkçe başlık metnini karşılaştırılabilir küçük harfli forma indirger."""

    translation = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")
    return re.sub(r"[^a-z0-9]+", " ", str(value).translate(translation).casefold()).strip()


def parse_number(value: object) -> float | int | None:
    """Hücre metninden sayı çıkar (virgüllü ondalık, gömülü metin toleranslı)."""

    cleaned = str(value).strip().replace(",", ".")
    if not cleaned:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def parse_integer(value: object) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def calculate_total(scores: list) -> float:
    """Boş/eksik hücreleri 0 sayarak öğrencinin toplam puanını hesapla."""

    return round(sum(score or 0 for score in scores), 2)


def question_number(label: str) -> int | None:
    """Normalize edilmiş bir başlıktan ('soru 3' gibi) soru numarasını çıkar."""

    match = re.match(r"^(?:s|soru)\s*(\d+)\b", label)
    return int(match.group(1)) if match else None
