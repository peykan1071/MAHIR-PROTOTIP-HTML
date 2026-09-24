"""Privacy filtering tests for the OCR boundary.

2026-09-24: bu dosya eskiden `_parse_positional_row`u test ediyordu. O
fonksiyon, bir görselde BİRDEN ÇOK öğrenci satırı olabildiği döneme aitti ve
satırları konuma göre okuyordu; `b269de8` ("çoklu sınav evrak akışı") akışı
"bir görsel = bir öğrenci" haline getirip yerine `read_exam_document` ->
`_parse_exam_rows`ı koydu ama eski fonksiyon kodda kaldı. Fonksiyon silindiği
için testler CANLI yola taşındı: korunan garanti aynı - ad-soyad ve TCKN OCR
çıktısına asla girmez, yalnız `privacyFindings` sinyali üretir.
"""

import json
import unittest

from backend.app.ocr_engine import _looks_like_full_name, _looks_like_tckn, _parse_exam_rows


class OcrPrivacyHeuristicTests(unittest.TestCase):
    def test_valid_tckn_is_detected_but_arbitrary_eleven_digits_are_not(self):
        self.assertTrue(_looks_like_tckn("10000000146"))
        self.assertFalse(_looks_like_tckn("12345678901"))

    def test_two_word_name_detection_does_not_mark_scores(self):
        self.assertTrue(_looks_like_full_name("Mehmet Kaya"))
        self.assertFalse(_looks_like_full_name("15"))


class ExamDocumentPrivacyTests(unittest.TestCase):
    """Kâğıt şablonundaki kimlik hücreleri okunur ama ÇIKTIYA girmez."""

    def test_student_name_is_flagged_but_never_reaches_the_output(self):
        parsed = _parse_exam_rows([
            ["Öğrencinin Adı-Soyadı", "Ayşe Yılmaz"],
            ["Öğrenci Okul No", "123"],
            ["Sınıf/Şube", "9-A"],
            ["Sorular", "S1", "S2", "Toplam"],
            ["Azami Puan", "10", "20", "30"],
            ["Öğrencinin Aldığı Puan", "8", "15", "23"],
        ])

        self.assertEqual(parsed["privacyFindings"], ["AD_SOYAD"])
        self.assertEqual(parsed["student"]["studentNo"], "123")
        self.assertEqual(parsed["student"]["scores"], [8, 15])
        self.assertEqual(parsed["student"]["totalScore"], 23)
        # Ad hiçbir alana sızmamalı - çıktının tamamında aranır.
        self.assertNotIn("Ayşe", json.dumps(parsed, ensure_ascii=False))
        self.assertNotIn("Yılmaz", json.dumps(parsed, ensure_ascii=False))

    def test_tckn_written_in_the_school_number_cell_is_rejected(self):
        parsed = _parse_exam_rows([
            ["Öğrenci Okul No", "10000000146"],
            ["Sorular", "S1", "S2", "Toplam"],
            ["Azami Puan", "10", "20", "30"],
            ["Öğrencinin Aldığı Puan", "8", "15", "23"],
        ])

        self.assertIn("TCKN", parsed["privacyFindings"])
        self.assertEqual(parsed["student"]["studentNo"], "", "TCKN öğrenci referansı olarak kullanılamaz.")
        self.assertNotIn("10000000146", json.dumps(parsed, ensure_ascii=False))

    def test_clean_sheet_reports_no_privacy_findings(self):
        parsed = _parse_exam_rows([
            ["Öğrenci Okul No", "OGR-007"],
            ["Sınıf/Şube", "9-A"],
            ["Sorular", "S1", "S2", "Toplam"],
            ["Azami Puan", "10", "20", "30"],
            ["Öğrencinin Aldığı Puan", "8", "15", "23"],
        ])

        self.assertEqual(parsed["privacyFindings"], [])
        self.assertEqual(parsed["student"]["studentNo"], "OGR-007")


if __name__ == "__main__":
    unittest.main()
