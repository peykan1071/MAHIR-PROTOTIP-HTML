"""Tests that the prototype server forbids browser caching of its own code.

`SimpleHTTPRequestHandler` yalnızca `Last-Modified` gönderdiği için tarayıcı
sezgisel önbelleklemeye düşüyor ve dosyayı sunucuya sormadan kendi kopyasından
veriyor. Bu, rapor katmanını sessizce İKİYE BÖLDÜ: model tarafı
(`mahir-report-export-common.js`) tazelenmişken çıktı tarafı
(`mahir-pdf-exporter.js`) eski kopyadan geldi, ekranda görünen kaynak dipnotu
indirilen PDF'e hiç düşmedi. Arıza sessiz - ne konsolda hata var ne de eksik
alan; yalnızca resmî çıktı ekrandan farklı.

Testler yanıt BAŞLIKLARINA ve gönderilen BAYTLARA bakıyor: hangi dosyanın
tarayıcıya ulaştığı, kaynak ağacında ne yazdığından bağımsız bir olgudur.
"""

import threading
import unittest
import urllib.request
from pathlib import Path

from backend.app import file_receiver

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Rapor çıktısını üreten katman: biri tazelenip diğeri önbellekten gelirse
# öğretmenin imzalayacağı belge ekranda gördüğünden farklı olur.
_REPORT_LAYER = (
    "assets/js/mahir-report-export-common.js",
    "assets/js/mahir-pdf-exporter.js",
    "assets/js/mahir-docx-exporter.js",
)


class StaticCacheHeaderTests(unittest.TestCase):
    def setUp(self):
        self.server = file_receiver.create_server(host="127.0.0.1", port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        # addCleanup LIFO: server_close önce eklenmeli ki shutdown ondan ÖNCE koşsun.
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _get(self, path):
        port = self.server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{path}", timeout=30) as response:
            return response.status, response.headers, response.read()

    def test_report_layer_is_never_cached_by_the_browser(self):
        for path in _REPORT_LAYER:
            with self.subTest(path=path):
                status, headers, _ = self._get(path)
                self.assertEqual(status, 200)
                self.assertEqual(headers.get("Cache-Control"), "no-store")

    def test_page_itself_is_never_cached(self):
        # index.html önbellekten gelirse yeni bir betik etiketi eklendiğinde
        # tarayıcı onu hiç istemez - tek dosyanın eskimesinden daha kötüsü.
        _, headers, _ = self._get("index.html")
        self.assertEqual(headers.get("Cache-Control"), "no-store")

    def test_browser_receives_exactly_what_the_repository_holds(self):
        # "Sunucu eski bir kopyayı servis ediyor" ihtimalini kapatır: başlık
        # doğru olsa bile gönderilen bayt farklıysa arıza aynı yerde biter.
        for path in _REPORT_LAYER:
            with self.subTest(path=path):
                _, _, body = self._get(path)
                self.assertEqual(body, (_PROJECT_ROOT / path).read_bytes())

    def test_analysis_responses_are_not_cached_either(self):
        # Aynı `end_headers` yolundan geçiyorlar; bir analiz sonucunun
        # önbellekten dönmesi öğretmene başka bir sınavın raporunu gösterir.
        port = self.server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mahir-analyze", method="OPTIONS"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":
    unittest.main()
