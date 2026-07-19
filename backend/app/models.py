"""CED data models for the MAHIR prototype.

CED (Common Educational Data) defines the shared structure used by the
prototype to describe an assessment, its questions, student results, and
validation notes. This module intentionally contains no OCR, AI, API,
database, or user-system logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class CEDMetadata:
    """Document-level information for a CED payload."""

    ced_version: str
    created_at: str
    source: str
    language: str = "tr"


@dataclass(slots=True)
class CEDAssessment:
    """Assessment identity and high-level exam information."""

    id: str
    title: str
    course: str
    education_level: str | None = None
    school_type: str | None = None
    grade: str | None = None
    exam_type: str | None = None
    exam_date: str | None = None
    question_count: int | None = None
    total_score: float | None = None


@dataclass(slots=True)
class CEDQuestion:
    """Question-level assessment data."""

    id: str
    number: int
    text: str | None = None
    max_score: float | None = None
    learning_outcome_ids: list[str] = field(default_factory=list)
    answer_key: str | None = None


@dataclass(slots=True)
class CEDQuestionScore:
    """Score given to a student for a single question."""

    question_id: str
    score: float | None = None


@dataclass(slots=True)
class CEDStudentResult:
    """Student-level result data for one assessment."""

    student_no: str
    full_name: str
    question_scores: list[CEDQuestionScore] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)
    total_score: float | None = None


@dataclass(slots=True)
class CEDValidationIssue:
    """A non-blocking validation note for teacher review."""

    code: str
    message: str
    field: str | None = None
    severity: str = "info"


@dataclass(slots=True)
class CEDValidation:
    """Validation state for a CED payload."""

    valid: bool = True
    issues: list[CEDValidationIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CEDDocument:
    """Root CED model used as the shared MAHIR data contract."""

    metadata: CEDMetadata
    assessment: CEDAssessment
    questions: list[CEDQuestion] = field(default_factory=list)
    student_results: list[CEDStudentResult] = field(default_factory=list)
    validation: CEDValidation = field(default_factory=CEDValidation)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the CED document."""

        return asdict(self)