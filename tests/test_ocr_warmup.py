"""Tests for the OCR warm-up path added to cut the measured cold-start wait.

A cold Modal container spends 30-50 s booting and loading PaddleOCR-VL onto the
GPU against only 7-12 s of actual OCR, so the browser pings the local receiver
the moment files are picked and the receiver forwards that to the remote worker.
The one property that must never regress: that ping is fire-and-forget - if it
ever blocked, it would add the whole cold start to the teacher's file-selection
click instead of removing it from the upload.
"""

import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend.app import file_receiver, ocr_worker

_FAKE_REMOTE_URL = "https://fake.example"


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _get(server, path):
    port = server.server_address[1]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
        return response.status, response.read()


class ReceiverWarmUpRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = file_receiver.create_server(host="127.0.0.1", port=0)
        _serve(self.server)
        # addCleanup LIFO çalışıyor: server_close önce eklenmeli ki shutdown
        # ondan ÖNCE koşsun - tersi serve_forever'ı kapalı sokete düşürüyor.
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_warmup_returns_immediately_without_waiting_for_remote(self):
        started = threading.Event()

        def slow_warm_up(_remote_url):
            started.set()
            time.sleep(5)  # Soğuk konteyner gerçekte 30-50 sn sürüyor.
            return True

        with patch.object(file_receiver, "MAHIR_OCR_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.remote_ocr_client.warm_up_remote_ocr", slow_warm_up):
                begin = time.monotonic()
                status, body = _get(self.server, file_receiver.OCR_WARMUP_PATH)
                elapsed = time.monotonic() - begin

        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["started"])
        self.assertLess(elapsed, 1.0, "ısıtma ping'i uzak çağrıyı beklememeli")
        self.assertTrue(started.wait(timeout=5), "uzak ısıtma çağrısı hiç başlamadı")

    def test_no_remote_url_configured_makes_no_remote_call(self):
        with patch.object(file_receiver, "MAHIR_OCR_REMOTE_URL", ""):
            with patch("backend.app.remote_ocr_client.warm_up_remote_ocr") as mock_warm_up:
                status, body = _get(self.server, file_receiver.OCR_WARMUP_PATH)

        mock_warm_up.assert_not_called()
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["started"])

    def test_static_file_serving_still_works(self):
        # do_GET override'ı yalnızca ısıtma yolunu yakalamalı; prototipin geri
        # kalanı (index.html, script.js, assets) aynı sunucudan geliyor.
        status, body = _get(self.server, "/index.html")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body.lower())


class WorkerWarmUpRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = ocr_worker.create_server(host="127.0.0.1", port=0)
        _serve(self.server)
        # addCleanup LIFO çalışıyor: server_close önce eklenmeli ki shutdown
        # ondan ÖNCE koşsun - tersi serve_forever'ı kapalı sokete düşürüyor.
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_warmup_path_loads_pipeline_and_reports_ready(self):
        with patch("backend.app.ocr_engine.ensure_available") as mock_ensure:
            status, body = _get(self.server, ocr_worker.WARMUP_PATH)

        mock_ensure.assert_called_once()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ready"])

    def test_warmup_never_runs_ocr(self):
        with patch("backend.app.ocr_engine.ensure_available"):
            with patch("backend.app.ocr_engine.read_student_rows") as mock_read:
                _get(self.server, ocr_worker.WARMUP_PATH)
        mock_read.assert_not_called()

    def test_unknown_get_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            _get(self.server, "/baska-bir-yol")
        self.addCleanup(caught.exception.close)
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
