"""Tests for teacher-made PDF and Excel score tables."""

import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.file_receiver import UploadedFile, run_existing_backend_flow, validate_file_name
from backend.app.pdf_parser import parse_score_pdf
from backend.app.spreadsheet_parser import parse_score_xlsx
from backend.app.table_parser import parse_tabular_document


SAMPLE_ROWS = [
    ["Ad Soyad", "T.C. Kimlik No", "Okul No", "Soru 1 (25p)", "Soru 2 (25p)", "Toplam (50p)"],
    ["Deneme Öğrenci", "10000000146", "9999", 20, 15, 35],
]


class DocumentTableParserTests(unittest.TestCase):
    def test_multiple_word_documents_remain_separate_exam_groups(self):
        written = {
            "exam": {"classSection": "9-A", "examType": "Yazılı"},
            "questions": [{"number": 1, "maxScore": 10}],
            "students": [{"studentNo": "001", "scores": [8], "totalScore": 8}],
            "warnings": [],
            "summary": {"questionCount": 1, "studentCount": 1, "warningCount": 0},
        }
        listening = {
            "exam": {"classSection": "9-A", "examType": "Dinleme"},
            "questions": [{"number": 1, "maxScore": 10}],
            "students": [{"studentNo": "001", "scores": [7], "totalScore": 7}],
            "warnings": [],
            "summary": {"questionCount": 1, "studentCount": 1, "warningCount": 0},
        }
        files = [UploadedFile("yazili.docx", b"written"), UploadedFile("dinleme.docx", b"listening")]
        checks = [validate_file_name(uploaded.file_name) for uploaded in files]

        with patch("backend.app.file_receiver.parse_mahir_docx", side_effect=[written, listening]):
            ok, message, structured = run_existing_backend_flow(files, checks)

        self.assertTrue(ok)
        self.assertIn("2 veri belgesi ayrı sınav grupları olarak okundu", message)
        self.assertEqual(len(structured["groups"]), 2)
        self.assertEqual([group["exam"]["examType"] for group in structured["groups"]], ["Yazılı", "Dinleme"])
        self.assertEqual(structured["summary"]["studentCount"], 2)
        self.assertEqual(structured["groups"][0]["sourceFileName"], "yazili.docx")

    def test_teacher_columns_are_mapped_by_heading_and_identity_is_removed(self):
        result = parse_tabular_document([SAMPLE_ROWS], source_label="Deneme")
        self.assertEqual(result["questions"], [
            {"number": 1, "outcomeCode": "", "outcomeDescription": "", "maxScore": 25},
            {"number": 2, "outcomeCode": "", "outcomeDescription": "", "maxScore": 25},
        ])
        self.assertEqual(result["students"][0]["studentNo"], "9999")
        self.assertEqual(result["students"][0]["scores"], [20, 15])
        self.assertEqual(result["students"][0]["totalScore"], 35)
        self.assertNotIn("fullName", result["students"][0])
        self.assertNotIn("tckn", result["students"][0])
        self.assertTrue(any("KVKK" in warning for warning in result["warnings"]))

    def test_xlsx_cells_are_read_without_ocr(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        for row in SAMPLE_ROWS:
            sheet.append(row)
        content = io.BytesIO()
        workbook.save(content)

        result = parse_score_xlsx(content.getvalue())
        self.assertEqual(result["summary"]["studentCount"], 1)
        self.assertEqual(result["students"][0]["studentNo"], "9999")

        uploaded = UploadedFile("sinav.xlsx", content.getvalue())
        ok, message, structured = run_existing_backend_flow(
            [uploaded], [validate_file_name(uploaded.file_name)]
        )
        self.assertTrue(ok)
        self.assertIn("Excel tablosu okundu", message)
        self.assertEqual(structured["students"][0]["scores"], [20, 15])

    def test_text_pdf_tables_use_the_same_heading_mapping_without_ocr(self):
        class FakePage:
            def extract_tables(self):
                return [SAMPLE_ROWS]

            def extract_text(self):
                return "Okul No Soru 1 Soru 2 Toplam"

        class FakeDocument:
            pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        fake_pdfplumber = SimpleNamespace(open=lambda _stream: FakeDocument())
        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            result = parse_score_pdf(b"%PDF-test")

        self.assertEqual(result["summary"]["studentCount"], 1)
        self.assertEqual(result["students"][0]["studentNo"], "9999")
        self.assertEqual(result["students"][0]["scores"], [20, 15])

    def test_maximum_row_limits_fixed_question_columns_for_excel_and_pdf(self):
        rows = [
            ["Sıra", "Okul No", *[f"Soru {index}" for index in range(1, 11)], "Toplam"],
            ["AZAMİ", "AZAMİ", 25, 25, 25, 25, "-", "-", "-", "-", "-", "-", 100],
            [1, "1001", 22, 20, 15, 16, "-", "-", "-", "-", "-", "-", 73],
        ]

        result = parse_tabular_document([rows], source_label="Deneme")

        self.assertEqual(result["summary"]["questionCount"], 4)
        self.assertEqual([question["maxScore"] for question in result["questions"]], [25] * 4)
        self.assertEqual(result["students"][0]["scores"], [22, 20, 15, 16])
        self.assertEqual(result["students"][0]["calculatedTotal"], 73)


if __name__ == "__main__":
    unittest.main()
