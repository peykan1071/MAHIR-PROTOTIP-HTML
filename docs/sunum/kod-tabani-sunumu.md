---
marp: true
theme: gaia
paginate: true
header: 'MAHİR — kod tabanı'
footer: 'Kaynak: docs/architecture/kod-tabani-analizi.md · e4547e5'
math: false
style: |
  section {
    font-size: 25px;
  }
  section.lead h1 { font-size: 56px; }
  code { font-size: 0.82em; }
  pre { font-size: 0.72em; line-height: 1.35; }
  table { font-size: 0.80em; }
  .soru {
    border-left: 6px solid #38bdf8;
    background: rgba(56,189,248,0.10);
    padding: 0.5em 0.9em;
    margin: 0.5em 0;
    border-radius: 4px;
  }
  .patlar {
    border-left: 6px solid #f87171;
    background: rgba(248,113,113,0.12);
    padding: 0.5em 0.9em;
    margin: 0.5em 0;
    border-radius: 4px;
  }
  .iyi {
    border-left: 6px solid #4ade80;
    background: rgba(74,222,128,0.10);
    padding: 0.5em 0.9em;
    margin: 0.5em 0;
    border-radius: 4px;
  }
  .kucuk { font-size: 0.80em; opacity: 0.85; }
  /* Mermaid SVG'si kendi boyutunu dayatıyor; slayt 720px ve taşıyordu.
     max-height + height:auto ile ölçekleniyor. */
  .mermaid { display: flex; justify-content: center; }
  .mermaid svg {
    max-height: 395px !important;
    max-width: 94% !important;
    height: auto !important;
  }
  /* Altında callout olmayan, yalnız diyagram taşıyan slaytlar için */
  section.diyagram .mermaid svg { max-height: 540px !important; }
---

<!-- _class: lead -->

# MAHİR kod tabanı

### ~20.000 satır, 45 dosya, 4 süreç

Mimari · veri akışı · teknik borç

<span class="kucuk">Bu sunum ezber bilgi vermez. Her slayt iki soruya cevap arar.</span>

---

<!-- _class: lead -->

# Bu sunumun iki sorusu

<div class="soru">

**Burada veri nasıl akıyor?**
Hangi bileşen neyi görüyor, neyi göremiyor?

</div>

<div class="patlar">

**Burası patlarsa ne olur?**
Kullanıcı ne görür, ne kaybeder, sistem ayakta kalır mı?

</div>

Bir modülü anlamak, adını bilmek değil; **onu kırdığınızda ne olacağını**
bilmektir.

---

## Ölçek: neyle uğraşıyoruz

| Katman | Satır | Dosya | En büyüğü |
|---|---:|---:|---|
| Ön yüz | ~7.900 | 10 | `script.js` — 4.465 |
| Backend | ~7.000 | 30 | `pipeline.py` — 1.440 |
| RAG yığını | ~3.600 | 4 | `ingestion_pipeline.py` — 1.220 |

<div class="soru">

İki dosya toplam kodun **%38'ini** taşıyor. Bu, sonraki slaytlarda
karşımıza çıkacak her sorunun kök nedeni.

</div>

---

## Sistem tek uygulama değil: dört süreç

| Süreç | Port | Sunucu | Ağır bağımlılık |
|---|---|---|---|
| Web backend | 8000 | `ThreadingHTTPServer` | **yok** |
| RAG servisi | 8001 | FastAPI | torch, sentence-transformers |
| OCR işçisi | 8002 | `ThreadingHTTPServer` | paddle (GPU) |
| llama-server | 8080 | llama.cpp | GGUF (GPU) |

<div class="iyi">

**Bu ayrım bilinçli.** Web backend ML paketlerini **hiç import etmiyor** —
bu yüzden bir model çökmesi öğretmenin arayüzünü düşürmüyor.

</div>

---

## Bileşenler ve güven bölgeleri

<div class="mermaid">
flowchart LR
  subgraph K["Kimlikli veri"]
    UI["Tarayıcı"] --> WEB[":8000<br/>file_receiver"]
    WEB --> OCR[":8002<br/>OCR işçisi"]
  end
  subgraph T["Takma adlı veri"]
    GATE["gizlilik kapısı"] --> ORCH["orchestrator<br/>5 ajan"]
    ORCH --> RAG[":8001<br/>rag_service"]
    RAG --> LLM[":8080<br/>llama-server"]
  end
  UI -->|"Ö-001 + puan"| GATE
  RAG --> IDX[("qdrant_index<br/>gömülü")]
  style K fill:#7f1d1d,color:#fff
  style T fill:#14532d,color:#fff
