"""Paylaşılan parola katmanının sözleşmesi: OCR işçisi ve RAG servisinin rotaları.

Bu katman depoda VARDI ve `7189aba` ile kaldırılmıştı - o sırada iki servis de
yalnız 127.0.0.1'e bağlanıyordu, yani korunacak bir yüzey yoktu. RunPod'a
taşımayla birlikte ikisi de ağa açılıyor: OCR ucu kimlik doğrulaması olmadan
200 MB'a kadar dosya kabul eden açık bir yükleme noktası, `/agents` ucu ise
GPU'yu meşgul eden açık bir üretim noktası olurdu.

Sınanan güvenceler:

1. Parola TANIMSIZSA hiçbir şey değişmez. Yerel kurulum (varsayılan) bugünkü
   gibi çalışmalı - taşıma yerel akışı bozmuyor.
2. Parola tanımlıysa yanlış/eksik başlık 401 alır ve OCR motoru/GPU hiç
   çalışmaz. (Gövde 401'den önce okunur - `ocr_worker.do_POST`'taki yoruma
   bakınız: erken yanıt WinError 10053 üretip 401'i istemciden gizliyordu.)
3. İstemciler parolayı yalnız tanımlıysa gönderir.
"""

import importlib.util
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.app import ocr_worker, ocr_worker_client
from backend.app.agents import llm
from backend.app.file_receiver import UploadedFile

_LOCAL_DIR = Path(__file__).resolve().parents[1] / "local"
_SECRET = "dogru-parola-123"


def _load_local_service():
    """`local/rag_service.py`'yi dosya yolundan yükler (test_agents_contract ile aynı desen)."""

    name = "local_rag_service"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _LOCAL_DIR / "rag_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _lowercased(headers):
    """urllib başlık adlarını `capitalize()` ediyor; karşılaştırma büyük/küçük harfe takılmasın."""

    return {str(name).lower(): value for name, value in dict(headers).items()}


class RagAgentSecretDecisionTests(unittest.TestCase):
    """`agent_secret_rejection` - FastAPI kurulu olmadan sınanabilen saf karar."""

    def setUp(self):
        self.module = _load_local_service()

    def _rejection(self, header_value, secret=None):
        environment = {} if secret is None else {self.module.AGENT_SECRET_ENV: secret}
        with patch.dict("os.environ", environment, clear=False):
            if secret is None:
                # `clear=False` mevcut değeri bırakırdı; bu dal "hiç tanımlı değil"i sınıyor.
                import os

                os.environ.pop(self.module.AGENT_SECRET_ENV, None)
            return self.module.agent_secret_rejection(header_value)

    def test_without_a_configured_secret_every_request_passes(self):
        # Yerel varsayılan: parola yok, doğrulama yok, davranış bugünküyle aynı.
        self.assertEqual(self._rejection(""), "")
        self.assertEqual(self._rejection("rastgele"), "")

    def test_missing_header_is_rejected_when_a_secret_is_configured(self):
        self.assertEqual(self._rejection("", secret=_SECRET), "Yetkisiz istek.")

    def test_wrong_header_is_rejected(self):
        self.assertEqual(self._rejection("yanlis-parola", secret=_SECRET), "Yetkisiz istek.")

    def test_correct_header_passes(self):
        self.assertEqual(self._rejection(_SECRET, secret=_SECRET), "")


