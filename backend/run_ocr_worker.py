"""Run the MAHIR OCR worker (PaddleOCR-VL) - meant for a GPU machine such as
a Google Colab notebook, see `colab/mahir_ocr_colab.ipynb`.
"""

from __future__ import annotations

from app.ocr_worker import UPLOAD_PATH, create_server


def main() -> None:
    host = "0.0.0.0"
    port = 8000
    server = create_server(host=host, port=port)

    print(f"MAHİR OCR sunucusu çalışıyor: http://{host}:{port}", flush=True)
    print(f"OCR yolu: http://{host}:{port}{UPLOAD_PATH}", flush=True)
    print("Durdurmak için Ctrl+C kullanın.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("MAHİR OCR sunucusu durduruldu.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
