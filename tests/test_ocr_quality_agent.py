"""Belge Okuma ve OCR Kalite Ajanı güvence testleri."""

import unittest
from unittest.mock import patch

from backend.app.file_receiver import FileCheckResult, UploadedFile
from backend.app.ocr_quality_agent import assess_result, inspect_upload, warning_messages


class OCRQualityAgentTests(unittest.TestCase):
    def test_images_require_ocr(self):
        files = [UploadedFile("ogr-1.jpg", b"image"), UploadedFile("ogr-2.png", b"image")]
        checks = [FileCheckResult("ogr-1.jpg", ".jpg", True), FileCheckResult("ogr-2.png", ".png", True)]
        decision = inspect_upload(files, checks)
        self.assertEqual(decision.input_kind, "image-group")
        self.assertTrue(decision.ocr_required)
        self.assertTrue(decision.ocr_available)

    def test_native_table_document_never_uses_ocr(self):
        decision = inspect_upload(
            [UploadedFile("notlar.xlsx", b"xlsx")],
            [FileCheckResult("notlar.xlsx", ".xlsx", True)],
        )
        self.assertEqual(decision.input_kind, "native-table-document")
        self.assertFalse(decision.ocr_required)

    @patch("backend.app.ocr_quality_agent._pdf_has_extractable_text", return_value=False)
    def test_scanned_pdf_is_flagged_for_manual_completion(self, _mock_text_check):
        decision = inspect_upload(
            [UploadedFile("tarama.pdf", b"%PDF")],
            [FileCheckResult("tarama.pdf", ".pdf", True)],
        )
        quality = assess_result(decision, None, flow_ok=True, expected_file_count=1)
        self.assertTrue(decision.ocr_required)
        self.assertFalse(decision.ocr_available)
        self.assertEqual(quality["qualityStatus"], "manual-completion-required")
        self.assertTrue(any(issue["code"] == "OCR_ROUTE_UNAVAILABLE" for issue in quality["issues"]))

    def test_clean_ocr_result_is_still_sent_to_teacher_review(self):
        decision = inspect_upload(
            [UploadedFile("ogr.jpg", b"image")],
            [FileCheckResult("ogr.jpg", ".jpg", True)],
        )
        data = {
            "students": [
                {
                    "studentNo": "1001",
                    "scores": [10, 20],
                    "totalScore": 30,
                    "calculatedTotal": 30,
                    "privacyFindings": [],
                }
            ],
            "warnings": [],
        }
        quality = assess_result(decision, data, flow_ok=True, expected_file_count=1)
        self.assertEqual(quality["qualityStatus"], "ready-for-teacher-review")
        self.assertTrue(quality["teacherReviewRequired"])
        self.assertTrue(quality["ocrUsed"])
        self.assertFalse(quality["llmUsed"])

    def test_missing_cells_and_total_mismatch_are_explained(self):
        decision = inspect_upload(
            [UploadedFile("ogr.jpg", b"image")],
            [FileCheckResult("ogr.jpg", ".jpg", True)],
        )
        data = {
            "students": [
                {
                    "studentNo": "1001",
                    "scores": [10, None],
                    "totalScore": 40,
                    "calculatedTotal": 10,
                    "privacyFindings": ["AD_SOYAD"],
                }
            ],
            "warnings": [],
        }
        quality = assess_result(decision, data, flow_ok=True, expected_file_count=1)
        codes = {issue["code"] for issue in quality["issues"]}
        self.assertEqual(quality["qualityStatus"], "teacher-review-required")
        self.assertTrue({"EMPTY_SCORE_CELLS", "TOTAL_MISMATCH", "PRIVACY_DATA_REMOVED"} <= codes)
        self.assertEqual(len(warning_messages(quality)), 3)


if __name__ == "__main__":
    unittest.main()