class RagRouteProtectionTests(unittest.TestCase):
    """`request_secret_rejection` - parola tanımlıyken HANGİ yolların korunduğu.

    Önceki sürüm yalnız `/agents`'ı koruyordu; `/query` LLM üretimini,
    `/retrieve` gömme+reranker'ı parolasız çalıştırıyordu. llama-server tek
    yuvada koştuğu için açık bir `/query`, öğretmenin `/agents` turunu
    kilitleyebilirdi. Buradaki testler "varsayılan kapalı" sözleşmesini sabitler.
    """

    PROTECTED = ("/agents", "/retrieve", "/query", "/docs", "/openapi.json", "/yeni-bir-rota")

    def setUp(self):
        self.module = _load_local_service()

    def _decide(self, path, header_value, secret):
        import os

        saved = os.environ.pop(self.module.AGENT_SECRET_ENV, None)
        try:
            if secret is not None:
                os.environ[self.module.AGENT_SECRET_ENV] = secret
            return self.module.request_secret_rejection(path, header_value)
        finally:
            os.environ.pop(self.module.AGENT_SECRET_ENV, None)
            if saved is not None:
                os.environ[self.module.AGENT_SECRET_ENV] = saved

    def test_every_route_but_health_is_rejected_without_the_header(self):
        for path in self.PROTECTED:
            with self.subTest(path=path):
                self.assertEqual(self._decide(path, "", _SECRET), "Yetkisiz istek.")

    def test_wrong_header_is_rejected_on_the_generation_routes(self):
        for path in ("/query", "/retrieve"):
            with self.subTest(path=path):
                self.assertEqual(self._decide(path, "yanlis-parola", _SECRET), "Yetkisiz istek.")

    def test_correct_header_passes_every_route(self):
        for path in self.PROTECTED:
            with self.subTest(path=path):
                self.assertEqual(self._decide(path, _SECRET, _SECRET), "")

    def test_health_stays_open_for_the_reachability_probe(self):
        # `MAHIR_BASLAT.ps1 -Kip bulut` pod'u /health'ten parolasız yokluyor.
        self.assertEqual(self._decide("/health", "", _SECRET), "")

    def test_without_a_configured_secret_nothing_changes_locally(self):
        for path in self.PROTECTED + ("/health",):
            with self.subTest(path=path):
                self.assertEqual(self._decide(path, "", None), "")


