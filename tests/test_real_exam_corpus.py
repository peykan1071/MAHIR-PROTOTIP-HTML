"""GitHub'da tutulan anonimleştirilmiş MAHİR gerçek evrak kabul testleri."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.app.docx_parser import parse_mahir_docx


CORPUS = Path(__file__).parent / "fixtures" / "real_exam_corpus_anonymized"


class RealExamCorpusAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

    def _files(self, relative_dir: str, suffix: str) -> list[Path]:
        return sorted((CORPUS / relative_dir).glob(f"*{suffix}"))

    def test_manifest_matches_all_anonymized_files(self):
        entries = self.manifest["files"]
        self.assertEqual(len(entries), 132)
        for entry in entries:
            path = CORPUS / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertEqual(path.stat().st_size, entry["bytes"], entry["path"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"], entry["path"])

    def test_45_same_type_written_images_are_present_for_ocr(self):
        self.assertEqual(len(self._files("images/9A-written-25", ".png")), 25)
        self.assertEqual(len(self._files("images/9B-written-20", ".png")), 20)

    def test_five_same_type_written_word_score_sheets_are_parsed(self):
        sheets = self._files("word/five-classes-written", ".docx")
        self.assertEqual(len(sheets), 5)
        parsed = [parse_mahir_docx(path.read_bytes()) for path in sheets]
        self.assertEqual([item["exam"]["classSection"] for item in parsed], ["9-A", "9-B", "9-C", "9-D", "9-E"])
        self.assertEqual([item["summary"]["studentCount"] for item in parsed], [25, 28, 22, 20, 25])
        for item in parsed:
            self.assertEqual(item["summary"]["questionCount"], 7)
            self.assertEqual([question["maxScore"] for question in item["questions"]], [12, 12, 14, 12, 14, 12, 24])

    def test_25_student_exam_has_both_ocr_and_word_comparison_sources(self):
        images = self._files("images/9A-ocr-word-comparison-25", ".jpeg")
        sheets = sorted((CORPUS / "word/ocr-word-comparison").glob("*Yazili_Puan_Cizelgesi.docx"))
        self.assertEqual(len(images), 25)
        self.assertEqual(len(sheets), 1)
        parsed = parse_mahir_docx(sheets[0].read_bytes())
        self.assertEqual(parsed["exam"]["classSection"], "9-A")
        self.assertEqual(parsed["summary"]["studentCount"], 25)
        self.assertEqual(parsed["summary"]["questionCount"], 7)
        self.assertEqual([question["maxScore"] for question in parsed["questions"]], [12, 12, 14, 12, 14, 12, 24])

    def test_one_20_student_class_has_three_ocr_components(self):
        self.assertEqual(len(self._files("images/9B-written-20", ".png")), 20)
        self.assertEqual(len(self._files("images/9B-listening-20", ".png")), 20)
        self.assertEqual(len(self._files("images/9B-speaking-20", ".png")), 20)

    def test_general_evaluation_weights_are_declared(self):
        self.assertEqual(
            self.manifest["generalEvaluationWeights"],
            {"written": 70, "listening": 15, "speaking": 15},
        )


if __name__ == "__main__":
    unittest.main()
