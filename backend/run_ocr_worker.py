"""Run the MAHİR OCR worker (PaddleOCR-VL, GPU) as its own local process.

The web backend (`run_file_receiver.py`, :8000) forwards image uploads here
through `app/ocr_worker_client.py`; the default address on both sides is
`http://127.0.0.1:8002` (`MAHIR_OCR_WORKER_PORT` / `MAHIR_OCR_URL`). The
PaddleOCR-VL pipeline is loaded once here, before the first request.
Kept separate so the teacher-facing server never loads paddle/torch and a
model crash cannot take the web UI down. Needs the `local/requirements.txt`
environment (paddlepaddle-gpu; CUDA 12.6 / cuDNN 9 come with the pip wheels,
only the NVIDIA driver must be installed).

    cd backend ; python run_ocr_worker.py
"""

from __future__ import annotations

import os

from app import ocr_engine
from app.ocr_worker import UPLOAD_PATH, create_server


def main() -> None:
    # Bind adresi ortamdan; varsayılan yerel (bkz. run_file_receiver.py'deki
    # aynı gerekçe). Pod'da `MAHIR_OCR_WORKER_HOST=0.0.0.0` verilir.
    host = os.environ.get("MAHIR_OCR_WORKER_HOST", "127.0.0.1")
    port = int(os.environ.get("MAHIR_OCR_WORKER_PORT", 8002))
    server = create_server(host=host, port=port)

    print(f"MAHİR OCR işçisi çalışıyor: http://{host}:{port}", flush=True)
    print(f"OCR yolu: http://{host}:{port}{UPLOAD_PATH}", flush=True)

    # Pipeline'ı burada, sunucu istek almadan önce kuruyoruz (ilk model yükleme
    # birkaç dakika sürebilir) - aksi hâlde öğretmenin ilk yüklemesi o süreyi bekler.
    print("PaddleOCR-VL pipeline'ı ısıtılıyor (ilk model yükleme birkaç dakika sürebilir)...", flush=True)
    try:
        ocr_engine.ensure_available()
        print("Pipeline hazır.", flush=True)
    except RuntimeError as error:
        print(f"Pipeline ısıtılamadı: {error}", flush=True)

    print("Durdurmak için Ctrl+C kullanın.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("MAHİR OCR işçisi durduruldu.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
