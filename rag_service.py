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

# --- Genel ajan uç noktasının sınırları ---
# Bu uç nokta, çağıranın gönderdiği prompt'u bu GPU'da çalıştırır. Paylaşılan
# parola KÖTÜ NİYETLİYİ engelliyor; aşağıdaki sınırlar HATAYI engelliyor -
# döngüye giren ya da yanlışlıkla devasa bağlam gönderen bir ajan sessizce GPU
# dakikası yakmasın. Değerler `max_model_len=8192` ile uyumlu seçildi.
MAX_AGENT_PROMPTS = 16
MAX_AGENT_PROMPT_CHARS = 8000
MAX_AGENT_OUTPUT_TOKENS = 1024

# Getirim hiçbir şey bulamadığında dönen metin. `backend/app/` tarafı bu
# cümleyi tanıyor (`approved_data_analyzer._RAG_NO_ANSWER_TEXT`) ve modelin
# yanıtının başına eklediği hâlini kırpıyor - iki taraf birebir aynı kalmalı.
_NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."

# Getirim isabetlerinin, EN İYİ isabetin skoruna göre korunma alt sınırı - mutlak
# bir `score_threshold` DEĞİL. Gerekçe ölçüm: 8 gerçek zayıf öğrenme çıktısı,
# tema filtresi açık, top_k=8 (64 isabet). Her sorgu aynı şekli veriyor - 2 güçlü
# isabet (0,86-0,94), bir orta grup (~0,73-0,78), sonra 0,60-0,68'de bir kuyruk.
# Kopuşun iki yanındaki isabetlerin en iyi isabete oranı hesaplandığında, kopuş
# gösteren altı sorgunun ortak aralığı 0,771-0,793 çıktı; 0,78 hepsinde tam
# kopuş noktasından kesiyor. Mutlak bir eşik bunu yapamaz: bge-m3'ün skorları
# belgeye/sorguya göre kayıyor (aynı dizinde 0,60 ile 0,94 arası gözlendi) ve
# önerilen 0,40 gibi bir sayı burada hiçbir şeyi elemezdi.
#
# 2026-08-22 0,78 -> 0,60 DÜŞÜRÜLDÜ: bu ilk ölçüm yalnız "isabet var mı" (top_k
# tüm parçaları mı kapsıyor) sorusunu optimize etmişti, "hangi TÜR parça"
# sorusunu değil. Canlı incelemede görüldü ki bir kazanımın "kazanım
# tanımlama" tablosu (SORU'daki kazanım metnine neredeyse birebir aynı metin,
# bu yüzden hep 0,85-0,92 skorlanıyor) tek başına 8 slotu doldurup aynı
# temanın çok daha zengin "Öğrenme-Öğretme Uygulamaları" içeriğini (konu
# olarak alakalı ama kelime olarak farklı, bu yüzden ~0,65-0,75 skorlanıyor -
# 0,78 eşiğinin altında) sistematik olarak dışarıda bırakıyordu; sonuç,
# `agents/pipeline.py`nin evidenceTerms seçimi için elinde hiç iyi aday
# kalmaması ve modelin SORU'nun kendi cümlesine kaçmasıydı. 0,60 bu tarz
# konu-alakalı-ama-kelime-farklı içeriği de içeri alıyor; asıl alakasız kuyruk
# (0,60'ın altı, ölçümde 0,60-0,68 civarı görülmüştü) yine elenmeye devam
# ediyor.
#
# 2026-08-22 0,60 -> 0,68 (top_k=12 ile) -> 0,60'A GERİ. Ara durak (0,68):
# top_k'yi büyütüp eşiği yükseltmek bir sorguyu düzeltirken (Sözün İnceliği)
# başka birini bozuyordu (Anlamın Yapı Taşları, 5/5 -> 0/5) - kök sorun bir
# SAYI ayarıyla çözülemeyen yapısal bir tekrar sorunuydu (aynı kazanımın
# birbirine çok benzeyen "tanımlama" satırları top_k ne olursa olsun slotları
# dolduruyordu). Asıl çözüm `_mmr_select` (Maximal Marginal Relevance) -
# `_retrieve_for`/`_run_batch_query` artık ÇOK daha geniş bir ham havuz
# (bkz. `_MMR_CANDIDATE_MULTIPLIER`/`_MMR_MIN_CANDIDATE_POOL`) çekip bu
# eşikten geçirdikten SONRA MMR ile hem alakalı hem çeşitli bir alt küme
# seçiyor - tekrar sorunu artık MMR'nin işi, bu eşiğin tek görevi ham
# havuzdaki gerçekten alakasız kuyruğu elemek. Bu yüzden eşik tekrar
# gevşek varsayılana (0,60) dönebildi; MMR geniş havuzdan seçim yaptığı
# için tek başına top_k büyütmenin yarattığı "kalabalık bağlam" riski de
# yok - MMR seçilenler arasında zaten çeşitliliği zorluyor.
#
# 2026-08-22 0,60 -> 0,50 DÜŞÜRÜLDÜ: bazı kazanımlar için getirim SIFIR
# isabetle dönüyordu (`agents/pipeline.py` tarafında sessizce "kaynak-yok"
# olarak atlanıyor, öğretmen hiçbir yorum görmüyor) - dar/az yaygın
# kelime dağarcığı taşıyan kazanımların embedding'i o temanın en iyi
# isabetine göre 0,60'ın altında kalabiliyor. MMR zaten çeşitliliği
# gözettiği için eşiği gevşetmek "kalabalık bağlam" riskini geri
# getirmiyor; yalnızca ham havuza az sayıda ek (daha zayıf ama yine de
# konuyla ilgili) aday katıyor.
_RELATIVE_SCORE_FLOOR = 0.50