</div>

<div class="soru">

Kırmızı bölge ad-soyad görür. Yeşil bölge **görmez**. Bu sınır sistemin en
değerli mimari özelliği.

</div>

---

## Sınır nerede kuruluyor? — tarayıcıda

```js
// script.js:5400
students: (approvedData.students || []).map((student, index) => ({
  rowNumber: student.rowNumber,
  studentRef: student.technicalId || `Ö-${String(index + 1).padStart(3, "0")}`,
  scores: student.scores,
  totalScore: student.totalScore
})),
```

Sunucuya giden yükte ad, soyad, okul numarası **yok**. Yalnız satır
numarası, takma referans ve puanlar.

<div class="soru">

Eşleme tablosu nerede? **Yalnız tarayıcıda.** Sunucu hiçbir zaman
`Ö-001 = Ayşe Yılmaz` bilgisine sahip olmuyor.

</div>

---

## Sınır ikinci kez kodda zorlanıyor

```python
# backend/app/approved_data_analyzer.py:259
def _assert_privacy_safe_students(students: Any) -> None:
    """Reject identity-bearing fields at the analysis/LLM boundary."""
    forbidden = {
        "studentNo": "okul numarası",
        "fullName": "ad-soyad",
        "name": "ad-soyad",
        "surname": "soyad",
        "tckn": "T.C. kimlik numarası",
        "sourceFile": "kaynak dosya adı",
    }
```

<div class="iyi">

Bu bir yorum ya da konvansiyon değil — **çalışan bir kapı**. Kimlik alanı
taşıyan yük analiz hattına giremiyor, hata fırlatıyor.

</div>

---

<!-- _class: lead -->

# Akış A
## Evrak yükleme ve OCR

---

## Akış A: veri nasıl akıyor

<div class="mermaid">
sequenceDiagram
  autonumber
  participant T as Tarayıcı
  participant W as :8000
  participant O as :8002 OCR
  T->>W: POST /mahir-upload
  W->>W: doğrulama + tür tespiti
  W->>O: yalnız görselse
  O->>O: GPU · max_workers=1
  O-->>W: structuredData
  W-->>T: structuredData + uyarılar
</div>

<div class="patlar">

**OCR işçisi kapalıysa?** `WinError 10061` → yalnız görsel yükleme düşer.
CSV/Excel akışı çalışmaya devam eder. Zarif bozulma.

</div>

---

## `file_receiver.py` — üç rota, dokuz bağımlılık

**Görevi:** statik sunum + yükleme + analiz + rapor birleştirme.

```python
def do_POST(self) -> None:
    request_path = urlparse(self.path).path
    if request_path == ANALYZE_PATH:      # /mahir-analyze
    if request_path == MERGE_REPORTS_PATH: # /mahir-merge-reports
    if request_path != UPLOAD_PATH:        # /mahir-upload
```

<div class="patlar">

**Patlarsa:** her şey durur — arayüz bile servis edilemez. Tek giriş kapısı.
**Ama:** state tutmuyor, her istek bağımsız. Yeniden başlatmak bedelsiz.

</div>

<span class="kucuk">571 satır · 9 modüle bağımlı · en yoğun değişen dosya</span>

---

## `ocr_engine.py` — GPU'yu tek şeritte tutan hile

```python
def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1,
                                       thread_name_prefix="paddleocr-vl")
    return _executor
```

<div class="iyi">

`ThreadingHTTPServer` eşzamanlı istek kabul ediyor **ama** tüm çıkarım bu
tek şeritten geçiyor. İki öğretmen aynı anda yüklerse GPU'da çakışma yok.

</div>

<div class="patlar">

**Gizli kusur:** `_executor` kurulumu kilitsiz. Teorik olarak iki executor
→ iki pipeline → 6 GB kartta OOM. Açılıştaki ısıtma bunu maskeliyor.

</div>

---

<!-- _class: lead -->

# Akış B
## Analiz turu — sistemin kalbi

---

<!-- _class: diyagram -->

## Akış B: beş ajan, tek LLM isteği

<div class="mermaid">
sequenceDiagram
  autonumber
  participant Or as orchestrator
  participant R as :8001 RAG
  participant L as :8080 LLM
  loop 5 ajan sırayla
    Or->>Or: agent.run → enqueue_prompt
  end
  Or->>R: POST /agents — N prompt TEK istek
  loop her prompt
    R->>R: embed → Qdrant → reranker
    R->>L: chat.completions
  end
  R-->>Or: [{name, answer, sources}]
  Or->>Or: teşhis doğrulaması
