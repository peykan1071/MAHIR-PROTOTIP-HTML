"""MAHIR OCR işçisini Modal'da (GPU, sıfıra ölçeklenen serverless) çalıştırır.

Dağıtım: `modal deploy modal_app.py` (repo kökünden çalıştırın). Gerekli
kurulum ve komutlar için README.md'deki "Modal ile OCR" bölümüne bakın.

Neden Modal (Google Cloud Run değil): paddlepaddle-gpu'nun derlenmiş
çekirdeği import anında libcuda.so.1'i (NVIDIA sürücüsü) arıyor - bu yüzden
modelleri GPU'suz bir konteyner derleme makinesinde (ör. Cloud Build) build
sırasında imaja gömmek mümkün değil. Modal'ın `Image.run_function(...,
gpu=...)` özelliği, build adımlarına gerçek bir GPU bağlayabiliyor - bu
yüzden modelleri (PaddleOCR-VL-1.6 + PP-DocLayoutV3, ~2 GB) burada da
build sırasında indirip imaja gömebiliyoruz, çalışma zamanında hiçbir dış
depolamaya (Drive/GCS) ihtiyaç kalmıyor.

`ocr_engine.py` / `ocr_worker.py` / `run_ocr_worker.py` platformdan
bağımsızdır (Cloud Run'da da aynen kullanılıyordu) - burada sadece
`@modal.web_server` ile mevcut stdlib `http.server` uygulamasını sarıyoruz.
"""

from __future__ import annotations

import subprocess

import modal

app = modal.App("mahir-ocr-worker")


def _warm_up_pipeline() -> None:
    """Build adımında (GPU'lu) çalışır: modelleri indirip ~/.paddlex'e (imaja) gömer."""

    import sys

    sys.path.insert(0, "/srv/backend")
    from app import ocr_engine  # noqa: PLC0415 - sys.path yukarıda ayarlandı

    ocr_engine.ensure_available()


image = (
    modal.Image.debian_slim(python_version="3.13")
    # PaddleOCR/PaddleX'in (OpenMP ve OpenCV üzerinden) ihtiyaç duyduğu sistem
    # kütüphaneleri - debian_slim imajında varsayılan olarak yok.
    .apt_install("libgomp1", "libgl1", "libglib2.0-0")
    .pip_install("paddleocr[doc-parser]==3.7.0", "paddlex==3.7.2")
    .pip_install(
        "paddlepaddle-gpu==3.3.1",
        index_url="https://www.paddlepaddle.org.cn/packages/stable/cu126/",
    )
    # PaddleOCR-VL-1.6-0.9B'nin "transformers" motoru için gerekli - paddle_dynamic
    # (eager) motorundan çok daha yavaş token token üretim yapıyordu. torchvision
    # olmadan AutoImageProcessor ImportError veriyor.
    .pip_install("transformers", "torchvision")
    # OMP_NUM_THREADS>1, bu paddlepaddle-gpu wheel'inin (OpenBLAS ile derlenmiş
    # olabilir) çoklu iş parçacığını güvenle desteklememesi yüzünden predict()
    # çağrısını sessizce kilitleyebiliyor (kendi uyarı mesajı bunu söylüyor).
    .env({"PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True", "OMP_NUM_THREADS": "1"})
    .add_local_dir("backend", "/srv/backend", copy=True)
    .run_function(_warm_up_pipeline, gpu="T4")
)


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=8192,
    timeout=900,
)
@modal.web_server(8000, startup_timeout=300)
def ocr_worker() -> None:
    # Modelleri yeniden indirmiyor (imaja gömülü); yine de pipeline'ı bu
    # konteynerin belleğine/GPU'suna yüklemesi (CUDA init + ağırlıkları
    # diskten okuma) biraz sürebilir - run_ocr_worker.py bunu istek almadan
    # önce yapıyor, startup_timeout bu yüzden geniş tutuldu.
    subprocess.Popen(["python", "run_ocr_worker.py"], cwd="/srv/backend")