# MEB müfredat PDF'lerindeki hiyerarşi başlıkları - tdeogr.pdf üzerinde tüm
# 5 sınıf düzeyi ve 20 sınıf×tema kombinasyonu için elle doğrulandı. Satırın
# TAMAMINI kaplayan bağımsız bir metin satırı arıyoruz (`^...$`, MULTILINE) -
# bu, İçindekiler'deki aynı metni (satır sonunda sayfa numarasıyla birlikte
# geldiği için `$` ile eşleşmiyor) doğal olarak eler. Desenler eşleşmezse
# index_pdf SINIF/tema-bölme adımını atlar - yalnızca bu belge yapısına özgü
# kalır, genel kod bozulmaz.
GRADE_HEADING_PATTERN = re.compile(r"^\s*(HAZIRLIK SINIFI TEMALARI|\d+\.\s*SINIF TEMALARI)\s*$", re.MULTILINE)
TEMA_HEADING_PATTERN = re.compile(r"^\s*\d+\.\s*TEMA\s*:\s*(.+?)\s*$", re.MULTILINE)

# Müfredata demirlenmiş teşhis prompt'u - yalnızca TEŞHİS (kanıtlarıyla
# eksiklik/risk tespiti), asla ÇÖZÜM/YÖNTEM önerisi değil
# (DEVELOPMENT_CHARTER.md: "MAHİR ... öğretim yöntemi veya telafi programı
# önermez"). Kod tarafındaki emniyet ağı için bkz.
# `agents/pipeline.py::_compose_grounded_pedagogical_answer` (gerekçe
# metnini `charter_guard.strip_recommendation_sentences`den geçirir).
#
# 2026-08-22 (2. sürüm): prompts.DIAGNOSIS_SYSTEM_PROMPT ile birebir aynı
# tutulmalı (bkz. o dosyadaki değişiklik notu) - yapılandırılmış kanıt
# şemasına geçildi, `{"evidenceTerms":[...]}` yerine artık her terim kendi
# `contextSnippet`ini, `pedagogicalRole`ünü ve `gapRationale`sini taşıyan
# bir `evidence` dizisi.
SYSTEM_PROMPT = (
    "Sen; Veri Odaklı Ölçme-Değerlendirme ve Program Geliştirme alanlarında uzmanlaşmış kıdemli bir Eğitim Analistisin.\n"
    "Görevin: Verilen resmî BAĞLAM (öğretim programı) ve SORU'daki kazanım/başarı verisini inceleyerek, yaşanan öğrenme eksikliğini doğrudan kanıtlayan somut müfredat bileşenlerini yapılandırılmış JSON formatında teşhis etmektir.\n\n"
    "TEMEL İLKELER:\n"
    "1) BAĞLAMA VE VERİYE DEMİRLE: Yalnızca BAĞLAM'da BİREBİR geçen terimleri ve ifadeleri kullan. Soru metnini görmediğini unutma; soru içeriği hakkında spekülasyon yapma. Başarı oranını ('%30' gibi) kanıt terimi olarak alma.\n"
    "2) ANALİTİK DERİNLİK: Genel/jenerik ifadeler ('okuma', 'kavrama', 'strateji') seçme. Seçilen terim; müfredatın o kazanıma özel tanımladığı kritik bir süreç bileşeni, kavram yanılgısı riski taşıyan bir kavram, uygulama adımı veya kazanım sınırlandırması olmalıdır.\n"
    "3) YALNIZCA BAĞLAMDA YOKSA: Bağlamda bu kazanıma ait hiçbir içerik yoksa doğrudan `{\"status\": \"not_found\"}` döndür.\n"
    "4) KANIT SAYISI: `evidence` dizisi EN AZ BİR, EN ÇOK İKİ öğe içermeli. BAĞLAM'da bu kazanıma dair BİREBİR geçen birden fazla güçlü/somut terim varsa en iyi ikisini yaz; yalnızca TEK güçlü/somut terim bulabiliyorsan yalnızca onu yaz - ikinciyi asla uydurma veya zayıf/alakasız bir terimle doldurma.\n\n"
    "ÇIKTI FORMATI (Yalnızca geçerli JSON döndür, markdown veya ek metin yazma):\n"
    "{\n"
    '  "status": "success",\n'
    '  "evidence": [\n'
    "    {\n"
    '      "exactTerm": "BAĞLAMDA BİREBİR GEÇEN 1. TERİM/BİLEŞEN",\n'
    '      "contextSnippet": "Terimin bağlamda geçtiği kısa cümle parçası",\n'
    '      "pedagogicalRole": "Kritik Ön Koşul | Süreç Bileşeni | Kazanım Sınırı | Uygulama Adımı",\n'
    '      "gapRationale": "Bu terim/bileşen özelinde öğrencinin aldığı düşük puana bağlı oluşan kavramsal veya yöntemsel eksikliğin 1 cümlelik teknik gerekçesi."\n'
    "    },\n"
    "    {\n"
    '      "exactTerm": "BAĞLAMDA BİREBİR GEÇEN 2. TERİM/BİLEŞEN",\n'
    '      "contextSnippet": "Terimin bağlamda geçtiği kısa cümle parçası",\n'
    '      "pedagogicalRole": "Kritik Ön Koşul | Süreç Bileşeni | Kazanım Sınırı | Uygulama Adımı",\n'
    '      "gapRationale": "Bu terim/bileşen özelinde yaşanan eksikliğin 1 cümlelik teknik gerekçesi."\n'
    "    }\n"
    "  ]\n"
    "}"
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

_shared_secret = modal.Secret.from_dict(
    {"MAHIR_RAG_SHARED_SECRET": os.environ.get("MAHIR_RAG_SHARED_SECRET", "")}
)


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
    ada sahip parçalar dizine girdikten sonra ancak `clear_index` + yeniden
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
            "rag_service.DOCUMENT_TITLES'a ekleyin ya da --document-title ile verin."
        )
    return title


