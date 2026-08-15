"""Ajanları sırayla koşturur, her devir sınırında CED'i doğrular, iz biriktirir.

Handoff SIRALI ve CED TEK YAZARLI: her an yalnız bir ajan belgeye yazar.
Paralel koşum bilinçli olarak kapsam dışı - kazanç küçük (hat zaten saniyeler
sürüyor, darboğaz uzak LLM çağrısı), bedeli büyük (aynı belgeye eşzamanlı
yazım).

Arıza yalıtımı: bir ajan istisna fırlatırsa iz `failed` işaretlenir ve KALAN
ajanlar yine çalışır. Sebep, bu depoda tekrarlanan ilke: bir bileşenin arızası
öğretmenin analizini tamamen boş bırakmamalı (bkz. `_attach_rag_context`,
`run_image_group_ocr`). Tek istisna `ValueError`: o, öğretmenin düzeltmesi
gereken veri hatasıdır ve sessizce yutulursa öğretmen yanlış veriyle
üretilmiş bir raporu doğru sanır - bu yüzden yukarı fırlatılır.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..models import CEDDocument, CEDMetadata, CEDAssessment
from .base import Agent, AgentContext, AgentIssue, AgentTrace
from .pipeline import (
    DocumentUnderstandingAgent,
    MeasurementAgent,
    PedagogicalAnalysisAgent,
    ProgramMappingAgent,
    ReportingAgent,
)

_logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Zorunlu bir ajan düştüğünde fırlatılır; kısmi bağlamı da taşır.

    İzi hata nesnesine iliştirmek kasıtlı: arıza ANINDA hangi ajanların
    çalıştığı, hangilerinin atlandığı ve ne ürettikleri, hatanın kendisi kadar
    değerli. Bunu yalnız log'a yazmak, çağıran katmanın (HTTP/rapor) aynı
    bilgiye ulaşmasını imkânsız kılardı.
    """

    def __init__(self, message: str, context: "AgentContext") -> None:
        super().__init__(message)
        self.context = context

# Sıra şartnamedeki devir zinciridir; değiştirilmemeli:
# Belge Anlama -> Program Eşleştirme -> Ölçme -> Pedagojik Analiz -> Raporlama
PIPELINE: tuple[Agent, ...] = (
    DocumentUnderstandingAgent(),
    ProgramMappingAgent(),
    MeasurementAgent(),
    PedagogicalAnalysisAgent(),
    ReportingAgent(),
)


def _empty_ced() -> CEDDocument:
    """Belge Anlama Ajanı çalışmadan önceki yer tutucu CED."""

    return CEDDocument(
        metadata=CEDMetadata(ced_version="1.0", created_at="", source="bootstrap"),
        assessment=CEDAssessment(id="", title="", course=""),
    )


def _validate_boundary(context: AgentContext, agent_name: str) -> list[AgentIssue]:
    """Devir sınırında CED'in kendi içinde tutarlı olduğunu kontrol eder.

    Ucuz ve yapısal kontroller: soru kimlikleri benzersiz mi, her öğrenci
    puanı var olan bir soruya mı bağlı. Pahalı şema doğrulaması
    (`validator.validate_ced_payload`) burada koşulmuyor - her sınırda
    tüm belgeyi dolaşmak, hattı yavaşlatmaktan başka bir şey yapmazdı.
    """

    ced = context.ced
    if not ced.questions:
        return []

    issues: list[AgentIssue] = []
    question_ids = [question.id for question in ced.questions]
    if len(set(question_ids)) != len(question_ids):
        issues.append(AgentIssue(
            agent=agent_name,
            code="ced-yinelenen-soru-kimligi",
            message="Belgede yinelenen soru kimliği bulundu; puan eşleştirmesi güvenilir değil.",
            severity="error",
        ))

    known = set(question_ids)
    for student in ced.student_results:
        unknown = [score.question_id for score in student.question_scores if score.question_id not in known]
        if unknown:
            issues.append(AgentIssue(
                agent=agent_name,
                code="ced-bilinmeyen-soru-referansi",
                message="Bir öğrenci puanı var olmayan bir soruya bağlı; belge tutarsız.",
                severity="error",
            ))
            break

    return issues


def run_pipeline(
    payload: dict[str, Any],
    component_type: str,
    profile_id: str,
) -> AgentContext:
    """Beş ajanı sırayla koşturur ve dolu bir `AgentContext` döndürür.

    `component_type` / `profile_id` çağıran tarafta doğrulanmış olarak gelir
    (bkz. `approved_data_analyzer.analyze_approved_data`): bunlar istek
    düzeyinde kararlar, ajanların işi değil.
    """

    context = AgentContext(payload=payload, ced=_empty_ced())
    context.scratch["componentType"] = component_type
    context.scratch["profileId"] = profile_id

    aborted = False
    for agent in PIPELINE:
        if aborted:
            # Zorunlu bir ajan düştü: kalanları koşturmak yanıltıcı olurdu
            # (eksik girdiyle üretilmiş bir rapor, rapor yokluğundan kötüdür).
            # Yine de ize yazılıyorlar, çünkü "neden çalışmadı" da izlenebilir
            # olmalı.
            context.trace.append(AgentTrace(agent=agent.name, skipped=True))
            continue

        started = time.perf_counter()
        trace = AgentTrace(agent=agent.name)
        try:
            result = agent.run(context)
            trace.outputs = result.outputs
            trace.issues = list(result.issues)
            context.issues.extend(result.issues)
        except ValueError:
            # Öğretmenin düzeltmesi gereken veri hatası - yutulmaz. İz yine de
            # `finally` içinde kaydedilir, böylece hatanın hangi ajanda
            # oluştuğu çağıran tarafta görülebilir.
            trace.failed = True
            raise
        except Exception as error:  # noqa: BLE001 - isteğe bağlı bir ajanın arızası
            # analizi düşürmemeli; zorunlu olan yukarı fırlatılır (aşağıda).
            _logger.exception("Ajan başarısız: %s", agent.name)
            trace.failed = True
            failure = AgentIssue(
                agent=agent.name,
                code="ajan-arizasi",
                message=f"{agent.description} adımı tamamlanamadı: {error}",
                severity="error",
            )
            trace.issues = [failure]
            context.issues.append(failure)
            if agent.required:
                aborted = True
        else:
            boundary_issues = _validate_boundary(context, agent.name)
            if boundary_issues:
                trace.issues.extend(boundary_issues)
                context.issues.extend(boundary_issues)
        finally:
            trace.duration_ms = (time.perf_counter() - started) * 1000
            context.trace.append(trace)

    if aborted:
        failed_agent = next(entry.agent for entry in context.trace if entry.failed)
        raise PipelineError(
            f"Analiz tamamlanamadı: '{failed_agent}' adımı başarısız oldu.", context
        )

    return context
