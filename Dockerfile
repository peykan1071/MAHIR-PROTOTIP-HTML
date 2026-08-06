# MAHIR OCR işçisi (PaddleOCR-VL) için Google Cloud Run (GPU) imajı.
# Dağıtım: bkz. cloud-run/deploy.sh. `gcloud run deploy --source .` kaynak
# kökünde bu adla bir Dockerfile bulunca otomatik onu kullanır (özel yol
# vermenin bir bayrağı yok), o yüzden bu dosya repo kökünde duruyor.

FROM python:3.13-slim

# PaddleOCR/PaddleX'in (OpenMP ve OpenCV üzerinden) ihtiyaç duyduğu sistem
# kütüphaneleri - python:slim imajında varsayılan olarak yok.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY backend/ backend/

# Colab'da doğrulanan sürüm kombinasyonu (bkz. README). paddlepaddle-gpu
# ayrı bir index'ten geldiği için iki ayrı pip install adımı gerekiyor.
RUN pip install --no-cache-dir "paddleocr[doc-parser]==3.7.0" paddlex==3.7.2 && \
    pip install --no-cache-dir paddlepaddle-gpu==3.3.1 \
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# Colab'da paddlepaddle-gpu kurulumu önceden yüklü torch'un nvidia-nccl/cudnn/
# cusparselt sürümlerini bozup torch'u kırıyordu. Bu temiz imajda önceden
# kurulu bir torch olmadığı için o düzeltmeye muhtemelen gerek yok - ilk
# derlemede `python -c "import paddleocr"` adımının hatasız geçtiği
# doğrulanacak, hata çıkarsa aynı düzeltme buraya eklenecek.

ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Model dosyalarını (PaddleOCR-VL-1.6 + PP-DocLayoutV3, ~2 GB) imaja göm: bir
# kerelik pipeline kurulumu çalıştırıp ~/.paddlex altına indirtiyoruz, böylece
# çalışma zamanında hiçbir dış depolamaya (Drive/GCS) bağlanmaya gerek kalmıyor
# ve konteyner tamamen kendi kendine yeterli oluyor. Derleme makinesinde GPU
# olmayabileceği için bu adımı CPU ile yapıyoruz - amaç yalnızca ağırlıkları
# indirmek; MAHIR_OCR_DEVICE burada kalıcı ayarlanmadığından çalışma
# zamanında varsayılan "gpu" geçerli olacak.
RUN cd backend && MAHIR_OCR_DEVICE=cpu python -c "from app import ocr_engine; ocr_engine.ensure_available()"

EXPOSE 8080

CMD ["python", "backend/run_ocr_worker.py"]
