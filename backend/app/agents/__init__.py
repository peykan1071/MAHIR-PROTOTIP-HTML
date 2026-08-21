"""MAHİR'in çok ajanlı analiz hattı.

`docs/architecture/` altındaki beş ajan şartnamesinin çalışan karşılığı:
Belge Anlama -> Program Eşleştirme -> Ölçme-Değerlendirme -> Pedagojik Analiz
-> Raporlama. Ajanlar ortak veri sözleşmesi olarak Canonical Education
Document'i (`backend/app/models.py`) devreder; orkestratör her devir
sınırında belgeyi doğrular ve iz (trace) biriktirir.

Bu paket öğretmen onayından sonra çalışan beş analiz ajanını içerir. Yükleme
öncesindeki Belge Okuma ve OCR Kalite Ajanı `backend/app/ocr_quality_agent.py`
altında ayrı çalışır. Uzak LLM bağımlılığı yalnız ihtiyaç anında çağrılır.
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
