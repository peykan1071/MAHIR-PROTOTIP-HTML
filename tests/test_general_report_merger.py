"""Tests for privacy-safe language report merging."""

import base64
import io
import json
import unittest
import zipfile

from backend.app.analysis_report_parser import parse_analysis_report_docx
from backend.app.general_report_merger import merge_component_reports


def report(component: str, average: float, *, course: str = "Türk Dili ve Edebiyatı", section: str = "9/A"):
    return {
        "schema": "mahir.analysis-report",
        "schemaVersion": 1,
        "exam": {
            "courseName": course,
            "academicYear": "2026-2027",
            "term": "1. Dönem",
            "classSection": section,
            "schoolName": "Örnek Anadolu Lisesi",
            "componentType": component,
        },
        "analysis": {
            "componentType": component,
            "summary": {"classAverage": average},
            "outcomes": [
                {
                    "outcomeCode": f"{component}.1",
                    "outcomeDescription": "Örnek öğrenme çıktısı",
                    "outcomeSkill": component,
                    "successRate": average / 100,
                }
            ],
        },
        "privacy": {"scope": "aggregate-class-evidence", "excludedFields": ["students"]},
    }


def docx_with_manifest(payload: dict) -> bytes:
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    xml = f'<mahirReport xmlns="urn:mahir:analysis-report:v1"><payload encoding="base64">{encoded}</payload></mahirReport>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("customXml/mahir-report.xml", xml)
    return output.getvalue()


class GeneralReportMergerTests(unittest.TestCase):
    def test_parser_reads_aggregate_manifest(self):
        payload = report("written", 80)
        parsed = parse_analysis_report_docx(docx_with_manifest(payload))
        self.assertEqual(parsed["exam"]["componentType"], "written")
        self.assertNotIn("students", parsed["analysis"])

    def test_tde_reports_are_merged_with_70_15_15(self):
        exam, analysis = merge_component_reports([
            report("written", 80),
            report("listening", 60),
            report("speaking", 90),
        ])
        self.assertEqual(exam["componentType"], "general")
        self.assertEqual(analysis["classAverage"], 78.5)
        self.assertEqual(analysis["componentResults"]["written"]["weightedContribution"], 56.0)
        self.assertEqual(len(analysis["componentEvidence"]), 3)
        self.assertEqual(analysis["componentEvidence"][1]["realizationRate"], 0.6)
        self.assertEqual(analysis["componentEvidence"][1]["weightedContribution"], 0.09)
        self.assertEqual(analysis["studentScores"], {})

    def test_turkish_reports_use_50_25_25(self):
        _exam, analysis = merge_component_reports([
            report("written", 80, course="Türkçe"),
            report("listening", 60, course="Türkçe"),
            report("speaking", 90, course="Türkçe"),
        ])
        self.assertEqual(analysis["classAverage"], 77.5)

    def test_mismatched_class_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "sınıf/şube"):
            merge_component_reports([
                report("written", 80),
                report("listening", 60, section="9/B"),
                report("speaking", 90),
            ])

    def test_selected_course_must_match_reports(self):
        with self.assertRaisesRegex(ValueError, "seçilen ders"):
            merge_component_reports([
                report("written", 80),
                report("listening", 60),
                report("speaking", 90),
            ], expected_course="Türkçe")

    def test_duplicate_component_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "birden fazla"):
            merge_component_reports([
                report("written", 80),
                report("written", 60),
                report("speaking", 90),
            ])

    def test_non_language_course_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "yalnız"):
            merge_component_reports([
                report("written", 80, course="Fen Bilimleri"),
                report("listening", 60, course="Fen Bilimleri"),
                report("speaking", 90, course="Fen Bilimleri"),
            ])


if __name__ == "__main__":
    unittest.main()
