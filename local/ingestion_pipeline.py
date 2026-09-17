"""MAHİR yerel çok kipli (multimodal) RAG indeksleme hattı.

Bir PDF'i şu adımlardan geçirip Qdrant'a yazar:

0. **Müfredat bölümleri (pypdf)** - MEB program PDF'lerinde "N. SINIF TEMALARI" ve
   "N. TEMA: AD" başlıkları bulunup belge SINIF×TEMA alt-PDF'lerine bölünür
   (`curriculum.py`); her parça `grade`/`theme`/`theme_key`/`skill_key` ile
   etiketlenir ki `rag_service.py` doğru sınıf/tema/beceriyle filtreleyebilsin.
   Desen yoksa belge tek, etiketsiz bölüm olarak işlenir.
1. **Docling (CPU)** - metin katmanı olan sayfaları hiyerarşik (başlık zinciri
   korunarak) ayrıştırır, tablo yapısını çıkarır; `HybridChunker` ile
   bge-m3 tokenizer'ına göre en çok `CHUNK_MAX_TOKENS` tokenlik parçalara böler.
2. **PaddleOCR-VL 1.6 (GPU)** - yalnız gerektiğinde:
   (a) metin katmanı olmayan ("taranmış") sayfalar bütün olarak VLM'den geçer,
       dönen Markdown yine Docling ile ayrıştırılıp aynı chunker'a girer;
   (b) metinli sayfalardaki görseller (şema, tablo resmi, ekran görüntüsü)
       kırpılıp VLM'e verilir; anlamlı metin çıkarsa ayrı bir parça olur.
   GPU belleği her çıkarımdan sonra boşaltılır, OOM'da görsel küçültülüp bir
   kez daha denenir, yine olmazsa o sayfa/görsel atlanır - iş çökmez.
3. **bge-m3 gömme (CPU)** - OCR modeli bellekten atıldıktan SONRA başlar.
4. **Qdrant** - koleksiyon yoksa oluşturulur; noktalar içerik adresli
   (uuid5) kimliklerle `upsert` edilir, yeniden indeksleme ikizlemez.

Kullanım:

    python local/ingestion_pipeline.py --pdf docs/tde2026.pdf --program-id tde-9-tymm --replace
        [--document-title "..."] [--start-page 65 --end-page 71] [--no-ocr] [--dry-run] [--show-chunks N]

Sayfa aralığı verilmezse programın indeks planı (`curriculum.INDEX_PLANS`)
uygulanır: tde-9-tymm için önce s.20-27 ortak süreç bileşenleri (kazanım
başına parça), sonra s.65-96 tema sayfaları. Her parça `section_kind` (tema
içi bölüm türü) ve `outcome_codes` taşır; gömülen metin "9. Sınıf | 1. Tema:
... | Öğrenme-Öğretme Yaşantıları | TDE2.2 | Okuma" ön ekiyle başlar.

`--document-title` belgenin RESMÎ adıdır, dosya adı değil - Qdrant payload'ına
yazılır ve oradan öğretmenin raporundaki kaynak gösterimine çıkar. Kayıtlı
programlar için `curriculum.DOCUMENT_TITLES`'tan çözülür; kayıtsız programda
zorunludur (sessiz geri düşüş yok - yanlış ad dizine girmeden yakalanmalı).

Tek iş parçacığından çalıştırılmak üzere yazıldı (CLI). PaddleOCR-VL pipeline'ı
farklı iş parçacıklarından çağrılınca PaddleX içinde çöküyor (bkz.
`backend/app/ocr_engine.py` modül docstring'i) - burada tüm OCR çağrıları zaten
ana iş parçacığında ve sıralı.
"""

from __future__ import annotations

import argparse
import gc
import inspect
import io
import logging
import os
import sys
import tempfile
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

# `python local/ingestion_pipeline.py` ile çalıştırıldığında sys.path[0] zaten
# bu dizin; başka bir cwd'den `python -m` ile çağrılırsa da bulunsun.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from curriculum import (  # noqa: E402 - sys.path yukarıda ayarlandı
    PageRange,
    build_vocabulary,
    classify_sections,
    context_prefix,
    dehyphenate,
    detect_grade_sections,
    detect_skill_key,
    detect_theme_sections,
    extract_outcome_codes,
    first_locatable_position,
    fix_spurious_spaces,
    heading_precedes,
    is_boilerplate_piece,
    recover_inline_titles,
    resolve_document_title,
    resolve_index_plan,
    split_process_components,
    squash,
    theme_match_key,
)
from rag_common import (  # noqa: E402
    CpuEmbedder,
    IngestionError,
    OcrError,
    RagConfigError,
    Settings,
    configure_logging,
    deterministic_point_id,
    ensure_collection,
    make_qdrant_client,
)

if TYPE_CHECKING:  # yalnız tip belirtimi
    from docling_core.types.doc import DoclingDocument
    from PIL import Image
    from qdrant_client import QdrantClient

logger = logging.getLogger("mahir.local.ingest")

MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024
UPSERT_BATCH_SIZE = 64
# Bir görselden OCR ile çıkan metin bundan az alfasayısal karakter taşıyorsa
# (logo, süs, boş kutu) parça üretilmez.
MIN_FIGURE_TEXT_CHARS = 20
# Taranmış sayfa render çözünürlüğü (pypdfium2 ölçeği: 1.0 = 72 dpi). ~200 dpi
# VLM için yeterli; `OCR_MAX_IMAGE_SIDE` yine de üst sınırı belirler.
SCANNED_PAGE_RENDER_SCALE = 200 / 72

SOURCE_TEXT = "text"
SOURCE_OCR_PAGE = "ocr_page"
SOURCE_OCR_FIGURE = "ocr_figure"
# Bundan kısa, cümle olmayan Docling parçası başlık artığı sayılır (bkz. HierarchicalChunker.chunk).
TINY_CHUNK_CHARS = 40


