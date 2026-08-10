"""Türkçe belgeler için RAG sistemini Modal'da (GPU, sıfıra ölçeklenen
serverless) çalıştırır. Bağımsız bir Modal App'tir ("turkish-rag-system"),
`modal_app.py` (OCR işçisi) ile aynı desende ama ondan tamamen habersiz -
ikisi ayrı ayrı dağıtılır, birbirini etkilemez.

Dağıtım: `modal deploy rag_service.py` (repo kökünden).

Neden iki ayrı Image (indexing_image / inference_image): PDF ayrıştırma
(Docling) ve LLM sunumu (vLLM) çok farklı ve ağır bağımlılık ağaçlarına
sahiptir (ikisi de kendi `torch` sürümünü ister). Aynı image içinde
dördünü (docling + qdrant-client + sentence-transformers + vllm) birlikte
çözümlemeye zorlamak gereksiz bir çakışma riski yaratır. `index_pdf`
yalnızca `indexing_image`'i, `RAGInference` yalnızca `inference_image`'i
kullanır; ikisi de aynı iki Volume'u ("rag-storage", "rag-hf-cache")
paylaşır.

Bu dosya kasıtlı olarak `backend/app/`e değil (o paket %100 stdlib kalır -
bkz. `ocr_engine.py`nin ağır importları hep fonksiyon içine erteleyen
düzeni), `modal_app.py` ile aynı köke konur - hiçbir mevcut backend
dosyası bunu import etmez. Dağıtılmış servise ayrı bir betikten nasıl
erişileceği dosya sonundaki örnekte gösterilir.

Bilinen sınırlama (öne çıkan): Qdrant'ın yerel (embedded) modu tek
yazarlıdır - `RAGInference` sıcak konteyner tutarken (scaledown_window=300)
eşzamanlı bir `index_pdf` çağrısı kilit hatası alabilir. Bkz. `index_pdf`
ve `RAGInference.close` içindeki yorumlar.
"""

from __future__ import annotations

import hmac
import io
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import modal

if TYPE_CHECKING:
    # Yalnızca tip belirtimi için - `from __future__ import annotations` sayesinde
    # bu importlar çalışma zamanında hiç değerlendirilmez, bu yüzden bu dosya
    # (Modal dışında) hiçbir ağır bağımlılık kurulu olmadan da import edilebilir.
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer
    from vllm import LLM

try:
    from fastapi import Request
    from fastapi.responses import JSONResponse
except ImportError:  # yalnızca "pip install modal" yapılmış yerel makinede olabilir -
    # @modal.fastapi_endpoint yalnızca konteyner İÇİNDE gerçekten çağrılır
    # (inference_image, fastapi'yi vllm üzerinden zaten transitive içerir).
    # `from __future__ import annotations` sayesinde bu adlar yalnızca
    # RAGInference.web_query'nin imza belirtiminde string olarak kalır -
    # burada gerçek bir sınıf olmaları şart değil.
    Request = object  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]

APP_NAME = "turkish-rag-system"

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

QDRANT_MOUNT_DIR = "/data"
QDRANT_STORAGE_PATH = "/data/qdrant_db"
QDRANT_COLLECTION_NAME = "mahir_rag_chunks"

HF_CACHE_DIR = "/root/.cache/huggingface"

CHUNK_MAX_TOKENS = 512
DEFAULT_TOP_K = 5
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # backend/app/file_receiver.py ile aynı sınır

# MEB müfredat PDF'lerindeki hiyerarşi başlıkları - tdeogr.pdf üzerinde tüm
# 5 sınıf düzeyi ve 20 sınıf×tema kombinasyonu için elle doğrulandı. Satırın
# TAMAMINI kaplayan bağımsız bir metin satırı arıyoruz (`^...$`, MULTILINE) -
# bu, İçindekiler'deki aynı metni (satır sonunda sayfa numarasıyla birlikte
# geldiği için `$` ile eşleşmiyor) doğal olarak eler. Desenler eşleşmezse
# index_pdf SINIF/tema-bölme adımını atlar - yalnızca bu belge yapısına özgü
# kalır, genel kod bozulmaz.
GRADE_HEADING_PATTERN = re.compile(r"^\s*(HAZIRLIK SINIFI TEMALARI|\d+\.\s*SINIF TEMALARI)\s*$", re.MULTILINE)
TEMA_HEADING_PATTERN = re.compile(r"^\s*\d+\.\s*TEMA\s*:\s*(.+?)\s*$", re.MULTILINE)

