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


def _skipped_trace(agent) -> AgentTrace:
    """Hiç çalışmamış ajanın izi - etiketiyle birlikte.

    Atlanan ajan da öğretmene gösteriliyor ("Çalıştırılmadı"), yani adının
    çalışanlarla aynı biçimde gelmesi gerekiyor.
    """

    return AgentTrace(
        agent=agent.name,
        label=getattr(agent, "label", "") or agent.name,
        description=getattr(agent, "description", ""),
        skipped=True,
    )


def _execute(agent, context: AgentContext) -> bool:
    """Tek ajanı koşturur, izini yazar; ZORUNLU bir ajan düştüyse True döner.

    `ValueError` bilerek yukarı geçer: o, öğretmenin düzeltmesi gereken veri
    hatasıdır ve sessizce yutulursa öğretmen yanlış veriyle üretilmiş bir
    raporu doğru sanır.
    """

    started = time.perf_counter()
    trace = AgentTrace(
        agent=agent.name,
        label=getattr(agent, "label", "") or agent.name,
        description=getattr(agent, "description", ""),
    )
    try:
        result = agent.run(context)
        trace.outputs = result.outputs
        trace.issues = list(result.issues)
        context.issues.extend(result.issues)
    except ValueError:
        trace.failed = True
        raise
    except Exception as error:  # noqa: BLE001 - isteğe bağlı bir ajanın arızası
        # analizi düşürmemeli; zorunlu olan çağırana bildirilir.
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
        return bool(agent.required)
    else:
        boundary_issues = _validate_boundary(context, agent.name)
        if boundary_issues:
            trace.issues.extend(boundary_issues)
            context.issues.extend(boundary_issues)
        return False
    finally:
        trace.duration_ms = (time.perf_counter() - started) * 1000
        context.trace.append(trace)


def run_pipeline(
    payload: dict[str, Any],
    component_type: str,
    profile_id: str,
) -> AgentContext:
    """Beş ajanı koşturur ve dolu bir `AgentContext` döndürür.

    `component_type` / `profile_id` çağıran tarafta doğrulanmış olarak gelir
    (bkz. `approved_data_analyzer.analyze_approved_data`): bunlar istek
    düzeyinde kararlar, ajanların işi değil.

    Üç aşama:
      1. LLM'den önceki ajanlar koşar; LLM'e ihtiyacı olanlar prompt'larını
         `context.enqueue_prompt` ile kuyruğa yazar - çağırmaz.
      2. Kuyruk TEK istekte gönderilir, sonuçlar `apply_llm` ile sahiplerine
         dağıtılır.
      3. Sonuca bağımlı ajanlar (Raporlama) koşar.

    Raporlama'nın bilerek en sonda olması, LLM sonuçlarının rapora ulaşmasını
    paylaşılan referans tesadüfüne değil, akış sırasına bağlıyor.
    """

    context = AgentContext(payload=payload, ced=_empty_ced())
    context.scratch["componentType"] = component_type
    context.scratch["profileId"] = profile_id

    before_llm = [agent for agent in PIPELINE if not getattr(agent, "after_llm", False)]
    after_llm = [agent for agent in PIPELINE if getattr(agent, "after_llm", False)]

    aborted = False
    for agent in before_llm:
        if aborted:
            # Zorunlu bir ajan düştü: kalanları koşturmak yanıltıcı olurdu
            # (eksik girdiyle üretilmiş bir rapor, rapor yokluğundan kötüdür).
            # Yine de ize yazılıyorlar - "neden çalışmadı" da izlenebilir olmalı.
            context.trace.append(_skipped_trace(agent))
            continue
        aborted = _execute(agent, context)

    if not aborted:
        _flush_llm_queue(context)

    for agent in after_llm:
        if aborted:
            context.trace.append(_skipped_trace(agent))
            continue
        aborted = _execute(agent, context)

    if aborted:
        failed_agent = next(entry.agent for entry in context.trace if entry.failed)
        raise PipelineError(
            f"Analiz tamamlanamadı: '{failed_agent}' adımı başarısız oldu.", context
        )

    return context


