# MAHİR GPU katmanı - YALNIZ AĞIR BAĞIMLILIKLAR.
#
# ÖNEMLİ: Uygulama kodu bu imaja GİRMEZ. Kod, pod'un ağ diskine (`/workspace`)
# `git clone` ile iner ve `git pull` ile güncellenir. Ayrımın sebebi bu
# projenin geçmişi: 2026-08'deki RunPod denemesi mimari yüzünden değil,
# HER düzeltmenin 15-20 dakikalık `docker build + push` gerektirmesi yüzünden
# terk edildi. Bu ayrımla kod değişikliği ~10 saniye sürer:
#
#     git pull && scripts/gpu_services.sh restart
#
# İmaj yalnız `local/requirements.txt` değişince yeniden kurulur (~ayda 1).
#
# Kurulum:
#     docker build -t <kullanici>/mahir-gpu:latest .
#     docker push  <kullanici>/mahir-gpu:latest
#
# Pod'da beklenen ortam değişkenleri (RunPod panelinden):
#     MAHIR_RAG_SHARED_SECRET, MAHIR_OCR_SHARED_SECRET   (zorunlu - aksi hâlde
#         uçlar korumasız açılır; bkz. local/.env.bulut.example)
#     HF_HOME=/workspace/.cache/huggingface                (modeller ağ diskinde
#         kalsın ki her yeniden başlatmada ~9 GB yeniden inmesin)
#     PADDLE_PDX_MODEL_SOURCE / ~/.paddlex de aynı sebeple /workspace altına
#         bağlanmalı.

# --- llama-server kaynağı ----------------------------------------------------
# Resmî llama.cpp sürümleri Linux için YALNIZ CPU binary'si yayımlıyor
# (`llama-*-bin-ubuntu-x64.tar.gz`); CUDA'lı Linux binary'si için açık bir
# istek var (ggml-org/llama.cpp#16205). Upstream'in desteklediği CUDA yolu
# resmî Docker imajı: binary `/app/llama-server`, yanında kendi .so'ları.
# Tek dosya değil `/app` bütünüyle kopyalanıyor - binary libggml/libllama'ya
# bağlı.
# Her iki ARG da İLK FROM'dan ÖNCE tanımlanmalı: bir FROM'dan sonra gelen ARG
# o aşamaya kapsanır ve sonraki FROM onu boş görür ("base name should not be
# blank" ile build düşer).
ARG LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda
# CUDA 12.8, 12.6 DEĞİL - llama.cpp imajıyla eşleşmesi için. Ölçüldü:
# `libggml-cuda.so` `/usr/local/cuda/lib64`'teki libcudart.so.12 /
# libcublas.so.12'ye bağlanıyor ve bu kütüphaneler `/app`'te DEĞİL, yani
# temel imajdan gelmek zorunda. llama.cpp imajı CUDA 12.8 taşıyor; 12.6
# runtime'ı SONAME olarak uyar ama 12.8'de eklenen simgeleri garanti etmez.
# torch/paddle bu seçimden etkilenmiyor: kendi CUDA kütüphanelerini
# `nvidia-*-cu12` pip paketleriyle getiriyorlar (bkz. local/requirements.txt).
# Temel imaj "runtime" olmalı, "base" değil - cuBLAS yalnız runtime'da var.
ARG CUDA_IMAGE=nvidia/cuda:12.8.1-runtime-ubuntu24.04

FROM ${LLAMA_IMAGE} AS llama
FROM ${CUDA_IMAGE}

# Bu COPY BİLEREK en başta: imaj adı ya da `/app` yolu yanlışsa build
# saniyeler içinde düşsün, 10 GB'lık pip kurulumundan SONRA değil. Bu
# projenin RunPod geçmişi tam olarak "20 dakika bekle, sonra patla"
# döngüsü yüzünden terk edilmişti.
COPY --from=llama /app /opt/llama.cpp

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Sistem paketleri --------------------------------------------------------
# gcc/g++       : PaddleOCR-VL'nin `transformers` motoru Triton ile GPU
#                 kernel'lerini ÇALIŞMA ANINDA derliyor. Önceki denemede bu
#                 blokerdi (Modal build-time GPU ile gizliyordu, RunPod'da
#                 GPU'lu build adımı yok). Kaçış yolu da var:
#                 OCR_ENGINE=paddle_dynamic Triton'a hiç dokunmaz.
# libgl1, libglib2.0-0 : opencv (paddlex + docling'in rapidocr'ı) libGL ister;
#                 konteynerde klasik "ImportError: libGL.so.1" sebebi.
# git           : kod ağ diskine git ile iniyor - iş akışının kendisi.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev \
        build-essential gcc g++ \
        git curl ca-certificates \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# --- Sanal ortam -------------------------------------------------------------