# Öğrenme Analitiği / Bloom taksonomisi tabanlı teşhis prompt'u - yalnızca
# TEŞHİS (kanıtlarıyla eksiklik/risk tespiti), asla ÇÖZÜM/YÖNTEM önerisi değil
# (DEVELOPMENT_CHARTER.md: "MAHİR ... öğretim yöntemi veya telafi programı
# önermez"). Çıktı biçimi kasıtlı olarak tek akıcı paragraf - rapor tarafında
# bu metin tek bir tablo hücresine yazılıyor (mahir-report-export-common.js
# normalizeText() tüm satır sonlarını tek boşluğa indirger), bu yüzden
# başlık/madde işareti/markdown biçimlendirmesi burada anlamsız olurdu.
SYSTEM_PROMPT = (
    "Sen; Öğrenme Analitiği, Veri Odaklı Ölçme-Değerlendirme ve Program "
    "Geliştirme alanlarında uzmanlaşmış kıdemli bir Eğitim Analistisin. "
    "Görevin: sana BAĞLAM olarak verilen referans müfredat metni ile "
    "kazanıma ait başarı oranını çapraz analiz ederek, bu kazanıma özgü "
    "öğrenme eksikliğini, risk düzeyini ve bilişsel tıkanma noktasını "
    "kanıta dayalı ve eleştirel bir gözle teşhis etmektir.\n\n"
    "TEMEL İLKELER:\n"
    "1) Teşhisini yalnızca BAĞLAM'a, SORU'da verilen kazanım metnine ve "
    "başarı oranına dayandır; sınav sorusunun tam metnini veya ders kitabını "
    "görmediğini unutma, soru içeriği hakkında spekülasyon yapma. BAĞLAM sana "
    "zaten ders, sınıf düzeyi ve tema filtresinden geçirilerek verilir - yani "
    "önüne gelen metin HER ZAMAN sorulan kazanımın ait olduğu temaya aittir. "
    "Kazanımın bilişsel düzeyini, SORU'daki kazanım metninin fiilinden "
    "(ör. \"yönetebilme\", \"anlam oluşturabilme\", \"karşılaştırabilme\", "
    '"değerlendirebilme") ve BAĞLAM\'daki açıklamalardan ÇIKARMAKLA '
    "YÜKÜMLÜSÜN; bilişsel düzey BAĞLAM'da açıkça \"Bloom\" etiketiyle "
    "yazmıyor diye teşhisten kaçınma. Yalnızca BAĞLAM bu kazanıma dair "
    "hiçbir bilgi içermiyorsa, YANITININ TAMAMI OLARAK yalnızca şu cümleyi "
    'yaz ve başka HİÇBİR ŞEY ekleme: "Bu bilgi belgede bulunmuyor." Bu '
    "cümleyi yazdıysan, ardından teşhis/kıyas eklemeye devam ETME; teşhis "
    "yazacaksan da bu cümleyi hiç kullanma.\n"
    "2) Eleştirel ve gerçekçi ol: yüzeysel teselliler (\"geçerli bir puan\", "
    '"gelişime açık" gibi yuvarlak ifadeler) yasak. Düşük başarı oranını '
    "doğrudan öğrenme kaybı veya kazanımın kavranamadığı şeklinde net "
    "teşhis et.\n"
    "3) Bilişsel düzeyi ADLANDIRIRKEN yalnızca şu altı Bloom basamağından "
    "BİRİNİ kullan: Hatırlama, Anlama, Uygulama, Analiz, Değerlendirme, "
    "Yaratma. Kazanım metnindeki fiili (\"anlam oluşturabilme\", "
    '"yönetebilme", "değerlendirebilme" gibi) bilişsel düzeyin ADI olarak '
    "TEKRARLAMA - o fiilin karşılık geldiği basamağı seç ve yalnızca o "
    "basamağın adını yaz. Sonra bu basamağı başarı oranıyla kıyasla: alt "
    "basamaktaki (Hatırlama/Anlama) bir kazanımda düşük puan ile üst "
    "basamaktaki (Analiz/Değerlendirme/Yaratma) bir kazanımda düşük puanı "
    "farklı risk gruplarına ayır.\n"
    "4) Eksikliğin ŞİDDET etiketi sana SORU'nun içinde hazır verilir "
    "(\"Bu oran için şiddet etiketi: ...\"). O etiketi kendin yeniden "
    "hesaplama, yumuşatma veya sertleştirme; yanıtının içinde şu kalıbı "
    "AYNEN, bir kez kullan: \"Eksikliğin şiddeti: <etiket>.\" Sana \"Orta\" "
    "verildiyse hiçbir yerde \"kritik\" kelimesini KULLANMA; \"Kritik\" "
    "verildiyse hiçbir yerde \"orta\" deme. \"Hafif\" kelimesini hiçbir "
    "durumda kullanma - bu prompt yalnızca başarı oranı %70'in altındaki "
    "kazanımlar için çalıştırılır, bu aralıkta hiçbir durum hafif sayılmaz. "
    "Bu kazanım genellikle sonraki/ileri düzey kazanımların temelini "
    "oluşturduğundan, eksikliğin sonraki öğrenmelere sarmal (kümülatif) bir "
    "risk oluşturup oluşturmadığını da teşhisine kısaca ekle - yalnızca bu "
    "riski TEŞHİS ET, nasıl giderileceğini önerme (madde 5).\n"
    "5) Yalnızca teşhis koy, ÇÖZÜM ÖNERME - bu kural istisnasızdır ve "
    "yanıtının SON cümlesi dâhil her cümlesi için geçerlidir. Etkinlik, "
    "kaynak, ders, öğretim yöntemi, çalışma veya telafi programı önerme. "
    "Şu ifadeleri hiç kullanma: \"önerilir\", \"tavsiye edilir\", "
    "\"gerekmektedir\", \"gerekir\", \"gereklidir\", \"ihtiyaç duyulmaktadır\", "
    "\"yapılmalıdır\", \"verilmelidir\", "
    "\"geliştirilmelidir\", \"desteklenmelidir\". Ne YAPILMASI gerektiğini "
    "değil, yalnızca NE OLDUĞUNU yaz: durumu, eksikliği ve risk düzeyini "
    "kanıtlarıyla belirle ve orada bitir.\n\n"
    "Yanıtını Türkçe, tek bir akıcı paragraf hâlinde (madde işareti, başlık "
    "veya markdown biçimlendirmesi kullanmadan) yaz; şunları kısaca "
    "kapsasın: (a) kazanımın bilişsel düzeyi (altı Bloom basamağından biriyle "
    "adlandırılmış) ile başarı oranının karşılaştırması ve bu kazanıma özgü "
    "eksiklik teşhisi, (b) SORU'da verilen şiddet etiketi ve eksikliğin bilgi "
    "düzeyinden mi yoksa üst düzey beceri eksikliğinden mi kaynaklandığı, "
    "(c) eksikliğin sonraki kazanımlara olası sarmal riski."
)

rag_storage_volume = modal.Volume.from_name("rag-storage", create_if_missing=True)
hf_cache_volume = modal.Volume.from_name("rag-hf-cache", create_if_missing=True)

VOLUMES: dict[str, modal.Volume] = {
    QDRANT_MOUNT_DIR: rag_storage_volume,
    HF_CACHE_DIR: hf_cache_volume,
}