</div>

---

## `base.py` — merkezî state: `AgentContext`

```python
@dataclass
class AgentContext:
    payload: dict      # tarayıcıdan gelen ham yük
    ced: CEDDocument   # ortak veri sözleşmesi
    analysis: dict     # öğretmenin göreceği rapor
    scratch: dict      # ajanlar arası ara veri
    llm_queue: list    # promptlar BURAYA yazılır
    llm_results: dict
```

<div class="soru">

**Ajanlar LLM'i doğrudan çağırmıyor.** Promptunu kuyruğa yazıyor,
orkestratör hepsini tek HTTP isteğinde gönderiyor. Neden? Ağ turunu
çoğaltmamak için.

</div>

---

## `pipeline.py` — beş ajan, tek dosya, 1.440 satır

| Ajan | Satır | LLM? |
|---|---:|:-:|
| `DocumentUnderstandingAgent` | 167 | — |
| `ProgramMappingAgent` | 215 | — |
| `MeasurementAgent` | 279 | — |
| `PedagogicalAnalysisAgent` | 417 | ✅ |
| `ReportingAgent` | 672 | ✅ |

<div class="patlar">

**Patlarsa:** orkestratör o ajanı `skipped` işaretler, tur devam eder ama
rapor eksik kalır. **Asıl risk:** 1.440 satırda beş sorumluluk — birini
değiştirirken diğerini bozmak kolay.

</div>

---

## `rag_service.py` — getirim + üretim

```python
# /agents turunda her prompt için:
# 1) bge-m3 ile gömme        (CPU)
# 2) gömülü Qdrant'ta arama  (~6 ms)
# 3) bge-reranker-v2-m3      (CPU, ~8.000 ms)
# 4) llama-server            (GPU)
```

<div class="patlar">

**Darboğaz beklediğiniz yerde değil.** Vektör araması 6 ms; **reranker
8 saniye** ve kilitli olduğu için istemler arasında seri. 11 istemlik
turda tek başına **~88 saniye**.

</div>

---

## En pahalı borç: `/agents` hepsi-ya-hiç

```python
# local/rag_service.py:705
except Exception as error:
    return False, f"Ajan yanıtları üretilemedi: {error}", None
```

Gerçek bir tur kaydı:

```
LLM turu başarısız (... Model boş yanıt döndürdü.)
LLM turu: prompt=11 sonuc=0 sure=249.3s
```

<div class="patlar">

**11 istemden 10'u başarılı olsa bile 249 saniye çöpe gidiyor.** Kusur
modelde değil, **yapıda**: boş yanıt hangi modelden gelirse gelsin tur
tümüyle düşüyor.

</div>

---

## Döngüsel bağımlılık — çözülmemiş, ertelenmiş

```python
# ocr_worker_client.py:20 — MODÜL düzeyinde
from .file_receiver import UploadedFile
```

```python
# file_receiver.py:508 — FONKSİYON içinde saklanmış
from .ocr_worker_client import request_image_group_ocr
```

<div class="patlar">

Döngü kırılmadı, geciktirilmiş import'la **saklandı**. `UploadedFile` bir
veri sınıfı; HTTP sunucu modülünde durmamalı. Klasik "vibe coding" yaması.

</div>

---

## `script.js` — 1.752 satır ölü kod silindi

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Satır | 6.217 | **4.465** |
| Üst düzey IIFE | 8 | **4** |
| `addEventListener` | 68 | 67 |
| `fetch` çağrısı | 5 | 5 |
| En büyük closure | — | `fileUploadBridge` **3.485** |

<div class="patlar">

**Patlarsa:** tek JS hatası tüm arayüzü kilitler — `try/catch` dışında
kalan bir hata oturumu bitirir, öğretmen onayladığı veriyi kaybeder.
Sayfa yenilenirse oturum sıfırlanır.

</div>

---

## Hata yönetimi: genişlik körlük yaratıyor

| Dosya | `except Exception` |
|---|---:|
| `ingestion_pipeline.py` | 12 |
| `rag_service.py` | 8 |
| `orchestrator.py` | 3 |

Üç yerde gövde `pass` / `continue` ile bitiyor.

<div class="soru">

Çoğu bilinçli ve yorumlanmış. Ama `_get_pipeline` içinde bir `ImportError`
ile CUDA OOM **aynı mesaja** düşüyor. Teşhis koyamadığınız hata,
düzeltemediğiniz hatadır.

