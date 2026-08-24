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
GENERAL = "general"


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


def _normalized_course_name(course_name: object) -> str:
    value = unicodedata.normalize("NFKC", str(course_name or "")).translate(
        str.maketrans({"I": "ı", "İ": "i"})
    )
    value = value.casefold().strip()
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
    GENERAL: "Genel Değerlendirme",
}

REQUIRED_COMPONENTS = (WRITTEN, LISTENING, SPEAKING)


def build_general_evaluation(
    profile_id: str, component_analyses: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Combine three language components without reducing evidence to one score."""

    profile = PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"Bilinmeyen değerlendirme ağırlık profili: {profile_id}")
    missing = [key for key in REQUIRED_COMPONENTS if key not in component_analyses]
    if missing:
        return {
            "assessmentScope": "language-composite",
            "complete": False,
            "missingComponents": missing,
            "missingComponentLabels": [COMPONENT_LABELS[key] for key in missing],
            "notice": "Genel değerlendirme, tüm bileşenlere ait öğrenme kanıtları tamamlandığında kesinleştirilebilir.",
        }

    component_scores: dict[str, dict[str, float]] = {}
    component_results: dict[str, dict[str, float | str]] = {}
    skill_evidence: list[dict[str, Any]] = []
    for component in REQUIRED_COMPONENTS:
        analysis = component_analyses[component]
        students = analysis.get("cohortEvidence") or analysis.get("students") or []
        component_scores[component] = {
            str(student.get("studentRef")): float(student.get("calculatedTotal", 0))
            for student in students
            if student.get("studentRef") not in (None, "")
        }
        raw_average = (analysis.get("summary") or {}).get("classAverage")
        if raw_average in (None, "") and component_scores[component]:
            raw_average = sum(component_scores[component].values()) / len(component_scores[component])
        try:
            class_average = float(raw_average)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{COMPONENT_LABELS[component]} raporunda sınıf ortalaması bulunamadı.") from error
        weight = profile.weights[component]
        component_results[component] = {
            "componentType": component,
            "componentLabel": COMPONENT_LABELS[component],
            "classAverage": round(class_average, 2),
            "weight": weight,
            "weightedContribution": round(class_average * weight, 2),
            "maximumContribution": round(100 * weight, 2),
        }
        for outcome in analysis.get("outcomes") or []:
            realization_rate = float(outcome.get("realizationRate", outcome.get("successRate", 0.0)))
            skill_evidence.append(
                {
                    "componentType": component,
                    "componentLabel": COMPONENT_LABELS[component],
                    "learningOutcomeCode": outcome.get("outcomeCode", ""),
                    "learningOutcomeTheme": outcome.get("outcomeTheme", ""),
                    "learningOutcomeDescription": outcome.get("outcomeDescription", ""),
                    "fieldSkill": outcome.get("outcomeSkill", ""),
                    "realizationRate": realization_rate,
                    "componentWeight": weight,
                    "weightedContribution": round(realization_rate * weight, 4),
                    "developmentLevel": outcome.get("developmentLevel", outcome.get("category", "")),
                    "decision": outcome.get("decision", ""),
                    "ragContext": outcome.get("ragContext", ""),
                    "ragSources": outcome.get("ragSources", []),
                }
            )

    weighted_class_average = round(
        sum(float(item["weightedContribution"]) for item in component_results.values()), 2
    )
    has_student_scores = all(component_scores[component] for component in REQUIRED_COMPONENTS)
    if has_student_scores:
        reference_students = set(component_scores[REQUIRED_COMPONENTS[0]])
        if any(set(component_scores[component]) != reference_students for component in REQUIRED_COMPONENTS[1:]):
            raise ValueError(
                "Yüklenen raporlar aynı öğrenci grubuna ait değildir; takma öğrenci kodları "
                "ve katılımcı sayıları birbiriyle uyuşmalıdır."
            )
    composite = calculate_composite_scores(profile_id, component_scores) if has_student_scores else {
        "profileId": profile.id,
        "profileTitle": profile.title,
        "complete": True,
        "weights": profile.weights,
        "missingComponents": [],
        "missingComponentLabels": [],
        "studentScores": {},
        "classAverage": weighted_class_average,
    }
    return {
        **composite,
        "assessmentScope": "language-composite",
        "summary": {
            "classAverage": composite["classAverage"],
            "classSuccessRate": composite["classAverage"] / 100,
            "componentCount": len(REQUIRED_COMPONENTS),
            "participatingStudentCount": len(composite.get("studentScores") or {}),
        },
        "componentResults": component_results,
        "componentEvidence": skill_evidence,
        "outcomes": [
            {
                "outcomeCode": item["learningOutcomeCode"],
                "outcomeTheme": item["learningOutcomeTheme"],
                "outcomeDescription": item["learningOutcomeDescription"],
                "outcomeSkill": item["fieldSkill"],
                "successRate": item["realizationRate"],
                "category": item["developmentLevel"],
                "decision": item["decision"],
                "componentType": item["componentType"],
                "componentLabel": item["componentLabel"],
                "componentWeight": item["componentWeight"],
                "weightedContribution": item["weightedContribution"],
                "ragContext": item["ragContext"],
                "ragSources": item["ragSources"],
            }
            for item in skill_evidence
        ],
        "questions": [],
        "notice": (
            "Aynı öğrenci grubuna ait yazılı, dinleme/izleme ve konuşma puanları öğrenci "
            "bazında belirlenen ağırlıklarla birleştirilmiş; sınıf ortalaması bu birleşik "
            "puanlardan hesaplanmıştır. Öğrenme kanıtları her bileşenin kendi bağlamında korunur."
        ),
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

