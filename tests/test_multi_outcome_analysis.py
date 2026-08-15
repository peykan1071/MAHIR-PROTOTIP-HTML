import unittest

from backend.app.approved_data_analyzer import analyze_approved_data


class MultiOutcomeAnalysisTests(unittest.TestCase):
    def test_question_evidence_is_split_equally_without_double_counting(self):
        payload = {
            "exam": {"componentType": "written"},
            "questions": [
                {
                    "number": 1,
                    "maxScore": 50,
                    "outcomes": [
                        {"outcomeCode": "OUT-A", "outcomeDescription": "Çıktı A", "outcomeKey": "a"},
                        {"outcomeCode": "OUT-B", "outcomeDescription": "Çıktı B", "outcomeKey": "b"},
                    ],
                },
                {
                    "number": 2,
                    "maxScore": 50,
                    "outcomes": [
                        {"outcomeCode": "OUT-A", "outcomeDescription": "Çıktı A", "outcomeKey": "a"},
                    ],
                },
            ],
            "students": [
                {"studentRef": "Ö-001", "scores": [40, 30], "totalScore": 70},
                {"studentRef": "Ö-002", "scores": [20, 10], "totalScore": 30},
            ],
        }

        result = analyze_approved_data(payload)
        outcomes = {item["outcomeCode"]: item for item in result["outcomes"]}

        self.assertEqual([item["weight"] for item in result["questions"][0]["outcomes"]], [0.5, 0.5])
        self.assertEqual(result["questions"][1]["outcomes"][0]["weight"], 1.0)
        self.assertAlmostEqual(outcomes["OUT-A"]["earnedScore"], 70.0)
        self.assertAlmostEqual(outcomes["OUT-A"]["possibleScore"], 150.0)
        self.assertAlmostEqual(outcomes["OUT-B"]["earnedScore"], 30.0)
        self.assertAlmostEqual(outcomes["OUT-B"]["possibleScore"], 50.0)
        self.assertAlmostEqual(sum(item["earnedScore"] for item in result["outcomes"]), 100.0)
        self.assertAlmostEqual(sum(item["possibleScore"] for item in result["outcomes"]), 200.0)

    def test_legacy_single_outcome_remains_supported(self):
        result = analyze_approved_data({
            "exam": {"componentType": "written"},
            "questions": [{
                "number": 1,
                "maxScore": 20,
                "outcomeCode": "OUT-A",
                "outcomeDescription": "Çıktı A",
                "outcomeKey": "a",
            }],
            "students": [{"studentRef": "Ö-001", "scores": [15], "totalScore": 15}],
        })

        self.assertEqual(len(result["questions"][0]["outcomes"]), 1)
        self.assertEqual(result["questions"][0]["outcomes"][0]["weight"], 1.0)
        self.assertEqual(result["outcomes"][0]["earnedScore"], 15.0)


if __name__ == "__main__":
    unittest.main()
