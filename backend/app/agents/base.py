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
    # Öğretmene gösterilen ad ve görev cümlesi. Ajanın kendisinden kopyalanıyor
    # (bkz. `orchestrator._execute`) çünkü tarayıcıda slug -> ad sözlüğü tutmak
    # ikinci bir doğruluk kaynağı yaratırdı: yeni bir ajan eklendiğinde iki
    # yerden birini güncellemeyi unutmak sessizce yanlış etiket gösterirdi.
    label: str = ""
    description: str = ""
    duration_ms: float = 0.0
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    issues: list[AgentIssue] = field(default_factory=list)
    # LLM turundan dönen kayıtlar (bkz. `agents/llm.py::trace_entry`): yalnız
    # sayım ve süre, prompt/yanıt METNİ yok. LLM kullanmayan üç ajanda boş.
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    failed: bool = False
    # Kendinden önceki ZORUNLU bir ajan düştüğü için hiç çalışmadı.
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_wire(self) -> dict[str, Any]:
        """Tarayıcıya giden biçim (camelCase, `/mahir-analyze` yanıtındaki `trace`).

        `to_dict`ten ayrı: o `asdict` üzerinden snake_case üretiyor ve testler
        ona bağlı; tarayıcı sözleşmesi ise depodaki diğer alanlarla aynı dilde
        olmalı. `inputs` bilerek dışarıda - bugün hep boş, göndermek yalnız
        gürültü olurdu.

        GİZLİLİK: taşınan her şey sayım (`outputs`) veya öğretmene gösterilebilir
        Türkçe cümle (`issues`); öğrenci satırı yapısal olarak giremiyor
        (bkz. `tests/test_agent_pipeline.py::test_trace_carries_no_student_rows`).
        """

        return {
            "agent": self.agent,
            "label": self.label or self.agent,
            "description": self.description,
            "durationMs": round(self.duration_ms, 1),
            "outputs": dict(self.outputs),
            "issues": [asdict(issue) for issue in self.issues],
            "llmCalls": list(self.llm_calls),
            "failed": self.failed,
            "skipped": self.skipped,
        }


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
    # LLM kuyruğu: ajanlar doğrudan çağırmak yerine prompt'larını buraya yazar,
    # orkestratör hepsini TEK istekte gönderir. Ajan başına ayrı HTTP turu
    # atsaydık her yeni LLM'li ajan analize ~3 sn eklerdi ve "ek GPU maliyeti
    # yok" iddiası beş ajanda çökerdi.
    llm_queue: list[dict[str, Any]] = field(default_factory=list)
    llm_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    # LLM turunun kendisinin kaydı. Ajan izlerinden AYRI tutuluyor çünkü tur
    # ortak: dokuz prompt tek istekte çözülüyor ve süreyi ajanlara bölmek
    # uydurma olurdu. Ayrı satır olarak göstermek hem dürüst hem de tek istekli
    # mimarinin kanıtı - bölüştürülseydi o kanıt kaybolurdu.
    llm_round: dict[str, Any] = field(default_factory=dict)

    def enqueue_prompt(self, prompt: dict[str, Any]) -> None:
        self.llm_queue.append(prompt)

    def llm_result(self, name: str) -> dict[str, Any] | None:
        """Kuyruğa verilen `name` ile dönen sonucu getirir (yoksa `None` -
        flush hiç yapılmamış ya da başarısız olmuş olabilir)."""

        return self.llm_results.get(name)

    def trace_for(self, agent_name: str) -> AgentTrace | None:
        for entry in self.trace:
            if entry.agent == agent_name:
                return entry
        return None


def trace_of(context: AgentContext) -> dict[str, Any]:
    """Bağlamın izini `/mahir-analyze` yanıtına konacak biçime çevirir.

    Ajan izinin yanına hat düzeyindeki bulgular da konuyor: bir bulgu tek bir
    ajanın izinde de duruyor ama öğretmene "analiz sırasında şunlar fark edildi"
    diye topluca göstermek için tek bir listeye ihtiyaç var.
    """

    return {
        "agents": [entry.to_wire() for entry in context.trace],
        "issues": [asdict(issue) for issue in context.issues],
        # Ortak LLM turu: kaç prompt, tek istekte mi, ne kadar sürdü. Tur hiç
        # yapılmadıysa boş sözlük.
        "llmRound": dict(context.llm_round),
    }


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
    # `name` adreslenebilir kimlik (slug, log ve eşleştirme için); `label`
    # öğretmenin ekranda gördüğü ad. İkisi ayrı çünkü biri sözleşme, diğeri
    # sunum - slug'ı Türkçeleştirmek log ve prompt eşleştirmesini bozardı.
    label: str
    description: str
    required: bool

    def run(self, context: AgentContext) -> AgentResult: ...

    # --- LLM kullanan ajanlar için isteğe bağlı iki geçiş ---
    # `run` sırasında ajan LLM'i ÇAĞIRMAZ; yalnız `context.enqueue_prompt(...)`
    # ile prompt'unu kuyruğa yazar. Orkestratör tüm ajanlar koştuktan sonra
    # kuyruğu tek istekte gönderir ve sonuçları `apply_llm` ile geri dağıtır.
    # Bu iki metodu uygulamayan ajanlar (bugün üçü) hiç etkilenmez.

    def apply_llm(self, context: AgentContext) -> AgentResult: ...