# Ubuntu 24.04 PEP 668 uyguluyor: sistem Python'ına pip ile kurmak
# "externally-managed-environment" hatası verir. Önceki denemede zaman
# kaybettiren noktalardan biri buydu. venv o sorunu tümüyle ortadan kaldırır
# ve --break-system-packages gibi bir kaçamağa gerek bırakmaz.
ENV VIRTUAL_ENV=/opt/mahir-venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# --- Ağır çerçeveler: AYRI KATMANLAR ----------------------------------------
# Tek bir dev katman yerine üç katman: `docker push` önceki denemede büyük
# katmanlarda tekrar tekrar düşüyordu (Docker Desktop/WSL2 ağ sorunları).
# Küçük katmanlar hem yeniden denenebilir hem de yalnız değişen katman gider.
# Sürümler `local/requirements.txt` ile AYNI olmalı - orası tek doğru kaynak,
# buradakiler yalnız katmanlama içindir (aşağıdaki -r kurulumu doğrular).
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cu126 \
        torch==2.8.0+cu126 torchvision==0.23.0+cu126

RUN pip install --no-cache-dir \
        --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
        paddlepaddle-gpu==3.3.1

# --- nvidia yığınını torch'un pinlerine geri hizala --------------------------
# Bu katman bir ÖLÇÜMÜN sonucu (ilk build, adım #14): paddlepaddle-gpu 3.3.1
# kurulumu torch'un ÜÇ bağımlılığını sessizce DÜŞÜRÜYOR ve pip bunu yalnız bir
# uyarı olarak basıyor ("...but you have nvidia-cudnn-cu12 9.5.1.17 which is
# incompatible"), çıkış kodu 0:
#     nvidia-cudnn-cu12       9.10.2.21 -> 9.5.1.17
#     nvidia-cusparselt-cu12  0.7.1     -> 0.6.3
#     nvidia-nccl-cu12        2.27.3    -> 2.25.1
# Bu katman olmasa imaj KIRIK bir torch ile çıkar. Çakışma Linux'a ÖZGÜ: her
# iki pin de `platform_system == "Linux"` işaretli, bu yüzden Windows'taki
# yerel kurulumda hiç görülmüyor (bkz. local/requirements.txt).
#
# Yön bilinçli olarak YENİ sürüm: üçünün de SONAME'i değişmiyor
# (libcudnn.so.9, libcusparseLt.so.0, libnccl.so.2) ve bu kütüphaneler ana
# sürüm içinde geriye dönük uyumlu - yani 9.5'e derlenmiş paddle 9.10 ile
# koşar; TERSİ garanti değil (torch 2.8 doğrudan 9.10'a derlendi). NCCL ise
# tek GPU'lu pod'da hiç kullanılmıyor.
# `--no-deps`: paddle'ı yeniden çözümlemeye sokmadan yalnız bu üçünü değiştir.
RUN pip install --no-cache-dir --no-deps \
        nvidia-cudnn-cu12==9.10.2.21 \
        nvidia-cusparselt-cu12==0.7.1 \
        nvidia-nccl-cu12==2.27.3

# --- Kalan bağımlılıklar -----------------------------------------------------
# YALNIZ requirements dosyaları kopyalanır; uygulama kodu değil. Böylece kod
# değişikliği bu katmanların önbelleğini HİÇ bozmaz.
COPY local/requirements.txt /tmp/requirements-local.txt
COPY requirements.txt /tmp/requirements-web.txt

# GPU çerçeveleri yukarıda ayrı katmanlarda kuruldu ve burada TEKRAR
# istenmiyor: pip ikisini AYNI çözümlemede görürse iş imkânsız
# (`ResolutionImpossible`, ilk build'de ölçüldü) - iki paketin `==` pinleri
# uzlaşamaz. Süzme paket ADIYLA yapılıyor; `paddleocr`/`paddlex` paddle'ı
# bağımlılık olarak BİLDİRMEDİĞİ için süzülen satırlar geri gelmiyor.
# `-c` kısıtı ikinci bir tuzağı kapatıyor: bir alt bağımlılık `torch>=2.9`
# isterse +cu126 wheel'i sessizce PyPI'ın CPU wheel'iyle DEĞİŞMESİN - build
# düşsün. (GPU'suz bir torch, pod'da ancak çalışma anında fark edilirdi.)
RUN grep -vE '^(torch|torchvision|paddlepaddle-gpu)==' /tmp/requirements-local.txt \
        > /tmp/requirements-rest.txt \
    && printf 'torch==2.8.0+cu126\ntorchvision==0.23.0+cu126\n' > /tmp/constraints-gpu.txt \
    && pip install --no-cache-dir -c /tmp/constraints-gpu.txt -r /tmp/requirements-rest.txt \
    && pip install --no-cache-dir -r /tmp/requirements-web.txt \
    && rm -f /tmp/requirements-local.txt /tmp/requirements-rest.txt \
             /tmp/requirements-web.txt /tmp/constraints-gpu.txt

