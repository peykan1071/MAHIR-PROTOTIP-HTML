"""Read privacy-safe structured evidence embedded in MAHIR Word reports."""

from __future__ import annotations

import base64
import json
import zipfile
from io import BytesIO
from typing import Any
from xml.etree import ElementTree


MANIFEST_PATH = "customXml/mahir-report.xml"
MAX_MANIFEST_SIZE = 2 * 1024 * 1024


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
    return payload
