"""Tests for the connection-level retry-with-backoff in `run_remote_image_group_ocr`.

A live WinError 10053 ("bağlantı ana makinedeki yazılım tarafından iptal
edildi") showed the worker itself was healthy - the request never reached it.
A first fix added one retry, but a second live occurrence failed on BOTH the
original attempt and that retry (the process had already restarted onto the
fixed code), showing this local network path can drop more than one attempt
in a row. `_post_to_worker_with_retry` now backs off across
`_CONNECTION_RETRY_DELAYS_SECONDS` (2s, 5s) for up to 3 total attempts.
HTTP-level errors (401, 500, ...) are a real answer from the server and must
NOT be retried.
"""

import io
import http.client
import json
import unittest
import urllib.error
from unittest.mock import call, patch

from backend.app import remote_ocr_client
from backend.app.file_receiver import UploadedFile

_FAKE_URL = "https://fake.example"


def _uploaded_files():
    return [UploadedFile(file_name="sinav.jpg", content=b"fake-bytes")]


def _response(payload: dict[str, object]):
    body = json.dumps(payload).encode("utf-8")

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _FakeResponse(body)


class RunRemoteImageGroupOcrRetryTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("backend.app.remote_ocr_client.time.sleep")
        self.addCleanup(patcher.stop)
        self.mock_sleep = patcher.start()

    def test_connection_error_then_success_on_second_attempt_is_hidden(self):
        ok_response = _response({"ok": True, "message": "tamam", "structuredData": {"a": 1}})
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("kopma"), ok_response],
        ) as mock_urlopen:
            ok, message, data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertTrue(ok)
        self.assertEqual(message, "tamam")
        self.assertEqual(data, {"a": 1})
        self.assertEqual(mock_urlopen.call_count, 2)
        self.mock_sleep.assert_called_once_with(2)

    def test_connection_error_twice_then_success_on_third_attempt_is_hidden(self):
        ok_response = _response({"ok": True, "message": "tamam", "structuredData": {"a": 1}})
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            side_effect=[OSError("kopma-1"), OSError("kopma-2"), ok_response],
        ) as mock_urlopen:
            ok, _message, _data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertTrue(ok)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(self.mock_sleep.call_args_list, [call(2), call(5)])

    def test_connection_error_on_all_three_attempts_reports_unreachable(self):
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            side_effect=[OSError("kopma-1"), OSError("kopma-2"), OSError("kopma-3")],
        ) as mock_urlopen:
            ok, message, data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertFalse(ok)
        self.assertIn("Uzak OCR sunucusuna ulaşılamadı", message)
        self.assertIn("kopma-3", message)
        self.assertIsNone(data)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(self.mock_sleep.call_args_list, [call(2), call(5)])

    def test_http_error_is_not_retried(self):
        http_error = urllib.error.HTTPError(
            url=_FAKE_URL,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(json.dumps({"ok": False, "message": "yetkisiz"}).encode("utf-8")),
        )
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            side_effect=http_error,
        ) as mock_urlopen:
            ok, message, data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertFalse(ok)
        self.assertEqual(message, "yetkisiz")
        self.assertIsNone(data)
        mock_urlopen.assert_called_once()
        self.mock_sleep.assert_not_called()

    def test_truncated_401_body_reports_authorization_without_crashing(self):
        class _TruncatedBody:
            def read(self):
                raise http.client.IncompleteRead(b"", 43)

            def close(self):
                pass

        http_error = urllib.error.HTTPError(
            url=_FAKE_URL,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=_TruncatedBody(),
        )
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            side_effect=http_error,
        ) as mock_urlopen:
            ok, message, data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertFalse(ok)
        self.assertIn("yetkilendirmesi başarısız", message)
        self.assertIsNone(data)
        mock_urlopen.assert_called_once()
        self.mock_sleep.assert_not_called()

    def test_single_attempt_success_still_works(self):
        ok_response = _response({"ok": True, "message": "tamam", "structuredData": None})
        with patch(
            "backend.app.remote_ocr_client.urllib.request.urlopen",
            return_value=ok_response,
        ) as mock_urlopen:
            ok, message, data = remote_ocr_client.run_remote_image_group_ocr(_uploaded_files(), _FAKE_URL)

        self.assertTrue(ok)
        self.assertEqual(message, "tamam")
        self.assertIsNone(data)
        mock_urlopen.assert_called_once()
        self.mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
