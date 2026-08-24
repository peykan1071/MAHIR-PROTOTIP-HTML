"""Run the minimal MAHIR local file receiver."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.file_receiver import UPLOAD_PATH, create_server


def _configure_logging() -> None:
    """Kök logger'ı bir dosyaya yazacak şekilde yapılandırır.

    2026-08-23: bu çağrı olmadan `agents/pipeline.py` gibi modüllerin
    `_logger.info(...)` çağrıları hiçbir yere yazılmıyordu - Python'un kök
    logger'ı varsayılan olarak WARNING seviyesinde ve handler'sız, bu
    yüzden RAG doğrulama/red sebepleri şu ana kadar hiç gözlemlenemiyordu.
    Gizlilik: yalnızca kod/sebep/sayı içeren log satırları buraya düşer -
    ham model cevabı, gerekçe metni veya kaynak alıntısı ASLA loglanmaz
    (bkz. `agents/llm.py::trace_entry`deki aynı disiplin).
    """

    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "mahir-backend.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main() -> None:
    _configure_logging()
    host = "127.0.0.1"
    port = 8000
    server = create_server(host=host, port=port)

    print(f"MAHİR dosya alıcı çalışıyor: http://{host}:{port}/index.html", flush=True)
    print(f"Dosya alıcı yolu: http://{host}:{port}{UPLOAD_PATH}", flush=True)
    print("Durdurmak için Ctrl+C kullanın.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("MAHİR dosya alıcı durduruldu.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