# --- index_pdf'in imajı: Docling + gömme + Qdrant yazımı ---
indexing_image = (
    modal.Image.debian_slim(python_version="3.12")
    # Docling'in PDF/görüntü işleme alt katmanının (OpenCV tabanlı) ihtiyaç
    # duyduğu sistem kütüphaneleri - debian_slim imajında varsayılan olarak yok.
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install("qdrant-client", "sentence-transformers", "pypdf")
    .pip_install("docling")
    .env({"HF_HOME": HF_CACHE_DIR})
)

# --- RAGInference'ın imajı: gömme (sorgu) + Qdrant okuma + vLLM sunumu ---
inference_image = (
    modal.Image.debian_slim(python_version="3.12")
    # vLLM en kırılgan/sürüme duyarlı paket - kendi torch çözümünü önce
    # oturtması için ayrı ve ilk pip_install katmanında kalıyor.
    .pip_install("vllm")
    .pip_install("qdrant-client", "sentence-transformers")
    .env({
        "HF_HOME": HF_CACHE_DIR,
        # debian_slim imajında nvcc/CUDA toolkit yok. vLLM'in varsayılan
        # FlashInfer örnekleyicisi ilk istekte bir CUDA çekirdiğini JIT
        # derlemeye çalışıp "Could not find nvcc and default
        # cuda_home='/usr/local/cuda' doesn't exist" ile çöküyordu (gerçek
        # deploy'da görüldü - flashinfer/jit/cpp_ext.py:get_cuda_path).
        # PyTorch tabanlı yerleşik örnekleyiciye zorlayarak bu JIT
        # derlemeyi tamamen devre dışı bırakıyoruz.
        "VLLM_USE_FLASHINFER_SAMPLER": "0",
    })
)

app = modal.App(APP_NAME)

_SHARED_SECRET_HEADER = "X-MAHIR-RAG-Key"

if modal.is_local():
    _shared_secret = modal.Secret.from_dict(
        {"MAHIR_RAG_SHARED_SECRET": os.environ.get("MAHIR_RAG_SHARED_SECRET", "")}
    )
else:
    _shared_secret = modal.Secret.from_dict({})


