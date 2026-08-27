import unittest
from unittest.mock import patch

from backend.app.ocr_engine import _parse_exam_rows, read_exam_document
from backend.app.ocr_worker import _run_image_group_ocr
from backend.app.file_receiver import UploadedFile, FileCheckResult
from backend.app.ocr_quality_agent import OCRDecision, assess_result


class ExamDocumentParserTests(unittest.TestCase):
    @patch("backend.app.ocr_engine._extract_table_rows")
    @patch("backend.app.ocr_engine._run_ocr", return_value="<table></table>")
    def test_explicit_exam_type_cell_is_the_only_exam_type_evidence(self, _run_ocr, extract_rows):
        extract_rows.return_value = [
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-001", "Sınav Türü", "Konuşma"],
            ["Öğrenci Okul No", "OGR-001"],
            ["Sınıf/Şube", "9-A"],
            ["Azami Puan", "10", "10", "20"],
            ["Öğrencinin Aldığı Puan", "2", "3", "5"],
        ]

        result = read_exam_document(b"image", ".png")

        self.assertEqual(result["exam"]["examType"], "Konuşma")

    def test_class_section_accepts_ocr_space_separator(self):
        rows = [["Sınıf/Şube", "9", "A"]]

        result = _parse_exam_rows(rows)

        self.assertEqual(result["exam"]["classSection"], "9-A")

    def test_all_supported_class_section_spellings_are_one_class(self):
        variants = ["9/a", "9/A", "9-a", "9-A", "9 A", "9a", "9 a", "9A"]
        for variant in variants:
            with self.subTest(variant=variant):
                result = _parse_exam_rows([["Sınıf/Şube", variant]])
                self.assertEqual(result["exam"]["classSection"], "9-A")

    def test_unlabelled_class_like_text_is_not_used(self):
        result = _parse_exam_rows([["Açıklama", "9-A"], ["Sınav Türü", "Yazılı"]])
        self.assertEqual(result["exam"]["classSection"], "")

    def test_one_image_becomes_one_student_document(self):
        rows = [
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-001", "Sınav Türü", "Yazılı"],
            ["Öğrenci Okul No", "OGR-001", "Sınav Tarihi", "15.05.2025"],
            ["Sınıf/Şube", "9-A"],
            ["Dersin Adı", "Türk Dili ve Edebiyatı"],
            ["Sorular", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "Toplam"],
            ["Azami Puan", "12", "12", "14", "12", "14", "12", "24", "100"],
            ["Öğrencinin Aldığı Puan", "4", "3", "0", "4", "0", "4", "6", "21"],
        ]

        parsed = _parse_exam_rows(rows)

        self.assertEqual(parsed["exam"]["classSection"], "9-A")
        self.assertEqual(parsed["exam"]["course"], "Türk Dili ve Edebiyatı")
        self.assertEqual([question["maxScore"] for question in parsed["questions"]], [12, 12, 14, 12, 14, 12, 24])
        self.assertEqual(parsed["student"]["scores"], [4, 3, 0, 4, 0, 4, 6])
        self.assertEqual(parsed["student"]["totalScore"], 21)
        self.assertEqual(parsed["student"]["studentNo"], "OGR-001")

    def test_context_is_preserved_when_question_count_cannot_be_read(self):
        rows = [
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-011", "Sınav Türü", "Dinleme"],
            ["Öğrenci Okul No", "OGR-011"],
            ["Sınıf/Şube", "9-A"],
            ["Dersin Adı", "Türk Dili ve Edebiyatı"],
        ]

        parsed = _parse_exam_rows(rows)

        self.assertTrue(parsed["requiresQuestionCount"])
        self.assertEqual(parsed["questions"], [])
        self.assertEqual(parsed["exam"]["classSection"], "9-A")
        self.assertEqual(parsed["exam"]["course"], "Türk Dili ve Edebiyatı")
        self.assertEqual(parsed["exam"]["examType"], "Dinleme")
        self.assertEqual(parsed["student"]["studentNo"], "OGR-011")
        self.assertEqual(parsed["student"]["scores"], [])

    def test_combined_metadata_cells_are_canonicalized(self):
        rows = [
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-009", "Sınav Türü", "□ Yazılı ☑ 2. Dinleme □ Konuşma"],
            ["Öğrenci Okul No", "OGR-009"],
            ["Sınıf/Şube 9 - a"],
            ["Azami Puan", "10", "10", "100"],
            ["Öğrencinin Aldığı Puan", "3", "2", "5"],
        ]

        parsed = _parse_exam_rows(rows)

        self.assertEqual(parsed["exam"]["classSection"], "9-A")
        self.assertEqual(parsed["exam"]["examType"], "")
        self.assertEqual(parsed["student"]["studentNo"], "OGR-009")

    def test_written_and_listening_documents_keep_references_and_separate_shapes(self):
        written = _parse_exam_rows([
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-003", "Sınav Türü", "Yazılı"],
            ["Öğrenci Okul No", "OGR - 003"],
            ["Sınıf/Şube", "9-A"],
            ["Azami Puan", "12", "12", "14", "12", "14", "12", "24", "100"],
            ["Öğrencinin Aldığı Puan", "4", "3", "0", "4", "0", "4", "6", "21"],
        ])
        listening = _parse_exam_rows([
            ["Öğrencinin Adı-Soyadı", "ÖĞRENCİ-009", "Sınav Türü", "Dinleme"],
            ["Öğrenci Okul No", "OGR-009"],
            ["Sınıf/Şube", "9-A"],
            ["Azami Puan", "10", "10", "10", "10", "10", "10", "10", "10", "10", "10", "100"],
            ["Öğrencinin Aldığı Puan", "3", "3", "2", "2", "2", "2", "3", "3", "3", "2", "25"],
        ])

        self.assertEqual(written["student"]["studentNo"], "OGR-003")
        self.assertEqual(written["exam"]["classSection"], "9-A")
        self.assertEqual(written["exam"]["examType"], "Yazılı")
        self.assertEqual(len(written["questions"]), 7)
        self.assertEqual(listening["student"]["studentNo"], "OGR-009")
        self.assertEqual(listening["exam"]["classSection"], "9-A")
        self.assertEqual(listening["exam"]["examType"], "Dinleme")
        self.assertEqual(len(listening["questions"]), 10)
        self.assertEqual(listening["student"]["scores"], [3, 3, 2, 2, 2, 2, 3, 3, 3, 2])

    def test_blank_score_cell_keeps_its_question_position_and_total_stays_blank(self):
        parsed = _parse_exam_rows([
            ["Sınav Türü", "Yazılı"],
            ["Sınıf/Şube", "9-A"],
            ["Sorular", "S1", "S2", "S3", "Toplam"],
            ["Azami Puan", "30", "30", "40", "100"],
            ["Öğrencinin Aldığı Puan", "20", "", "35", ""],
        ])
        self.assertEqual(parsed["student"]["scores"], [20, None, 35])
        self.assertIsNone(parsed["student"]["totalScore"])

    def test_isolated_class_value_beats_incidental_question_fragment(self):
        rows = [
            ["S1-Soru başlığı"],
            ["Sınıf/Şube", "9-A"],
            ["Azami Puan", "10", "10", "20"],
            ["Öğrencinin Aldığı Puan", "3", "4", "7"],
        ]
        parsed = _parse_exam_rows(rows)
        self.assertEqual(parsed["exam"]["classSection"], "9-A")

    def test_split_azami_label_is_recognized(self):
        rows = [
            ["Sınıf/Şube", "9-A"],
            ["Aza mi Puan", "10", "10", "20"],
            ["Öğrencinin Aldığı Puan", "3", "4", "7"],
        ]
        parsed = _parse_exam_rows(rows)
        self.assertEqual([question["maxScore"] for question in parsed["questions"]], [10, 10])

    def test_quality_agent_counts_students_inside_multiple_groups(self):
        decision = OCRDecision("image-group", True, True, "test")
        structured = {
            "students": [],
            "groups": [
                {"students": [{"scores": [4], "totalScore": 4, "calculatedTotal": 4}]},
                {"students": [{"scores": [3], "totalScore": 3, "calculatedTotal": 3}]},
            ],
        }

        quality = assess_result(decision, structured, flow_ok=True, expected_file_count=2)

        self.assertEqual(quality["checks"]["readStudentRowCount"], 2)
        self.assertNotIn("NO_OCR_ROWS", [issue["code"] for issue in quality["issues"]])

    @patch("backend.app.ocr_worker.ocr_engine.ensure_available")
    @patch("backend.app.ocr_worker.ocr_engine.read_exam_document")
    def test_each_image_is_one_record_and_groups_ignore_score_reading_variation(
        self, read_exam_document, ensure_available
    ):
        ensure_available.return_value = None
        read_exam_document.side_effect = [
            {
                "exam": {"course": "Matematik", "classSection": "9-A", "examType": "Yazılı"},
                "questions": [{"number": 1, "maxScore": 10}],
                "student": {"studentNo": "OGR-003", "scores": [8], "totalScore": 8},
            },
            {
                "exam": {"course": "Türk Dili ve Edebiyatı", "classSection": "9-A", "examType": "Yazılı"},
                "questions": [{"number": 1, "maxScore": 12}],
                "student": {"studentNo": "OGR-022", "scores": [9], "totalScore": 9},
            },
        ]
        files = [
            UploadedFile("a.png", b"a"),
            UploadedFile("b.png", b"b"),
        ]
        checks = [
            FileCheckResult("a.png", ".png", True),
            FileCheckResult("b.png", ".png", True),
        ]

        ok, _, structured = _run_image_group_ocr(files, checks)

        self.assertTrue(ok)
        self.assertEqual(structured["summary"]["studentCount"], 2)
        self.assertEqual(len(structured["documents"]), 2)
        self.assertEqual(len(structured["groups"]), 1)
        self.assertEqual(len(structured["groups"][0]["students"]), 2)
        self.assertEqual(
            [student["studentNo"] for student in structured["groups"][0]["students"]],
            ["OGR-003", "OGR-022"],
        )
        self.assertEqual(
            [student["sourceFile"] for student in structured["groups"][0]["students"]],
            ["a.png", "b.png"],
        )

    @patch("backend.app.ocr_worker.ocr_engine.ensure_available")
    @patch("backend.app.ocr_worker.ocr_engine.read_exam_document")
    def test_students_are_sorted_numerically_by_reference_not_upload_order(self, read_exam_document, ensure_available):
        ensure_available.return_value = None
        read_exam_document.side_effect = [
            {"exam": {"classSection": "9/A", "examType": "Yazılı"}, "questions": [{"number": 1, "maxScore": 100}], "student": {"studentNo": "OGR-21", "scores": [80], "totalScore": 80}},
            {"exam": {"classSection": "9a", "examType": "Yazılı"}, "questions": [{"number": 1, "maxScore": 100}], "student": {"studentNo": "OGR-2", "scores": [70], "totalScore": 70}},
        ]
        files = [UploadedFile("21-y.jpg", b"a"), UploadedFile("2-y.jpg", b"b")]
        checks = [FileCheckResult("21-y.jpg", ".jpg", True), FileCheckResult("2-y.jpg", ".jpg", True)]

        ok, _, structured = _run_image_group_ocr(files, checks)

        self.assertTrue(ok)
        self.assertEqual([student["studentNo"] for student in structured["groups"][0]["students"]], ["OGR-2", "OGR-21"])
        self.assertEqual([student["sourceFile"] for student in structured["groups"][0]["students"]], ["2-y.jpg", "21-y.jpg"])

    @patch("backend.app.ocr_worker.ocr_engine.ensure_available")
    @patch("backend.app.ocr_worker.ocr_engine.read_exam_document")
    def test_exam_type_does_not_create_a_separate_ocr_group(self, read_exam_document, ensure_available):
        ensure_available.return_value = None
        read_exam_document.side_effect = [
            {"exam": {"classSection": "9-A", "examType": "Yazılı"}, "questions": [{"number": 1, "maxScore": 12}], "student": {"studentNo": "OGR-003", "scores": [4], "totalScore": 4}},
            {"exam": {"classSection": "9-A", "examType": "Dinleme"}, "questions": [{"number": 1, "maxScore": 10}, {"number": 2, "maxScore": 10}], "student": {"studentNo": "OGR-009", "scores": [3, 3], "totalScore": 6}},
        ]
        files = [UploadedFile("written.png", b"a"), UploadedFile("listening.png", b"b")]
        checks = [FileCheckResult("written.png", ".png", True), FileCheckResult("listening.png", ".png", True)]

        ok, _, structured = _run_image_group_ocr(files, checks)

        self.assertTrue(ok)
        self.assertEqual(structured["summary"]["groupCount"], 1)
        group = structured["groups"][0]
        self.assertEqual(group["exam"]["classSection"], "9-A")
        self.assertEqual([student["studentNo"] for student in group["students"]], ["OGR-003", "OGR-009"])


if __name__ == "__main__":
    unittest.main()
