"""Run the MAHIR OCR worker (PaddleOCR-VL) - meant for a GPU machine, see
`modal_app.py`.
"""

from __future__ import annotations

import os

from app import ocr_engine
from app.ocr_worker import UPLOAD_PATH, create_server


def main() -> None:
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8000))
    server = create_server(host=host, port=port)

    print(f"MAHİR OCR sunucusu çalışıyor: http://{host}:{port}", flush=True)
    print(f"OCR yolu: http://{host}:{port}{UPLOAD_PATH}", flush=True)

    # Pipeline'ı burada, sunucu istek almadan önce kuruyoruz (model yükleme birkaç
    # dakika sürebilir) - aksi halde platformun soğuk başlangıç zaman aşımını
    # aşıp ilk istek başarısız olabilir.
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
        print("MAHİR OCR sunucusu durduruldu.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