def _slice_pdf_pages(pdf_bytes: bytes, start_page: int, end_page: int) -> bytes:
    """1-indeksli/dahil `[start_page, end_page]` sayfa aralığını yeni, bağımsız
    bir bellek-içi PDF'e kopyalar (`pypdf.PdfWriter`). Sayfa numaraları belge
    sınırları dışındaysa `IndexError` verir - çağıran taraf yakalar."""

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page_number in range(start_page, end_page + 1):
        writer.add_page(reader.pages[page_number - 1])  # pypdf 0-indeksli
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _find_heading_pages(pdf_bytes: bytes, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """`pattern`'a uyan başlıkları tüm sayfalarda arar; aynı başlık metni
    birden fazla sayfada eşleşirse yalnızca EN SON (en yüksek sayfa numaralı)
    eşleşmeyi tutar - `tdeogr.pdf`'te doğrulandı: hem İçindekiler'deki
    girişler (aynı metin ama satır sonunda sayfa numarasıyla, bu yüzden zaten
    `pattern`'ın `$` çapasıyla elenir) hem de "1.5 Programın Yapısı"
    bölümünün örnek/önizleme amaçlı tekrarladığı bir tema başlığı (s.30, gerçek
    başlangıcı s.32) her zaman gerçek bölümden ÖNCE gelir, bu yüzden "en son
    eşleşme kazanır" kuralı güvenilir. Sonuç, sayfa numarasına göre artan
    sırada `(sayfa, başlık_metni)` listesi olarak döner."""

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    last_page_for_label: dict[str, int] = {}
    for page_index, page in enumerate(reader.pages):
        match = pattern.search(page.extract_text() or "")
        if match:
            label = (match.group(1) if pattern.groups else match.group(0)).strip()
            last_page_for_label[label] = page_index + 1  # üzerine yaz -> son (en büyük) sayfa kalır

    return sorted(((page, label) for label, page in last_page_for_label.items()), key=lambda item: item[0])


def _sections_from_heading_pages(
    heading_pages: list[tuple[int, str]], total_pages: int
) -> list[tuple[str | None, int, int]]:
    """`_find_heading_pages` çıktısını `(etiket, başlangıç_sayfa, bitiş_sayfa)`
    (1-indeksli/dahil) üçlülerinden oluşan, tüm belgeyi/aralığı kapsayan bir
    listeye çevirir. Hiç başlık bulunamazsa tüm aralığı tek, etiketsiz
    (`None`) bir bölüm olarak döndürür - bölme yalnızca desene uyan
    belgelerde devreye girer, genel davranışı bozmaz."""

    if not heading_pages:
        return [(None, 1, total_pages)]

    sections: list[tuple[str | None, int, int]] = []
    for index, (start_page, label) in enumerate(heading_pages):
        end_page = heading_pages[index + 1][0] - 1 if index + 1 < len(heading_pages) else total_pages
        sections.append((label, start_page, end_page))
    return sections


def _theme_match_key(theme_text: str) -> str:
    """Tüm boşlukları atarak bir eşleştirme anahtarı üretir - pypdf'in bazı
    harf çiftlerinde (örn. "YAPI" -> "Y API", `tdeogr.pdf` s.80'de doğrulandı,
    muhtemelen PDF'in harf aralığı/kerning kodlamasından kaynaklanıyor) sahte
    boşluk eklemesi yüzünden, tema adının kendisi (`theme` alanı, gösterim
    için ham hâliyle saklanır) eşleştirme için güvenilir değil. Hem indeksleme
    hem sorgu tarafında (`approved_data_analyzer.py::_normalize_theme_for_rag`)
    aynı fonksiyon kullanılmalı."""

    return re.sub(r"\s+", "", theme_text.upper())


def _normalize_grade_label(raw_heading: str) -> str:
    """`"9. SINIF TEMALARI"` -> `"9"`, `"HAZIRLIK SINIFI TEMALARI"` -> `"hazırlık"` -
    `backend/app/program_catalog.py`'deki `ProgramProfile.grade` biçimiyle
    (düz rakam string'i) doğrudan karşılaştırılabilir olması için."""

    match = re.match(r"\s*(\d+)\.\s*SINIF", raw_heading, re.IGNORECASE)
    return match.group(1) if match else "hazırlık"


def _detect_theme_sections(pdf_bytes: bytes) -> list[tuple[str | None, int, int]]:
    """Verilen PDF baytları içinde `TEMA_HEADING_PATTERN`'a uyan başlıkları
    tarar ve `(tema_adı, başlangıç_sayfa, bitiş_sayfa)` (1-indeksli/dahil)
    üçlülerinden oluşan, tüm belgeyi kapsayan bir liste döndürür."""

    from pypdf import PdfReader

    total_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    heading_pages = _find_heading_pages(pdf_bytes, TEMA_HEADING_PATTERN)
    return _sections_from_heading_pages(heading_pages, total_pages)


def _detect_grade_sections(pdf_bytes: bytes) -> list[tuple[str | None, int, int]]:
    """Verilen PDF baytları içinde `GRADE_HEADING_PATTERN`'a uyan SINIF
    başlıklarını tarar ve `(normalize_edilmiş_sınıf, başlangıç_sayfa,
    bitiş_sayfa)` (1-indeksli/dahil) üçlülerinden oluşan, tüm belgeyi
    kapsayan bir liste döndürür (etiketler `_normalize_grade_label` ile
    `"9"`/`"hazırlık"` biçimine çevrilir)."""

    from pypdf import PdfReader

    total_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    heading_pages = _find_heading_pages(pdf_bytes, GRADE_HEADING_PATTERN)
    sections = _sections_from_heading_pages(heading_pages, total_pages)
    return [
        (_normalize_grade_label(label) if label is not None else None, start, end)
        for label, start, end in sections
    ]


def _extract_original_pages(chunk: object, page_offset: int) -> list[int]:
    """Bir Docling chunk'ının kaynaklandığı sayfa numaralarını (`chunk.meta.
    doc_items[i].prov[j].page_no`, alt-PDF'e göre 1-indeksli) `page_offset`
    (o alt-PDF'in orijinal belgedeki başlangıç sayfası - 1) ekleyerek ORİJİNAL
    PDF'teki gerçek sayfa numaralarına çevirir. Alan yolu bulunamazsa
    (Docling sürüm farkı vb.) boş liste döner - kaynak gösterimi zayıflar
    ama indeksleme çökmez."""

    pages: set[int] = set()
    for doc_item in getattr(getattr(chunk, "meta", None), "doc_items", None) or []:
        for prov in getattr(doc_item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if isinstance(page_no, int):
                pages.add(page_no + page_offset)
    return sorted(pages)


@app.function(image=indexing_image, volumes=VOLUMES, timeout=60)
def clear_index(program_id: str | None = None) -> tuple[bool, str]:
    """Belge dizinini temizler - `program_id` verilirse yalnızca o programa ait
    parçaları, verilmezse TÜM koleksiyonu siler. SINIF/tema ayrımı olmadan
    (bu güncellemeden önce) indekslenmiş eski veriyi temizleyip doğru
    yöntemle yeniden indekslemeden önce çalıştırılmalı. GPU gerektirmez."""

    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    try:
        client = QdrantClient(path=QDRANT_STORAGE_PATH)
    except Exception as error:  # noqa: BLE001 - "storage folder already accessed" gibi kilit hataları da dahil.
        return False, f"Belge dizinine erişilemedi (eşzamanlı kullanım olabilir): {error}"

    try:
        if not client.collection_exists(QDRANT_COLLECTION_NAME):
            return True, "Koleksiyon zaten yok, temizlenecek bir şey yok."
        if program_id:
            client.delete(
                collection_name=QDRANT_COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="program_id", match=MatchValue(value=program_id))]
                ),
            )
            message = f"'{program_id}' programına ait parçalar silindi."
        else:
            client.delete_collection(QDRANT_COLLECTION_NAME)
            message = "Tüm koleksiyon silindi."
        rag_storage_volume.commit()
        return True, message
    finally:
        client.close()


