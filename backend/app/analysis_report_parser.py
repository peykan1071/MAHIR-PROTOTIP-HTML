"""Read privacy-safe structured evidence embedded in MAHIR Word reports."""

from __future__ import annotations

import base64
import json
import zipfile
from io import BytesIO
from typing import Any
import unicodedata
from xml.etree import ElementTree


MANIFEST_PATH = "customXml/mahir-report.xml"
MAX_MANIFEST_SIZE = 2 * 1024 * 1024


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character)).strip()
    return " ".join(text.split())


def _repair_legacy_component_type(payload: dict[str, Any]) -> None:
    """Repair manifests whose exporter persisted a stale written component."""

    analysis = payload.get("analysis") or {}
    exam = payload.get("exam") or {}
    skills = {
        _normalize(outcome.get("outcomeSkill"))
        for outcome in analysis.get("outcomes") or []
        if isinstance(outcome, dict) and _normalize(outcome.get("outcomeSkill"))
    }
    if skills and skills <= {"dinleme/izleme", "dinleme", "izleme"}:
        component, label = "listening", "Dinleme/İzleme Sınavı"
    elif skills and skills <= {"konusma"}:
        component, label = "speaking", "Konuşma Sınavı"
    elif skills and skills <= {"okuma", "yazma"}:
        component, label = "written", "Yazılı Sınav"
    else:
        return
    analysis["componentType"] = component
    exam["componentType"] = component
    exam["examType"] = label


def parse_analysis_report_docx(content: bytes) -> dict[str, Any]:
    """Return the aggregate MAHIR report manifest stored in a DOCX package."""

    try:
        with zipfile.ZipFile(BytesIO(content)) as package:
            if package.getinfo(MANIFEST_PATH).file_size > MAX_MANIFEST_SIZE:
                raise ValueError("MAHİR rapor veri bölümü izin verilen boyutu aşıyor.")
            raw_xml = package.read(MANIFEST_PATH)
    except ValueError:
        raise
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            "Bu belge birleştirilebilir MAHİR analiz raporu değildir. "
            "Raporu güncel MAHİR sürümünden Word olarak yeniden indiriniz."
        ) from error

    if len(raw_xml) > MAX_MANIFEST_SIZE:
        raise ValueError("MAHİR rapor veri bölümü izin verilen boyutu aşıyor.")

    try:
        root = ElementTree.fromstring(raw_xml)
        payload_node = next(node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "payload")
        encoded = "".join(payload_node.itertext()).strip()
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ElementTree.ParseError, StopIteration, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MAHİR analiz raporunun yapılandırılmış veri bölümü okunamadı.") from error

    if payload.get("schema") != "mahir.analysis-report" or payload.get("schemaVersion") != 1:
        raise ValueError("MAHİR analiz raporunun veri sürümü desteklenmiyor.")
    if not isinstance(payload.get("exam"), dict) or not isinstance(payload.get("analysis"), dict):
        raise ValueError("MAHİR analiz raporunda sınav bağlamı veya analiz verisi eksik.")
    if "students" in payload["analysis"]:
        raise ValueError("Rapor, genel değerlendirme için gerekli veri minimizasyonu koşulunu sağlamıyor.")
    _repair_legacy_component_type(payload)
    return payload
