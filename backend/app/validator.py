"""Minimal CED validation flow for the MAHIR backend skeleton.

This module reads CED-shaped dictionaries, checks them against the current
dataclass model, and returns a small validation result. It intentionally avoids
API, OCR, AI, database, and user-system behavior.
"""

from __future__ import annotations

import json
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from .models import (
    CEDAssessment,
    CEDDocument,
    CEDMetadata,
    CEDQuestion,
    CEDQuestionScore,
    CEDStudentResult,
    CEDValidation,
    CEDValidationIssue,
)


MODEL_BY_SECTION = {
    "metadata": CEDMetadata,
    "assessment": CEDAssessment,
    "questions": CEDQuestion,
    "student_results": CEDStudentResult,
    "validation": CEDValidation,
}


class CEDValidationError(ValueError):
    """Raised when a CED payload cannot be converted to the CED model."""


def load_ced_json(path: str | Path) -> dict[str, Any]:
    """Read a CED JSON file from disk."""

    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_ced_payload(payload: dict[str, Any]) -> tuple[bool, list[str], CEDDocument | None]:
    """Validate a CED payload and return success state, errors, and model."""

    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["root: CED verisi bir nesne olmalıdır."], None

    required_sections = ("metadata", "assessment", "questions", "student_results", "validation")
    for section in required_sections:
        if section not in payload:
            errors.append(f"{section}: zorunlu bölüm bulunamadı.")

    unknown_sections = sorted(set(payload) - set(required_sections))
    for section in unknown_sections:
        errors.append(f"{section}: CED modelinde tanımlı olmayan bölüm.")

    if errors:
        return False, errors, None

    try:
        document = CEDDocument(
            metadata=_build_dataclass(CEDMetadata, payload["metadata"], "metadata"),
            assessment=_build_dataclass(CEDAssessment, payload["assessment"], "assessment"),
            questions=[
                _build_dataclass(CEDQuestion, item, f"questions[{index}]")
                for index, item in enumerate(_expect_list(payload["questions"], "questions"))
            ],
            student_results=[
                _build_student_result(item, f"student_results[{index}]")
                for index, item in enumerate(_expect_list(payload["student_results"], "student_results"))
            ],
            validation=_build_validation(payload["validation"], "validation"),
        )
    except CEDValidationError as error:
        errors.append(str(error))
        return False, errors, None

    return True, [], document


def validate_ced_file(path: str | Path) -> tuple[bool, str, list[str]]:
    """Validate a CED file and return a command-line friendly result."""

    try:
        payload = load_ced_json(path)
    except FileNotFoundError:
        return False, "CED doğrulama başarısız.", [f"{path}: dosya bulunamadı."]
    except json.JSONDecodeError as error:
        return False, "CED doğrulama başarısız.", [f"{path}: JSON okunamadı ({error})."]

    is_valid, errors, document = validate_ced_payload(payload)
    if not is_valid:
        return False, "CED doğrulama başarısız.", errors

    question_count = len(document.questions) if document else 0
    student_count = len(document.student_results) if document else 0
    message = f"CED doğrulama başarılı. {question_count} soru ve {student_count} öğrenci sonucu okundu."
    return True, message, []


def _build_student_result(data: Any, path: str) -> CEDStudentResult:
    result = _build_dataclass(CEDStudentResult, data, path, skip_fields={"question_scores"})
    scores = [
        _build_dataclass(CEDQuestionScore, item, f"{path}.question_scores[{index}]")
        for index, item in enumerate(_expect_list(data.get("question_scores", []), f"{path}.question_scores"))
    ]
    result.question_scores = scores
    return result


def _build_validation(data: Any, path: str) -> CEDValidation:
    validation = _build_dataclass(CEDValidation, data, path, skip_fields={"issues"})
    issues = [
        _build_dataclass(CEDValidationIssue, item, f"{path}.issues[{index}]")
        for index, item in enumerate(_expect_list(data.get("issues", []), f"{path}.issues"))
    ]
    validation.issues = issues
    return validation


def _build_dataclass(
    model_type: type[Any],
    data: Any,
    path: str,
    skip_fields: set[str] | None = None,
) -> Any:
    if not is_dataclass(model_type):
        raise CEDValidationError(f"{path}: geçerli bir CED model tipi değil.")
    if not isinstance(data, dict):
        raise CEDValidationError(f"{path}: nesne olmalıdır.")

    skip_fields = skip_fields or set()
    model_fields = {field.name: field for field in fields(model_type)}
    type_hints = get_type_hints(model_type)
    allowed_fields = set(model_fields)
    unknown_fields = sorted(set(data) - allowed_fields)
    if unknown_fields:
        joined = ", ".join(unknown_fields)
        raise CEDValidationError(f"{path}: modelde tanımlı olmayan alan(lar): {joined}.")

    values: dict[str, Any] = {}
    for name, field in model_fields.items():
        if name in skip_fields:
            continue
        if name not in data:
            if field.default is not MISSING:
                continue
            if field.default_factory is not MISSING:
                continue
            raise CEDValidationError(f"{path}.{name}: zorunlu alan bulunamadı.")
        value = data[name]
        if not _matches_type(value, type_hints.get(name, field.type)):
            raise CEDValidationError(f"{path}.{name}: beklenen veri tipiyle uyumlu değil.")
        values[name] = value

    return model_type(**values)


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise CEDValidationError(f"{path}: liste olmalıdır.")
    return value


def _matches_type(value: Any, expected_type: Any) -> bool:
    if value is None:
        return _allows_none(expected_type)

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin in (list,):
        return isinstance(value, list)

    if origin in (dict,):
        return isinstance(value, dict)

    if origin is UnionType:
        return any(_matches_type(value, item) for item in args)

    if expected_type is Any:
        return True

    if expected_type is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)

    if expected_type is str:
        return isinstance(value, str)

    if expected_type is bool:
        return isinstance(value, bool)

    return True


def _allows_none(expected_type: Any) -> bool:
    if expected_type is Any:
        return True
    args = get_args(expected_type)
    return type(None) in args