@app.function(
    image=indexing_image,
    gpu="A10G",
    memory=16384,
    volumes=VOLUMES,
    timeout=600,
)
def index_pdf(
    pdf_bytes: bytes,
    document_name: str,
    program_id: str,
    start_page: int | None = None,
    end_page: int | None = None,
) -> tuple[bool, str, dict[str, object] | None]:
    """PDF baytlarını (opsiyonel bir sayfa aralığına daraltıp) Docling ile
    ayrıştırır, tema sınırlarına saygılı biçimde HybridChunker ile parçalara
    ayırır, bge-m3 ile gömer ve Qdrant'a yazar.

    `program_id`, hangi ders-sınıf programına ait olduğunu işaretler (örn.
    `backend/app/program_catalog.py`'deki "tde-9-tymm") - MAHİR tek derslik
    değil (60+ ders seçilebiliyor) ve tek program (TDE9) bile birden fazla
    referans belgesi gerektiriyor, bu yüzden getirim zamanında (RAGInference)
    yanlış ders/temanın içeriğiyle karışmaması için her parça bu alanla
    etiketlenir. Bu fonksiyon `program_id`'yi doğrulamaz (düz string olarak
    alır, `document_name` gibi) - katalog-farkındalığı `backend/app/`
    katmanında kalır, bu dosya kasıtlı olarak backend'i import etmez.

    `start_page`/`end_page` (1-indeksli, dahil): MEB müfredat PDF'leri gibi
    TEK bir dosyanın birden fazla sınıf düzeyini (SINIF) kapsadığı durumlarda,
    çağıranın (bu belgenin hangi sayfa aralığının hangi `program_id`'ye ait
    olduğunu bilen tek taraf) yalnızca ilgili aralığı indekslemesini sağlar -
    aksi hâlde tüm belge tek bir `program_id`'ye etiketlenip başka sınıf
    düzeylerinin içeriği yanlışlıkla aynı havuza karışır (bkz. gerçek
    `tdeogr.pdf` üzerinde doğrulanan sorun: aynı öğrenme çıktısı kodu her
    sınıf düzeyinde ve her temada tekrarlanıyor). Verilmezse (`None`) bugünkü
    gibi belgenin tamamı kullanılır - geriye dönük uyumlu.

    Belirlenen aralık içinde ayrıca önce "HAZIRLIK/N. SINIF TEMALARI" (bkz.
    `_detect_grade_sections`), sonra her SINIF içinde "N. TEMA: İSİM"
    başlıklarına göre (bkz. `_detect_theme_sections`) otomatik alt-bölümlere
    ayrılır ve HER (sınıf, tema) çifti kendi Docling dönüşümünden/HybridChunker
    geçişinden ayrı ayrı geçirilir - bu, hiçbir parçanın iki tema (veya iki
    sınıf) arasında sınır geçmesini yapısal olarak imkânsız kılar. Her
    parçanın Qdrant payload'ına tespit edilen `grade` (SINIF, ör. `"9"` veya
    `"hazırlık"`) ve `theme` (tema adı) alanları ile orijinal PDF'teki gerçek
    sayfa numaraları (`pages`, kaynak göstermek için) yazılır; tespit
    edilemeyen alanlar `None`/boş liste kalır.

    Dönüş, `backend/app/remote_ocr_client.py`nin `run_remote_image_group_ocr`
    ile aynı (ok, mesaj, structuredData) kalıbını izler - bu fonksiyon Modal
    üzerinden `.remote()` ile çağrılacağı için hata durumunda İstisna
    fırlatmak yerine çağırana gösterilebilecek bir Türkçe mesaj döndürür.
    """

    if not pdf_bytes:
        return False, "PDF verisi boş.", None
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        return False, "PDF 20 MB sınırını aşıyor.", None
    if not program_id or not program_id.strip():
        return False, "program_id boş olamaz.", None
    if (start_page is None) != (end_page is None):
        return False, "start_page ve end_page birlikte verilmeli.", None
    if start_page is not None and (start_page < 1 or end_page < start_page):  # type: ignore[operator]
        return False, "Geçersiz sayfa aralığı.", None

    try:
        if start_page is not None:
            scoped_pdf_bytes = _slice_pdf_pages(pdf_bytes, start_page, end_page)  # type: ignore[arg-type]
            scope_offset = start_page - 1  # scoped_pdf_bytes'daki sayfa 1 = orijinaldeki start_page
        else:
            scoped_pdf_bytes = pdf_bytes
            scope_offset = 0
        grade_sections = _detect_grade_sections(scoped_pdf_bytes)
    except IndexError:
        return False, "Sayfa aralığı belgenin sınırları dışında.", None
    except Exception as error:  # noqa: BLE001 - pypdf üçüncü parti bir kütüphane; bozuk bir PDF
        # dilimleme/SINIF-tespit adımında da tüm işi çökertmemeli.
        return False, f"PDF sayfaları işlenemedi: {error}", None

    from docling.chunking import HybridChunker
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer

    # MAHİR'e yüklenen PDF'ler taranmış/görüntü tabanlı değil, metni zaten
    # gömülü belgeler - OCR'ı kapatmak hem gereksiz RapidOCR model
    # indirmesini ve her sayfada boş sonuç veren tespit turlarını (gerçek
    # deploy'da görüldü) önler hem de indeksleme süresini kısaltır.
    # Tablo/başlık yapı tespiti (do_table_structure) varsayılan açık kalır.
    pdf_pipeline_options = PdfPipelineOptions()
    pdf_pipeline_options.do_ocr = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options)}
    )
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_MODEL_NAME),
        max_tokens=CHUNK_MAX_TOKENS,
    )
    chunker = HybridChunker(tokenizer=tokenizer)

    # (chunk, contextualized_text, grade, theme, pages) - tüm sınıf/tema
    # bölümlerinden biriken, tek seferde gömülüp tek seferde yazılacak son liste.
    chunk_records: list[tuple[object, str, str | None, str | None, list[int]]] = []
    tmp_paths: list[str] = []
    section_count = 0
    try:
        for grade_label, grade_start, grade_end in grade_sections:
            grade_pdf_bytes = (
                scoped_pdf_bytes
                if len(grade_sections) == 1
                else _slice_pdf_pages(scoped_pdf_bytes, grade_start, grade_end)
            )
            # grade_pdf_bytes'daki sayfa 1'in orijinal belgedeki karşılığı.
            grade_offset = scope_offset + (grade_start - 1)

            theme_sections = _detect_theme_sections(grade_pdf_bytes)
            for theme_name, theme_start, theme_end in theme_sections:
                section_pdf_bytes = (
                    grade_pdf_bytes
                    if len(theme_sections) == 1
                    else _slice_pdf_pages(grade_pdf_bytes, theme_start, theme_end)
                )
                # section_pdf_bytes'daki sayfa 1'in orijinal belgedeki karşılığı -
                # Docling'in bu alt-PDF için raporlayacağı yerel sayfa numaralarına
                # eklenerek gerçek PDF sayfa numarasına çevrilecek.
                section_offset = grade_offset + (theme_start - 1)
                section_count += 1

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                    tmp_file.write(section_pdf_bytes)
                    tmp_paths.append(tmp_file.name)

                try:
                    converted_document = converter.convert(tmp_paths[-1]).document
                except Exception as error:  # noqa: BLE001 - Docling üçüncü parti bir ML pipeline'ı;
                    # öğretmenin yüklediği bozuk/desteklenmeyen bir PDF tüm işi çökertmemeli.
                    label = theme_name or grade_label or "belge"
                    return False, f"PDF ayrıştırılamadı ({label}): {error}", None

                section_chunks = list(chunker.chunk(dl_doc=converted_document))
                for chunk in section_chunks:
                    pages = _extract_original_pages(chunk, section_offset)
                    chunk_records.append(
                        (chunk, chunker.contextualize(chunk=chunk), grade_label, theme_name, pages)
                    )
    finally:
        for tmp_path in tmp_paths:
            Path(tmp_path).unlink(missing_ok=True)

    if not chunk_records:
        return False, "Belgeden okunabilir içerik çıkarılamadı.", None

    contextualized_texts = [record[1] for record in chunk_records]

    from sentence_transformers import SentenceTransformer

    try:
        embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        vectors = embedder.encode(contextualized_texts, normalize_embeddings=True).tolist()
    except Exception as error:  # noqa: BLE001 - gömme de üçüncü parti bir ML çağrısı; tek
        # bir belge işi tüm fonksiyonu çökertmemeli.
        return False, f"Metin parçaları gömülemedi: {error}", None

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    try:
        client = QdrantClient(path=QDRANT_STORAGE_PATH)
    except Exception as error:  # noqa: BLE001 - "storage folder already accessed" gibi kilit
        # hataları da dahil - bkz. modül docstring'i / bilinen sınırlamalar.
        return False, f"Belge dizinine erişilemedi (eşzamanlı kullanım olabilir): {error}", None

    try:
        if not client.collection_exists(QDRANT_COLLECTION_NAME):
            client.create_collection(
                QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
            )

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": chunk.text,
                    "contextualized_text": contextualized_text,
                    "document_name": document_name,
                    "program_id": program_id,
                    "grade": grade_label,
                    "theme": theme_name,
                    "theme_key": _theme_match_key(theme_name) if theme_name else None,
                    "pages": pages,
                    "headings": list(getattr(chunk.meta, "headings", None) or []),
                    "chunk_index": index,
                },
            )
            for index, ((chunk, contextualized_text, grade_label, theme_name, pages), vector) in enumerate(
                zip(chunk_records, vectors)
            )
        ]
        client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=points)

        # KESİNLİKLE yazımdan sonra: aksi halde değişiklikler bu konteyner
        # dışında hiçbir yerde (başka bir RAGInference konteyneri dahil)
        # görünmez.
        rag_storage_volume.commit()
    except Exception as error:  # noqa: BLE001 - Qdrant yazımı; kısmi/bozuk bir yazım da
        # fonksiyonu çökertmeden bildirilmeli.
        return False, f"Belge dizinine yazılamadı: {error}", None
    finally:
        # Kilidi elden geldiğince hızlı bırak - bkz. bilinen sınırlamalar.
        client.close()

    # Operatörün "doğru sayfa aralığını mı seçtim?" diye görsel olarak
    # doğrulayabilmesi için tespit edilen SINIF etiketlerini mesaja ekle.
    detected_grades = sorted({grade for grade, _, _ in grade_sections if grade is not None})
    grade_summary = f", SINIF: {', '.join(detected_grades)}" if detected_grades else ""
    return (
        True,
        f"'{document_name}' işlendi: {len(points)} parça dizine eklendi "
        f"({section_count} sınıf/tema bölümü{grade_summary}).",
        {
            "documentName": document_name,
            "chunkCount": len(points),
            "collectionName": QDRANT_COLLECTION_NAME,
        },
    )


