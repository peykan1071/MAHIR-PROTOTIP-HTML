"""`ocr_worker.py` (sunucu) ile `remote_ocr_client.py` (istemci) arasında
paylaşılan yol/başlık sabitleri.

`remote_ocr_client.py`, `ocr_worker.py`'yi doğrudan import edemez: o modül
PaddleOCR bağımlılığını yükler ve istemci öğretmenin makinesinde (yerel
dosya alıcısı yanında) çalıştığı için bu ağırlığı taşımamalı (bkz.
`remote_ocr_client.py` modül docstring'i). Bu modül bağımlılıksız olduğu
için iki taraf da aynı sabitleri buradan okuyabiliyor - elle kopyalama
ortadan kalkıyor.
"""

from __future__ import annotations

UPLOAD_PATH = "/mahir-upload"
WARMUP_PATH = "/mahir-warmup"
SHARED_SECRET_HEADER = "X-MAHIR-OCR-Key"
