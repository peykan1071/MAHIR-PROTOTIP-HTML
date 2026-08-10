"""Tests for RAG-sourced conceptual context attached to weak outcomes."""

import unittest
from unittest.mock import patch

from backend.app.approved_data_analyzer import _normalize_theme_for_rag, analyze_approved_data

_FAKE_REMOTE_URL = "https://fake.example/web_query"


def _weak_tde_payload():
    return {
        "exam": {"courseName": "Türk Dili ve Edebiyatı", "grade": "9", "componentType": "written"},
        "questions": [
            {
                "number": 1,
                "maxScore": 100,
                "outcomeCode": "TDE1.2",
                "outcomeTheme": "1. Tema: Sözün İnceliği",
                "outcomeSkill": "Dinleme/İzleme",
            }
        ],
        "students": [{"studentNo": "1", "scores": [30]}],
    }


class RagContextAttachmentTests(unittest.TestCase):
    def test_ragcontext_field_always_present_even_without_remote_url(self):
        # MAHIR_RAG_REMOTE_URL artık koda gömülü bir varsayılana sahip (bkz.
        # approved_data_analyzer.py) - "yapılandırılmamış" durumu burada
        # açıkça boş string'e çekilerek test ediliyor, gerçek ağ çağrısı yapılmaz.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_unregistered_course_never_calls_rag(self):
        payload = {
            "exam": {"courseName": "Fen Bilimleri", "componentType": "written"},
            "questions": [{"number": 1, "maxScore": 100}],
            "students": [{"studentNo": "1", "scores": [10]}],
        }
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_strong_outcome_is_not_queried(self):
        payload = _weak_tde_payload()
        payload["students"][0]["scores"] = [90]  # successRate 0.90 >= eşik (0.70)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_weak_registered_outcome_attaches_answer(self):
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Bu kazanım dinleme becerisini kapsar.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_called_once()
        called_question, called_program_id, called_url = mock_query.call_args[0]
        called_kwargs = mock_query.call_args[1]
        self.assertIn("Sözün İnceliği", called_question)
        self.assertIn("TDE1.2", called_question)
        self.assertEqual(called_program_id, "tde-9-tymm")
        self.assertEqual(called_url, _FAKE_REMOTE_URL)
        self.assertEqual(called_kwargs["grade"], "9")
        self.assertEqual(called_kwargs["theme"], "SÖZÜN İNCELİĞİ")
        self.assertEqual(result["outcomes"][0]["ragContext"], "Bu kazanım dinleme becerisini kapsar.")

    def test_no_answer_in_document_leaves_ragcontext_empty(self):
        canned = (True, "Yanıt üretildi.", {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []})
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_rag_failure_leaves_ragcontext_empty_and_does_not_raise(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch(
                "backend.app.rag_client.query_rag_context",
                return_value=(False, "Uzak RAG sunucusuna ulaşılamadı.", None),
            ):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_rag_exception_leaves_ragcontext_empty_and_does_not_raise(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", side_effect=RuntimeError("boom")):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")


class NormalizeThemeForRagTests(unittest.TestCase):
    def test_strips_tema_prefix_and_uppercases(self):
        self.assertEqual(_normalize_theme_for_rag("1. Tema: Sözün İnceliği"), "SÖZÜN İNCELİĞİ")

    def test_turkish_dotted_and_dotless_i_both_uppercase_correctly(self):
        # Standart Unicode .upper() Türkçe 'i'/'ı' ayrımını kaybediyor (ikisi de
        # düz "I"ya dönüşür) - rag_service.py'nin PDF'ten çıkardığı tema
        # etiketleriyle eşleşmesi için 'i' -> 'İ', 'ı' -> 'I' olmalı.
        self.assertEqual(_normalize_theme_for_rag("Dilin Zenginliği"), "DİLİN ZENGİNLİĞİ")
        self.assertEqual(_normalize_theme_for_rag("Anlamın Yapı Taşları"), "ANLAMIN YAPI TAŞLARI")


if __name__ == "__main__":
    unittest.main()