# --- Veri yapıları ----------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """Qdrant'a yazılacak tek parça (gömme öncesi)."""

    text: str
    contextualized_text: str
    headings: list[str]
    pages: list[int]  # orijinal PDF'te 1-indeksli sayfa numaraları
    source_kind: str
    chunk_index: int = -1  # tüm parçalar toplandıktan sonra tek sırada atanır
    # Müfredat yapısı (curriculum.py): SINIF/TEMA bölümünden gelir, beceri parçanın
    # kendi başlığından okunur. Desene uymayan belgede hepsi None kalır.
    grade: str | None = None
    theme: str | None = None
    skill_key: str | None = None
    # Tema içi bölüm türü (curriculum.SECTION_KINDS) ve parçada geçen üst
    # kazanım kodları - rag_service bunlarla bileşen parçasını kilitler.
    section_kind: str | None = None
    outcome_codes: list[str] = field(default_factory=list)

    @property
    def theme_key(self) -> str | None:
        return theme_match_key(self.theme) if self.theme else None

    def payload(self, document_name: str, program_id: str, ingested_at: str) -> dict[str, Any]:
        """Qdrant payload'ı - `rag_service.py` filtreleri bu anahtarlara bakar."""

        return {
            "text": self.text,
            "contextualized_text": self.contextualized_text,
            "document_name": document_name,
            "program_id": program_id,
            "pages": self.pages,
            "headings": self.headings,
            "chunk_index": self.chunk_index,
            "source_kind": self.source_kind,
            "grade": self.grade,
            "theme": self.theme,
            "theme_key": self.theme_key,
            "skill_key": self.skill_key,
            "section_kind": self.section_kind,
            "outcome_codes": list(self.outcome_codes),
            "ingested_at": ingested_at,
        }


@dataclass(frozen=True)
class CurriculumSection:
    """Belgenin SINIF × TEMA alt-PDF'i; `page_offset` + yerel sayfa = orijinal sayfa."""

    grade: str | None
    theme: str | None
    pdf_bytes: bytes = field(repr=False)
    page_offset: int
    page_count: int
    theme_no: int | None = None  # sınıf içindeki sıra (belgedeki "N. TEMA" numarası)

    @property
    def label(self) -> str:
        return " / ".join(part for part in (self.grade and f"{self.grade}. sınıf", self.theme) if part) or "belge"


@dataclass
class IngestionReport:
    """Bir indeksleme koşusunun özeti - CLI bunu basar, çağıran programlar okur."""

    document_name: str
    program_id: str
    collection: str
    dry_run: bool
    total_pages: int = 0
    page_ranges: list[tuple[int, int]] = field(default_factory=list)  # indekslenen orijinal sayfa aralıkları
    scanned_pages: list[int] = field(default_factory=list)
    ocr_failed_pages: list[int] = field(default_factory=list)
    figures_seen: int = 0
    figures_ocr: int = 0
    chunks_text: int = 0
    chunks_ocr_page: int = 0
    chunks_ocr_figure: int = 0
    points_written: int = 0
    warnings: list[str] = field(default_factory=list)
    durations_s: dict[str, float] = field(default_factory=dict)
    # Tespit edilen SINIF/TEMA bölümleri: (sınıf, tema, orijinal başlangıç, bitiş).
    sections: list[tuple[str | None, str | None, int, int]] = field(default_factory=list)
    # Bölüm türü -> parça sayısı (chunking kalitesinin hızlı göstergesi).
    section_kind_counts: dict[str, int] = field(default_factory=dict)
    # Üretilen parçalar (gömme öncesi hâliyle) - `--show-chunks` ve programatik
    # çağıranlar için; özet metnine girmez.
    chunks: list[ChunkRecord] = field(default_factory=list, repr=False)

    @property
    def chunk_count(self) -> int:
        return self.chunks_text + self.chunks_ocr_page + self.chunks_ocr_figure

    def summary(self) -> str:
        pages = ", ".join(f"{first}-{last}" for first, last in self.page_ranges) or f"1-{self.total_pages}"
        grades = sorted({grade for grade, _, _, _ in self.sections if grade})
        themes = [theme for _, theme, _, _ in self.sections if theme]
        lines = [
            f"Belge: {self.document_name} (program={self.program_id}, sayfa {pages})",
            f"Bölümler: {len(self.sections)}"
            + (f" (sınıf: {', '.join(grades)}; tema: {len(themes)})" if grades or themes else " (etiketsiz - müfredat deseni yok)"),
            f"Parçalar: {self.chunk_count} = metin {self.chunks_text} + taranmış sayfa {self.chunks_ocr_page} "
            f"+ görsel {self.chunks_ocr_figure}",
            "Bölüm türleri: "
            + (", ".join(f"{kind}={count}" for kind, count in sorted(self.section_kind_counts.items())) or "-"),
            f"Taranmış sayfalar: {self.scanned_pages or 'yok'}; görsel: {self.figures_ocr}/{self.figures_seen} OCR'landı",
            f"Qdrant: {'KURU ÇALIŞMA - yazılmadı' if self.dry_run else f'{self.points_written} nokta yazıldı'} "
            f"(koleksiyon {self.collection})",
            "Süreler: " + ", ".join(f"{name} {seconds:.1f}s" for name, seconds in self.durations_s.items()),
        ]
        if self.ocr_failed_pages:
            lines.append(f"OCR başarısız sayfalar: {self.ocr_failed_pages}")
        for warning in self.warnings:
            lines.append(f"UYARI: {warning}")
        return "\n".join(lines)


# --- PDF yardımcıları (pypdf) ------------------------------------------------------------


