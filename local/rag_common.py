"""MAHİR yerel RAG hattının paylaşılan parçaları: ayarlar, CPU gömme, reranker,
Qdrant yardımcıları, günlükleme ve hata tipleri.

`ingestion_pipeline.py` (indeksleme) ve `rag_service.py` (sorgu) bu modülü
import eder; ikisinde de aynı model adı, aynı koleksiyon ve aynı nokta-kimliği
şeması kullanılsın diye tek yerde tutulur. Bu modülün KENDİSİ hafiftir: torch,
sentence-transformers ve qdrant-client yalnızca ilgili metot çağrılınca import
edilir (bkz. `backend/app/ocr_engine.py`'deki ertelenmiş import düzeni) -
`Settings.from_env()` hiçbir ML kütüphanesi kurulu olmadan da çalışır.

Donanım varsayımı: 4-6 GB VRAM'li tek GPU. Gömme modeli bu yüzden KASITLI olarak
CPU'da (`CpuEmbedder`); GPU, indeksleme sırasında PaddleOCR-VL'ye, sorgu
sırasında yerel LLM'e (llama-server, Qwen3-4B-Instruct-2507 Q4_K_M ~3,1 GB) kalır -
reranker da bu yüzden varsayılan olarak CPU'da (`RERANKER_DEVICE=cpu`).
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:  # yalnız tip belirtimi - çalışma zamanında değerlendirilmez
    from qdrant_client import QdrantClient
    from sentence_transformers import CrossEncoder, SentenceTransformer

LOCAL_DIR = Path(__file__).resolve().parent
DEFAULT_DOTENV_PATH = LOCAL_DIR / ".env"

# Getirim hiçbir şey bulamadığında ya da model bağlamda yanıt bulamadığında
# dönen metin. `backend/app/approved_data_analyzer.py::_RAG_NO_ANSWER_TEXT`
# ile birebir aynı tutulmalı (backend bu cümleyi tanıyıp teşhisi eliyor).
NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."

# uuid5 ad alanı. Aynı (program, belge, sıra, metin) dörtlüsü her zaman aynı
# nokta kimliğini üretir (bkz. tests/test_rag_service_indexing.py'deki altın
# değer); değeri değiştirmek kalıcı şemayı bozar.
_POINT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mahir-rag-chunk")

logger = logging.getLogger("mahir.local")


# --- Hata tipleri ---------------------------------------------------------------


class RagConfigError(RuntimeError):
    """Eksik/geçersiz ortam değişkeni - kullanıcıya gösterilebilir Türkçe mesaj taşır."""


class IngestionError(RuntimeError):
    """İndeksleme adımlarından biri (ayrıştırma, gömme, Qdrant yazımı) başarısız."""


class OcrError(RuntimeError):
    """PaddleOCR-VL tek bir görselde başarısız - çağıran sayfayı atlayıp devam eder."""


class LlmError(RuntimeError):
    """LLM (llama-server ya da başka OpenAI uyumlu uç) çağrısı başarısız; anahtar/istek gövdesi mesaja girmez."""


# --- Günlükleme -----------------------------------------------------------------------


def configure_logging(level: str = "INFO") -> None:
    """Kök logger'ı tek satırlık, zaman damgalı biçimle kurar (idempotent)."""

    numeric = getattr(logging, level.upper(), None)
    if not isinstance(numeric, int):
        raise RagConfigError(f"LOG_LEVEL geçersiz: {level!r} (DEBUG/INFO/WARNING/ERROR).")
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # Üçüncü parti kütüphanelerin gürültüsünü kıs - hattın kendi mesajları öne çıksın.
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "transformers", "docling"):
        logging.getLogger(noisy).setLevel(max(numeric, logging.WARNING))


