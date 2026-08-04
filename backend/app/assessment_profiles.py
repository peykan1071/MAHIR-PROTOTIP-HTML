"""Course-specific assessment component and weighting rules for MAHIR.

Each component is evaluated on a 100-point scale. A composite score is only
final when every required component in the selected profile is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import unicodedata


WRITTEN = "written"
LISTENING = "listening"
SPEAKING = "speaking"


@dataclass(frozen=True, slots=True)
class AssessmentProfile:
    id: str
    title: str
    course_names: tuple[str, ...]
    weights: dict[str, float]
    source: str


PROFILES = {
    "tde-70-15-15": AssessmentProfile(
        id="tde-70-15-15",
        title="Türk Dili ve Edebiyatı sınav puanı",
        course_names=("Türk Dili ve Edebiyatı",),
        weights={WRITTEN: 0.70, LISTENING: 0.15, SPEAKING: 0.15},
        source="MEB Yazılı ve Uygulamalı Sınavlar Yönergesi md. 6/2-d",
    ),
    "language-50-25-25": AssessmentProfile(
        id="language-50-25-25",
        title="Türkçe ve yabancı dil sınav puanı",
        course_names=(
            "Türkçe",
            "Yabancı Dil",
            "Birinci Yabancı Dil",
            "İkinci Yabancı Dil",
            "İngilizce",
            "Almanca",
            "Fransızca",
            "Arapça",
            "Mesleki Arapça",
            "Rusça",
            "İspanyolca",
            "İtalyanca",
            "Çince",
            "Japonca",
            "Farsça",
        ),
        weights={WRITTEN: 0.50, LISTENING: 0.25, SPEAKING: 0.25},
        source="MEB Yazılı ve Uygulamalı Sınavlar Yönergesi md. 6/2-ç",
    ),
}


def _normalized_course_name(course_name: str) -> str:
    value = unicodedata.normalize("NFKC", str(course_name or "")).casefold().strip()
    return " ".join(value.split())


def profile_for_course(course_name: str) -> AssessmentProfile | None:
    """Resolve only explicitly registered language courses to a weighting profile."""

    normalized = _normalized_course_name(course_name)
    if not normalized:
        return None

    tde_names = {
        _normalized_course_name("Türk Dili ve Edebiyatı"),
        _normalized_course_name("Seçmeli Türk Dili ve Edebiyatı"),
    }
    if normalized in tde_names:
        return PROFILES["tde-70-15-15"]

    language_profile = PROFILES["language-50-25-25"]
    if normalized in {_normalized_course_name(name) for name in language_profile.course_names}:
        return language_profile
    return None

COMPONENT_LABELS = {
    WRITTEN: "Yazılı Sınav",
    LISTENING: "Dinleme/İzleme Sınavı",
    SPEAKING: "Konuşma Sınavı",
}


def calculate_composite_scores(
    profile_id: str, components: dict[str, dict[str, float]]
) -> dict[str, Any]:
    """Return student and class composite scores for a complete component set."""

    profile = PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"Bilinmeyen değerlendirme ağırlık profili: {profile_id}")

    missing = [key for key in profile.weights if key not in components]
    if missing:
        return {
            "profileId": profile.id,
            "profileTitle": profile.title,
            "complete": False,
            "missingComponents": missing,
            "missingComponentLabels": [COMPONENT_LABELS[key] for key in missing],
            "studentScores": {},
            "classAverage": None,
        }

    student_ids = set.intersection(*(set(components[key]) for key in profile.weights))
    if not student_ids:
        raise ValueError("Bileşenlerde ortak öğrenci kaydı bulunamadı.")

    student_scores = {
        student_id: round(
            sum(float(components[key][student_id]) * weight for key, weight in profile.weights.items()),
            2,
        )
        for student_id in sorted(student_ids)
    }
    return {
        "profileId": profile.id,
        "profileTitle": profile.title,
        "complete": True,
        "weights": profile.weights,
        "missingComponents": [],
        "missingComponentLabels": [],
        "studentScores": student_scores,
        "classAverage": round(sum(student_scores.values()) / len(student_scores), 2),
    }