@app.cls(
    image=inference_image,
    gpu="A10G",
    volumes=VOLUMES,
    scaledown_window=300,  # GPU soğuk başlangıcının sık tetiklenmesini (churn) önler.
    timeout=300,
    secrets=[_shared_secret],
)
class RAGInference:
    """bge-m3, Qdrant ve vLLM/Qwen2.5-7B-Instruct'ı bir arada bellekte tutan
    RAG sorgu servisi. Modeller ve Qdrant bağlantısı yalnızca `load()`
    içinde, konteyner ısınırken bir kez kurulur.
    """

    # Modal artık @app.cls sınıflarında özel __init__ desteklemiyor (bkz.
    # modal.com/docs/guide/parametrized-functions) - bu yüzden örnek
    # değişkenleri __init__ yerine bare sınıf-seviyeli tip belirtimiyle
    # tanımlanıp değerleri `load()` içinde (@modal.enter()) atanıyor.
    _embedder: SentenceTransformer | None
    _qdrant: QdrantClient | None
    _llm: LLM | None

    @modal.enter()
    def load(self) -> None:
        """Konteyner ısınırken bir kez çalışır: modelleri ve Qdrant'ı belleğe yükler."""

        from qdrant_client import QdrantClient
        from sentence_transformers import SentenceTransformer
        from vllm import LLM

        # Başka bir konteynerin (index_pdf) bu ısınmadan sonra commit ettiği
        # yazımları görebilmek için - bkz. bilinen sınırlamalar (Volume tazeliği).
        rag_storage_volume.reload()

        # Sorgu anında tek bir kısa soru cümlesi gömülüyor - GPU'yu (zaten
        # Qwen2.5-7B'nin KV cache'iyle dolu olan A10G, 24 GB VRAM) vLLM'e
        # bırakmak için gömme modelini kasıtlı olarak CPU'da çalıştırıyoruz.
        # (index_pdf'te toplu gömme GPU'da kalır - orada vLLM hiç yok.)
        self._embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

        self._llm = LLM(
            model=LLM_MODEL_NAME,
            dtype="bfloat16",
            max_model_len=8192,
            gpu_memory_utilization=0.80,  # bge-m3 + CUDA ek yüküne pay bırak.
        )

        # LLM(...) kendi EngineCore alt sürecini çatallıyor (forks); Qdrant
        # client'ını (ve onun .lock dosya tanıtıcısını) bilerek bundan SONRA
        # açıyoruz - aksi halde alt süreç bu tanıtıcıyı devralıyor ve
        # query() içindeki volume.reload() "qdrant_db/.lock is open from
        # 'VLLM::EngineCore'" hatasıyla başarısız oluyor (gerçek deploy'da
        # görüldü - kendi client'ımızı kapatmak alt sürecin devraldığı
        # kopyayı etkilemiyordu).
        self._qdrant = QdrantClient(path=QDRANT_STORAGE_PATH)

    @modal.exit()
    def close(self) -> None:
        """Konteyner kapanırken (scaledown veya preemption) Qdrant kilidini bırakır."""

        if self._qdrant is not None:
            self._qdrant.close()

    @modal.method()
    def query(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
        program_id: str | None = None,
        grade: str | None = None,
        theme: str | None = None,
        retrieval_query: str | None = None,
    ) -> tuple[bool, str, dict[str, object] | None]:
        """Soruyu göm, Qdrant'tan en yakın parçaları getir, Qwen2.5 ile Türkçe yanıt üret.

        SDK/`.remote()` üzerinden çağıranlar için giriş noktası - asıl iş
        `_run_query`'de. `web_query` (HTTP giriş noktası) da aynı yardımcıyı
        çağırır, böylece iki giriş noktası arasında mantık kopyalanmaz.
        `program_id` verilirse yalnızca o programa etiketlenmiş parçalarda
        arama yapılır; `None` ise (ör. `main()`'in ad-hoc testleri) bugüne
        kadarki filtresiz davranış aynen korunur. `grade`/`theme` verilirse
        ek güvenlik/hassasiyet filtresi olarak `program_id`'ye eklenir (bkz.
        `_run_query`, `index_pdf`'in yazdığı `grade`/`theme` alanlarıyla
        eşleşir). `retrieval_query` verilirse vektör aramasında `question`
        yerine o gömülür (LLM yine `question`'ı görür) - bkz. `_run_query`.
        """

        return self._run_query(question, top_k, program_id, grade, theme, retrieval_query)

    @modal.fastapi_endpoint(method="POST")
    async def web_query(self, request: Request) -> JSONResponse:
        """HTTP giriş noktası - `backend/app/rag_client.py` bunu çağırır.

        `_run_query`'nin (ok, mesaj, veri) sözleşmesini `ocr_worker.py`'deki
        ile aynı {"ok", "message", "structuredData"} zarfına sarar. Modal her
        `@modal.fastapi_endpoint` metoduna TEK, TAM bir URL üretir (path
        eklenecek bir taban değil) - `remote_ocr_client.py`'nin
        "+ /mahir-upload" deseni burada yok.
        """

        expected_secret = os.environ.get("MAHIR_RAG_SHARED_SECRET", "")
        if expected_secret and not hmac.compare_digest(
            request.headers.get(_SHARED_SECRET_HEADER, ""), expected_secret
        ):
            return JSONResponse({"ok": False, "message": "Yetkisiz istek."}, status_code=401)

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - okunamayan istek gövdesi 500'e değil 400'e düşmeli.
            return JSONResponse({"ok": False, "message": "İstek gövdesi okunamadı."}, status_code=400)

        question = str((body or {}).get("question") or "").strip()
        if not question:
            return JSONResponse({"ok": False, "message": "Soru boş olamaz."}, status_code=400)
        program_id = (body or {}).get("programId") or None
        top_k = int((body or {}).get("topK") or DEFAULT_TOP_K)
        grade = (body or {}).get("grade") or None
        theme = (body or {}).get("theme") or None
        retrieval_query = str((body or {}).get("retrievalQuery") or "").strip() or None

        ok, message, data = self._run_query(question, top_k, program_id, grade, theme, retrieval_query)
        return JSONResponse({"ok": ok, "message": message, "structuredData": data}, status_code=200 if ok else 500)

    def _run_query(
        self,
        question: str,
        top_k: int,
        program_id: str | None,
        grade: str | None = None,
        theme: str | None = None,
        retrieval_query: str | None = None,
    ) -> tuple[bool, str, dict[str, object] | None]:
        """`query`/`web_query`'nin ortak mantığı: göm, filtrelenmiş getirim, üret.

        `retrieval_query` verilirse gömülen (aranan) metin odur, LLM'e giden
        soru yine `question` olur. Çağıran taraf (bkz.
        `approved_data_analyzer.py::_build_rag_retrieval_query`) getirim
        sorgusuna yalnızca kazanımın kendi içeriğini koyar; `question`'daki
        başarı oranı ve "teşhis et" emri müfredat metninde hiçbir karşılığı
        olmayan, sorgu vektörünü müfredat düzyazısından uzaklaştıran gürültü.
        Verilmezse `question` gömülür - eski davranış birebir korunur.
        """

        if not question or not question.strip():
            return False, "Soru boş olamaz.", None

        # Bu konteyner sıcak kalırken başka bir konteynerde (index_pdf) commit
        # edilmiş yeni belgeleri görebilmek için her sorguda reload. Volume
        # reload() açık dosya varken başarısız olur (embedded Qdrant'ın
        # tuttuğu qdrant_db/.lock dahil - gerçek deploy'da görülen hata:
        # "there are open files preventing the operation: qdrant_db/.lock
        # is open") - bu yüzden client'ı önce kapatıp reload'dan sonra
        # yeniden açıyoruz.
        from qdrant_client import QdrantClient

        try:
            self._qdrant.close()
            rag_storage_volume.reload()
            self._qdrant = QdrantClient(path=QDRANT_STORAGE_PATH)
        except Exception as error:  # noqa: BLE001 - Volume/Qdrant altyapı çağrısı; bir sorgu
            # tüm servis konteynerini çökertmemeli.
            return False, f"Belge dizini tazelenemedi: {error}", None

        try:
            embedded_text = (retrieval_query or "").strip() or question
            query_vector = self._embedder.encode([embedded_text], normalize_embeddings=True)[0].tolist()
        except Exception as error:  # noqa: BLE001 - gömme üçüncü parti bir ML çağrısı; tek bir
            # sorgu tüm servis konteynerini çökertmemeli.
            return False, f"Soru gömülemedi: {error}", None

        no_answer: dict[str, object] = {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []}

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # program_id verilirse yalnızca o programa etiketli parçalarda ara -
        # MAHİR tek derslik değil (60+ ders), aynı öğrenme çıktısı kodu farklı
        # temalarda/sınıf düzeylerinde farklı anlama gelebiliyor; filtresiz
        # getirim yanlış dersin/sınıfın/temanın içeriğini sessizce
        # karıştırabilir. grade/theme verilirse ek (AND) güvenlik/hassasiyet
        # katmanı olarak eklenir - bkz. index_pdf'in yazdığı aynı adlı alanlar.
        # theme, "theme_key" alanına göre eşleşir (`_theme_match_key`) - ham
        # tema metni pypdf'in bazı harf çiftlerinde eklediği sahte boşluklar
        # yüzünden (bkz. _theme_match_key docstring'i) birebir eşleşme için
        # güvenilir değil.
        filter_conditions = []
        if program_id:
            filter_conditions.append(FieldCondition(key="program_id", match=MatchValue(value=program_id)))
        if grade:
            filter_conditions.append(FieldCondition(key="grade", match=MatchValue(value=grade)))
        if theme:
            filter_conditions.append(
                FieldCondition(key="theme_key", match=MatchValue(value=_theme_match_key(theme)))
            )
        query_filter = Filter(must=filter_conditions) if filter_conditions else None

        try:
            if not self._qdrant.collection_exists(QDRANT_COLLECTION_NAME):
                return True, "Bu bilgi belgede bulunmuyor.", no_answer
            hits = self._qdrant.query_points(
                collection_name=QDRANT_COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            ).points
        except Exception as error:  # noqa: BLE001 - yerel Qdrant okuması; bozuk/erişilemeyen
            # bir depo tüm servisi çökertmemeli.
            return False, f"Belge dizininden okunamadı: {error}", None

        if not hits:
            return True, "Bu bilgi belgede bulunmuyor.", no_answer

        context_blocks = [
            str((hit.payload or {}).get("contextualized_text") or (hit.payload or {}).get("text", ""))
            for hit in hits
        ]
        context_text = "\n\n---\n\n".join(context_blocks)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"BAĞLAM:\n{context_text}\n\nSORU: {question}\n\n"
                "Yalnızca yukarıdaki BAĞLAM'a dayanarak Türkçe yanıtla.",
            },
        ]

        try:
            from vllm import SamplingParams

            outputs = self._llm.chat(messages, SamplingParams(temperature=0.1, max_tokens=1024))
            answer = outputs[0].outputs[0].text.strip()
        except Exception as error:  # noqa: BLE001 - vLLM üretimi üçüncü parti bir ML çağrısı;
            # bir sorgunun başarısız olması servis konteynerini çökertmemeli.
            return False, f"Yanıt üretilemedi: {error}", None

        sources = [
            {
                "documentName": (hit.payload or {}).get("document_name"),
                "grade": (hit.payload or {}).get("grade"),
                "theme": (hit.payload or {}).get("theme"),
                "pages": (hit.payload or {}).get("pages", []),
                "headings": (hit.payload or {}).get("headings", []),
                "excerpt": str((hit.payload or {}).get("text", ""))[:300],
                "score": hit.score,
            }
            for hit in hits
        ]
        return True, "Yanıt üretildi.", {"answer": answer, "sources": sources}


