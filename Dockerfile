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
# Kurulum: imajı GitHub Actions derler ve GHCR'a iter
# (`.github/workflows/gpu-image.yml`); yerel makineden push EDİLMEZ. Ölçüldü:
# Docker Desktop registry trafiğini VM vekilinden geçiriyor ve bu makineden
# 64 MB'tan büyük bir blob hiç yüklenemedi (2 GB'lık katmanda iki kez düştü).
#     ghcr.io/peykan1071/mahir-gpu:<git-sha>    <- ana makinede BU kullanılır
#     ghcr.io/peykan1071/mahir-gpu:latest
#
# Ana makinede beklenen ortam değişkenleri - YALNIZ iki parola:
#     MAHIR_RAG_SHARED_SECRET, MAHIR_OCR_SHARED_SECRET   (zorunlu - aksi hâlde
#         uçlar korumasız açılır; bkz. local/.env.bulut.example)
# Model önbellek yolları imajın içinde tanımlı (aşağıda) - sağlayıcı panelinde
# hatırlanması gereken bir şey kalmasın. Ana makine sözleşmesinin tamamı:
# docs/deploy/README.md.

# --- llama-server kaynağı ----------------------------------------------------
# Resmî Docker imajından kopyalanıyor: binary `/app/llama-server`, yanında
# kendi .so'ları. Tek dosya değil `/app` bütünüyle kopyalanıyor - binary
# libggml/libllama'ya bağlı.
#
# Resmî sürümlerde Linux CUDA tarball'ı da VAR
# (`llama-bNNNNN-bin-ubuntu-cuda-12.8-x64.tar.gz` + `cudart-...` eki; b11195'te
# ölçüldü) ama imaj bilinçli tercih: doğrulanan build 11176'nın sürüm sayfası
# birkaç gün sonra bile YOKTU ("release not found", 2026-09-26) - GitHub
# sürüm arşivi kalıcı değil. Digest ile sabitlenmiş imaj, doğrulanan binary'nin
# kalıcı tek kopyası.
#
# Temel imajlar DIGEST ile sabit: aylar sonraki bir rebuild doğrulanan bitleri
# üretsin. `:server-cuda` her gece değişen bir etiket; digest'siz bir rebuild
# sessizce başka bir llama.cpp getirirdi. Yükseltme bilinçli bir düzenleme
# olmalı: yeni digest + `scripts/verify_gpu_image.sh`.
#
# Her iki ARG da İLK FROM'dan ÖNCE tanımlanmalı: bir FROM'dan sonra gelen ARG
# o aşamaya kapsanır ve sonraki FROM onu boş görür ("base name should not be
# blank" ile build düşer).
ARG LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda@sha256:1f4b9cf58982dd4d7cc497aea31b1a456ca9a3a1f94f527d317d3fdee0d60ab6
# CUDA 12.8, 12.6 DEĞİL - llama.cpp imajıyla eşleşmesi için. Ölçüldü:
# `libggml-cuda.so` `/usr/local/cuda/lib64`'teki libcudart.so.12 /
# libcublas.so.12'ye bağlanıyor ve bu kütüphaneler `/app`'te DEĞİL, yani
# temel imajdan gelmek zorunda. llama.cpp imajı CUDA 12.8 taşıyor; 12.6
# runtime'ı SONAME olarak uyar ama 12.8'de eklenen simgeleri garanti etmez.
# torch/paddle bu seçimden etkilenmiyor: kendi CUDA kütüphanelerini
# `nvidia-*-cu12` pip paketleriyle getiriyorlar (bkz. local/requirements.txt).
# Temel imaj "runtime" olmalı, "base" değil - cuBLAS yalnız runtime'da var.
ARG CUDA_IMAGE=nvidia/cuda:12.8.1-runtime-ubuntu24.04@sha256:ebef3c171eeef0298e4eb2e4be843105edf3b8b0ac45e0b43acee358e8046867

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

# --- İmaj kendi kilidini taşır ----------------------------------------------
# `local/requirements.txt`'teki aralıklı pinler (docling, transformers...) iki
# CI build'i arasında farklı çözülebilir; bu dosya her imajın GERÇEK içeriğini
# kaydeder. İki kullanımı var:
#   * kayma teşhisi: iki imajın freeze.txt'i `diff` ile karşılaştırılır;
#   * Docker'sız bir makineye taşınma: `pip install --no-deps -r freeze.txt`.
#     `--no-deps` ŞART - aksi hâlde paddle'ın üç nvidia pini çözümlemeyi
#     yeniden kırar (yukarıdaki hizalama katmanına bakınız).
RUN pip freeze > /opt/mahir-venv/freeze.txt

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

# Model önbellekleri kalıcı diskte (`/workspace`) olmalı; konteyner diski
# durdurulunca silinir ve ~13 GB model her açılışta yeniden inerdi.
# PADDLE_PDX_CACHE_HOME ayrıca şart: paddlex önbelleğini HF_HOME/XDG'den değil
# bu değişkenden okuyor (paddlex/utils/cache.py:29), varsayılanı `~/.paddlex`
# = konteyner diski. Önceki runbook bunu kaçırıyordu - PaddleOCR-VL (1,9 GB)
# her pod açılışında yeniden inerdi.
# TRITON_CACHE_DIR aynı sebeple (triton/knobs.py:341; varsayılanı
# `~/.triton/cache`): PaddleOCR-VL'nin `transformers` motorunun çalışma anında
# derlediği kernel'ler kalıcı diskte dursun, her açılışta yeniden derlenmesin.
# Yollar imajda tanımlı ki hiçbir sağlayıcının panelinde hatırlanmaları
# gerekmesin; kalıcı disk yoksa da çalışır (yalnız önbellek kalıcı olmaz).
ENV HF_HOME=/workspace/.cache/huggingface \
    XDG_CACHE_HOME=/workspace/.cache \
    PADDLE_PDX_CACHE_HOME=/workspace/.paddlex \
    TRITON_CACHE_DIR=/workspace/.cache/triton

EXPOSE 8001 8002

# Varsayılan komut yok: ana makine açıldığında `/workspace`'te kod olmayabilir.
# Kurulum, doğrulama ve başlatma elle yapılır (bkz. docs/deploy/README.md):
#     scripts/verify_gpu_image.sh && scripts/gpu_services.sh start
CMD ["sleep", "infinity"]
