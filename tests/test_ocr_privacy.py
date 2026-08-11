"""Privacy filtering tests for the OCR boundary."""

import unittest

from backend.app.ocr_engine import _looks_like_full_name, _looks_like_tckn, _parse_positional_row


class OcrPrivacyTests(unittest.TestCase):
    def test_valid_tckn_is_detected_but_arbitrary_eleven_digits_are_not(self):
        self.assertTrue(_looks_like_tckn("10000000146"))
        self.assertFalse(_looks_like_tckn("12345678901"))

    def test_name_and_tckn_are_removed_from_score_row(self):
        row = _parse_positional_row(
            ["123", "10000000146", "Ayşe Yılmaz", "8", "7", "15"]
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["studentNo"], "123")
        self.assertEqual(row["scores"], [8, 7])
        self.assertEqual(row["privacyFindings"], ["TCKN", "AD_SOYAD"])
        self.assertNotIn("fullName", row)

    def test_two_word_name_detection_does_not_mark_scores(self):
        self.assertTrue(_looks_like_full_name("Mehmet Kaya"))
        self.assertFalse(_looks_like_full_name("15"))


if __name__ == "__main__":
    unittest.main()
