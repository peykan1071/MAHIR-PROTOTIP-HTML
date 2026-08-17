"""Course and grade scoped curriculum-program registry for MAHIR."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramProfile:
    id: str
    course_names: tuple[str, ...]
    grade: str
    outcome_prefix: str


TDE9 = ProgramProfile(
    id="tde-9-tymm",
    course_names=("Türk Dili ve Edebiyatı", "Seçmeli Türk Dili ve Edebiyatı"),
    grade="9",
    outcome_prefix="TDE",
)
PROGRAMS = (TDE9,)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return " ".join(text.split())


def _grade(value: object) -> str:
    return re.sub(r"\.\s*sınıf$", "", str(value or "").strip(), flags=re.IGNORECASE)


def resolve_program(course_name: object, grade: object) -> ProgramProfile | None:
    """Return only an explicitly registered course-grade program."""

    normalized_course = _normalize(course_name)
    normalized_grade = _grade(grade)
    for program in PROGRAMS:
        if program.grade == normalized_grade and normalized_course in {
            _normalize(name) for name in program.course_names
        }:
            return program
    return None


def validate_question_program_context(
    course_name: object, grade: object, questions: list[dict[str, object]]
) -> ProgramProfile | None:
    """Reject curriculum codes that belong to a different course or grade."""

    program = resolve_program(course_name, grade)
    for question in questions:
        raw_outcomes = question.get("outcomes")
        mappings = raw_outcomes if isinstance(raw_outcomes, list) and raw_outcomes else [question]
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            code = str(mapping.get("outcomeCode") or "").strip()
            key = str(mapping.get("outcomeKey") or "").strip()
            has_tde_code = code.upper().startswith("TDE") or key.casefold().startswith("tema")
            if has_tde_code and program is None:
                raise ValueError(
                    "Türk Dili ve Edebiyatı öğrenme çıktısı kodları yalnız tanımlı "
                    "Türk Dili ve Edebiyatı ders-sınıf profilinde kullanılabilir."
                )
            if program and code and not code.upper().startswith(program.outcome_prefix):
                raise ValueError("Seçilen öğrenme çıktısı kodu bu ders programıyla eşleşmiyor.")
    return program
