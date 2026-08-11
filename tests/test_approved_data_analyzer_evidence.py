"""Tests for the per-outcome `evidence` block behind the report's "Kanıtları Gör".

The point of this data is that a teacher (or a jury) can ask "bu %68 nereden
geldi?" and get the answer from the same place the number was computed. So the
tests here mostly assert *consistency*: the evidence must never tell a
different story than `analysis["questions"]` and the outcome's own
`successRate`.
"""

import unittest

from backend.app.approved_data_analyzer import analyze_approved_data


def _question(number, outcome_code, theme="1. Tema: Sayılar", max_score=10):
    return {
        "number": number,
        "maxScore": max_score,
        "outcomeCode": outcome_code,
        "outcomeDescription": f"{outcome_code} kazanım metni",
        "outcomeTheme": theme,
        "outcomeSkill": "Okuma",
        "parentOutcomeDescription": f"{outcome_code} kazanım metni",
    }


def _payload(questions, students, **extra):
    return {
        "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
        "questions": questions,
        "students": students,
        **extra,
    }


# Üç soru tek çıktıya, bir soru başka bir çıktıya bağlı. Puanlar, oranların
# elle doğrulanabileceği kadar basit tutuldu.
_QUESTIONS = [
    _question(2, "M9.OB2"),
    _question(5, "M9.OB2"),
    _question(8, "M9.OB2"),
    _question(9, "M9.OB3"),
]
_STUDENTS = [
    {"studentNo": "Ö-001", "scores": [8, 6, 7, 5]},
    {"studentNo": "Ö-002", "scores": [6, 6, 7, 9]},
]


def _outcome(analysis, code):
    return next(item for item in analysis["outcomes"] if item["outcomeCode"] == code)


class OutcomeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.analysis = analyze_approved_data(_payload(_QUESTIONS, _STUDENTS))
        self.outcome = _outcome(self.analysis, "M9.OB2")
        self.evidence = self.outcome["evidence"]

    def test_reports_which_questions_produced_the_percentage(self):
        self.assertEqual(self.evidence["questionNumbers"], [2, 5, 8])
        self.assertEqual(self.evidence["questionCount"], 3)

    def test_reports_how_many_students_were_counted(self):
        self.assertEqual(self.evidence["participatingStudentCount"], 2)
        self.assertEqual(
            self.evidence["participatingStudentCount"],
            self.analysis["summary"]["participatingStudentCount"],
        )

    def test_scores_reproduce_the_outcome_percentage(self):
        # Kanıtın tek işi bu: gösterilen yüzde, gösterilen puanlardan çıkmalı.
        recomputed = self.evidence["earnedScore"] / self.evidence["possibleScore"]
        self.assertAlmostEqual(recomputed, self.outcome["successRate"])
        # 8+6 + 6+6 + 7+7 = 40 puan, 3 soru x 10 puan x 2 öğrenci = 60.
        self.assertAlmostEqual(self.evidence["earnedScore"], 40.0)
        self.assertAlmostEqual(self.evidence["possibleScore"], 60.0)

    def test_per_question_rates_match_the_question_table(self):
        by_number = {item["number"]: item for item in self.analysis["questions"]}
        for entry in self.evidence["questions"]:
            with self.subTest(question=entry["number"]):
                self.assertAlmostEqual(
                    entry["successRate"], by_number[entry["number"]]["successRate"]
                )
                self.assertAlmostEqual(
                    entry["earnedScore"], by_number[entry["number"]]["earnedScore"]
                )

    def test_question_totals_add_up_to_the_outcome_total(self):
        self.assertAlmostEqual(
            sum(entry["earnedScore"] for entry in self.evidence["questions"]),
            self.evidence["earnedScore"],
        )
        self.assertAlmostEqual(
            sum(entry["possibleScore"] for entry in self.evidence["questions"]),
            self.evidence["possibleScore"],
        )

    def test_each_outcome_gets_only_its_own_questions(self):
        other = _outcome(self.analysis, "M9.OB3")["evidence"]
        self.assertEqual(other["questionNumbers"], [9])
        self.assertEqual(other["questionCount"], 1)

    def test_every_outcome_carries_evidence(self):
        for outcome in self.analysis["outcomes"]:
            with self.subTest(outcome=outcome["outcomeCode"]):
                self.assertIn("evidence", outcome)


class CorrectedCellTests(unittest.TestCase):
    def test_absent_corrected_cells_reports_zero(self):
        # Geriye dönük uyum: eski tarayıcı bu alanı hiç göndermiyor.
        analysis = analyze_approved_data(_payload(_QUESTIONS, _STUDENTS))
        for outcome in analysis["outcomes"]:
            with self.subTest(outcome=outcome["outcomeCode"]):
                self.assertEqual(outcome["evidence"]["correctedCellCount"], 0)

    def test_corrections_are_attributed_by_question_index(self):
        # Soru indeksleri 0-tabanlı: 0 -> Soru 2, 2 -> Soru 8, 3 -> Soru 9.
        analysis = analyze_approved_data(
            _payload(_QUESTIONS, _STUDENTS, correctedCells={"0": 2, "2": 1, "3": 4})
        )
        self.assertEqual(_outcome(analysis, "M9.OB2")["evidence"]["correctedCellCount"], 3)
        self.assertEqual(_outcome(analysis, "M9.OB3")["evidence"]["correctedCellCount"], 4)

    def test_correction_counts_are_visible_per_question(self):
        analysis = analyze_approved_data(
            _payload(_QUESTIONS, _STUDENTS, correctedCells={"1": 2})
        )
        by_number = {
            item["number"]: item
            for item in _outcome(analysis, "M9.OB2")["evidence"]["questions"]
        }
        self.assertEqual(by_number[5]["correctedCellCount"], 2)
        self.assertEqual(by_number[2]["correctedCellCount"], 0)

    def test_malformed_corrected_cells_never_block_the_analysis(self):
        # Bu alan yalnız bir açıklanabilirlik göstergesi; hiçbir puanı
        # etkilemediği için bozuk bir değer öğretmenin analizini durdurmamalı.
        for broken in ([1, 2], "iki", {"a": "b"}, {"-1": 3}, {"0": -5}, {"0": None}, None):
            with self.subTest(value=broken):
                analysis = analyze_approved_data(
                    _payload(_QUESTIONS, _STUDENTS, correctedCells=broken)
                )
                self.assertEqual(
                    _outcome(analysis, "M9.OB2")["evidence"]["correctedCellCount"], 0
                )

    def test_corrections_do_not_change_any_score_or_rate(self):
        plain = analyze_approved_data(_payload(_QUESTIONS, _STUDENTS))
        corrected = analyze_approved_data(
            _payload(_QUESTIONS, _STUDENTS, correctedCells={"0": 2, "1": 1})
        )
        self.assertEqual(plain["summary"], corrected["summary"])
        for left, right in zip(plain["outcomes"], corrected["outcomes"]):
            self.assertAlmostEqual(left["successRate"], right["successRate"])


if __name__ == "__main__":
    unittest.main()
