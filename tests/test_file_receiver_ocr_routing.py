"""`file_receiver.run_image_group_ocr` yönlendirme sözleşmesi.

Görsel yükleme grubu için iki davranış var ve ikisi de OCR servisinin adresine
bağlı: adres boşsa OCR'sız "pass-through" (öğretmen kontrolüne düşer, yapısal
veri yok), adres doluysa grup OCR istemcisine AYNEN o adresle iletilir.
Bu sözleşme servisin nerede koştuğundan bağımsızdır; adres değişse de aynı
kalmalı.
"""

import unittest
from unittest.mock import patch

from backend.app import file_receiver, ocr_worker_client
from backend.app.file_receiver import FileCheckResult, UploadedFile

_FILES = [
    UploadedFile("exam-001.png", b"png-bytes"),
    UploadedFile("exam-002.jpg", b"jpg-bytes"),
]
_CHECKS = [
    FileCheckResult("exam-001.png", ".png", True),
    FileCheckResult("exam-002.jpg", ".jpg", True),
]


class ImageGroupRoutingTests(unittest.TestCase):
    def test_empty_url_passes_the_group_through_without_ocr(self):
        with patch.object(file_receiver, "MAHIR_OCR_URL", ""):
            with patch.object(ocr_worker_client, "request_image_group_ocr") as forward:
                ok, message, structured = file_receiver.run_image_group_ocr(_FILES)

        self.assertTrue(ok)
        self.assertIn("2 görsel", message)
        self.assertIsNone(structured)
        forward.assert_not_called()

    def test_configured_url_forwards_the_whole_group_to_that_address(self):
        expected = (True, "OCR tamam", {"students": []})
        with patch.object(file_receiver, "MAHIR_OCR_URL", "http://127.0.0.1:9"):
            with patch.object(ocr_worker_client, "request_image_group_ocr", return_value=expected) as forward:
                result = file_receiver.run_image_group_ocr(_FILES)

        self.assertEqual(result, expected)
        forward.assert_called_once_with(_FILES, "http://127.0.0.1:9")

    def test_all_image_upload_takes_the_ocr_route(self):
        with patch.object(file_receiver, "run_image_group_ocr", return_value=(True, "yol", None)) as route:
            result = file_receiver.run_existing_backend_flow(_FILES, _CHECKS)

        self.assertEqual(result, (True, "yol", None))
        route.assert_called_once_with(_FILES)

    def test_default_url_is_a_configured_non_empty_address(self):
        # Env değişkeni verilmediğinde OCR bilinçli olarak AÇIK: varsayılan adres
        # boş olmamalı, aksi hâlde görseller sessizce OCR'sız geçer.
        self.assertTrue(file_receiver._DEFAULT_MAHIR_OCR_URL.startswith("http"))


if __name__ == "__main__":
    unittest.main()
