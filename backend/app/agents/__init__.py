"""MAHİR'in çok ajanlı analiz hattı.

`docs/architecture/` altındaki beş ajan şartnamesinin çalışan karşılığı:
Belge Anlama -> Program Eşleştirme -> Ölçme-Değerlendirme -> Pedagojik Analiz
-> Raporlama. Ajanlar ortak veri sözleşmesi olarak Canonical Education
Document'i (`backend/app/models.py`) devreder; orkestratör her devir
sınırında belgeyi doğrular ve iz (trace) biriktirir.

Bu paket kasıtlı olarak yalnız stdlib + mevcut `backend/app` modüllerini
kullanır; ağır/uzak bağımlılıklar (OCR, LLM) ajanların içinde, çağrı anında
import edilir - `ocr_engine.py`nin düzeniyle aynı.
"""

from .base import Agent, AgentContext, AgentIssue, AgentResult, AgentTrace, trace_of
from .orchestrator import PIPELINE, run_pipeline

__all__ = [
    "Agent",
    "AgentContext",
    "AgentIssue",
    "AgentResult",
    "AgentTrace",
    "PIPELINE",
    "run_pipeline",
    "trace_of",
]