# uuid5 için sabit ad alanı - değeri değişirse aynı içerik farklı ID üretir,
# yani bu string kalıcı bir şemanın parçasıdır ve DEĞİŞTİRİLMEMELİDİR.
_POINT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mahir-rag-chunk")


def _deterministic_point_id(program_id: str, document_name: str, chunk_index: int, text: str) -> str:
    """Aynı içerik -> aynı Qdrant nokta ID'si (içerik adresli, uuid5).

    Eskiden `uuid4()` kullanılıyordu: aynı PDF'i `clear_index` çağırmadan
    yeniden indekslemek 118 parçayı ikizler, `top_k` neredeyse birebir aynı
    metinlerle dolar ve getirim sessizce bozulurdu - hiçbir hata vermeden.
    uuid5 ile ikinci yazım aynı ID'lere denk gelir, `upsert` üzerine yazar.

    `chunk_index` kasıtlı olarak anahtarın içinde: HybridChunker'ın
    `repeat_table_header` davranışı aynı başlık satırını tekrarladığı için tek
    bir tema İÇİNDE birebir aynı metne sahip iki parça mümkün ve bir ID
    çakışması sessiz veri kaybı olurdu. Aynı PDF + aynı aralık + aynı kod aynı
    sırayı ürettiğinden bu, belirlenimciliği bozmaz.

    Bu, `clear_index`'in yerini ALMAZ: parçalama değişirse (ör. chunker ayarı)
    eski ID'ler öksüz kalır ve yine temizlik gerekir. Kaldırdığı şey,
    `clear_index`'i unutmanın bedeli.
    """

    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{program_id}|{document_name}|{chunk_index}|{text}"))


def _drop_weak_hits(hits: list, floor_ratio: float = _RELATIVE_SCORE_FLOOR) -> list:
    """En iyi isabetin `floor_ratio` katının altında kalan isabetleri atar.

    Qdrant isabetleri skora göre azalan sırada döndürür, bu yüzden eşik en
    baştaki isabetten hesaplanır. Ölçüm gerekçesi için bkz.
    `_RELATIVE_SCORE_FLOOR`.

    Qdrant'ın kendi `score_threshold` parametresi yerine sorgudan SONRA
    kırpıyoruz, çünkü orada eşiğin altında kalan bir sorgu BOŞ isabet listesi
    döndürür ve `_no_answer()` yoluna düşerdi - yani öğretmenin raporunda boş
    bir hücre. Bu fonksiyon her zaman en az bir isabet bırakır: kırpma bağlamı
    daraltabilir, ama teşhisi asla tamamen ortadan kaldıramaz.
    """

    if not hits:
        return hits
    top_score = hits[0].score
    if top_score <= 0:  # kosinüs negatif olabilir; oranla kırpmak orada anlamsız.
        return hits
    cutoff = top_score * floor_ratio
    return [hit for hit in hits if hit.score >= cutoff] or hits[:1]


# MMR (Maximal Marginal Relevance) çeşitlilik parametresi - 1,0 saf alaka
# (skor sıralamasıyla aynı, çeşitlilik yok), 0,0 saf çeşitlilik (skoru yok
# sayar). Klasik literatür aralığı 0,5-0,7; 0,6 alakayı öne alan ama tekrarı
# belirgin biçimde cezalandıran bir orta nokta.
_MMR_LAMBDA = 0.6

# MMR'nin seçeceği ham aday havuzu, çağıranın istediği nihai `k`'nin katı
# olarak alınır - MMR'nin gerçekten çeşitlilik arasından seçim
# yapabilmesi için skor sıralamasındaki ilk `k`'den daha geniş bir havuza
# ihtiyacı var (bkz. `_mmr_select`).
_MMR_CANDIDATE_MULTIPLIER = 3
_MMR_MIN_CANDIDATE_POOL = 24


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """İki vektörün kosinüs benzerliği. Embedder çıktıları zaten normalize
    (`normalize_embeddings=True`) - bu yüzden yalnız iç çarpım yeterli, ayrıca
    normlama gerekmiyor."""

    return sum(x * y for x, y in zip(a, b))


