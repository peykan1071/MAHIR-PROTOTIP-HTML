"""Run the minimal MAHIR local file receiver."""

from __future__ import annotations

from app.file_receiver import UPLOAD_PATH, create_server


def main() -> None:
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