def slice_pdf_pages(pdf_bytes: bytes, start_page: int, end_page: int) -> bytes:
    """1-indeksli/dahil `[start_page, end_page]` aralığını bağımsız bir PDF'e kopyalar.

    Sayfa numaraları belge sınırları dışındaysa `IndexError` - çağıran yakalar.
    """

    from pypdf import PdfReader, PdfWriter  # noqa: PLC0415

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page_number in range(start_page, end_page + 1):
        writer.add_page(reader.pages[page_number - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def read_page_texts(pdf_bytes: bytes) -> list[str]:
    """Her sayfanın pypdf metin katmanı (1. sayfa -> indeks 0); bozuk sayfa boş string."""

    from pypdf import PdfReader  # noqa: PLC0415

    texts: list[str] = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - bozuk bir sayfa metin katmanı yok sayılsın, OCR karar versin
            texts.append("")
    return texts


def find_scanned_pages(pdf_bytes: bytes, min_text_chars: int) -> tuple[int, set[int]]:
    """`(toplam sayfa, metin katmanı olmayan 1-indeksli sayfalar)` döndürür.

    Ölçüt pypdf'in metin katmanından okuduğu karakter sayısı: taranmış bir
    sayfada 0'a yakındır, yalnız sayfa numarası/başlık taşıyan bir kapak da
    eşiğin altında kalıp OCR'a gidebilir - bu kabul edilebilir bir maliyet
    (VLM o sayfayı yine doğru okur).
    """

    texts = read_page_texts(pdf_bytes)
    scanned = {index for index, text in enumerate(texts, start=1) if len(text.strip()) < min_text_chars}
    return len(texts), scanned


def render_pdf_page(pdf_bytes: bytes, page_number: int, scale: float = SCANNED_PAGE_RENDER_SCALE) -> "Image.Image":
    """Tek sayfayı (1-indeksli) RGB PIL görseline çevirir (pypdfium2, docling bağımlılığı)."""

    import pypdfium2 as pdfium  # noqa: PLC0415

    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page = document[page_number - 1]
        return page.render(scale=scale).to_pil().convert("RGB")
    finally:
        # pypdfium2 4.x'te açık `close()` var, 5.x'te nesneler kendini kapatıyor.
        closer = getattr(document, "close", None)
        if callable(closer):
            closer()


# --- Docling ------------------------------------------------------------------------------


class DoclingParser:
    """PDF ve Markdown -> `DoclingDocument`. Modeller (layout, TableFormer) CPU'ya sabitlenir."""

    def __init__(self, threads: int) -> None:
        self._threads = threads
        self._pdf_converter: Any = None
        self._md_converter: Any = None

    def _build_pdf_converter(self) -> Any:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions  # noqa: PLC0415
        from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
        from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: PLC0415
        from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: PLC0415

        options = PdfPipelineOptions()
        # OCR Docling'de KAPALI: taranmış sayfalar ve görseller PaddleOCR-VL'ye
        # gidiyor (bkz. modül docstring'i). Docling'in kendi OCR'ı (RapidOCR)
        # hem gereksiz model indirir hem de metinli sayfalarda boş tur atar.
        options.do_ocr = False
        options.do_table_structure = True
        # Sayfa görselleri tutulmaz (100 sayfalık belgede ~1 GB RAM ederdi);
        # taranmış sayfalar `render_pdf_page` ile gerektiğinde ayrıca render
        # edilir. Görsel kırpıntıları (PictureItem.get_image) ise tutulur.
        options.generate_page_images = False
        options.generate_picture_images = True
        options.images_scale = 2.0  # 144 dpi kırpıntı - VLM için yeterli, RAM'i şişirmez
        options.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=self._threads)
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )

    def _build_md_converter(self) -> Any:
        from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
        from docling.document_converter import DocumentConverter  # noqa: PLC0415

        return DocumentConverter(allowed_formats=[InputFormat.MD])

    def convert_pdf(self, pdf_path: Path) -> "DoclingDocument":
        if self._pdf_converter is None:
            self._pdf_converter = self._build_pdf_converter()
        return self._pdf_converter.convert(str(pdf_path)).document

    def convert_markdown(self, markdown: str, name: str = "ocr_page.md") -> "DoclingDocument":
        """OCR çıktısını (Markdown) Docling belgesine çevirir - başlıklar korunur."""

        from docling.datamodel.base_models import DocumentStream  # noqa: PLC0415

        if self._md_converter is None:
            self._md_converter = self._build_md_converter()
        stream = DocumentStream(name=name, stream=io.BytesIO(markdown.encode("utf-8")))
        return self._md_converter.convert(stream).document


# --- Parçalama --------------------------------------------------------------------------------


