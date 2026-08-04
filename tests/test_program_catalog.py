"""Tests for strict course-grade curriculum scoping."""

import unittest

from backend.app.program_catalog import resolve_program, validate_question_program_context


class ProgramCatalogTests(unittest.TestCase):
    def test_tde9_is_registered(self):
        self.assertEqual(resolve_program("Türk Dili ve Edebiyatı", "9").id, "tde-9-tymm")

    def test_tde10_and_mathematics_are_not_registered(self):
        self.assertIsNone(resolve_program("Türk Dili ve Edebiyatı", "10"))
        self.assertIsNone(resolve_program("Matematik", "9"))

    def test_mathematics_rejects_tde_outcome(self):
        with self.assertRaisesRegex(ValueError, "yalnız tanımlı"):
            validate_question_program_context(
                "Matematik", "9", [{"outcomeCode": "TDE2.2", "outcomeKey": "tema1-tde2-2"}]
            )

    def test_tde9_accepts_tde_outcome(self):
        result = validate_question_program_context(
            "Türk Dili ve Edebiyatı",
            "9. sınıf",
            [{"outcomeCode": "TDE2.2", "outcomeKey": "tema1-tde2-2"}],
        )
        self.assertEqual(result.id, "tde-9-tymm")


if __name__ == "__main__":
    unittest.main()