</div>

---

## Kimlik doğrulama: yok

```python
# file_receiver.py:89
self.send_header("Access-Control-Allow-Origin", "*")
```

Hiçbir serviste kimlik doğrulama yok. Hepsi `127.0.0.1`'e bağlı.

<div class="soru">

**Yerel kullanımda borç değil** — makineye erişen zaten dosyalara da
erişir. Ama bu, sistemi bir ağa ya da buluta taşımayı **bugün imkânsız**
kılıyor. Taşıma kararı verildiği an ilk iş budur.

</div>

---

<!-- _class: lead -->

# Doğru yapılanlar

Eleştiri, ancak neyin sağlam olduğunu da söylerse güvenilir olur.

---

## Beklenenden iyi olan beş şey

<div class="iyi">

**1. Gizlilik kodda zorlanıyor** — yorum değil, çalışan kapı.

**2. Paylaşılan modeller iş parçacığı güvenli** — `CpuEmbedder` ve
reranker `threading.Lock` kullanıyor.

**3. GPU erişimi seri** — `max_workers=1`, yarış durumu yok.

**4. Zarif bozulma** — OCR/RAG kapalıyken CSV akışı çalışıyor.

**5. 365 test** (352 Python + 13 JS) ve gerçekten iyi docstring'ler.

</div>

---

<!-- _class: lead -->

# İlk üç refactor

Sıralama: **etki ÷ risk**

---

## 1) `/agents` kısmi sonuç

**Neden ilk:** tek dosya, ~20 satır, etkisi ölçülebilir, bugün yaşanan
somut hatayı çözüyor.

**Ne yapılmalı:** düşen prompt turu düşürmesin; sonucunda açık hata alanı
taşısın, rapor "teşhis üretilemedi" göstersin.

<div class="patlar">

**Bedeli:** sözleşme değişikliği.
`test_generation_failure_returns_false_with_a_turkish_message` bilinçli
olarak güncellenmeli. Yarım turun arayüzde nasıl görüneceği düşünülmeli.

</div>

---

## 2) `file_receiver.py` ayrıştırması

**Neden ikinci:** döngüyü de çözüyor ve testleri HTTP katmanından
kurtarıyor.

**Ne yapılmalı:**
- `UploadedFile` / `FileCheckResult` → ayrı modül *(döngü kırılır)*
- rota işleyicileri → `upload` / `analyze` / `merge` modülleri
- `file_receiver` yalnız HTTP + yönlendirme kalsın

<div class="soru">

**Bedeli orta.** `ocr_worker.py` de `file_receiver`'dan import ediyor;
o da güncellenmeli.

</div>

---

## 3) `script.js` modüllemesi

**İlk adım yapıldı:** ölü `window.MAHIR` katmanı + çağrılmayan iki
fonksiyon + hiç tetiklenmeyen dört olay dalı → **1.752 satır** gitti,
davranış değişmedi. Çağrısı olmayan kodu silmek risksizdi.

**Kalan iş, en yüksek risk:** `fileUploadBridge` tek closure'da 3.485
satır — 67 olay dinleyici, paylaşılan onlarca değişken, tip yok.

<div class="patlar">

**Bu iş ancak arayüz testleri güçlendirildikten sonra güvenli.** Aksi
hâlde regresyon görünmez kalır — ve bunu fark eden kişi öğretmen olur.

</div>

---

<!-- _class: lead -->

# Kapanış: üç cümle

---

## Akılda kalması gereken

<div class="iyi">

**1.** Sistemin en değerli özelliği kimlik sınırı — `script.js:5400` ile
`approved_data_analyzer.py:259` arasında kurulu ve kod düzeyinde zorlanıyor.
Her mimari kararda korunması gereken şey bu.

</div>

<div class="patlar">

**2.** En pahalı kusur `/agents` hepsi-ya-hiç — 249 saniyelik iş tek boş
yanıtla çöpe gidiyor. Ucuz düzeltme, yüksek etki.

</div>

<div class="soru">

**3.** İki dosya kodun %38'i. Teknik borcun tamamı buradan türüyor;
bölmek, yeni özellik eklemekten önce gelir.

</div>

---

<!-- _class: lead -->

# Sorular

<span class="kucuk">

Ayrıntılı analiz: [`docs/architecture/kod-tabani-analizi.md`](../architecture/kod-tabani-analizi.md)
· satır atıfları `e4547e5` sürümüne göre doğrulanmıştır

</span>

<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
</script>