def _pages_of_chunk(chunk: Any, page_offset: int) -> list[int]:
    """`chunk.meta.doc_items[i].prov[j].page_no` (alt-PDF'e göre 1-indeksli) + offset."""

    pages: set[int] = set()
    for doc_item in getattr(getattr(chunk, "meta", None), "doc_items", None) or []:
        for prov in getattr(doc_item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if isinstance(page_no, int):
                pages.add(page_no + page_offset)
    return sorted(pages)


class HierarchicalChunker:
    """Docling `HybridChunker` - başlık zincirini taşıyan, token sınırlı parçalar.

    Tokenizer gömme modelininki (bge-m3): parça sınırı, gömme modelinin
    gerçekten gördüğü token sayısına göre çizilir.
    """

    def __init__(self, tokenizer_model: str, max_tokens: int) -> None:
        self._tokenizer_model = tokenizer_model
        self._max_tokens = max_tokens
        self._chunker: Any = None

    def _get(self) -> Any:
        if self._chunker is None:
            from docling.chunking import HybridChunker  # noqa: PLC0415
            from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer  # noqa: PLC0415
            from transformers import AutoTokenizer  # noqa: PLC0415

            tokenizer = HuggingFaceTokenizer(
                tokenizer=AutoTokenizer.from_pretrained(self._tokenizer_model),
                max_tokens=self._max_tokens,
            )
            self._chunker = HybridChunker(tokenizer=tokenizer)
        return self._chunker

    def chunk(
        self,
        document: "DoclingDocument",
        page_offset: int,
        source_kind: str,
        fixed_pages: Sequence[int] | None = None,
    ) -> list[ChunkRecord]:
        """Belgeyi parçalar. `fixed_pages` verilirse (OCR'lı tek sayfa) sayfa bilgisi oradan gelir."""

        chunker = self._get()
        records: list[ChunkRecord] = []
        pending_headings: list[str] = []
        for chunk in chunker.chunk(dl_doc=document):
            text = (chunk.text or "").strip()
            if not text:
                continue
            headings = [str(heading) for heading in (getattr(chunk.meta, "headings", None) or [])]
            # Başlık artığı parça ("Temel Kabuller", 15 karakter, cümle değil): tek
            # başına gömülmez, bir sonraki parçanın başlık zincirine eklenir.
            if len(text) < TINY_CHUNK_CHARS and not text.endswith((".", "!", "?", ":")) and "\n" not in text:
                pending_headings.extend(heading for heading in [*headings, text] if heading not in pending_headings)
                continue
            merged_headings = [*pending_headings, *(heading for heading in headings if heading not in pending_headings)]
            pending_headings = []
            pages = list(fixed_pages) if fixed_pages is not None else _pages_of_chunk(chunk, page_offset)
            # `contextualized_text` burada geçici; `_ingest_section` bölüm etiketiyle
            # yapısal ön eki kurar (Docling'in `contextualize()` zinciri tek seviyeliydi).
            records.append(
                ChunkRecord(text=text, contextualized_text=text, headings=merged_headings, pages=pages, source_kind=source_kind)
            )
        return records


# --- PaddleOCR-VL (GPU) ---------------------------------------------------------------------


def _is_out_of_memory(error: BaseException) -> bool:
    """torch (`OutOfMemoryError`) ve paddle (mesajda "out of memory") OOM'larını tek yerde tanır."""

    name = error.__class__.__name__.lower()
    message = str(error).lower()
    return "outofmemory" in name or "out of memory" in message or "cuda error 2" in message


class VisionOcr:
    """PaddleOCR-VL 1.6 sarmalayıcısı - tembel yükleme, sıkı VRAM disiplini, context manager.

    Kullanım: `with VisionOcr(...) as ocr: ocr.page_to_markdown(img)`. `close()`
    pipeline'ı ve önbellekleri bırakır; gömme adımı bundan SONRA başlar ki 6 GB
    VRAM'de iki model üst üste binmesin (gömme CPU'da olsa da torch/paddle
    CUDA bağlamları ayakta kalmasın).
    """

    def __init__(self, device: str, engine: str, max_image_side: int) -> None:
        self._device = device
        self._engine = engine
        self._max_image_side = max_image_side
        self._pipeline: Any = None
        self.calls = 0
        self.oom_retries = 0

    def __enter__(self) -> "VisionOcr":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        # PaddleX her kurulumda çevrim içi model kaynaklarını yoklayıp dakikalarca
        # bekletebiliyor - .env'de de var ama import'tan önce burada da garanti.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCRVL  # noqa: PLC0415
            from paddlex.utils import deps as paddlex_deps  # noqa: PLC0415
        except ImportError as error:
            raise OcrError(
                "PaddleOCR-VL bu ortamda kurulu değil (paddleocr/paddlepaddle-gpu). "
                "local/requirements.txt'i kurun ya da --no-ocr ile çalıştırın."
            ) from error

        # `is_dep_available` lru_cache'li; paddlepaddle-gpu tam import edilmeden
        # bir kez çağrılmışsa olumsuz sonuç süreç boyunca yapışıyor (bkz.
        # backend/app/ocr_engine.py). Kullanmadan hemen önce temizle.
        paddlex_deps.is_dep_available.cache_clear()

        kwargs: dict[str, Any] = {
            "device": self._device,
            "engine": self._engine,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_chart_recognition": False,
        }
        # Sürüm seçici parametre paddleocr sürümüne göre var/yok - varsa 1.6'yı açıkça iste.
        try:
            if "pipeline_version" in inspect.signature(PaddleOCRVL.__init__).parameters:
                kwargs["pipeline_version"] = "v1.6"
        except (TypeError, ValueError):
            pass
        started = time.monotonic()
        logger.info("PaddleOCR-VL yükleniyor (device=%s, engine=%s)...", self._device, self._engine)
        try:
            self._pipeline = PaddleOCRVL(**kwargs)
        except Exception as error:  # noqa: BLE001 - CUDA/cuDNN/model indirme; hepsi aynı kullanıcı mesajı
            raise OcrError(f"PaddleOCR-VL başlatılamadı: {error}") from error
        logger.info("PaddleOCR-VL hazır (+%.1fs)", time.monotonic() - started)
        return self._pipeline

    @staticmethod
    def _release_vram() -> None:
        """Her çıkarımdan sonra: torch ve paddle önbelleklerini sürücüye geri ver."""

        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        try:
            import paddle  # noqa: PLC0415

            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - paddle yoksa/CPU derlemesiyse sessizce geç
            pass

    def _fit(self, image: "Image.Image", max_side: int) -> "Image.Image":
        from PIL import Image as PILImage  # noqa: PLC0415

        width, height = image.size
        longest = max(width, height)
        if longest <= max_side:
            return image
        ratio = max_side / float(longest)
        return image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))), PILImage.LANCZOS)

    def _predict_markdown(self, image: "Image.Image") -> str:
        """Görseli VLM'den geçirir, Markdown döndürür. OOM'da bir kez küçültüp yeniden dener."""

        pipeline = self._get_pipeline()
        attempts = (self._max_image_side, int(self._max_image_side * 0.7))
        last_error: BaseException | None = None
        for attempt, max_side in enumerate(attempts):
            fitted = self._fit(image, max_side)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                fitted.save(tmp, format="PNG")
                tmp_path = tmp.name
            try:
                results = list(pipeline.predict(tmp_path))
                self.calls += 1
                if not results:
                    return ""
                markdown = results[0].markdown
                text = markdown.get("markdown_texts", "") if isinstance(markdown, dict) else str(markdown)
                return str(text or "")
            except Exception as error:  # noqa: BLE001 - OOM mu, başka bir çıkarım hatası mı burada ayrılır
                last_error = error
                if not _is_out_of_memory(error) or attempt == len(attempts) - 1:
                    break
                self.oom_retries += 1
                logger.warning(
                    "GPU belleği yetmedi (%dx%d); önbellek boşaltılıp görsel %d px'e küçültülerek yeniden deneniyor.",
                    fitted.size[0], fitted.size[1], attempts[attempt + 1],
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)
                self._release_vram()
        assert last_error is not None
        if _is_out_of_memory(last_error):
            raise OcrError(
                "GPU belleği bu görsel için yetersiz (iki denemede de OOM). OCR_MAX_IMAGE_SIDE'ı düşürün."
            ) from last_error
        raise OcrError(f"OCR çıkarımı başarısız: {last_error}") from last_error

    def page_to_markdown(self, page_image: "Image.Image") -> str:
        """Taranmış tam sayfa -> Markdown (başlıklar, paragraflar, tablolar)."""

        return self._predict_markdown(page_image)

    def region_to_text(self, region_image: "Image.Image") -> str:
        """Görsel kırpıntısı -> düz metin/Markdown (şema etiketleri, tablo resmi vb.)."""

        return self._predict_markdown(region_image).strip()

    def close(self) -> None:
        """Pipeline'ı bırakır ve VRAM'i boşaltır (idempotent).

        Hiç yüklenmediyse (OCR açık ama taranmış sayfa/görsel çıkmadı) torch/
        paddle import edilmez - bölüm döngüsü bu yüzden bağlamı gönül rahatlığıyla
        her koşuda açabiliyor.
        """

        if self._pipeline is None:
            return
        logger.info("PaddleOCR-VL bellekten atılıyor (%d çıkarım, %d OOM yeniden denemesi)", self.calls, self.oom_retries)
        self._pipeline = None
        gc.collect()
        self._release_vram()


# --- Görsel toplama (metinli sayfalardaki resimler) -------------------------------------


@dataclass
class _Figure:
    page: int  # alt-PDF'e göre 1-indeksli
    headings: list[str]
    caption: str
    image: "Image.Image"