# --- Ortam değişkeni okuma ----------------------------------------------------------


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise RagConfigError(f"{name} tam sayı olmalı, verilen: {raw!r}.") from error
    if minimum is not None and value < minimum:
        raise RagConfigError(f"{name} en az {minimum} olmalı, verilen: {value}.")
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw.replace(",", "."))
    except ValueError as error:
        raise RagConfigError(f"{name} ondalık sayı olmalı, verilen: {raw!r}.") from error
    if minimum is not None and value < minimum:
        raise RagConfigError(f"{name} en az {minimum} olmalı, verilen: {value}.")
    if maximum is not None and value > maximum:
        raise RagConfigError(f"{name} en çok {maximum} olmalı, verilen: {value}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "evet"}:
        return True
    if raw in {"0", "false", "no", "off", "hayır", "hayir"}:
        return False
    raise RagConfigError(f"{name} true/false olmalı, verilen: {raw!r}.")


def physical_cpu_count() -> int:
    """Fiziksel çekirdek sayısı; psutil yoksa mantıksal sayının yarısı (HT varsayımı).

    torch/ONNX çıkarımında iş parçacığı sayısını mantıksal çekirdeğe
    eşitlemek genellikle yavaşlatır - varsayılan bu yüzden fiziksel sayı.
    """

    try:
        import psutil  # noqa: PLC0415 - isteğe bağlı bağımlılık (paddlex getirebilir)

        physical = psutil.cpu_count(logical=False)
        if physical:
            return int(physical)
    except ImportError:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


# --- Ayarlar --------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Tüm hat ayarları - `.env` + süreç ortamından bir kez okunur, sonra değişmez."""

    # LLM - yerel llama-server (OpenAI uyumlu /v1). Aynı istemci herhangi bir
    # OpenAI uyumlu uca da konuşabilir; yalnız LLM_BASE_URL/LLM_API_KEY değişir.
    llm_base_url: str
    llm_api_key: str
    model_name: str
    llm_context_window: int
    llm_temperature: float
    llm_max_tokens: int
    llm_timeout_s: float
    # Qdrant
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: str
    qdrant_collection: str
    # Gömme (CPU)
    embedding_model: str
    embedding_device: str
    embedding_threads: int
    embedding_batch_size: int
    chunk_max_tokens: int
    # OCR (GPU)
    ocr_enabled: bool
    ocr_device: str
    ocr_engine: str
    ocr_max_image_side: int
    ocr_min_text_chars_per_page: int
    ocr_min_figure_side_px: int
    # Reranker
    reranker_enabled: bool
    reranker_model: str
    reranker_device: str
    reranker_candidate_multiplier: int
    reranker_min_candidates: int
    reranker_batch_size: int
    reranker_max_length: int
    reranker_min_score: float
    # Docling
    docling_threads: int
    # Servis
    service_host: str
    service_port: int
    default_top_k: int
    max_top_k: int
    relative_score_floor: float
    log_level: str
    dotenv_path: Path | None = field(default=None, compare=False)

    @classmethod
    def from_env(cls, dotenv_path: Path | None = DEFAULT_DOTENV_PATH) -> "Settings":
        """`.env` dosyasını (varsa) süreç ortamına yükler ve ayarları doğrular.

        `override=False`: kabukta zaten tanımlı bir değişken `.env`'i ezer -
        geçici denemeler (`OCR_ENABLED=false python ...`) dosyayı düzenlemeden
        yapılabilir. `.env`'deki `PYTORCH_CUDA_ALLOC_CONF`, `PADDLE_PDX_*`,
        `HF_HOME` gibi kütüphanelerin doğrudan ortamdan okuduğu değerler de bu
        çağrıyla ortama yazılır; bu yüzden torch/paddle import edilmeden ÖNCE
        çağrılmalı (bu modülde ağır importlar ertelenmiş durumda).

        LLM için anahtar ZORUNLU DEĞİL: varsayılan uç yerel llama-server
        (`LLM_BASE_URL`), anahtar kabul etmez/istemez. Başka bir OpenAI uyumlu
        uca geçilirse `LLM_API_KEY` verilir.
        """

        resolved_path: Path | None = None
        if dotenv_path is not None and Path(dotenv_path).is_file():
            from dotenv import load_dotenv  # noqa: PLC0415 - hafif ama isteğe bağlı

            load_dotenv(dotenv_path, override=False)
            resolved_path = Path(dotenv_path)

        llm_base_url = _env_str("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        if not llm_base_url.startswith(("http://", "https://")):
            raise RagConfigError(f"LLM_BASE_URL http(s):// ile başlamalı, verilen: {llm_base_url!r}.")
        llm_context_window = _env_int("LLM_CONTEXT_WINDOW", 8192, minimum=1024)
        llm_max_tokens = _env_int("LLM_MAX_TOKENS", 1024, minimum=1)
        if llm_max_tokens >= llm_context_window:
            raise RagConfigError(
                f"LLM_MAX_TOKENS ({llm_max_tokens}) LLM_CONTEXT_WINDOW'dan ({llm_context_window}) küçük olmalı."
            )

        reranker_device = _env_str("RERANKER_DEVICE", "cpu").lower()
        if reranker_device not in {"auto", "cpu", "cuda"}:
            raise RagConfigError(f"RERANKER_DEVICE auto/cpu/cuda olmalı, verilen: {reranker_device!r}.")
        ocr_engine = _env_str("OCR_ENGINE", "transformers")
        if ocr_engine not in {"transformers", "paddle_dynamic", "paddle_static", "paddle"}:
            raise RagConfigError(f"OCR_ENGINE geçersiz: {ocr_engine!r}.")

        default_top_k = _env_int("RAG_DEFAULT_TOP_K", 5, minimum=1)
        max_top_k = _env_int("RAG_MAX_TOP_K", 20, minimum=1)
        if default_top_k > max_top_k:
            raise RagConfigError(f"RAG_DEFAULT_TOP_K ({default_top_k}) RAG_MAX_TOP_K'yı ({max_top_k}) aşamaz.")

        return cls(
            llm_base_url=llm_base_url,
            llm_api_key=_env_str("LLM_API_KEY", ""),
            model_name=_env_str("MODEL_NAME", "qwen3-4b-instruct-2507-q4_k_m"),
            llm_context_window=llm_context_window,
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.1, minimum=0.0, maximum=2.0),
            llm_max_tokens=llm_max_tokens,
            llm_timeout_s=_env_float("LLM_TIMEOUT_S", 180.0, minimum=1.0),
            # "localhost" DEĞİL: Windows'ta httpx önce ::1'i dener, Docker Desktop
            # yalnız IPv4 loopback'e bağlıdır ve reddedilen IPv6 denemesi her
            # istekte ~2 s yer (ölçüldü: 2.050 ms -> 5 ms).
            qdrant_host=_env_str("QDRANT_HOST", "127.0.0.1"),
            qdrant_port=_env_int("QDRANT_PORT", 6333, minimum=1),
            qdrant_api_key=_env_str("QDRANT_API_KEY", ""),
            qdrant_collection=_env_str("QDRANT_COLLECTION", "mahir_local_chunks_v1"),
            embedding_model=_env_str("EMBEDDING_MODEL", "BAAI/bge-m3"),
            embedding_device=_env_str("EMBEDDING_DEVICE", "cpu"),
            embedding_threads=_env_int("EMBEDDING_THREADS", 0, minimum=0),
            embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", 8, minimum=1),
            chunk_max_tokens=_env_int("CHUNK_MAX_TOKENS", 320, minimum=64),
            ocr_enabled=_env_bool("OCR_ENABLED", True),
            ocr_device=_env_str("OCR_DEVICE", "gpu:0"),
            ocr_engine=ocr_engine,
            ocr_max_image_side=_env_int("OCR_MAX_IMAGE_SIDE", 1600, minimum=256),
            ocr_min_text_chars_per_page=_env_int("OCR_MIN_TEXT_CHARS_PER_PAGE", 40, minimum=0),
            ocr_min_figure_side_px=_env_int("OCR_MIN_FIGURE_SIDE_PX", 120, minimum=1),
            reranker_enabled=_env_bool("RERANKER_ENABLED", True),
            reranker_model=_env_str("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
            reranker_device=reranker_device,
            reranker_candidate_multiplier=_env_int("RERANKER_CANDIDATE_MULTIPLIER", 3, minimum=1),
            reranker_min_candidates=_env_int("RERANKER_MIN_CANDIDATES", 12, minimum=1),
            reranker_batch_size=_env_int("RERANKER_BATCH_SIZE", 8, minimum=1),
            reranker_max_length=_env_int("RERANKER_MAX_LENGTH", 640, minimum=64),
            reranker_min_score=_env_float("RERANKER_MIN_SCORE", 0.0, minimum=0.0, maximum=1.0),
            docling_threads=_env_int("DOCLING_THREADS", 0, minimum=0),
            service_host=_env_str("RAG_SERVICE_HOST", "127.0.0.1"),
            service_port=_env_int("RAG_SERVICE_PORT", 8001, minimum=1),
            default_top_k=default_top_k,
            max_top_k=max_top_k,
            relative_score_floor=_env_float("RAG_RELATIVE_SCORE_FLOOR", 0.5, minimum=0.0, maximum=1.0),
            log_level=_env_str("LOG_LEVEL", "INFO"),
            dotenv_path=resolved_path,
        )

    def candidate_pool_size(self, top_k: int) -> int:
        """Reranker açıkken Qdrant'tan çekilecek ham aday sayısı."""

        return max(top_k * self.reranker_candidate_multiplier, self.reranker_min_candidates)

    def context_char_budget(self, chars_per_token: float = 2.5) -> int:
        """LLM'e gönderilebilecek BAĞLAM için karakter üst sınırı.

        `LLM_CONTEXT_WINDOW` (llama-server `-c` ile aynı olmalı) - üretim payı
        (`LLM_MAX_TOKENS`) - sistem promptu/şablon payı (~512 token), Türkçe
        için temkinli 2,5 karakter/token ile çarpılır. Bütçe aşılırsa parça
        kırpmak, llama-server'ın "context size exceeded" hatasından iyidir.
        """

        prompt_tokens = self.llm_context_window - self.llm_max_tokens - 512
        return max(2000, int(prompt_tokens * chars_per_token))

    def resolved_threads(self, requested: int) -> int:
        return requested if requested > 0 else physical_cpu_count()


# --- Getirim isabeti ------------------------------------------------------------------


@dataclass
class Hit:
    """Qdrant'tan dönen tek parça + (varsa) reranker skoru."""

    point_id: str
    payload: dict[str, Any]
    retrieval_score: float
    rerank_score: float | None = None

    @property
    def text(self) -> str:
        return str(self.payload.get("text") or "")

    @property
    def contextualized_text(self) -> str:
        """Başlık zinciriyle zenginleştirilmiş metin - gömme ve reranker bunu görür."""

        return str(self.payload.get("contextualized_text") or self.text)

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.retrieval_score


def deterministic_point_id(program_id: str, document_name: str, chunk_index: int, text: str) -> str:
    """Aynı içerik -> aynı Qdrant nokta kimliği (uuid5, içerik adresli).

    Aynı PDF'i yeniden indekslemek parçaları ikizlemez, `upsert` üzerine yazar.
    `chunk_index` anahtarın parçası çünkü HybridChunker tekrarlanan tablo
    başlıkları yüzünden aynı metinli iki parça üretebilir.
    """

    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{program_id}|{document_name}|{chunk_index}|{text}"))


def drop_weak_hits(hits: Sequence[Hit], floor_ratio: float) -> list[Hit]:
    """En iyi isabetin `floor_ratio` katının altında kalanları atar; en az bir isabet bırakır.

    Mutlak bir kosinüs eşiği yerine göreli eşik: bge-m3 skorları belgeye/sorguya
    göre kayıyor (canlı ölçümlerde aynı dizinde 0,60-0,94). Skora göre azalan
    sıra beklenir (Qdrant öyle döndürür).
    """

    if not hits:
        return []
    top = hits[0].retrieval_score
    if top <= 0:
        return list(hits)
    cutoff = top * floor_ratio
    kept = [hit for hit in hits if hit.retrieval_score >= cutoff]
    return kept or [hits[0]]


# --- Gömme (CPU) ----------------------------------------------------------------------


class CpuEmbedder:
    """`sentence-transformers` ile bge-m3 dense gömme - CPU'da, iş parçacığı sayısı sabitlenmiş.

    Tek örnek paylaşılır; `encode` çağrıları kilitle sıralanır (FastAPI'nin
    thread-pool'undan eşzamanlı istek gelebilir, torch CPU çıkarımı zaten
    çekirdekleri dolduruyor - paralel çağrı yalnız çekişme yaratır).
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        threads: int = 0,
        batch_size: int = 8,
        max_seq_length: int = 1024,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._threads = threads
        self._batch_size = batch_size
        self._max_seq_length = max_seq_length
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def device(self) -> str:
        return self._device

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Modeli belleğe alır (idempotent). İlk çağrıda HF'den ~2,2 GB indirir."""

        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch  # noqa: PLC0415
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            if self._device == "cpu":
                threads = self._threads if self._threads > 0 else physical_cpu_count()
                torch.set_num_threads(threads)
                logger.info("Gömme modeli yükleniyor: %s (cpu, %d iş parçacığı)", self._model_name, threads)
            else:
                logger.info("Gömme modeli yükleniyor: %s (%s)", self._model_name, self._device)
            model = SentenceTransformer(self._model_name, device=self._device)
            # bge-m3 8192'ye kadar kabul eder; parçalar 512 token olduğundan CPU
            # süresini sınırlamak için kırpıyoruz.
            model.max_seq_length = self._max_seq_length
            self._model = model

    @property
    def dimension(self) -> int:
        self.load()
        assert self._model is not None
        dimension = self._model.get_sentence_embedding_dimension()
        if not dimension:
            raise RagConfigError(f"{self._model_name} gömme boyutu okunamadı.")
        return int(dimension)

    def embed_documents(self, texts: Sequence[str], show_progress: bool = False) -> list[list[float]]:
        """Belge parçalarını gömer; çıktı L2-normalize (cosine için iç çarpım yeterli)."""

        if not texts:
            return []
        self.load()
        assert self._model is not None
        with self._lock:
            vectors = self._model.encode(
                list(texts),
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=show_progress,
            )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


# --- Reranker (cross-encoder) ---------------------------------------------------------


class CrossEncoderReranker:
    """`BAAI/bge-reranker-v2-m3` ile (soru, parça) çiftlerini yeniden puanlar.

    Varsayılan cihaz CPU: VRAM sorgu anında yerel LLM'e (llama-server, Qwen3-4B
    Q4_K_M ~3,1 GB) ve OCR işçisine (~2-3 GB) ayrılmıştır, fp16 reranker
    (~1,2-1,5 GB) 4 GB karta sığmaz, 6 GB'de payı daraltır.
    `device="cuda"`/`"auto"` ancak LLM kısmi offload ile (`LLM_GPU_LAYERS`
    düşürülerek) yer açıldığında anlamlı; GPU'da OOM olursa model CPU'ya
    taşınıp aynı parti yeniden denenir - sorgu düşmez, yalnız yavaşlar.
    """

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        batch_size: int = 8,
        max_length: int = 1024,
        min_score: float = 0.0,
        threads: int = 0,
    ) -> None:
        self._model_name = model_name
        self._requested_device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._min_score = min_score
        self._threads = threads
        self._model: CrossEncoder | None = None
        self._device: str | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def device(self) -> str | None:
        """Çözümlenmiş cihaz ("cuda"/"cpu"); model yüklenmeden `None`."""

        return self._device

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _resolve_device(self) -> str:
        import torch  # noqa: PLC0415

        if self._requested_device == "cuda":
            if not torch.cuda.is_available():
                raise RagConfigError("RERANKER_DEVICE=cuda istendi ama CUDA kullanılamıyor.")
            return "cuda"
        if self._requested_device == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _build(self, device: str) -> "CrossEncoder":
        import torch  # noqa: PLC0415
        from sentence_transformers import CrossEncoder  # noqa: PLC0415

        model_kwargs: dict[str, Any] = {}
        if device == "cuda":
            model_kwargs["torch_dtype"] = torch.float16
        else:
            threads = self._threads if self._threads > 0 else physical_cpu_count()
            torch.set_num_threads(threads)
        logger.info("Reranker yükleniyor: %s (%s)", self._model_name, device)
        # bge-reranker tek logit üretir; sigmoid ile 0-1 aralığına çekiyoruz ki
        # `RERANKER_MIN_SCORE` mutlak bir eşik olarak anlamlı olsun.
        return CrossEncoder(
            self._model_name,
            max_length=self._max_length,
            device=device,
            activation_fn=torch.nn.Sigmoid(),
            model_kwargs=model_kwargs or None,
        )

    def load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            device = self._resolve_device()
            self._model = self._build(device)
            self._device = device

    def _predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Skorları döndürür; GPU'da bellek yetmezse CPU'ya düşüp yeniden dener."""

        import torch  # noqa: PLC0415

        self.load()
        assert self._model is not None
        try:
            scores = self._model.predict(pairs, batch_size=self._batch_size, convert_to_numpy=True, show_progress_bar=False)
        except torch.cuda.OutOfMemoryError:
            if self._device != "cuda":
                raise
            logger.warning(
                "Reranker GPU'da belleğe sığmadı (%d çift); CPU'ya taşınıp yeniden deneniyor. "
                "Kalıcı çözüm: RERANKER_DEVICE=cpu ya da RERANKER_BATCH_SIZE'ı düşürün.",
                len(pairs),
            )
            self._model = None
            torch.cuda.empty_cache()
            self._model = self._build("cpu")
            self._device = "cpu"
            scores = self._model.predict(pairs, batch_size=self._batch_size, convert_to_numpy=True, show_progress_bar=False)
        finally:
            if self._device == "cuda":
                torch.cuda.empty_cache()
        return [float(score) for score in scores]

    def rerank(self, query: str, candidates: Sequence[Hit], top_k: int) -> list[Hit]:
        """Adayları cross-encoder skoruna göre sıralar, eşik uygular, ilk `top_k`'yı döndürür.

        Girdi listesindeki `Hit` nesnelerinin `rerank_score` alanı yerinde
        doldurulur. Eşik (`min_score`) her şeyi elerse en iyi aday yine de
        kalır - boş bağlam, düşük skorlu bağlamdan daha kötü bir sonuç
        (öğretmene "belgede yok" demek) üretir.
        """

        if not candidates:
            return []
        pairs = [(query, hit.contextualized_text) for hit in candidates]
        with self._lock:
            scores = self._predict(pairs)
        for hit, score in zip(candidates, scores):
            hit.rerank_score = score
        ordered = sorted(candidates, key=lambda hit: hit.rerank_score or 0.0, reverse=True)
        if self._min_score > 0:
            kept = [hit for hit in ordered if (hit.rerank_score or 0.0) >= self._min_score]
            ordered = kept or ordered[:1]
        return ordered[:top_k]


# --- Qdrant -----------------------------------------------------------------------------


def make_qdrant_client(settings: Settings, timeout_s: int = 30) -> "QdrantClient":
    """REST istemcisi (docker-compose.yml'deki loopback portuna)."""

    from qdrant_client import QdrantClient  # noqa: PLC0415

    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key or None,
        timeout=timeout_s,
        prefer_grpc=False,
    )


def check_qdrant_ready(client: "QdrantClient", collection: str) -> tuple[bool, str, dict[str, Any]]:
    """Sunucuya ulaşılabiliyor mu, koleksiyon var mı, kaç nokta var - tek çağrıda.

    Hiç istisna fırlatmaz: `(ok, Türkçe mesaj, bilgi)` döndürür; `ok=False`
    yalnız SUNUCUYA ulaşılamadığında (koleksiyonun henüz olmaması normal bir
    durumdur - ilk indekslemeden önce öyle olur).
    """

    info: dict[str, Any] = {"collection": collection, "exists": False, "points": 0}
    try:
        exists = client.collection_exists(collection)
    except Exception as error:  # noqa: BLE001 - bağlantı/yetki/zaman aşımı; hepsi aynı şekilde raporlanır
        return (
            False,
            f"Qdrant'a ulaşılamadı ({error.__class__.__name__}). Sunucu çalışıyor mu? "
            "`docker compose -f local/docker-compose.yml up -d` ile başlatın.",
            info,
        )
    info["exists"] = exists
    if exists:
        try:
            info["points"] = int(client.count(collection, exact=True).count)
        except Exception:  # noqa: BLE001 - sayım başarısız olsa da "var" bilgisi yeterli
            info["points"] = -1
        return True, f"Qdrant hazır; '{collection}' koleksiyonunda {info['points']} nokta.", info
    return True, f"Qdrant hazır; '{collection}' koleksiyonu henüz yok (ilk indekslemede oluşturulur).", info


# Filtrelenen payload alanları: `program_id`/`document_name`/`source_kind` genel,
# `grade`/`theme_key`/`skill_key` müfredat belgelerine özgü (bkz. curriculum.py;
# rag_service.py `retrieve()` bu anahtarlarla `must`/`must_not` kurar).
PAYLOAD_INDEX_FIELDS = ("program_id", "document_name", "source_kind", "grade", "theme_key", "skill_key", "section_kind", "outcome_codes")


def ensure_collection(client: "QdrantClient", collection: str, dimension: int) -> bool:
    """Koleksiyon yoksa (dense, cosine) oluşturur; filtre alanlarına indeks açar.

    Varsa vektör boyutunu doğrular: farklı boyutlu bir gömme modeliyle var olan
    koleksiyona yazmak Qdrant'ta sessizce başarısız olmaz ama noktalar
    karışır - burada açık hata veriyoruz (çözüm: yeni `QDRANT_COLLECTION` adı).
    Payload indeksleri her çağrıda yeniden istenir (idempotent) ki sonradan
    eklenen alanlar eski koleksiyonlarda da indekslensin. Dönüş: yeni
    oluşturulduysa True.
    """

    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams  # noqa: PLC0415

    created = False
    if client.collection_exists(collection):
        existing = client.get_collection(collection).config.params.vectors
        size = getattr(existing, "size", None)
        if isinstance(size, int) and size != dimension:
            raise IngestionError(
                f"'{collection}' koleksiyonu {size} boyutlu vektörler için oluşturulmuş, gömme modeli "
                f"{dimension} üretiyor. Yeni bir QDRANT_COLLECTION adı verin ya da eski koleksiyonu silin."
            )
    else:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        logger.info("Koleksiyon oluşturuldu: %s (%d-d, cosine)", collection, dimension)
        created = True

    for field_name in PAYLOAD_INDEX_FIELDS:
        client.create_payload_index(
            collection_name=collection, field_name=field_name, field_schema=PayloadSchemaType.KEYWORD
        )
    return created
