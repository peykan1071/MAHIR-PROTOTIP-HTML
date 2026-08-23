"""Validate and combine three aggregate language-assessment reports."""

from __future__ import annotations

from typing import Any

from .assessment_profiles import (
    GENERAL,
    REQUIRED_COMPONENTS,
    build_general_evaluation,
    normalize_course_name,
    profile_for_course,
)


REQUIRED_CONTEXT_FIELDS = {
    "courseName": "Ders",
    "academicYear": "Eğitim öğretim yılı",
    "term": "Dönem",
    "classSection": "Sınıf/şube",
    "schoolName": "Okul/kurum",
}


def _class_average(report: dict[str, Any]) -> float:
    value = report.get("analysis", {}).get("summary", {}).get("classAverage")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Raporların birinde sınıf ortalaması bulunamadı.") from error
    if number < 0 or number > 100:
        raise ValueError("Raporların birindeki sınıf ortalaması 0–100 aralığında değildir.")
    return number


def merge_component_reports(
    reports: list[dict[str, Any]], *, expected_course: str = "", expected_grade: str = ""
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate report identity and return general exam context plus analysis."""

    if len(reports) != 3:
        raise ValueError("Genel değerlendirme için üç MAHİR analiz raporu yüklenmelidir.")

    by_component: dict[str, dict[str, Any]] = {}
    for report in reports:
        exam = report["exam"]
        analysis = report["analysis"]
        component = str(analysis.get("componentType") or exam.get("componentType") or "").strip()
        if component not in REQUIRED_COMPONENTS:
            raise ValueError("Her rapor yazılı, dinleme/izleme veya konuşma bileşenlerinden birine ait olmalıdır.")
        if component in by_component:
            raise ValueError(f"{component} bileşenine ait birden fazla rapor yüklendi.")
        by_component[component] = report

    missing = [component for component in REQUIRED_COMPONENTS if component not in by_component]
    if missing:
        raise ValueError("Genel değerlendirme için yazılı, dinleme/izleme ve konuşma raporlarının tamamı gereklidir.")

    reference_exam = by_component[REQUIRED_COMPONENTS[0]]["exam"]
    for field, label in REQUIRED_CONTEXT_FIELDS.items():
        reference_value = normalize_course_name(reference_exam.get(field))
        if not reference_value:
            raise ValueError(f"{label} bilgisi raporlardan birinde bulunmuyor.")
        for component in REQUIRED_COMPONENTS[1:]:
            candidate = normalize_course_name(by_component[component]["exam"].get(field))
            if not candidate:
                raise ValueError(f"{label} bilgisi raporlardan birinde bulunmuyor.")
            if candidate != reference_value:
                raise ValueError(f"Yüklenen raporların {label.lower()} bilgileri birbiriyle uyuşmuyor.")

    course_name = str(reference_exam.get("courseName") or "").strip()
    if expected_course and normalize_course_name(course_name) != normalize_course_name(expected_course):
        raise ValueError("Yüklenen raporların dersi, hazırlık aşamasında seçilen dersle uyuşmuyor.")
    if expected_grade:
        report_grade = "".join(character for character in str(reference_exam.get("classSection") or "") if character.isdigit())
        selected_grade = "".join(character for character in str(expected_grade) if character.isdigit())
        if report_grade and selected_grade and report_grade != selected_grade:
            raise ValueError("Yüklenen raporların sınıf düzeyi, hazırlık aşamasında seçilen sınıfla uyuşmuyor.")
    profile = profile_for_course(course_name)
    if profile is None:
        raise ValueError("Genel rapor birleştirme yalnız Türk Dili ve Edebiyatı, Türkçe ve yabancı dil derslerinde kullanılabilir.")

    component_analyses: dict[str, dict[str, Any]] = {}
    for component, report in by_component.items():
        analysis = dict(report["analysis"])
        analysis.setdefault("summary", {})["classAverage"] = _class_average(report)
        component_analyses[component] = analysis

    general_analysis = build_general_evaluation(profile.id, component_analyses)
    general_exam = {
        **reference_exam,
        "componentType": GENERAL,
        "examType": "Genel Değerlendirme",
        "assessmentScope": "language-composite",
        "weightingProfileId": profile.id,
        "participatingStudentCount": len(general_analysis.get("studentScores") or {}),
    }
    return general_exam, general_analysis
