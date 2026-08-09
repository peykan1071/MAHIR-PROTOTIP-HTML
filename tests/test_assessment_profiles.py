"""Deterministic tests for language-assessment weighting."""

import unittest

from backend.app.approved_data_analyzer import analyze_approved_data
from backend.app.assessment_profiles import (
    build_general_evaluation,
    calculate_composite_scores,
    profile_for_course,
)


class AssessmentProfileTests(unittest.TestCase):
    def test_tde_uses_70_15_15(self):
        result = calculate_composite_scores(
            "tde-70-15-15",
            {
                "written": {"1": 80, "2": 60},
                "listening": {"1": 100, "2": 80},
                "speaking": {"1": 60, "2": 100},
            },
        )
        self.assertTrue(result["complete"])
        self.assertEqual(result["studentScores"], {"1": 80.0, "2": 69.0})
        self.assertEqual(result["classAverage"], 74.5)

    def test_incomplete_bundle_is_not_finalized(self):
        result = calculate_composite_scores(
            "tde-70-15-15",
            {"written": {"1": 80}, "listening": {"1": 90}},
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["missingComponents"], ["speaking"])
        self.assertIsNone(result["classAverage"])

    def test_course_profile_resolution_is_limited_to_language_courses(self):
        self.assertEqual(profile_for_course("Türk Dili ve Edebiyatı").id, "tde-70-15-15")
        self.assertEqual(profile_for_course("Rusça").id, "language-50-25-25")
        self.assertIsNone(profile_for_course("Fen Bilimleri"))

    def test_science_course_rejects_language_component(self):
        with self.assertRaisesRegex(ValueError, "yalnız dil dersi"):
            analyze_approved_data(
                {
                    "exam": {"courseName": "Fen Bilimleri", "componentType": "listening"},
                    "questions": [{"number": 1, "maxScore": 100}],
                    "students": [
                        {"studentNo": "1", "fullName": "Örnek Öğrenci", "scores": [80]}
                    ],
                }
            )

    def test_performance_is_not_an_exam_type(self):
        with self.assertRaisesRegex(ValueError, "Sınav türü"):
            analyze_approved_data(
                {
                    "exam": {
                        "courseName": "Türk Dili ve Edebiyatı",
                        "componentType": "performance",
                    },
                    "questions": [{"number": 1, "maxScore": 100}],
                    "students": [
                        {"studentNo": "1", "fullName": "Örnek Öğrenci", "scores": [80]}
                    ],
                }
            )

    def test_foreign_language_accepts_matching_profile(self):
        result = analyze_approved_data(
            {
                "exam": {
                    "courseName": "Arapça",
                    "componentType": "speaking",
                    "weightingProfileId": "language-50-25-25",
                },
                "questions": [{"number": 1, "maxScore": 100}],
                "students": [
                    {"studentNo": "1", "fullName": "Örnek Öğrenci", "scores": [80]}
                ],
            }
        )
        self.assertEqual(result["exam"]["componentWeight"], 0.25)

    def test_student_name_is_not_required_or_returned(self):
        result = analyze_approved_data(
            {
                "exam": {"courseName": "Fen Bilimleri", "componentType": "written"},
                "questions": [{"number": 1, "maxScore": 100}],
                "students": [{"studentNo": "Ö-001", "scores": [80]}],
            }
        )
        self.assertEqual(result["students"][0]["studentNo"], "Ö-001")
        self.assertNotIn("fullName", result["students"][0])

    def test_general_evaluation_requires_all_language_components(self):
        result = build_general_evaluation(
            "tde-70-15-15",
            {
                "written": {"students": [{"studentNo": "1", "calculatedTotal": 80}], "outcomes": []},
                "listening": {"students": [{"studentNo": "1", "calculatedTotal": 100}], "outcomes": []},
            },
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["missingComponentLabels"], ["Konuşma Sınavı"])

    def test_general_evaluation_preserves_skill_evidence(self):
        components = {}
        for component, score, skill in (
            ("written", 80, "Okuma"),
            ("listening", 100, "Dinleme/İzleme"),
            ("speaking", 60, "Konuşma"),
        ):
            components[component] = {
                "students": [{"studentNo": "1", "calculatedTotal": score}],
                "outcomes": [{"outcomeCode": "ÖÇ.1", "outcomeSkill": skill, "realizationRate": score / 100}],
            }
        result = build_general_evaluation("tde-70-15-15", components)
        self.assertTrue(result["complete"])
        self.assertEqual(result["studentScores"], {"1": 80.0})
        self.assertEqual(len(result["componentEvidence"]), 3)


if __name__ == "__main__":
    unittest.main()