class OcrWorkerSecretTests(unittest.TestCase):
    """Canlı işçi sunucusu: 401 kararı OCR motoruna HİÇ dokunmadan verilmeli."""

    def setUp(self):
        self.server = ocr_worker.create_server(host="127.0.0.1", port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        # addCleanup LIFO: server_close önce eklenmeli ki shutdown ondan ÖNCE koşsun.
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _post(self, header_value=None):
        boundary = uuid.uuid4().hex
        body = ocr_worker_client._build_multipart_body(
            [UploadedFile(file_name="sinav.jpg", content=b"sahte-bayt")], boundary
        )
        headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
        if header_value is not None:
            headers[ocr_worker_client.SHARED_SECRET_HEADER] = header_value
        port = self.server.server_address[1]
        request = urllib.request.Request(
            "http://127.0.0.1:{}{}".format(port, ocr_worker_client.UPLOAD_PATH),
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_missing_header_is_rejected(self):
        with patch.dict("os.environ", {ocr_worker_client.SHARED_SECRET_ENV: _SECRET}, clear=False):
            status, payload = self._post()
        self.assertEqual(status, 401)
        self.assertEqual(payload["message"], "Yetkisiz istek.")

    def test_wrong_header_is_rejected(self):
        with patch.dict("os.environ", {ocr_worker_client.SHARED_SECRET_ENV: _SECRET}, clear=False):
            status, _payload = self._post("yanlis-parola")
        self.assertEqual(status, 401)

    def test_rejection_happens_before_any_ocr_work(self):
        # Korunan şey OCR motoru ve GPU. Gövde 401'den ÖNCE okunuyor - bu
        # bilinçli: gönderim sürerken yanıt verip bağlantıyı kapatmak
        # WinError 10053'e yol açıyor ve istemci 401'i hiç göremiyor
        # (bkz. `ocr_worker.do_POST` yorumu). Tampon MAX_REQUEST_SIZE ile
        # zaten sınırlı; ağır iş bu kontrolün arkasında kalmalı.
        with patch.object(ocr_worker, "_run_image_group_ocr") as run_ocr:
            with patch.dict("os.environ", {ocr_worker_client.SHARED_SECRET_ENV: _SECRET}, clear=False):
                status, _payload = self._post("yanlis-parola")
        self.assertEqual(status, 401)
        run_ocr.assert_not_called()

    def test_correct_header_reaches_the_ocr_layer(self):
        with patch.object(
            ocr_worker, "_run_image_group_ocr", return_value=(True, "tamam", {"students": []})
        ) as run_ocr:
            with patch.dict("os.environ", {ocr_worker_client.SHARED_SECRET_ENV: _SECRET}, clear=False):
                status, payload = self._post(_SECRET)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        run_ocr.assert_called_once()

    def test_without_a_configured_secret_the_worker_stays_open(self):
        # Yerel kurulumda parola yoktur; işçi bugünkü gibi çalışmalı.
        import os

        with patch.object(
            ocr_worker, "_run_image_group_ocr", return_value=(True, "tamam", {"students": []})
        ):
            saved = os.environ.pop(ocr_worker_client.SHARED_SECRET_ENV, None)
            try:
                status, _payload = self._post()
            finally:
                if saved is not None:
                    os.environ[ocr_worker_client.SHARED_SECRET_ENV] = saved
        self.assertEqual(status, 200)


class ClientHeaderInjectionTests(unittest.TestCase):
    """İstemciler parolayı yalnız tanımlıysa göndermeli."""

    def _ocr_request_headers(self, secret):
        import os

        captured = {}

        def fake_post(request):
            captured.update(_lowercased(request.headers))
            return {"ok": True, "message": "tamam", "structuredData": {}}

        saved = os.environ.pop(ocr_worker_client.SHARED_SECRET_ENV, None)
        try:
            if secret is not None:
                os.environ[ocr_worker_client.SHARED_SECRET_ENV] = secret
            with patch.object(ocr_worker_client, "_post_to_worker_with_retry", fake_post):
                ocr_worker_client.request_image_group_ocr(
                    [UploadedFile(file_name="a.jpg", content=b"x")], "http://ornek.gecersiz"
                )
        finally:
            os.environ.pop(ocr_worker_client.SHARED_SECRET_ENV, None)
            if saved is not None:
                os.environ[ocr_worker_client.SHARED_SECRET_ENV] = saved
        return captured

    def test_ocr_client_sends_the_header_when_configured(self):
        headers = self._ocr_request_headers(_SECRET)
        self.assertEqual(headers.get(ocr_worker_client.SHARED_SECRET_HEADER.lower()), _SECRET)

    def test_ocr_client_omits_the_header_when_not_configured(self):
        headers = self._ocr_request_headers(None)
        self.assertNotIn(ocr_worker_client.SHARED_SECRET_HEADER.lower(), headers)

    def _rag_request_headers(self, secret):
        import os

        captured = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"ok": True, "message": "tamam", "structuredData": {}}).encode("utf-8")

        def fake_urlopen(request, timeout=None):
            captured.update(_lowercased(request.headers))
            return _FakeResponse()

        saved = os.environ.pop(llm.SHARED_SECRET_ENV, None)
        try:
            if secret is not None:
                os.environ[llm.SHARED_SECRET_ENV] = secret
            with patch.object(llm.urllib.request, "urlopen", fake_urlopen):
                llm._post_json("http://ornek.gecersiz/agents", {"agents": []})
        finally:
            os.environ.pop(llm.SHARED_SECRET_ENV, None)
            if saved is not None:
                os.environ[llm.SHARED_SECRET_ENV] = saved
        return captured

    def test_rag_client_sends_the_header_when_configured(self):
        headers = self._rag_request_headers(_SECRET)
        self.assertEqual(headers.get(llm.SHARED_SECRET_HEADER.lower()), _SECRET)

    def test_rag_client_omits_the_header_when_not_configured(self):
        headers = self._rag_request_headers(None)
        self.assertNotIn(llm.SHARED_SECRET_HEADER.lower(), headers)


if __name__ == "__main__":
    unittest.main()