# --- Bağımlılık tutarlılığı kapısı ------------------------------------------
# `pip check`in tam yeşil olması BEKLENMİYOR: paddle'ın üç nvidia pini
# yukarıda bilerek eziliyor. Ama BAŞKA bir tutarsızlık çıkarsa build burada
# düşsün - bu projede sessiz bağımlılık kayması pahalıya geldi.
# Ayrıca üç sürümün gerçekten torch'un istediği değerde kaldığı doğrulanıyor:
# yukarıdaki katmanların sırası değişirse bu satır hemen haber verir.
RUN pip check | tee /tmp/pip-check.txt; \
    if grep -v 'nvidia-\(cudnn\|cusparselt\|nccl\)-cu12' /tmp/pip-check.txt \
         | grep -q 'requires'; then \
        echo "BEKLENMEYEN bagimlilik tutarsizligi (yukari bakiniz)." >&2; exit 1; \
    fi; \
    rm -f /tmp/pip-check.txt
RUN python -c "import importlib.metadata as m; \
want = {'nvidia-cudnn-cu12': '9.10.2.21', 'nvidia-cusparselt-cu12': '0.7.1', 'nvidia-nccl-cu12': '2.27.3'}; \
got = {k: m.version(k) for k in want}; \
assert got == want, f'nvidia yigini torch pinlerinden sapmis: {got}'; \
print('nvidia yigini torch pinleriyle uyumlu:', got)"

# --- Çalışma zamanı ----------------------------------------------------------
# Kod buraya `git clone` ile iner (ağ diski). İmajda boş durur.
WORKDIR /workspace

# `scripts/gpu_services.sh` bu değişkeni okur; venv'deki yorumlayıcı
# kullanılsın diye açıkça veriliyor (`python3` sistemdekini gösterirdi).
ENV MAHIR_PYTHON=/opt/mahir-venv/bin/python

# `local/llm_server.sh` bu değişkeni okur; verilmezse local/llama.cpp/ altına
# bakar (Windows'taki yerel kurulum düzeni).
ENV LLAMA_SERVER_EXE=/opt/llama.cpp/llama-server

# `llama-server` kendi .so'larını RPATH ($ORIGIN) ile buluyor; bu yalnız
# güvenlik ağı. ggml, CUDA backend'ini (`libggml-cuda.so`) çalışma anında
# yüklüyor ve o da temel imajdaki libcudart/libcublas'a bağlanıyor.
ENV LD_LIBRARY_PATH=/opt/llama.cpp:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

# Servisler konteyner dışından erişilebilir olmalı. Kodun varsayılanı
# 127.0.0.1; ağa açılmak AÇIK bir karar (bkz. backend/run_ocr_worker.py).
ENV RAG_SERVICE_HOST=0.0.0.0 \
    MAHIR_OCR_WORKER_HOST=0.0.0.0

# 24 GB kartta gömme ve reranker GPU'da olmalı - asıl gecikme kazancı burada
# (reranker istem başına ~8 sn -> ~0,2 sn). Yereldeki 6 GB kart yüzünden
# depodaki varsayılan CPU; burada bilinçli olarak eziliyor.
ENV EMBEDDING_DEVICE=cuda \
    RERANKER_DEVICE=cuda

# paddle ve torch aynı süreçte çakışabiliyor (yerelde WinError 127 ölçüldü);
# OCR bu yüzden AYRI süreçte çalışıyor ve bu ayrım pod'da da korunuyor.
# PaddleX'in çevrim içi model kaynağı kontrolü dakikalarca bekletebiliyor.
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

EXPOSE 8001 8002

# Varsayılan komut yok: pod açıldığında `/workspace`'te kod olmayabilir.
# Kurulum ve başlatma `scripts/gpu_services.sh` ile elle yapılır
# (bkz. docs/deploy/runpod.md).
CMD ["sleep", "infinity"]