def _record_llm_calls(context: AgentContext, results: list[dict[str, Any]]) -> None:
    """Her LLM sonucunun kaydını, prompt'u kuyruğa yazan ajanın izine düşürür.

    Sahiplik prompt'un `agent` alanından okunuyor, adından ÇIKARILMIYOR: anomali
    prompt'unun adı ajan adıyla aynı ama teşhis prompt'ları "pedagoji/..."
    biçiminde ve sahibi "pedagojik-analiz" - ada dayalı bir kural sessizce
    yanlış ajana yazardı.

    Kaydın kendisi `llm.trace_entry`den geliyor ve prompt/yanıt METNİ taşımıyor;
    iz, gizlilik kapısının arkasına açılan bir yan kapı olmamalı.
    """

    from .llm import trace_entry

    owner_by_name = {
        str(item.get("name")): str(item.get("agent") or "")
        for item in context.llm_queue
    }
    for result in results:
        owner = owner_by_name.get(str(result.get("name")))
        trace = context.trace_for(owner) if owner else None
        if trace is not None:
            trace.llm_calls.append(trace_entry(result))


def _flush_llm_queue(context: AgentContext) -> None:
    """Kuyruğa yazılmış TÜM ajan prompt'larını tek istekte gönderir.

    Mevcut iki LLM destekli rolün istemleri burada tek ağ isteğinde
    birleştirilir. Böylece her rol için ayrı uzak servis turu oluşturulmaz.

    Kuyruk boşsa hiç istek atılmaz - kayıtlı olmayan derslerde ve LLM'in
    yapılandırılmadığı ortamlarda bugünkü davranış aynen korunur.

    Asla istisna fırlatmaz: LLM arızası isteğe bağlı zenginleştirmeyi düşürür,
    öğretmenin analizini değil. `apply_llm` her hâlükârda çağrılır ki ajanlar
    "sonuç gelmedi" durumunu kendi sebep koduyla loglayabilsin.
    """

    from ..approved_data_analyzer import MAHIR_RAG_REMOTE_URL

    if context.llm_queue and MAHIR_RAG_REMOTE_URL:
        from .llm import run_agent_prompts

        started = time.perf_counter()
        try:
            ok, message, results = run_agent_prompts(context.llm_queue, MAHIR_RAG_REMOTE_URL)
        except Exception:  # noqa: BLE001 - istemci zaten yutuyor; bu son emniyet.
            _logger.exception("LLM turu istisna verdi")
            ok, message, results = False, "istisna", None

        if ok and results:
            context.llm_results = {str(item.get("name")): item for item in results}
            _record_llm_calls(context, results)
        else:
            _logger.warning("LLM turu başarısız (%s); ajanlar sonuçsuz devam edecek", message)
        elapsed_ms = (time.perf_counter() - started) * 1000
        context.llm_round = {
            "promptCount": len(context.llm_queue),
            "resultCount": len(context.llm_results),
            "durationMs": round(elapsed_ms, 1),
            "ok": bool(ok and results),
        }
        _logger.info(
            "LLM turu: prompt=%d sonuc=%d sure=%.1fs",
            len(context.llm_queue),
            len(context.llm_results),
            elapsed_ms / 1000,
        )
    elif context.llm_queue:
        _logger.info("LLM turu atlandı: sebep=yapilandirilmamis prompt=%d", len(context.llm_queue))

    for agent in PIPELINE:
        apply_llm = getattr(agent, "apply_llm", None)
        if apply_llm is None:
            continue
        trace = context.trace_for(agent.name)
        started = time.perf_counter()
        try:
            result = apply_llm(context)
        except Exception as error:  # noqa: BLE001 - zenginleştirme analizi kesmemeli.
            _logger.exception("Ajan LLM sonucunu işleyemedi: %s", agent.name)
            issue = AgentIssue(
                agent=agent.name,
                code="llm-sonucu-islenemedi",
                message=f"{agent.description} adımının LLM sonucu işlenemedi: {error}",
                severity="error",
            )
            context.issues.append(issue)
            if trace is not None:
                trace.issues.append(issue)
            continue
        if trace is not None and result is not None:
            trace.outputs.update(result.outputs)
            trace.issues.extend(result.issues)
            trace.duration_ms += (time.perf_counter() - started) * 1000
        if result is not None:
            context.issues.extend(result.issues)
