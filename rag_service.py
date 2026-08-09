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

SYSTEM_PROMPT = (
    "Sen MAHİR projesi için çalışan, belge tabanlı bir soru-cevap asistanısın. "
    "Yanıtını yalnızca sana BAĞLAM olarak verilen metne dayandır; kendi genel "
    "bilgini, tahminini veya BAĞLAM dışındaki hiçbir kaynağı kullanma. "
    "Eğer sorunun yanıtı BAĞLAM içinde yoksa ya da BAĞLAM yetersizse, başka "
    "hiçbir açıklama eklemeden tam olarak şu cümleyi yaz: "
    '"Bu bilgi belgede bulunmuyor." '
    "Yanıtların Türkçe, kısa, açık ve yalnızca BAĞLAM'daki ifadelerle "
    "doğrulanabilir olsun; yorum katma veya BAĞLAM'ın ötesinde sonuç çıkarma."
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
    .pip_install("qdrant-client", "sentence-transformers")
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


@app.function(
    image=indexing_image,
    gpu="A10G",
    memory=16384,
    volumes=VOLUMES,
    timeout=600,
)
def index_pdf(pdf_bytes: bytes, document_name: str) -> tuple[bool, str, dict[str, object] | None]:
    """PDF baytlarını Docling ile ayrıştırır, HybridChunker ile parçalara
    ayırır, bge-m3 ile gömer ve Qdrant'a yazar.

    Dönüş, `backend/app/remote_ocr_client.py`nin `run_remote_image_group_ocr`
    ile aynı (ok, mesaj, structuredData) kalıbını izler - bu fonksiyon Modal
    üzerinden `.remote()` ile çağrılacağı için hata durumunda İstisna
    fırlatmak yerine çağırana gösterilebilecek bir Türkçe mesaj döndürür.
    """

    if not pdf_bytes:
        return False, "PDF verisi boş.", None
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        return False, "PDF 20 MB sınırını aşıyor.", None

    # Baytları geçici dosyaya yaz - ocr_engine.py'nin _run_ocr'ıyla aynı desen.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_path = tmp_file.name

    try:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            # MAHİR'e yüklenen PDF'ler taranmış/görüntü tabanlı değil, metni
            # zaten gömülü belgeler - OCR'ı kapatmak hem gereksiz RapidOCR
            # model indirmesini ve her sayfada boş sonuç veren tespit
            # turlarını (gerçek deploy'da görüldü) önler hem de indeksleme
            # süresini kısaltır. Tablo/başlık yapı tespiti (do_table_structure)
            # varsayılan açık kalır - bu OCR'dan bağımsız bir adım.
            pdf_pipeline_options = PdfPipelineOptions()
            pdf_pipeline_options.do_ocr = False
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options)}
            )
            converted_document = converter.convert(tmp_path).document
        except Exception as error:  # noqa: BLE001 - Docling üçüncü parti bir ML pipeline'ı;
            # öğretmenin yüklediği bozuk/desteklenmeyen bir PDF tüm işi çökertmemeli.
            return False, f"PDF ayrıştırılamadı: {error}", None

        # Başlık/tablo yapısını koruyarak parçala (HybridChunker).
        from docling.chunking import HybridChunker
        from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
        from transformers import AutoTokenizer

        tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_MODEL_NAME),
            max_tokens=CHUNK_MAX_TOKENS,
        )
        chunker = HybridChunker(tokenizer=tokenizer)
        chunks = list(chunker.chunk(dl_doc=converted_document))
        if not chunks:
            return False, "Belgeden okunabilir içerik çıkarılamadı.", None

        # contextualize(): başlık bağlamını metne ekler - hem gömme kalitesini
        # hem de sorgu anında LLM'e verilecek bağlamı iyileştirir.
        contextualized_texts = [chunker.contextualize(chunk=chunk) for chunk in chunks]

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
                        "headings": list(getattr(chunk.meta, "headings", None) or []),
                        "chunk_index": index,
                    },
                )
                for index, (chunk, contextualized_text, vector) in enumerate(
                    zip(chunks, contextualized_texts, vectors)
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

        return (
            True,
            f"'{document_name}' işlendi: {len(points)} parça dizine eklendi.",
            {
                "documentName": document_name,
                "chunkCount": len(points),
                "collectionName": QDRANT_COLLECTION_NAME,
            },
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.cls(
    image=inference_image,
    gpu="A10G",
    volumes=VOLUMES,
    scaledown_window=300,  # GPU soğuk başlangıcının sık tetiklenmesini (churn) önler.
    timeout=300,
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
    def query(self, question: str, top_k: int = DEFAULT_TOP_K) -> tuple[bool, str, dict[str, object] | None]:
        """Soruyu göm, Qdrant'tan en yakın parçaları getir, Qwen2.5 ile Türkçe yanıt üret."""

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
            query_vector = self._embedder.encode([question], normalize_embeddings=True)[0].tolist()
        except Exception as error:  # noqa: BLE001 - gömme üçüncü parti bir ML çağrısı; tek bir
            # sorgu tüm servis konteynerini çökertmemeli.
            return False, f"Soru gömülemedi: {error}", None

        no_answer: dict[str, object] = {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []}

        try:
            if not self._qdrant.collection_exists(QDRANT_COLLECTION_NAME):
                return True, "Bu bilgi belgede bulunmuyor.", no_answer
            hits = self._qdrant.query_points(
                collection_name=QDRANT_COLLECTION_NAME,
                query=query_vector,
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
                "headings": (hit.payload or {}).get("headings", []),
                "excerpt": str((hit.payload or {}).get("text", ""))[:300],
                "score": hit.score,
            }
            for hit in hits
        ]
        return True, "Yanıt üretildi.", {"answer": answer, "sources": sources}


@app.local_entrypoint()
def main(pdf_path: str, question: str = "Bu belge ne hakkında?") -> None:
    """Uçtan uca örnek kullanım:

        modal run rag_service.py --pdf-path C:\\yol\\ornek.pdf --question "..."

    Bu fonksiyon yalnızca örnektir; hiçbir mevcut MAHIR backend dosyası bunu
    çağırmaz (proje kapsam kararı: yalnızca örnek kod, canlı entegrasyon yok).
    """

    pdf_bytes = Path(pdf_path).read_bytes()
    document_name = Path(pdf_path).name

    print(f"[rag_service] '{document_name}' dizine ekleniyor...", flush=True)
    index_ok, index_message, index_data = index_pdf.remote(pdf_bytes, document_name)
    print(f"[rag_service] index_pdf: ok={index_ok} mesaj={index_message} veri={index_data}", flush=True)
    if not index_ok:
        return

    print(f"[rag_service] Soru soruluyor: {question!r}", flush=True)
    query_ok, query_message, query_data = RAGInference().query.remote(question)
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
#         ok, message, data = index_pdf.remote(f.read(), "belge.pdf")
#
#     ok, message, data = rag().query.remote("Soru metni")
