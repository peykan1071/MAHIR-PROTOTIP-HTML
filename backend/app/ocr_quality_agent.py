"""Belge türü, OCR gereksinimi ve okuma kalitesi için deterministik ajan.

Bu ajan bir dil modeli kullanmaz. Dosya biçimine göre OCR'nin gerekip
gerekmediğine karar verir; okuma sonrasında eksik satır, boş hücre, toplam
uyuşmazlığı ve kişisel veri bulgularını öğretmen kontrolüne taşır. OCR motoru
yalnız görüntüden metin çıkarır; bu ajan çıkarımı doğrulanmış veri saymaz.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


AGENT_ID = "belge-okuma-ocr-kalite"
AGENT_LABEL = "Belge Okuma ve OCR Kalite Ajanı"
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
NATIVE_TABLE_EXTENSIONS = {".docx", ".xlsx"}


@dataclass(frozen=True)
class OCRDecision:
    input_kind: str
    ocr_required: bool
    ocr_available: bool
    reason: str


def inspect_upload(uploaded_files: Sequence[object], file_checks: Sequence[object]) -> OCRDecision:
    """Dosya grubunu sınıflandır ve OCR yönlendirme kararını üret."""

    extensions = [str(getattr(item, "extension", "")).lower() for item in file_checks]
    if extensions and all(extension in IMAGE_EXTENSIONS for extension in extensions):
        return OCRDecision(
            input_kind="image-group",
            ocr_required=True,
            ocr_available=True,
            reason="Görüntü dosyalarındaki puan tablosu yalnız OCR ile okunabilir.",
        )

    if len(extensions) == 1 and extensions[0] in NATIVE_TABLE_EXTENSIONS:
        return OCRDecision(
            input_kind="native-table-document",
            ocr_required=False,
            ocr_available=True,
            reason="Belge, tablo yapısı doğrudan okunabildiği için OCR kullanılmaz.",
        )

    if len(extensions) == 1 and extensions[0] == ".pdf":
        content = bytes(getattr(uploaded_files[0], "content", b""))
        if _pdf_has_extractable_text(content):
            return OCRDecision(
                input_kind="text-pdf",
                ocr_required=False,
                ocr_available=True,
                reason="PDF metin katmanı içerdiği için doğrudan okunur; OCR kullanılmaz.",
            )
        return OCRDecision(
            input_kind="scanned-pdf",
            ocr_required=True,
            ocr_available=False,
            reason=(
                "PDF'de kullanılabilir metin katmanı bulunamadı. Taranmış PDF sayfaları "
                "mevcut prototipte otomatik OCR'a dönüştürülmez; öğretmen doğrulaması gerekir."
            ),
        )

    return OCRDecision(
        input_kind="other-document",
        ocr_required=False,
        ocr_available=True,
        reason="Dosya doğrudan belge okuyucusuna veya öğretmen kontrolüne yönlendirilir.",
    )


def assess_result(
    decision: OCRDecision,
    structured_data: Mapping[str, object] | None,
    *,
    flow_ok: bool,
    expected_file_count: int,
) -> dict[str, object]:
    """Okuma çıktısının kullanılabilirliğini kanıtlanabilir kontrollerle değerlendir."""

    data = structured_data or {}
    students = list(data.get("students") or [])
    warnings = [str(item) for item in (data.get("warnings") or [])]
    issues: list[dict[str, str]] = []

    if not flow_ok:
        issues.append(_issue("READING_FAILED", "Belge okuma işlemi tamamlanamadı.", "error"))
    if decision.ocr_required and not decision.ocr_available:
        issues.append(_issue("OCR_ROUTE_UNAVAILABLE", decision.reason, "error"))
    if decision.ocr_required and not students:
        issues.append(
            _issue(
                "NO_OCR_ROWS",
                "OCR sonucunda doğrulanabilir öğrenci satırı elde edilemedi; bilgiler elle tamamlanmalıdır.",
                "error",
            )
        )
    if decision.input_kind == "image-group" and len(students) < expected_file_count:
        issues.append(
            _issue(
                "MISSING_IMAGE_ROWS",
                f"{expected_file_count} görselden {len(students)} öğrenci satırı okunabildi.",
                "warning",
            )
        )

    empty_score_cells = 0
    total_mismatches = 0
    privacy_findings: set[str] = set()
    for student in students:
        if not isinstance(student, Mapping):
            continue
        scores = list(student.get("scores") or [])
        empty_score_cells += sum(score is None or str(score).strip() == "" for score in scores)
        supplied_total = _number(student.get("totalScore"))
        calculated_total = _number(student.get("calculatedTotal"))
        if supplied_total is not None and calculated_total is not None and abs(supplied_total - calculated_total) > 0.01:
            total_mismatches += 1
        privacy_findings.update(str(item) for item in (student.get("privacyFindings") or []))

    if empty_score_cells:
        issues.append(
            _issue(
                "EMPTY_SCORE_CELLS",
                f"{empty_score_cells} soru puanı hücresi okunamadı; öğretmen tarafından tamamlanmalıdır.",
                "warning",
            )
        )
    if total_mismatches:
        issues.append(
            _issue(
                "TOTAL_MISMATCH",
                f"{total_mismatches} öğrenci satırında yazılı toplam ile soru puanları toplamı uyuşmuyor.",
                "warning",
            )
        )
    if privacy_findings:
        issues.append(
            _issue(
                "PRIVACY_DATA_REMOVED",
                "OCR sınırında kişisel veri alanı algılandı ve analiz verisinden çıkarıldı: "
                + ", ".join(sorted(privacy_findings)),
                "warning",
            )
        )
    if warnings:
        issues.append(
            _issue(
                "PARSER_WARNINGS",
                f"Belge okuyucu {len(warnings)} uyarı üretti; öğretmen kontrol ekranında gösterildi.",
                "info",
            )
        )

    has_blocker = any(issue["severity"] == "error" for issue in issues)
    has_warning = any(issue["severity"] == "warning" for issue in issues)
    if has_blocker:
        quality_status = "manual-completion-required"
    elif has_warning:
        quality_status = "teacher-review-required"
    else:
        quality_status = "ready-for-teacher-review"

    return {
        "agentId": AGENT_ID,
        "agentLabel": AGENT_LABEL,
        "llmUsed": False,
        "inputKind": decision.input_kind,
        "ocrRequired": decision.ocr_required,
        "ocrUsed": bool(decision.ocr_required and decision.ocr_available and flow_ok),
        "decisionReason": decision.reason,
        "qualityStatus": quality_status,
        # OCR çıktısı hiçbir durumda kendiliğinden onaylanmaz.
        "teacherReviewRequired": True,
        "checks": {
            "uploadedFileCount": expected_file_count,
            "readStudentRowCount": len(students),
            "emptyScoreCellCount": empty_score_cells,
            "totalMismatchCount": total_mismatches,
            "privacyFindingCount": len(privacy_findings),
        },
        "issues": issues,
    }


def warning_messages(quality: Mapping[str, object]) -> list[str]:
    """Ajan bulgularını mevcut öğretmen uyarı listesine dönüştür."""

    messages = []
    for issue in quality.get("issues") or []:
        if isinstance(issue, Mapping) and issue.get("severity") in {"warning", "error"}:
            messages.append(f"{AGENT_LABEL}: {issue.get('message')}")
    return messages


def _pdf_has_extractable_text(content: bytes) -> bool:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        text = "".join((page.extract_text() or "") for page in reader.pages[:3])
        return len("".join(text.split())) >= 40
    except Exception:  # Bozuk/şifreli PDF, öğretmen kontrolüne düşmelidir.
        return False


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _issue(code: str, message: str, severity: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}
