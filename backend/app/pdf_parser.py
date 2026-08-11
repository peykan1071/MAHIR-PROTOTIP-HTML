"""Read native tables from text-based PDF score documents."""

from __future__ import annotations

import io

from .table_parser import parse_tabular_document


def parse_score_pdf(content: bytes) -> dict[str, object]:
    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError("PDF okuma bileşeni kurulu değil. 'pip install pdfplumber' komutunu çalıştırınız.") from error

    try:
        with pdfplumber.open(io.BytesIO(content)) as document:
            tables = [table for page in document.pages for table in page.extract_tables() if table]
            has_text = any((page.extract_text() or "").strip() for page in document.pages)
    except Exception as error:
        raise ValueError("PDF belgesi açılamadı veya geçerli bir PDF değil.") from error

    if not tables:
        if has_text:
            raise ValueError("PDF metni okunabildi ancak öğrenci puan tablosunun hücreleri ayırt edilemedi.")
        raise ValueError("PDF taranmış görüntü biçiminde; sayfaların OCR ile okunması gerekir.")
    return parse_tabular_document(tables, source_label="PDF belgesi")