def _collect_figures(document: "DoclingDocument", min_side_px: int) -> tuple[int, list[_Figure]]:
    """Belgedeki resimleri, o anda geçerli başlık zinciriyle birlikte toplar.

    Başlık zinciri Docling'in okuma sırasından türetilir: her `SectionHeaderItem`
    kendi seviyesindeki başlığı günceller ve daha derinlerini temizler; resim
    geldiğinde zincirin o anki hâli ona yazılır. Dönüş: `(görülen, geçenler)`.
    """

    from docling_core.types.doc import PictureItem, SectionHeaderItem, TitleItem  # noqa: PLC0415

    heading_stack: dict[int, str] = {}
    figures: list[_Figure] = []
    seen = 0
    for item, _level in document.iterate_items():
        if isinstance(item, TitleItem):
            heading_stack = {0: item.text.strip()} if item.text.strip() else {}
            continue
        if isinstance(item, SectionHeaderItem):
            level = int(getattr(item, "level", 1) or 1)
            heading_stack = {depth: text for depth, text in heading_stack.items() if depth < level}
            if item.text.strip():
                heading_stack[level] = item.text.strip()
            continue
        if not isinstance(item, PictureItem):
            continue
        seen += 1
        prov = item.prov[0] if item.prov else None
        page = int(getattr(prov, "page_no", 0) or 0)
        if page < 1:
            continue
        try:
            image = item.get_image(document)
        except Exception as error:  # noqa: BLE001 - tek bir kırpıntı başarısızlığı belgeyi durdurmasın
            logger.debug("Resim kırpıntısı alınamadı (s.%d): %s", page, error)
            continue
        if image is None or min(image.size) < min_side_px:
            continue
        try:
            caption = (item.caption_text(document) or "").strip()
        except Exception:  # noqa: BLE001 - caption isteğe bağlı
            caption = ""
        figures.append(
            _Figure(
                page=page,
                headings=[heading_stack[key] for key in sorted(heading_stack)],
                caption=caption,
                image=image.convert("RGB"),
            )
        )
    return seen, figures


def _meaningful_text(text: str) -> bool:
    return sum(1 for char in text if char.isalnum()) >= MIN_FIGURE_TEXT_CHARS


# --- Ana akış ---------------------------------------------------------------------------------


class _Timer:
    def __init__(self, report: IngestionReport, name: str) -> None:
        self._report = report
        self._name = name
        self._started = 0.0

    def __enter__(self) -> "_Timer":
        self._started = time.monotonic()
        return self

    def __exit__(self, *_exc: object) -> None:
        # Toplanır: aynı aşama (docling/ocr) her SINIF×TEMA bölümü için bir kez koşar.
        elapsed = time.monotonic() - self._started
        self._report.durations_s[self._name] = round(self._report.durations_s.get(self._name, 0.0) + elapsed, 2)


