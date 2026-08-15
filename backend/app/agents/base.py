"""Ajan sözleşmesi: her ajanın uyduğu protokol, taşıdığı bağlam ve bıraktığı iz.

Bir ajanı "ajan" yapan şey burada tanımlı üç şey: (1) adreslenebilir bir birim
olması (`name`), (2) ortak veri sözleşmesi üzerinden devralıp devretmesi
(`AgentContext.ced`), (3) ne yaptığını kanıtlayan bir iz bırakması
(`AgentTrace`). Üçü olmadan elde kalan şey birbirini çağıran fonksiyonlardır.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from ..models import CEDDocument


@dataclass(slots=True)
class AgentIssue:
    """Ajanın fark ettiği, işi durdurmayan bir durum.

    Öğretmene gösterilebilir olmalı: teknik yığın izi değil, Türkçe cümle.
    `severity` `CEDValidationIssue` ile aynı sözlüğü kullanır ("info",
    "warning", "error") - böylece ajan bulguları CED doğrulama bulgularıyla
    aynı yerde toplanabilir.
    """

    agent: str
    code: str
    message: str
    severity: str = "info"


@dataclass(slots=True)
class AgentTrace:
    """Bir ajanın çalışmasının kaydı - "bu sonucu kim, neden üretti"nin cevabı.

    MAHİR'in açıklanabilirlik iddiasının ajan yarısı budur; veri yarısı
    (`evidence`, bir oranın hangi sorulardan geldiği) zaten öğrenme çıktısı
    sonuçlarında taşınıyor.

    GİZLİLİK: `inputs`/`outputs` yalnız SAYIM ve ÖZET taşır, asla öğrenci
    satırı taşımaz. Analiz katmanı kimlik alanlarını zaten reddediyor
    (`approved_data_analyzer._assert_privacy_safe_students`); iz, o kapının
    arkasına sızıntı açan bir yan kapı olmamalı.
    """

    agent: str
    duration_ms: float = 0.0
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    issues: list[AgentIssue] = field(default_factory=list)
    # Faz 1'de hep boş; LLM destekli ajanlar geldiğinde her çağrının kaydı
    # (hangi prompt, kaç token, ne kadar sürdü) buraya düşecek.
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    failed: bool = False
    # Kendinden önceki ZORUNLU bir ajan düştüğü için hiç çalışmadı.
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentResult:
    """Ajanın orkestratöre bildirdiği sonuç.

    Ajan `context`i yerinde günceller (CED tek yazarlı, sıralı devrediliyor);
    burada dönen şey yalnız o çalışmanın kaydı - orkestratör bunu süreyle
    birleştirip `AgentTrace` üretir.
    """

    outputs: dict[str, Any] = field(default_factory=dict)
    issues: list[AgentIssue] = field(default_factory=list)


@dataclass(slots=True)
class AgentContext:
    """Ajanlar arasında devredilen durum.

    `ced` ortak veri sözleşmesi; `analysis` ise öğretmenin gördüğü rapor
    sözleşmesi (`/mahir-analyze` yanıtı). İkisi ayrı tutuluyor çünkü CED
    belgeyi tarif eder, `analysis` ise ondan türetilen değerlendirmeyi -
    ve tarayıcı sözleşmesi CED'den bağımsız evrilebilmeli.
    """

    payload: dict[str, Any]
    ced: CEDDocument
    analysis: dict[str, Any] = field(default_factory=dict)
    trace: list[AgentTrace] = field(default_factory=list)
    issues: list[AgentIssue] = field(default_factory=list)
    # Ajanların birbirine ilettiği, CED'e ait olmayan ara veri (ör. çözümlenen
    # program profili). CED'i tarayıcıya özgü alanlarla kirletmemek için ayrı.
    scratch: dict[str, Any] = field(default_factory=dict)

    def trace_for(self, agent_name: str) -> AgentTrace | None:
        for entry in self.trace:
            if entry.agent == agent_name:
                return entry
        return None


class Agent(Protocol):
    """Beş uzman ajanın uyduğu protokol.

    `required`, bir ajanın arızasının ne anlama geldiğini belirler ve bu ayrım
    tasarımın en önemli parçası:

    - **Zorunlu** ajan düşerse analiz güvenilmezdir (sayılar yoksa ya da yanlışsa)
      ve öğretmene yarım bir rapor göstermek hatadan daha kötüdür - orkestratör
      durur, kalan ajanlar `skipped` işaretlenir, istisna yukarı çıkar.
    - **İsteğe bağlı** ajan düşerse rapor zenginliğini kaybeder ama geçerli
      kalır - hat devam eder, eksik kısım boş görünür. Bu, depodaki mevcut
      ilkenin aynısı (bkz. `_attach_rag_context`: RAG arızası `ragContext`i boş
      bırakır, analizi kesmez).
    """

    name: str
    description: str
    required: bool

    def run(self, context: AgentContext) -> AgentResult: ...