def _mmr_select(hits: list, k: int, lambda_param: float = _MMR_LAMBDA) -> list:
    """Skor sıralı `hits`ten, hem sorguya alakalı HEM DE birbirinden farklı
    en fazla `k` isabeti Maximal Marginal Relevance ile seçer.

    Neden gerekli: aynı kazanımın "kazanım tanımlama" satırları (ör. altı
    farklı beceri/alt-madde başlığı altında hep aynı "'X' temasında ele
    alınan metinlerde Y" kalıbıyla yazılmış kısa tanımlar) sorguya (kazanım
    kimliği + açıklaması) hepsi neredeyse aynı ölçüde yakın olduğundan, düz
    "en yüksek skorlu top_k" seçimi bu tekrarlı ailenin TAMAMINI alıp aynı
    temanın konu olarak alakalı ama kelime olarak farklı ("Öğrenme-Öğretme
    Uygulamaları" gibi) içeriğine hiç yer bırakmıyordu. `top_k`/`floor_ratio`
    ayarlarıyla (bkz. bu iki sabitin 2026-08-22 tarihli notları) düzeltilmeye
    çalışıldı ama bu yalnız bir SAYI ayarıyla çözülemeyen yapısal bir tekrar
    sorunuydu: bir sorgu için işe yarayan `top_k` diğerinde gürültü
    yaratıyordu (ölçüldü: bir senaryo 5/5 -> 0/5). MMR, "zaten seçtiklerime
    çok benzeyen bir sonraki en iyi aday" yerine "alakalı KALAN ama farklı"
    adayı tercih ederek ikisini birlikte çözüyor.

    Her adımda seçilecek aday, `lambda_param * sorguya_alaka - (1 -
    lambda_param) * en_yakın_seçili_isabete_benzerlik` skorunu maksimize
    eder. `hit.score` zaten sorgu vektörüne kosinüs benzerliği (Qdrant'ın
    COSINE mesafe ayarı) - yeniden hesaplamaya gerek yok. Aday-seçili
    benzerliği için `hit.vector` gerekiyor - çağıran taraf Qdrant sorgusunu
    `with_vectors=True` ile yapmalı.
    """

    if len(hits) <= k:
        return hits

    selected = [hits[0]]
    remaining = list(hits[1:])
    while remaining and len(selected) < k:
        best_index = 0
        best_mmr = None
        for index, candidate in enumerate(remaining):
            redundancy = max(
                _cosine_similarity(candidate.vector, chosen.vector) for chosen in selected
            )
            mmr = lambda_param * candidate.score - (1 - lambda_param) * redundancy
            if best_mmr is None or mmr > best_mmr:
                best_mmr = mmr
                best_index = index
        selected.append(remaining.pop(best_index))
    return selected


def _retrieve_hits(qdrant, query_vector, top_k: int, query_filter) -> list:
    """`_retrieve_for` ve `_run_batch_query`nin ortak tek-öğe getirim adımı.

    İkisi de bugüne kadar bu bloğu (geniş aday havuzu çek -> zayıfları at ->
    MMR ile çeşitlendir) ayrı ayrı taşıyordu - saf bir taşıma, davranış
    değişikliği yok. Hibrit (dense+sparse) arama eklendiğinde tek değişecek
    yer burası olacak, iki çağıran yerine.
    """

    hits = qdrant.query_points(
        collection_name=QDRANT_COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=max(top_k * _MMR_CANDIDATE_MULTIPLIER, _MMR_MIN_CANDIDATE_POOL),
        with_payload=True,
        with_vectors=True,
    ).points
    if not hits:
        return []
    return _mmr_select(_drop_weak_hits(hits), top_k)


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