def _validate_inputs(pdf_path: Path, document_name: str, program_id: str, start_page: int | None, end_page: int | None) -> None:
    if not pdf_path.is_file():
        raise IngestionError(f"PDF bulunamadı: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise IngestionError(f"Yalnız .pdf kabul edilir: {pdf_path.name}")
    if pdf_path.stat().st_size > MAX_PDF_SIZE_BYTES:
        raise IngestionError(f"PDF {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB sınırını aşıyor.")
    if not document_name.strip():
        raise IngestionError("document_name boş olamaz (belgenin resmî adı gerekli).")
    if not program_id.strip():
        raise IngestionError("program_id boş olamaz.")
    if (start_page is None) != (end_page is None):
        raise IngestionError("start_page ve end_page birlikte verilmeli.")
    if start_page is not None and end_page is not None and (start_page < 1 or end_page < start_page):
        raise IngestionError("Geçersiz sayfa aralığı.")


def _write_points(
    client: "QdrantClient",
    collection: str,
    records: Sequence[ChunkRecord],
    vectors: Sequence[Sequence[float]],
    document_name: str,
    program_id: str,
    replace: bool,
) -> int:
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct  # noqa: PLC0415

    if replace:
        client.delete(
            collection_name=collection,
            points_selector=Filter(must=[FieldCondition(key="program_id", match=MatchValue(value=program_id))]),
            wait=True,
        )
        logger.info("'%s' programına ait eski parçalar silindi.", program_id)

    ingested_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    points = [
        PointStruct(
            id=deterministic_point_id(program_id, document_name, record.chunk_index, record.text),
            vector=list(vector),
            payload=record.payload(document_name, program_id, ingested_at),
        )
        for record, vector in zip(records, vectors)
    ]
    for offset in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(collection_name=collection, points=points[offset : offset + UPSERT_BATCH_SIZE], wait=True)
    return len(points)


def split_curriculum_sections(
    pdf_bytes: bytes, page_offset: int, vocabulary: frozenset[str] = frozenset()
) -> list[CurriculumSection]:
    """PDF'i SINIF başlıklarına, her sınıfı TEMA başlıklarına göre alt-PDF'lere böler.

    Neden bölüyoruz: Docling'in başlık zinciri ve sayfa numaraları bölüm
    sınırlarını aşmasın, her parça hangi sınıf/temaya ait olduğunu kesin bilsin
    (`rag_service.py` filtreleri buna dayanır). Desen bulunmazsa tek, etiketsiz
    bölüm döner - müfredat dışı belgelerde davranış değişmez. `page_offset`,
    `pdf_bytes`'ın 1. sayfasının orijinal belgedeki (sayfa - 1) karşılığı.
    """

    sections: list[CurriculumSection] = []
    grade_sections = detect_grade_sections(pdf_bytes)
    for grade_label, grade_start, grade_end in grade_sections:
        grade_bytes = pdf_bytes if len(grade_sections) == 1 else slice_pdf_pages(pdf_bytes, grade_start, grade_end)
        grade_offset = page_offset + (grade_start - 1)
        theme_sections = detect_theme_sections(grade_bytes)
        for theme_no, (theme_name, theme_start, theme_end) in enumerate(theme_sections, start=1):
            section_bytes = grade_bytes if len(theme_sections) == 1 else slice_pdf_pages(grade_bytes, theme_start, theme_end)
            sections.append(
                CurriculumSection(
                    grade=grade_label,
                    # pypdf başlıkta sahte boşluk bırakabilir ("ANLAMIN Y API TAŞLARI"); `theme_key`
                    # boşluksuz olduğundan filtre etkilenmez, ama ön ek ve rapor düzgün görünsün.
                    theme=fix_spurious_spaces(theme_name, vocabulary) if theme_name else None,
                    pdf_bytes=section_bytes,
                    page_offset=grade_offset + (theme_start - 1),
                    page_count=theme_end - theme_start + 1,
                    theme_no=theme_no if theme_name else None,
                )
            )
    return sections


def _ingest_section(
    section: CurriculumSection,
    scanned: set[int],
    parser: DoclingParser,
    chunker: HierarchicalChunker,
    ocr: VisionOcr | None,
    settings: Settings,
    report: IngestionReport,
    vocabulary: frozenset[str] = frozenset(),
    reference_texts: Sequence[str] = (),
) -> list[ChunkRecord]:
    """Tek bir SINIF×TEMA bölümünü parçalar: Docling (CPU) + isteğe bağlı PaddleOCR-VL.

    `scanned`: bölüme göre 1-indeksli, metin katmanı olmayan sayfalar. Docling
    parçaları belge sırasında `curriculum.classify_sections`'tan geçer: satır
    içi bölüm başlıklarında bölünür, tür (`section_kind`) ve kazanım kodları
    etiketlenir, heceleme artıkları birleştirilir; gömülen metin yapısal ön ek
    (sınıf | tema | bölüm | kod | beceri) + ham metindir. Tek sayfa/görsel OCR
    hataları rapora uyarı olarak yazılır, bölüm çökmez.
    """

    page_offset = section.page_offset
    records: list[ChunkRecord] = []

    # Docling: metin katmanlı sayfalar + tablo yapısı + resim kırpıntıları.
    with _Timer(report, "docling"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(section.pdf_bytes)
            tmp_pdf = Path(tmp.name)
        try:
            try:
                document = parser.convert_pdf(tmp_pdf)
            except Exception as error:  # noqa: BLE001 - Docling üçüncü parti ML hattı
                raise IngestionError(f"PDF ayrıştırılamadı (Docling, {section.label}): {error}") from error
            try:
                text_records = chunker.chunk(document, page_offset, SOURCE_TEXT)
            except Exception as error:  # noqa: BLE001 - tokenizer indirme/chunker hatası
                raise IngestionError(f"Metin parçalanamadı ({section.label}): {error}") from error
        finally:
            tmp_pdf.unlink(missing_ok=True)
        # Taranmış sayfalara düşen (yalnız layout gürültüsü taşıyan) parçalar
        # elenir - o sayfaların içeriği aşağıda OCR'dan gelir.
        scanned_original = {page + page_offset for page in scanned}
        text_records = [
            record for record in text_records
            if not record.pages or not set(record.pages).issubset(scanned_original)
        ]
        # Bölüm etiketleme (curriculum.classify_sections): bir Docling parçası satır
        # içi başlıkta bölünüp birden çok kayıt üretebilir; sayfalar kaynaktan gelir.
        # Docling'in düşürdüğü satır içi etiketler pypdf akışından geri yerleştirilir
        # (curriculum.recover_inline_titles), sonra bölüm türleri etiketlenir.
        reference_squashed = squash("\n".join(reference_texts))
        aligned: list[tuple[list[str], str]] = []
        cursor = 0
        for record in text_records:
            text, headings = record.text, record.headings
            if reference_squashed:
                # Sayfa geçişinde bir sonraki sayfanın etiketi bu parçaya başlık
                # olmuşsa (akışta parçadan SONRA geçiyor) düşürülür.
                position = first_locatable_position(text, reference_squashed, cursor)
                headings = [heading for heading in headings if heading_precedes(heading, reference_squashed, position)]
                text, cursor = recover_inline_titles(text, reference_squashed, cursor)
            aligned.append((headings, text))
        pieces = [piece for piece in classify_sections(aligned) if not is_boilerplate_piece(piece.text)]
        for piece in pieces:
            origin = text_records[piece.source_index]
            text = dehyphenate(piece.text, vocabulary)
            skill_key = detect_skill_key([*piece.headings, *piece.outcome_codes], text)
            records.append(
                ChunkRecord(
                    text=text,
                    contextualized_text=text,
                    headings=piece.headings,
                    pages=origin.pages,
                    source_kind=SOURCE_TEXT,
                    skill_key=skill_key,
                    section_kind=piece.section_kind,
                    outcome_codes=piece.outcome_codes,
                )
            )
        report.chunks_text += len(pieces)
        logger.info("%s: Docling %d parça -> %d etiketli parça", section.label, len(text_records), len(pieces))

    # PaddleOCR-VL (GPU): taranmış sayfalar bütün olarak, metinli sayfalardaki resimler kırpılarak.
    if ocr is not None:
        with _Timer(report, "ocr"):
            figures_seen, figures = _collect_figures(document, settings.ocr_min_figure_side_px)
            figures = [figure for figure in figures if figure.page not in scanned]
            report.figures_seen += figures_seen
            for page in sorted(scanned):
                original_page = page + page_offset
                try:
                    image = render_pdf_page(section.pdf_bytes, page)
                    markdown = ocr.page_to_markdown(image)
                    if not markdown.strip():
                        report.warnings.append(f"s.{original_page}: OCR boş döndü.")
                        continue
                    page_document = parser.convert_markdown(markdown, name=f"page_{original_page}.md")
                    page_records = chunker.chunk(page_document, 0, SOURCE_OCR_PAGE, fixed_pages=[original_page])
                except OcrError as error:
                    report.ocr_failed_pages.append(original_page)
                    report.warnings.append(f"s.{original_page}: {error}")
                    logger.warning("s.%d OCR atlandı: %s", original_page, error)
                    continue
                except Exception as error:  # noqa: BLE001 - render/markdown dönüşümü; sayfa atlanır
                    report.ocr_failed_pages.append(original_page)
                    report.warnings.append(f"s.{original_page}: işlenemedi ({error}).")
                    logger.warning("s.%d işlenemedi: %s", original_page, error)
                    continue
                records.extend(page_records)
                report.chunks_ocr_page += len(page_records)
                logger.info("s.%d OCR: %d parça", original_page, len(page_records))

            for figure in figures:
                original_page = figure.page + page_offset
                try:
                    text = ocr.region_to_text(figure.image)
                except OcrError as error:
                    report.warnings.append(f"s.{original_page} görsel: {error}")
                    logger.warning("s.%d görsel OCR atlandı: %s", original_page, error)
                    continue
                if not _meaningful_text(text):
                    continue
                report.figures_ocr += 1
                context_lines = [*figure.headings]
                if figure.caption:
                    context_lines.append(figure.caption)
                body = f"[Görsel, s.{original_page}]" + (f" {figure.caption}\n" if figure.caption else "\n") + text
                records.append(
                    ChunkRecord(
                        text=body,
                        contextualized_text="\n".join([*context_lines, body]) if context_lines else body,
                        headings=figure.headings,
                        pages=[original_page],
                        source_kind=SOURCE_OCR_FIGURE,
                    )
                )
                report.chunks_ocr_figure += 1

    for record in records:
        record.grade = section.grade
        record.theme = section.theme
        if record.source_kind != SOURCE_TEXT:  # OCR kayıtları etiketlemeden geçmedi
            record.outcome_codes = extract_outcome_codes(record.headings, record.text)
            record.skill_key = detect_skill_key([*record.headings, *record.outcome_codes], record.text)
        prefix = context_prefix(
            section.grade, section.theme_no, section.theme, record.section_kind,
            record.outcome_codes, record.skill_key, record.headings,
        )
        record.contextualized_text = f"{prefix}\n{record.text}" if prefix else record.text
        report.section_kind_counts[record.section_kind or "-"] = report.section_kind_counts.get(record.section_kind or "-", 0) + 1
    return records


def _ingest_components(
    page_texts: list[str], page_range: PageRange, vocabulary: frozenset[str], settings: Settings, report: IngestionReport
) -> list[ChunkRecord]:
    """Ortak "Öğrenme Çıktıları ve Süreç Bileşenleri" sayfalarını kazanım başına parçalar.

    Docling değil pypdf metni: bölüm düz satır yapısında (`TDE1.2. ...` /
    `a) TDE1.2.1. ...` / göstergeler), tablo yok; satır tabanlı bölücü kesin
    sınır verir. Parçalar sınıf/tema taşımaz (tüm sınıflar için ortak) -
    `rag_service` bunları `section_kind` + `outcome_codes` ile getirir.
    """

    texts = [(page, page_texts[page - 1]) for page in range(page_range.start_page, page_range.end_page + 1)]
    # ~3,5 karakter/token: tavan `CHUNK_MAX_TOKENS` ile aynı ölçekte kalsın.
    blocks = split_process_components(texts, vocabulary, max_chars=int(settings.chunk_max_tokens * 3.5))
    records: list[ChunkRecord] = []
    for block in blocks:
        text = fix_spurious_spaces(block.text, vocabulary)
        skill_key = detect_skill_key([block.code], text)
        prefix = context_prefix(None, None, None, "surec_bilesenleri", [block.code], skill_key, [])
        records.append(
            ChunkRecord(
                text=text,
                contextualized_text=f"{prefix}\n{text}",
                headings=[block.title],
                pages=block.pages,
                source_kind=SOURCE_TEXT,
                skill_key=skill_key,
                section_kind="surec_bilesenleri",
                outcome_codes=[block.code],
            )
        )
    report.chunks_text += len(records)
    report.section_kind_counts["surec_bilesenleri"] = report.section_kind_counts.get("surec_bilesenleri", 0) + len(records)
    codes = sorted({record.outcome_codes[0] for record in records})
    logger.info("Süreç bileşenleri s.%d-%d: %d parça, %d kazanım kodu", page_range.start_page, page_range.end_page, len(records), len(codes))
    return records


def _resolve_page_ranges(program_id: str, start_page: int | None, end_page: int | None, total_pages: int) -> list[PageRange]:
    """Elle aralık > program planı > tüm belge."""

    if start_page is not None and end_page is not None:
        return [PageRange(start_page, end_page)]
    plan = resolve_index_plan(program_id)
    if plan:
        return list(plan)
    return [PageRange(1, total_pages)]


def ingest_pdf(
    settings: Settings,
    pdf_path: Path,
    document_name: str,
    program_id: str,
    start_page: int | None = None,
    end_page: int | None = None,
    replace: bool = False,
    ocr_enabled: bool | None = None,
    dry_run: bool = False,
) -> IngestionReport:
    """Bir PDF'i (isteğe bağlı sayfa aralığıyla) ayrıştırır, gömer ve Qdrant'a yazar.

    Hatalar `IngestionError` (giriş/ayrıştırma/gömme/yazım) ya da `RagConfigError`
    olarak yükselir; OCR'da tek sayfa/görsel hataları ise rapora uyarı olarak
    yazılıp atlanır. `dry_run=True` gömme ve Qdrant adımlarını atlar (GPU'suz
    makinede parçalamayı görmek için).
    """

    document_name = document_name.strip()
    program_id = program_id.strip()
    _validate_inputs(pdf_path, document_name, program_id, start_page, end_page)
    use_ocr = settings.ocr_enabled if ocr_enabled is None else ocr_enabled
    report = IngestionReport(
        document_name=document_name,
        program_id=program_id,
        collection=settings.qdrant_collection,
        dry_run=dry_run,
    )

    # 1) Kapsam: aralıklar (elle verilen tek aralık, yoksa programın indeks planı,
    #    yoksa tüm belge); taranmış sayfalar metin katmanından; SINIF/TEMA
    #    bölümleri (desen yoksa tek bölüm); heceleme/boşluk düzeltme sözlüğü.
    with _Timer(report, "hazırlık"):
        pdf_bytes = pdf_path.read_bytes()
        try:
            page_texts = read_page_texts(pdf_bytes)
            ranges = _resolve_page_ranges(program_id, start_page, end_page, len(page_texts))
            if any(r.start_page < 1 or r.end_page > len(page_texts) or r.end_page < r.start_page for r in ranges):
                raise IndexError("aralık")
            vocabulary = build_vocabulary(*page_texts)
            theme_ranges = [r for r in ranges if r.kind != "surec_bilesenleri"]
            sections_by_range: list[tuple[PageRange, list[CurriculumSection]]] = []
            for page_range in theme_ranges:
                whole = page_range.start_page == 1 and page_range.end_page == len(page_texts)
                scoped_bytes = pdf_bytes if whole else slice_pdf_pages(pdf_bytes, page_range.start_page, page_range.end_page)
                sections_by_range.append((page_range, split_curriculum_sections(scoped_bytes, page_range.start_page - 1, vocabulary)))
        except IndexError as error:
            raise IngestionError("Sayfa aralığı belgenin sınırları dışında.") from error
        except Exception as error:  # noqa: BLE001 - pypdf üçüncü parti; bozuk PDF açık mesajla dönmeli
            raise IngestionError(f"PDF sayfaları okunamadı: {error}") from error
        report.page_ranges = [(r.start_page, r.end_page) for r in ranges]
        report.total_pages = sum(r.end_page - r.start_page + 1 for r in ranges)
        in_theme_pages = {page for r in theme_ranges for page in range(r.start_page, r.end_page + 1)}
        report.scanned_pages = sorted(
            page for page, text in enumerate(page_texts, start=1)
            if page in in_theme_pages and len(text.strip()) < settings.ocr_min_text_chars_per_page
        )
        report.sections = [
            (section.grade, section.theme, section.page_offset + 1, section.page_offset + section.page_count)
            for _, sections in sections_by_range
            for section in sections
        ]
        if report.scanned_pages and not use_ocr:
            report.warnings.append(
                f"{len(report.scanned_pages)} sayfada metin katmanı yok ama OCR kapalı - bu sayfalar dizine girmeyecek."
            )
        logger.info(
            "%s: %d sayfa (aralık %s), %d bölüm, taranmış: %s", pdf_path.name, report.total_pages,
            ", ".join(f"{a}-{b}" for a, b in report.page_ranges), len(report.sections), report.scanned_pages or "yok",
        )
        for grade, theme, first, last in report.sections:
            if grade or theme:
                logger.info("  bölüm: sınıf=%s tema=%s sayfa %d-%d", grade, theme, first, last)

    # 2-3) Bileşen aralığı pypdf ile; tema bölümleri Docling (CPU) + PaddleOCR-VL
    #      (GPU). OCR modeli bölümler boyunca tembel yüklenir, tek kez; `with`
    #      biterken bırakılır - gömme VRAM boşaldıktan sonra başlar.
    records: list[ChunkRecord] = []
    with _Timer(report, "bileşenler"):
        for page_range in ranges:
            if page_range.kind == "surec_bilesenleri":
                records.extend(_ingest_components(page_texts, page_range, vocabulary, settings, report))
    parser = DoclingParser(threads=settings.resolved_threads(settings.docling_threads))
    chunker = HierarchicalChunker(settings.embedding_model, settings.chunk_max_tokens)
    scanned_original = set(report.scanned_pages)
    ocr_context = (
        VisionOcr(settings.ocr_device, settings.ocr_engine, settings.ocr_max_image_side) if use_ocr else nullcontext(None)
    )
    with ocr_context as ocr:
        for _, sections in sections_by_range:
            for section in sections:
                first, last = section.page_offset + 1, section.page_offset + section.page_count
                section_scanned = {page - section.page_offset for page in scanned_original if first <= page <= last}
                records.extend(
                    _ingest_section(
                        section, section_scanned, parser, chunker, ocr, settings, report, vocabulary,
                        reference_texts=page_texts[first - 1:last],
                    )
                )
    if use_ocr:
        logger.info(
            "OCR: %d taranmış sayfa, %d/%d görsel -> %d + %d parça",
            len(report.scanned_pages), report.figures_ocr, report.figures_seen, report.chunks_ocr_page, report.chunks_ocr_figure,
        )

    if not records:
        raise IngestionError("Belgeden okunabilir içerik çıkarılamadı.")
    for index, record in enumerate(records):
        record.chunk_index = index
    report.chunks = records

    if dry_run:
        logger.info("Kuru çalışma: gömme ve Qdrant yazımı atlandı (%d parça).", len(records))
        return report

    # 4) Gömme (CPU) - OCR modeli bellekten atıldıktan sonra.
    embedder = CpuEmbedder(
        settings.embedding_model,
        device=settings.embedding_device,
        threads=settings.embedding_threads,
        batch_size=settings.embedding_batch_size,
    )
    with _Timer(report, "gömme"):
        try:
            vectors = embedder.embed_documents([record.contextualized_text for record in records], show_progress=True)
        except Exception as error:  # noqa: BLE001 - model indirme/torch hatası tek mesajla dönmeli
            raise IngestionError(f"Metin parçaları gömülemedi: {error}") from error
        logger.info("Gömme: %d vektör (%d-d)", len(vectors), len(vectors[0]) if vectors else 0)

    # 5) Qdrant yazımı.
    with _Timer(report, "qdrant"):
        client = make_qdrant_client(settings)
        try:
            try:
                ensure_collection(client, settings.qdrant_collection, embedder.dimension)
                report.points_written = _write_points(
                    client, settings.qdrant_collection, records, vectors, document_name, program_id, replace
                )
            except IngestionError:
                raise
            except Exception as error:  # noqa: BLE001 - bağlantı/yazım hatası; kullanıcıya ipucuyla dön
                raise IngestionError(
                    f"Qdrant'a yazılamadı ({error.__class__.__name__}: {error}). Sunucu çalışıyor mu? "
                    "`docker compose -f local/docker-compose.yml up -d`"
                ) from error
        finally:
            client.close()
        logger.info("Qdrant: %d nokta yazıldı (%s)", report.points_written, settings.qdrant_collection)

    return report


# --- CLI --------------------------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingestion_pipeline.py",
        description="PDF'i Docling + PaddleOCR-VL ile ayrıştırıp bge-m3 ile gömer ve Qdrant'a yazar.",
    )
    parser.add_argument("--pdf", required=True, type=Path, help="İndekslenecek PDF dosyası")
    parser.add_argument("--program-id", required=True, help="Parçaların etiketi (ör. tde-9-tymm)")
    parser.add_argument(
        "--document-title",
        default=None,
        help="Belgenin RESMÎ adı (kaynak gösteriminde görünür). curriculum.py DOCUMENT_TITLES'ta kayıtlı "
        "program için isteğe bağlı, diğerlerinde zorunlu.",
    )
    parser.add_argument("--start-page", type=int, default=None, help="1-indeksli başlangıç sayfası (dahil)")
    parser.add_argument("--end-page", type=int, default=None, help="1-indeksli bitiş sayfası (dahil)")
    parser.add_argument("--replace", action="store_true", help="Önce bu program_id'ye ait eski parçaları sil")
    parser.add_argument("--no-ocr", action="store_true", help="PaddleOCR-VL'yi hiç yükleme (GPU'suz makine)")
    parser.add_argument("--dry-run", action="store_true", help="Yalnız ayrıştır+parçala; gömme ve Qdrant yok")
    parser.add_argument("--show-chunks", type=int, default=0, metavar="N", help="İlk N parçayı stdout'a bas")
    parser.add_argument("--env-file", type=Path, default=None, help="Varsayılan local/.env yerine başka .env")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING (varsayılan .env LOG_LEVEL)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        settings = Settings.from_env(dotenv_path=args.env_file) if args.env_file else Settings.from_env()
        configure_logging(args.log_level or settings.log_level)
    except RagConfigError as error:
        print(f"Yapılandırma hatası: {error}", file=sys.stderr)
        return 2

    logger.info("Ayarlar: %s", settings.dotenv_path or "(.env yok, varsayılanlar)")
    try:
        document_title = resolve_document_title(args.program_id.strip(), args.document_title)
    except ValueError as error:
        logger.error("%s", error)
        return 1
    try:
        report = ingest_pdf(
            settings,
            pdf_path=args.pdf,
            document_name=document_title,
            program_id=args.program_id,
            start_page=args.start_page,
            end_page=args.end_page,
            replace=args.replace,
            ocr_enabled=False if args.no_ocr else None,
            dry_run=args.dry_run,
        )
    except (IngestionError, RagConfigError) as error:
        logger.error("%s", error)
        return 1
    except KeyboardInterrupt:
        logger.error("Kullanıcı durdurdu.")
        return 130

    print()
    print(report.summary())
    if args.show_chunks > 0:
        for record in report.chunks[: args.show_chunks]:
            print(
                f"\n--- [{record.chunk_index}] {record.source_kind} sayfa={record.pages} "
                f"başlıklar={record.headings} ---"
            )
            print(record.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