@app.local_entrypoint()
def main(
    pdf_path: str,
    program_id: str,
    question: str = "Bu belge ne hakkında?",
    start_page: int | None = None,
    end_page: int | None = None,
) -> None:
    """Uçtan uca örnek kullanım:

        modal run rag_service.py --pdf-path C:\\yol\\ornek.pdf --program-id tde-9-tymm \
            --start-page 65 --end-page 97 --question "..."

    Bu fonksiyon yalnızca örnektir; hiçbir mevcut MAHIR backend dosyası bunu
    çağırmaz (proje kapsam kararı: yalnızca örnek kod, canlı entegrasyon yok -
    canlı entegrasyon `backend/app/rag_client.py` + `web_query` üzerinden).
    """

    pdf_bytes = Path(pdf_path).read_bytes()
    document_name = Path(pdf_path).name

    print(f"[rag_service] '{document_name}' ({program_id}, sayfa {start_page}-{end_page}) dizine ekleniyor...", flush=True)
    index_ok, index_message, index_data = index_pdf.remote(
        pdf_bytes, document_name, program_id, start_page, end_page
    )
    print(f"[rag_service] index_pdf: ok={index_ok} mesaj={index_message} veri={index_data}", flush=True)
    if not index_ok:
        return

    print(f"[rag_service] Soru soruluyor: {question!r}", flush=True)
    query_ok, query_message, query_data = RAGInference().query.remote(question, DEFAULT_TOP_K, program_id)
    print(f"[rag_service] query: ok={query_ok} mesaj={query_message}", flush=True)
    if query_ok and query_data:
        print(f"[rag_service] Yanıt: {query_data['answer']}", flush=True)
        print(f"[rag_service] Kaynaklar: {query_data['sources']}", flush=True)


# Örnek - bu dosyayı import ETMEDEN, `modal deploy rag_service.py` sonrasında
# dağıtılmış servisi ayrı bir Python betiğinden çağırmak için ("modal" paketi
# dışında hiçbir ağır bağımlılık gerekmez):
#
#     import modal
#
#     index_pdf = modal.Function.from_name("turkish-rag-system", "index_pdf")
#     rag = modal.Cls.from_name("turkish-rag-system", "RAGInference")
#
#     with open("belge.pdf", "rb") as f:
#         ok, message, data = index_pdf.remote(f.read(), "belge.pdf", "tde-9-tymm")
#
#     ok, message, data = rag().query.remote("Soru metni", 5, "tde-9-tymm")
#
# Ya da MAHIR'in kendi backend'inden (yalnızca stdlib, modal SDK gerekmez):
# `modal deploy` sonrası basılan web_query URL'ini MAHIR_RAG_REMOTE_URL olarak
# ayarlayın, `backend/app/rag_client.py`'deki query_rag_context(...) çağırsın.