@app.function(image=indexing_image, volumes=VOLUMES, timeout=60)
def list_chunks(program_id: str | None = None) -> int:
    """Docling + HybridChunker'ın `index_pdf` içinde ürettiği parçaları (chunk)
    inceleme amaçlı stdout'a döker - `program_id` verilirse yalnızca o
    programa ait parçaları, yoksa tüm koleksiyonu. GPU gerektirmez, gömme/LLM
    çağırmaz; yalnızca Qdrant'ta zaten depolanmış payload'ı okur.

    `modal run rag_service.py::list_chunks --program-id tde-9-tymm` ile
    çalıştırılır (çıktıyı bir dosyaya yönlendirmek için sonuna
    `> chunks.txt` eklenebilir). Dönüş değeri yalnızca parça sayısıdır -
    metin gövdeleri `modal run`'ın kendi return-value çıktısında değil,
    aşağıdaki print'lerde görünür.
    """

    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    try:
        client = QdrantClient(path=QDRANT_STORAGE_PATH)
    except Exception as error:  # noqa: BLE001 - "storage folder already accessed" gibi kilit hataları da dahil.
        print(f"Belge dizinine erişilemedi (eşzamanlı kullanım olabilir): {error}")
        return 0

    try:
        if not client.collection_exists(QDRANT_COLLECTION_NAME):
            print("Koleksiyon henüz yok - hiç belge indekslenmemiş.")
            return 0

        scroll_filter = (
            Filter(must=[FieldCondition(key="program_id", match=MatchValue(value=program_id))])
            if program_id
            else None
        )
        chunks: list[dict[str, object]] = []
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=100,
                offset=offset,
                with_payload=True,
            )
            chunks.extend(record.payload or {} for record in records)
            if offset is None:
                break
    finally:
        client.close()

    chunks.sort(key=lambda payload: (str(payload.get("document_name")), payload.get("chunk_index") or 0))

    for payload in chunks:
        print(
            f"--- [{payload.get('chunk_index')}] {payload.get('document_name')} | "
            f"program={payload.get('program_id')} sınıf={payload.get('grade')} "
            f"tema={payload.get('theme')} sayfa={payload.get('pages')} "
            f"başlıklar={payload.get('headings')} ---"
        )
        print(payload.get("text"))
        print()

    print(f"Toplam {len(chunks)} parça.")
    return len(chunks)


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

    `document_name` belgenin RESMÎ ADIDIR, dosya adı değil (ör. "Ortaöğretim
    Türk Dili ve Edebiyatı Dersi Öğretim Programı - Türkiye Yüzyılı Maarif
    Modeli (2024)"). Bu değer payload'a yazılıp getirimde `sources` içinde geri
    döner ve oradan öğretmenin raporundaki kaynak gösterimine çıkar - resmî bir
    rapor dayanağını "tdeogr.pdf" diye gösteremez. Bu fonksiyon değeri
    doğrulamaz (düz string olarak alır); adı çözen taraf çağırandır
    (bkz. `DOCUMENT_TITLES` / `resolve_document_title`).

    DİKKAT: `document_name` nokta kimliğinin parçası (`_deterministic_point_id`).
    Var olan bir belgenin adı değiştirilip yeniden indekslenirse parçalar YENİ
    kimlikler alır, eskiler üzerine yazılmaz ve dizinde aynı içerik iki adla
    kalır. Ad değişiminde önce `clear_index(program_id)` çağrılmalı.

    Dönüş, `backend/app/remote_ocr_client.py`nin `run_remote_image_group_ocr`
    ile aynı (ok, mesaj, structuredData) kalıbını izler - bu fonksiyon Modal
    üzerinden `.remote()` ile çağrılacağı için hata durumunda İstisna
    fırlatmak yerine çağırana gösterilebilecek bir Türkçe mesaj döndürür.
    """

    if not pdf_bytes:
        return False, "PDF verisi boş.", None
    if not document_name or not document_name.strip():
        return False, "document_name boş olamaz (belgenin resmî adı gerekli).", None
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
                id=_deterministic_point_id(program_id, document_name, index, chunk.text),
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

        program_id = (body or {}).get("programId") or None
        top_k = int((body or {}).get("topK") or DEFAULT_TOP_K)

        # Isıtma: soğuk başlangıç ölçüldü, ~110 sn (konteyner + modeller). Bu
        # dal hiçbir sorgu çalıştırmadan sadece konteynerin ayakta ve
        # @modal.enter()'ın bitmiş olmasını sağlar - öğretmen doğrulama
        # ekranında puanları incelerken çağrılıyor, böylece analiz anında
        # konteyner zaten sıcak oluyor (scaledown_window=300).
        if (body or {}).get("warmup"):
            return JSONResponse({"ok": True, "message": "RAG hattı hazır.", "structuredData": {"ready": True}})

        # Genel ajan biçimi: çağıran kendi system/user prompt'unu gönderir.
        # `queries`den farkı GETİRİM YOK - Qdrant'a hiç dokunulmaz, Volume
        # reload edilmez, gömme yapılmaz. Beş analiz ajanından yalnız LLM
        # desteği kullananlar (bugünkü akışta Ölçme-Değerlendirme ve Pedagojik
        # Analiz) prompt'larını buraya yollar; aynı sıcak konteyner ve tek
        # vLLM partisi paylaşılır. Diğer üç ajan kurallı çalışır.
        raw_agents = (body or {}).get("agents")
        if isinstance(raw_agents, list) and raw_agents:
            # Doğrulama ile üretim ayrı: geçersiz istek çağıranın hatası (400),
            # üretim arızası servisin hatası (500). İkisini tek dönüş değerinden
            # ayırt etmeye çalışmak mesaj metnine bakmak demek olurdu.
            rejection = _reject_agent_prompts(raw_agents)
            if rejection:
                return JSONResponse({"ok": False, "message": rejection}, status_code=400)
            ok, message, results = self._run_agent_prompts(raw_agents)
            return JSONResponse(
                {"ok": ok, "message": message, "structuredData": {"results": results} if ok else None},
                status_code=200 if ok else 500,
            )

        # Toplu biçim: N zayıf öğrenme çıktısı tek istekte, tek vLLM partisinde.
        raw_queries = (body or {}).get("queries")
        if isinstance(raw_queries, list) and raw_queries:
            ok, message, results = self._run_batch_query(raw_queries, top_k, program_id)
            return JSONResponse(
                {"ok": ok, "message": message, "structuredData": {"results": results} if ok else None},
                status_code=200 if ok else 500,
            )

        # Tekil biçim - eski istemciler ve `main()` için aynen korunuyor.
        question = str((body or {}).get("question") or "").strip()
        if not question:
            return JSONResponse({"ok": False, "message": "Soru boş olamaz."}, status_code=400)
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

        ok, message, results = self._run_batch_query(
            [
                {
                    "question": question,
                    "retrievalQuery": retrieval_query,
                    "grade": grade,
                    "theme": theme,
                }
            ],
            top_k,
            program_id,
        )
        if not ok or not results:
            return ok, message, None
        result = results[0]
        # Tek sorgu sözleşmesi korunuyor: kaynak yoksa mesaj "Bu bilgi belgede
        # bulunmuyor.", varsa "Yanıt üretildi." - çağıranlar (rag_client,
        # approved_data_analyzer, main()) buna göre yazılmış.
        found = bool(result.get("sources"))
        return True, "Yanıt üretildi." if found else "Bu bilgi belgede bulunmuyor.", result

    def _run_agent_prompts(
        self, items: list[dict[str, object]]
    ) -> tuple[bool, str, list[dict[str, object]] | None]:
        """Bir analiz turundaki TÜM ajan prompt'larını tek partide çalıştırır.

        Her öğe isteğe bağlı bir `retrieval` bloğu taşıyabilir:

            {"name", "system", "user",
             "retrieval": {"programId", "grade", "theme", "query", "topK"}}

        `retrieval` taşıyanlar için müfredat bağlamı Qdrant'tan getirilip user
        mesajının başına eklenir ve sonuca `sources` yazılır; taşımayanlar düz
        prompt olarak gider. İkisi de **aynı `self._llm.chat` çağrısında**
        çözülür.

        Bu birleştirme Faz 3'ün asıl amacı: eskiden getirimli sorgular
        `queries`, getirimsizler `agents` biçiminden gidiyordu ve iki ayrı
        HTTP turu + iki ayrı vLLM partisi demekti. Artık o analiz turunda kaç
        LLM destekli görev bulunursa bulunsun istemci tek toplu istek yollar.
        Bu teknik bir istek birleştirme davranışıdır; sıfır maliyet veya sabit
        süre iddiası değildir.

        Hiçbir öğe `retrieval` taşımıyorsa Qdrant'a HİÇ dokunulmaz - Volume
        reload ve gömme atlanır.

        Çıktılar giriş sırasıyla döner; `name` alanı çağıranın eşleştirme
        yapabilmesi için aynen geri verilir.
        """

        from vllm import SamplingParams

        retrieval_indexes = [
            index for index, item in enumerate(items) if isinstance(item.get("retrieval"), dict)
        ]
        contexts: dict[int, str] = {}
        sources: dict[int, list[dict[str, object]]] = {}
        if retrieval_indexes:
            ok, message, contexts, sources = self._retrieve_for(items, retrieval_indexes)
            if not ok:
                return False, message, None

        # Getirimi boş çıkan öğe partiye HİÇ girmez: üretecek bağlamı yok ve
        # bir yanıt uydurmasındansa "belgede bulunmuyor" demesi doğru.
        generated_indexes = [
            index
            for index in range(len(items))
            if index not in retrieval_indexes or contexts.get(index)
        ]

        conversations = [
            [
                {"role": "system", "content": str(items[index].get("system") or "")},
                {
                    "role": "user",
                    "content": (
                        f"BAĞLAM:\n{contexts[index]}\n\n{items[index].get('user')}"
                        if contexts.get(index)
                        else str(items[index].get("user") or "")
                    ),
                },
            ]
            for index in generated_indexes
        ]

        answers: dict[int, str] = {}
        if conversations:
            # Tavan uygulanır: çağıran daha büyük isterse sessizce kırpılır,
            # çünkü bu sınır GPU'yu korumak için var ve pazarlık konusu değil.
            max_tokens = min(
                MAX_AGENT_OUTPUT_TOKENS,
                max(int(_number_or(item.get("maxTokens"), MAX_AGENT_OUTPUT_TOKENS)) for item in items),
            )
            try:
                # 2026-08-22: 0,3 DENENDİ, 0,1'E GERİ ALINDI. Gerekçe: görev
                # serbest paragraf yazmak değil, BAĞLAM'dan doğrulanmış İKİ
                # terim SEÇMEK (`_compose_grounded_pedagogical_answer` katı bir
                # JSON + birebir-alıntı sözleşmesi bekliyor). 0,3 ile gerçek
                # sorgularla ölçüldü: önceden 5/5 güvenilir çalışan bir örnek
                # (Anlamın Yapı Taşları/TDE1.2) 0/5'e düştü - model terimleri
                # hafifçe değiştiriyor (ör. "kontrol listesi" yerine "bağlamanın
                # kontrol listesi" gibi kaynakta birebir geçmeyen bir ifade
                # uyduruyor) veya aynı terimi iki kez seçiyor. Bu görev şekli
                # için (katı biçim/alıntı uyumu önemli, "yaratıcılık" değil)
                # düşük sıcaklık doğru seçenekti - metin çeşitliliği artık
                # `pipeline.py`deki kalıp havuzlarından geliyor, modelden değil.
                outputs = self._llm.chat(
                    conversations, SamplingParams(temperature=0.1, max_tokens=max_tokens)
                )
            except Exception as error:  # noqa: BLE001 - vLLM üretimi üçüncü parti bir ML çağrısı;
                # bir partinin başarısız olması servis konteynerini çökertmemeli.
                return False, f"Ajan yanıtları üretilemedi: {error}", None
            if len(outputs) != len(conversations):
                return False, "Ajan partisinde yanıt sayısı istek sayısıyla eşleşmedi.", None
            answers = {
                index: output.outputs[0].text.strip()
                for index, output in zip(generated_indexes, outputs)
            }

        return True, "Ajan yanıtları üretildi.", [
            {
                "name": str(item.get("name") or ""),
                "answer": answers.get(index, _NO_ANSWER_TEXT),
                "sources": sources.get(index, []),
            }
            for index, item in enumerate(items)
        ]

    def _retrieve_for(
        self, items: list[dict[str, object]], retrieval_indexes: list[int]
    ) -> tuple[bool, str, dict[int, str], dict[int, list[dict[str, object]]]]:
        """`retrieval` taşıyan öğeler için müfredat bağlamını getirir.

        Parti başına BİR kez yapılanlar: Volume reload + Qdrant yeniden açma +
        gömme (hepsi tek `encode` çağrısında). Filtreler (program/sınıf/tema)
        öğe başına ayrı uygulanmaya devam eder - temalar birbirine karışmaz.
        """

        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Bu konteyner sıcak kalırken başka bir konteynerde (index_pdf) commit
        # edilmiş yeni belgeleri görebilmek için reload. Volume reload() açık
        # dosya varken başarısız olur (embedded Qdrant'ın .lock'u dâhil) - bu
        # yüzden client önce kapatılıp reload'dan sonra yeniden açılıyor.
        try:
            self._qdrant.close()
            rag_storage_volume.reload()
            self._qdrant = QdrantClient(path=QDRANT_STORAGE_PATH)
            collection_exists = self._qdrant.collection_exists(QDRANT_COLLECTION_NAME)
        except Exception as error:  # noqa: BLE001 - Volume/Qdrant altyapı çağrısı.
            return False, f"Belge dizini tazelenemedi: {error}", {}, {}
        if not collection_exists:
            return True, "", {}, {}

        try:
            query_texts = [
                str((items[index].get("retrieval") or {}).get("query") or items[index].get("user") or "")
                for index in retrieval_indexes
            ]
            query_vectors = self._embedder.encode(query_texts, normalize_embeddings=True)
        except Exception as error:  # noqa: BLE001 - gömme üçüncü parti bir ML çağrısı.
            return False, f"Getirim sorgusu gömülemedi: {error}", {}, {}

        contexts: dict[int, str] = {}
        sources: dict[int, list[dict[str, object]]] = {}
        for position, index in enumerate(retrieval_indexes):
            spec = items[index].get("retrieval") or {}
            conditions = []
            if spec.get("programId"):
                conditions.append(
                    FieldCondition(key="program_id", match=MatchValue(value=str(spec["programId"])))
                )
            if spec.get("grade"):
                conditions.append(
                    FieldCondition(key="grade", match=MatchValue(value=str(spec["grade"])))
                )
            if spec.get("theme"):
                conditions.append(
                    FieldCondition(
                        key="theme_key", match=MatchValue(value=_theme_match_key(str(spec["theme"])))
                    )
                )

            requested_top_k = int(_number_or(spec.get("topK"), DEFAULT_TOP_K))
            try:
                hits = _retrieve_hits(
                    self._qdrant,
                    query_vectors[position].tolist(),
                    requested_top_k,
                    Filter(must=conditions) if conditions else None,
                )
            except Exception as error:  # noqa: BLE001 - yerel Qdrant okuması.
                return False, f"Belge dizininden okunamadı: {error}", {}, {}

            if not hits:
                continue
            contexts[index] = "\n\n---\n\n".join(
                str((hit.payload or {}).get("contextualized_text") or (hit.payload or {}).get("text", ""))
                for hit in hits
            )
            sources[index] = _build_sources(hits)

        return True, "", contexts, sources

    def _run_batch_query(
        self,
        items: list[dict[str, object]],
        top_k: int,
        program_id: str | None,
    ) -> tuple[bool, str, list[dict[str, object]] | None]:
        """Birden çok soruyu TEK partide yanıtlar; sonuçlar giriş sırasıyla döner.

        Neden parti: ölçüldü (bkz. `modal app logs turkish-rag-system`), sıcak
        bir konteynerde tek sorgu ~10 s sürüyor ve bunun 7-8,6 s'si vLLM
        üretimi - `Processed prompts: 1/1`, ~29 çıktı token/s. Bu, 7B bir
        modelin A10G'de TEK dizilik çözme hızı; darboğaz GPU'nun bellek bant
        genişliği, hesap gücü değil. vLLM birden çok diziyi birlikte
        çözdüğünde toplam süre neredeyse değişmiyor, yani N zayıf öğrenme
        çıktısı için N × 10 s yerine ~10 s ödeniyor.

        Parti başına BİR kez yapılanlar (eskiden sorgu başınaydı): Volume
        reload + Qdrant yeniden açma, gömme çağrısı (hepsi tek `encode`'da).
        Qdrant araması ve filtreler (program_id/grade/theme_key) öğe başına
        ayrı ayrı uygulanmaya devam ediyor - temalar birbirine karışmaz.

        Altyapı hataları (volume/gömme/Qdrant/üretim) tüm parti için `False`
        döndürür; çağıran taraf tek tek sorgulamaya geri düşebilir (bkz.
        `approved_data_analyzer.py::_attach_rag_context`). Getirimi boş çıkan
        öğe partiye hiç girmez, kendi `no_answer` sonucunu alır - diğerlerini
        etkilemez.
        """

        if not items:
            return False, "Sorgu listesi boş olamaz.", None
        questions = [str(item.get("question") or "").strip() for item in items]
        if not all(questions):
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
            embedded_texts = [
                str(item.get("retrievalQuery") or "").strip() or question
                for item, question in zip(items, questions)
            ]
            query_vectors = self._embedder.encode(embedded_texts, normalize_embeddings=True)
        except Exception as error:  # noqa: BLE001 - gömme üçüncü parti bir ML çağrısı; tek bir
            # sorgu tüm servis konteynerini çökertmemeli.
            return False, f"Soru gömülemedi: {error}", None

        def _no_answer() -> dict[str, object]:
            return {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []}

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        try:
            collection_exists = self._qdrant.collection_exists(QDRANT_COLLECTION_NAME)
        except Exception as error:  # noqa: BLE001 - yerel Qdrant okuması; bozuk/erişilemeyen
            # bir depo tüm servisi çökertmemeli.
            return False, f"Belge dizininden okunamadı: {error}", None
        if not collection_exists:
            return True, "Bu bilgi belgede bulunmuyor.", [_no_answer() for _ in items]

        results: list[dict[str, object] | None] = [None] * len(items)
        conversations: list[list[dict[str, str]]] = []
        generated_indexes: list[int] = []
        hits_by_index: dict[int, list] = {}

        for index, (item, question) in enumerate(zip(items, questions)):
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
            grade = item.get("grade") or None
            theme = item.get("theme") or None
            filter_conditions = []
            if program_id:
                filter_conditions.append(FieldCondition(key="program_id", match=MatchValue(value=program_id)))
            if grade:
                filter_conditions.append(FieldCondition(key="grade", match=MatchValue(value=str(grade))))
            if theme:
                filter_conditions.append(
                    FieldCondition(key="theme_key", match=MatchValue(value=_theme_match_key(str(theme))))
                )
            query_filter = Filter(must=filter_conditions) if filter_conditions else None

            try:
                hits = _retrieve_hits(self._qdrant, query_vectors[index].tolist(), top_k, query_filter)
            except Exception as error:  # noqa: BLE001 - yerel Qdrant okuması; bozuk/erişilemeyen
                # bir depo tüm servisi çökertmemeli.
                return False, f"Belge dizininden okunamadı: {error}", None

            if not hits:
                results[index] = _no_answer()
                continue

            # `sources` da bu son listeden üretilir: rapordaki kaynak listesi
            # modelin gerçekten gördüğü bağlamla aynı kalmalı.
            context_blocks = [
                str((hit.payload or {}).get("contextualized_text") or (hit.payload or {}).get("text", ""))
                for hit in hits
            ]
            context_text = "\n\n---\n\n".join(context_blocks)
            conversations.append([
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"BAĞLAM:\n{context_text}\n\nSORU: {question}\n\n"
                    "Yalnızca yukarıdaki BAĞLAM'a dayanarak Türkçe yanıtla.",
                },
            ])
            generated_indexes.append(index)
            hits_by_index[index] = hits

        if conversations:
            try:
                from vllm import SamplingParams

                # Konuşma LİSTESİ veriliyor - vLLM partiyi kendi sıralayıp
                # birlikte çözüyor ve çıktıları giriş sırasıyla döndürüyor.
                # bkz. _run_agent_prompts'taki 2026-08-22 notu (0,3 denenip 0,1'e geri alındı).
                outputs = self._llm.chat(conversations, SamplingParams(temperature=0.1, max_tokens=1024))
            except Exception as error:  # noqa: BLE001 - vLLM üretimi üçüncü parti bir ML çağrısı;
                # bir sorgunun başarısız olması servis konteynerini çökertmemeli.
                return False, f"Yanıt üretilemedi: {error}", None
            if len(outputs) != len(conversations):
                return False, "Toplu üretimde yanıt sayısı sorgu sayısıyla eşleşmedi.", None

            for output, index in zip(outputs, generated_indexes):
                results[index] = {
                    "answer": output.outputs[0].text.strip(),
                    "sources": _build_sources(hits_by_index[index]),
                }

        return True, "Yanıt üretildi.", [result or _no_answer() for result in results]


def _number_or(value: object, fallback: int) -> int:
    """Sayıya çevrilemeyen `maxTokens` isteği sessizce varsayılana düşer -
    bir ajanın bozuk alanı yüzünden tüm parti reddedilmemeli."""

    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _reject_agent_prompts(items: list[object]) -> str:
    """Geçersizse Türkçe ret sebebi, geçerliyse boş string döndürür.

    Sınırların gerekçesi `MAX_AGENT_*` sabitlerinin yanında yazılı: parola
    kapısı kötü niyetliyi, bu kontroller hatayı durduruyor.
    """

    if len(items) > MAX_AGENT_PROMPTS:
        return f"Tek istekte en çok {MAX_AGENT_PROMPTS} ajan prompt'u gönderilebilir."
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            return f"{index}. ajan prompt'u geçersiz."
        system = str(item.get("system") or "").strip()
        user = str(item.get("user") or "").strip()
        if not system or not user:
            return f"{index}. ajan prompt'unda system ve user alanları zorunludur."
        if len(system) + len(user) > MAX_AGENT_PROMPT_CHARS:
            return (
                f"{index}. ajan prompt'u {MAX_AGENT_PROMPT_CHARS} karakter sınırını aşıyor."
            )
    return ""


def _build_sources(hits) -> list[dict[str, object]]:
    """Qdrant isabetlerini yanıtın `sources` listesine çevirir."""

    return [
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


@app.local_entrypoint()
def main(
    pdf_path: str,
    program_id: str,
    question: str = "Bu belge ne hakkında?",
    start_page: int | None = None,
    end_page: int | None = None,
    document_title: str | None = None,
    replace: bool = False,
) -> None:
    """Uçtan uca örnek kullanım:

        modal run rag_service.py --pdf-path C:\\yol\\ornek.pdf --program-id tde-9-tymm \
            --start-page 65 --end-page 97 --question "..."

    Belgenin adı `DOCUMENT_TITLES` kaydından gelir; `--document-title` ile
    geçersiz kılınabilir. Dosya adı KULLANILMAZ - bu ad öğretmenin raporundaki
    kaynak gösteriminde görünüyor.

    `--replace`: indekslemeden önce bu programa ait mevcut parçaları siler.
    Belge adı DEĞİŞTİYSE bu ŞARTTIR. Sebep: nokta kimliği içerik adresli ve
    `document_name` o kimliğin parçası (`_deterministic_point_id`) - yeni adla
    yazılan parçalar YENİ kimlikler alır, eskiler üzerine yazılmaz ve dizinde
    aynı içerik iki kez, iki farklı adla kalır. Getirim bunu hatasızca yutar,
    yalnız sonuç bozulur.

    Bu fonksiyon yalnızca örnektir; hiçbir mevcut MAHIR backend dosyası bunu
    çağırmaz (proje kapsam kararı: yalnızca örnek kod, canlı entegrasyon yok -
    canlı entegrasyon `backend/app/rag_client.py` + `web_query` üzerinden).
    """

    pdf_bytes = Path(pdf_path).read_bytes()
    document_name = resolve_document_title(program_id, document_title)

    if replace:
        clear_ok, clear_message = clear_index.remote(program_id)
        print(f"[rag_service] clear_index: ok={clear_ok} mesaj={clear_message}", flush=True)
        if not clear_ok:
            return

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
#         # İkinci argüman belgenin RESMÎ adı - dosya adı değil (bkz.
#         # DOCUMENT_TITLES): bu değer öğretmenin raporunda kaynak olarak görünür.
#         ok, message, data = index_pdf.remote(
#             f.read(), "Ortaöğretim ... Öğretim Programı (2024)", "tde-9-tymm"
#         )
#
#     ok, message, data = rag().query.remote("Soru metni", 5, "tde-9-tymm")
#
# Ya da MAHIR'in kendi backend'inden (yalnızca stdlib, modal SDK gerekmez):
# `modal deploy` sonrası basılan web_query URL'ini MAHIR_RAG_REMOTE_URL olarak
# ayarlayın, `backend/app/rag_client.py`'deki query_rag_context(...) çağırsın.
