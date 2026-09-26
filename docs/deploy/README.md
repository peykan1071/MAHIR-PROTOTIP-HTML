# MAHİR uzak dağıtım — sağlayıcıdan bağımsız rehber

GPU katmanı (RAG `:8001`, OCR `:8002`, LLM `:8080`) GPU'lu bir **ana makinede**,
web arayüzü (`:8000`) ayrı bir VPS'te çalışır. Bu belge, ana makinenin hangi
sağlayıcıda olduğundan bağımsız olan her şeyi anlatır. Sağlayıcıya özgü adımlar
kendi dosyalarında:

- [runpod.md](runpod.md) — RunPod (bugünkü hedef)

Yerel çalışma bundan etkilenmez: `MAHIR_BASLAT.cmd` hâlâ her şeyi bu makinede
açar (bkz. kök README, "Yerel mi, bulut mu?").

> **Durum (2026-09-26):** kod tarafı hazır ve sınandı. İmajı GitHub Actions
> derleyip GHCR'a itti (ilk koşu 16 dk, yeşil) ve imaj kimlik bilgisi
> olmadan çekilebiliyor. Güncel etiket:
> `ghcr.io/peykan1071/mahir-gpu:2e01c911aca5d321350462855864add03e98c385`.
> Henüz hiçbir ana makine kurulmadı; ölçüm tablosu ilk kurulumda
> doldurulacak.

## Neden bu biçim

Bu projede RunPod bir kez denendi ve terk edildi — mimari yüzünden değil,
**her düzeltmenin 15-20 dakikalık `docker build + push` gerektirmesi**
yüzünden. Bu düzen tam olarak onu hedefliyor:

| Katman | İçerik | Değişim sıklığı | Maliyeti |
|---|---|---|---|
| İmaj | torch, paddle, docling, llama-server binary'si | `local/requirements.txt` değişince | CI'de ~30-45 dk, gözetimsiz |
| Kalıcı disk `/workspace` | **uygulama kodu** (git), model önbellekleri | her kod değişikliğinde | **~10 sn** |

Kod imaja **girmez**. Döngü: `git pull && scripts/gpu_services.sh restart`.

## Ana makine sözleşmesi

Taşınabilirliğin özü bu tablo. Bunu karşılayan her makine MAHİR'in GPU
katmanını çalıştırabilir; başka hiçbir sağlayıcı özelliğine bağımlılık yok.

| Gereksinim | Değer |
|---|---|
| GPU | NVIDIA, ≥ 12 GB VRAM; 16+ önerilir (tahmini bütçe ~9,1 GB, henüz ölçülmedi) |
| Sürücü | CUDA 12.8'i destekleyen sürücü (r570+) |
| Çalışma zamanı | GPU'lu konteyner: Docker + NVIDIA Container Toolkit, ya da bir konteyner-GPU platformu |
| Kalıcı disk | `/workspace`'e bağlı, ≥ 30 GB (kod + ~13 GB model + log) |
| Ağ | 8001 ve 8002 TCP portları dışarı açık; zaman aşımı 250 sn'den kısa olan bir HTTP vekilinin **arkasında olmamalı** (analiz turu bugün ~250 sn) |
| Ortam değişkenleri | `MAHIR_RAG_SHARED_SECRET`, `MAHIR_OCR_SHARED_SECRET` — zorunlu olan yalnız bunlar |
| SSH (isteğe bağlı) | `22/tcp` + `SSH_PUBLIC_KEY` (ya da sağlayıcının enjekte ettiği `PUBLIC_KEY`). Anahtar yoksa imaj sshd'yi **hiç başlatmaz**; yalnız anahtarla giriş, parola kapalı |
| Kendiliğinden başlatma (isteğe bağlı) | `MAHIR_AUTOSTART=1`: kod kalıcı diskteyse açılışta `gpu_services.sh start` (`git pull` yapılmaz) |
| İmaj | `ghcr.io/peykan1071/mahir-gpu:<git-sha>` — değişmez etiket, `latest` değil |

Parolalar zorunlu: verilmezse uçlar korumasız açılır. Üretmek için
`python -c "import secrets; print(secrets.token_urlsafe(32))"` ya da RunPod'da
`py scripts/runpod_pod.py init-secrets` (değerleri `local/.env.bulut`'a yazar,
ekrana basmaz).

**Parola neyi korur:** OCR işçisinin yükleme ucu ve RAG servisinin `/health`
**dışındaki bütün** rotaları (`/agents`, `/query`, `/retrieve`, `/docs` ve
eklenecek her yeni rota — varsayılan kapalı). Önceki sürüm yalnız `/agents`'ı
koruyordu; `/query` parolasız LLM üretimi çalıştırıyordu ve llama-server tek
yuvada koştuğu için tek bir anonim istemci öğretmenin turunu kilitleyebilirdi.
`/health` açık kalıyor, çünkü `MAHIR_BASLAT.ps1 -Kip bulut` ulaşılabilirliği
oradan yokluyor.

Model önbellek yolları (`HF_HOME`, `XDG_CACHE_HOME`, `PADDLE_PDX_CACHE_HOME`,
`TRITON_CACHE_DIR`) imajın **içinde** `/workspace` altına tanımlı; hiçbir
sağlayıcının panelinde hatırlanmaları gerekmez. `PADDLE_PDX_CACHE_HOME` önceki
runbook'ta eksikti: paddlex önbelleğini HF/XDG'den değil bu değişkenden okuyor
(`paddlex/utils/cache.py:29`), yani PaddleOCR-VL (1,9 GB) her açılışta yeniden
inerdi.

`:8080` (llama-server) **dışarı açılmaz** — ona yalnız aynı makinedeki RAG
servisi konuşur.

## İmaj

İmajı **GitHub Actions derler ve GHCR'a iter**
([.github/workflows/gpu-image.yml](../../.github/workflows/gpu-image.yml)).
Tetik: `Dockerfile`, `local/requirements.txt` ya da `requirements.txt` değişince,
ya da Actions sekmesinden elle (`workflow_dispatch`). Gizli değer gerekmez
(`GITHUB_TOKEN`), depo public olduğu için dakikalar ücretsiz.

İş akışı özeti iki şeyi yazar: ana makinede kullanılacak **`:<git-sha>`
etiketi** ve ana makinenin çekeceği sıkıştırılmış veri miktarı.

**İlk CI koşusu (2026-09-26, run 36232709485) — ölçüldü:**

| | |
|---|---|
| Süre | **16 dk** (derleme + push); dizüstünden push 3,5 saatte düşmüştü |
| Runner'da boş disk (temizlikten sonra) | 110 GB / 145 GB — "disk yetmez" riski boşa çıktı |
| `pip check` kapısı | yalnız beklenen üç paddle satırı ✔ |
| nvidia sürüm doğrulaması | `cudnn 9.10.2.21, cusparselt 0.7.1, nccl 2.27.3` ✔ |
| Digest | `sha256:8c849985d1baf3de2e9ed21a82a6ae907ad69ece0a0833cfa1c5b0bd8896cd5b` |
| Manifest | düz OCI imaj manifesti (indeks değil — `provenance: false` tuttu) |
| Ana makinenin çekeceği | **10,75 GB**, 23 katman; en büyükleri torch 3,47 · paddle 2,98 · CUDA temel 2,06 · hizalama 1,32 GB |
| Erişim | kimlik bilgisi olmadan okunabiliyor (public depodan itildi) |

**Neden geliştirme makinesinden push edilmiyor — ölçüldü (2026-09-25/26).**
Docker Desktop bütün registry trafiğini VM vekilinden (`192.168.65.1:3128`)
geçiriyor. 29,4 GB'lık imajın push'u iki denemede, toplam ~3,5 saatte, ikisinde
de **aynı** blobda düştü: `nvidia/cuda` temel imajının 2.058 MB'lık katmanı.
Bu makineden yüklenebilmiş en büyük blob 64,3 MB. Katmanları bölmek de
çözmezdi — takılan katman temel imajın katmanı.

**Temel imajlar digest ile sabit.** Aylar sonraki bir rebuild doğrulanmış
bitleri üretsin diye. `llama.cpp:server-cuda` her gece değişen bir etiket;
ayrıca doğrulanan build 11176'nın GitHub sürüm sayfası birkaç gün içinde
kalkmıştı ("release not found"), yani o binary'nin kalıcı tek kopyası imaj.
**Yükseltme:** Dockerfile'daki digest'i değiştir → CI → yeni imajı yerelde
`scripts/verify_gpu_image.sh` ile sına.

**İmaj kendi kilidini taşır:** `/opt/mahir-venv/freeze.txt`. İki kullanımı var:

- **Kayma teşhisi:** aralıklı pinler (docling, transformers…) iki CI build'i
  arasında farklı çözülebilir. İki imajın `freeze.txt`'i `diff` ile karşılaştırılır.
- **Docker'sız bir makineye taşınma:** `pip install --no-deps -r freeze.txt`.
  `--no-deps` şart; aksi hâlde paddle'ın üç nvidia pini çözümlemeyi yeniden kırar.

**Kayma gerçekten oluyor — ölçüldü.** Yerel build (2026-09-25) ile ilk CI build'i
(2026-09-26) arasında, **bir günde**, 188 paketten biri kaydı:
`docling-parse 7.21.0 → 7.22.0` (`docling>=2.127,<3` aralığından geçişli).
Etkisi yok: `docling` yalnız çevrim dışı indeksleme aracında
(`local/ingestion_pipeline.py`) import ediliyor; ana makinedeki servisler
depoyla gelen hazır Qdrant indeksini kullanıyor. Ama aynı mekanizma bir gün
çalışma anındaki bir paketi de kaydırabilir — bu yüzden ana makine `latest`
değil değişmez `:<git-sha>` etiketini kullanır ve her yeni imaj
`verify_gpu_image.sh`'ten geçer.

**CI imajının yerelde doğrulanması (2026-09-26):** imaj bu makineye kimlik
bilgisi olmadan ~20 dakikada indi (digest CI'nin ittiğiyle aynı) ve
`verify_gpu_image.sh` **6/6** geçti: llama-server yine build 11176 (digest
sabitlemesi tuttu), torch ve paddle cuDNN 91002, `run_check` ve Triton tamam.
Dört önbellek değişkeni imajda tanımlı. Yani pod'un koşturacağı eser,
yerelde doğrulananla aynı.

## Yeni bir ana makinede kurulum

Sözleşme karşılandıktan sonra, makinenin içinde:

```bash
cd /workspace
git clone https://github.com/peykan1071/MAHIR-PROTOTIP-HTML.git
cd MAHIR-PROTOTIP-HTML
git checkout migrate-runpod            # birleştirilene kadar

scripts/verify_gpu_image.sh            # 1) önce DOĞRULA - altısı da geçmeli
scripts/gpu_services.sh start          # 2) sonra başlat
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
```

`.env` gerekmez: gereken her şey sözleşmedeki iki parola, imajın ortam
değişkenleri ve `gpu_services.sh`'in varsayılanlarından geliyor. Modeller ilk
koşuda iner (~13 GB, tek seferlik; kalıcı diskte kalır). `MAHIR_AUTOSTART=1`
verilmişse sonraki açılışlarda servisler kendiliğinden kalkar
(`scripts/image_start.sh`); ilk açılışta kod henüz olmadığı için atlanır.

`/health`'te `"ok": true` ve `reranker.device == "cuda"` görülmeli. `cuda`
yerine `cpu` yazıyorsa asıl gecikme kazancı kaçıyor demektir.

**SSH oturumları konteyner ortamını görür.** sshd oturumu Docker ortamından
değil sıfırdan kuruyor (ilk RunPod pod'unda ölçüldü: `env` boştu); bu olmadan
SSH'den `gpu_services.sh restart` servisleri **parolasız** ve venv'siz
kaldırırdı. `image_start.sh` açılışta ortamı `/etc/environment`'a (izin 600)
yazar, sshd onu PAM ile her oturumda yükler. SSH anahtarları aktarılmaz.

**Autostart GPU'yu denetler.** `nvidia-smi -L` başarısızsa servisler
başlatılmaz ve sebep açılış günlüğüne yazılır — ilk RunPod makinesinde NVML
"Unknown Error" verdi ve GPU kullanılamıyordu.

## Doğrulama betiği

[scripts/verify_gpu_image.sh](../../scripts/verify_gpu_image.sh) —
**her yeni ana makinede ilk komut.** Altı kontrol:

1. `llama-server --version`
2. önce paddle, sonra torch aynı süreçte import
3. `torch.cuda.is_available()`
4. torch **ve** paddle, torch'un metadata'sında pinlediği cuDNN'i yüklüyor
5. `paddle.utils.run_check()` + GPU'da küçük bir tensör işleminin sonucu
6. Triton çalışma anı kernel derlemesi

Aynı betik bir imajı **yerel kartla** da sınar (pod kiralamadan önce):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --gpus all \
    -v "$(pwd -W):/workspace/MAHIR" <imaj> \
    bash /workspace/MAHIR/scripts/verify_gpu_image.sh
```

**Betiğin gerçekten kırmızıya döndüğü sınandı** (2026-09-26, yerel kart):

| Senaryo | Sonuç |
|---|---|
| Sağlam imaj, `--gpus all` | 6/6 geçti, çıkış 0 |
| GPU verilmemiş konteyner | 5 düştü (llama-server `--version` GPU istemiyor), çıkış 5 |
| **cuDNN 9.5.1.17'ye düşürülmüş** (ilk build'deki arıza) | **yalnız 4/6 düştü**, torch'un kendi teşhisiyle: *"PyTorch was compiled against (9, 10, 2) but found runtime version (9, 5, 1)"* |

Son satır betiğin neden var olduğunu gösteriyor: **kırık torch import'u,
`torch.cuda.is_available()`'ı, paddle'ı ve Triton'u geçiyor.** Saf kontroller
bu arızayı hiç yakalamazdı; arıza ancak torch cuDNN kullandığında, bir modelin
içinde anlaşılmaz bir hata olarak çıkardı.

## Geliştirme döngüsü

```bash
# Kod değişikliği  (imaja DOKUNMADAN)
cd /workspace/MAHIR-PROTOTIP-HTML && git pull && scripts/gpu_services.sh restart

# Durum
scripts/gpu_services.sh status
```

Değişikliklerin çoğu ana makineye hiç uğramaz: ajan hattı ve istemler
(`backend/app/agents/*`) ile bütün ön yüz **VPS'te** çalışır. Ana makineyi
ilgilendiren yalnız `local/rag_service.py`, `local/rag_common.py`,
`local/curriculum.py`, `backend/app/ocr_engine.py`, `backend/app/ocr_worker.py`.

## VPS

`local/.env.bulut.example` kopyalanıp doldurulur (ana makinenin iki URL'si +
iki parola), sonra `MAHIR_BASLAT_BULUT.cmd` ya da Linux VPS'te doğrudan
`backend/run_file_receiver.py` (`MAHIR_HOST=127.0.0.1`, önünde Caddy).

## Taşınma (başka bir sağlayıcıya)

1. Yeni sağlayıcıda **ana makine sözleşmesini** karşıla (yukarıdaki tablo).
2. Kurulum bölümündeki komutlar: `git clone` → `verify_gpu_image.sh` →
   `gpu_services.sh start`.
3. VPS'te `.env.bulut`'taki iki URL'yi yeni adrese çevir.
4. Sağlayıcıya özgü adımları [runpod.md](runpod.md)'nin yanına küçük bir
   dosya olarak yaz.

Modeller yeni makinede bir kez yeniden iner; imaj ve kod birebir aynı kalır.

## İmajın derlenmesinde ölçülenler

### İlk build'de ölçülenler

Üçü de varsayım olarak yazılmıştı; build sırasında **ölçüldü** ve ikisi
Dockerfile'ı değiştirdi:

| Varsayım | Ölçüm | Sonuç |
|---|---|---|
| Temel imaj `nvidia/cuda:12.6.x` yeter | `ldd /app/libggml-cuda.so` → `libcudart.so.12`, `libcublas.so.12` **`/app`'te değil**, `/usr/local/cuda/lib64`'ten geliyor; llama.cpp imajı CUDA **12.8** taşıyor | Temel imaj `12.8.1-runtime-ubuntu24.04`'e çekildi + `LD_LIBRARY_PATH` eklendi |
| llama.cpp binary'si 24.04'te koşar | llama.cpp imajı **zaten** Ubuntu 24.04 / glibc 2.39 | Uyumsuzluk riski yokmuş |
| `paddle` ve `torch` aynı ortamda yaşar | **Hayır — Linux'ta pip düzeyinde çakışıyorlar** (aşağıya bakınız) | Üç nvidia pinini yeniden hizalayan katman eklendi |

**torch ↔ paddle nvidia pin çakışması (Linux'a özgü).** `pip install -r
local/requirements.txt` Linux'ta `ResolutionImpossible` ile düşüyor:

| paket | torch 2.8.0+cu126 | paddlepaddle-gpu 3.3.1 |
|---|---|---|
| `nvidia-cudnn-cu12` | `==9.10.2.21` | `==9.5.1.17` |
| `nvidia-cusparselt-cu12` | `==0.7.1` | `==0.6.3` |
| `nvidia-nccl-cu12` | `==2.27.3` | `==2.25.1` |

Her iki pin de `platform_system == "Linux"` işaretli, bu yüzden **Windows'taki
yerel kurulumda hiç görülmüyor** — bu bir taşıma sürprizi, yerel bir kusur
değil. Daha sinsi olanı: paddle'ı ayrı bir katmanda kurmak çakışmayı
*gizliyor*, çünkü pip üçünü düşürüp yalnız bir **uyarı** basıyor ve 0 ile
çıkıyor; imaj kırık bir torch ile üretilirdi.

Dockerfile'ın çözümü (gerekçeler dosyanın kendisinde):
1. paddle kurulduktan sonra üç paket `--no-deps` ile torch'un sürümlerine geri
   çekiliyor — yön **yeni** sürüm, çünkü SONAME'ler (`libcudnn.so.9`,
   `libcusparseLt.so.0`, `libnccl.so.2`) ana sürüm içinde geriye dönük uyumlu.
2. Son `-r` adımı üç GPU satırını süzüyor; pip iki çerçeveyi aynı çözümlemede
   görmezse çakışma doğmuyor.
3. `pip check` + sürüm doğrulaması build'i kapatıyor: beklenen üç tutarsızlık
   dışında bir şey çıkarsa build düşer.

### İmaj doğrulaması

| Doğrulama | Sonuç |
|---|---|
| `/opt/llama.cpp/llama-server --version` | `build 11176`, `built with GNU 14.2.0 for Linux x86_64`, çıkış 0 ✔ |
| `import paddle` + `import torch` (aynı süreç, paddle önce) | ikisi de yükleniyor ✔ |
| `torch.cuda.is_available()` | `True` ✔ |
| cuDNN, çalışma anında | torch **91002**, paddle **91002** — paddle'ın kendi pini 9.5.1.17 iken ✔ |
| `paddle.utils.run_check()` | `PaddlePaddle works well on 1 GPU.` ✔ |
| Triton çalışma anı kernel derlemesi (GPU'da) | derlendi ve doğru sonucu üretti ✔ |

- **cuDNN uyumu argüman değil ölçüm.** `ldd libpaddle.so` → `libcudnn.so.9`
  (minor sürüm SONAME'de yok) ve bu bağ pip'in `nvidia/cudnn` paketine
  çözülüyor. `paddle.device.get_cudnn_version()` derlendiği sürümü değil
  **yüklenen** kütüphaneyi bildiriyor ve 91002 döndü. Yani 9.5'e derlenmiş
  paddle 9.10.2.21 ile çalışıyor.
- **Triton bloker değil.** Önceki denemede PaddleOCR-VL'nin `transformers`
  motoru çalışma anı derleme yüzünden tıkanmıştı; imajda derleme çalışıyor,
  yani `MAHIR_OCR_ENGINE=paddle_dynamic` kaçış yoluna **mecbur değiliz**.
- `ldd`, `libcudart.so.12` ve `libcublas.so.12`'nin temel imajdan geldiğini
  gösteriyor — llama.cpp'nin `libggml-cuda.so`'su ile aynı yol. "runtime"
  temel imaj seçimi bu yüzden doğru; "base" imajda cuBLAS yok.

### İmaj boyutu

| Ölçüm | Değer |
|---|---|
| `docker image ls` (sıkıştırılmamış) | **29,4 GB** |
| Canlı `/opt/mahir-venv` | 11 GB |
| `/opt/llama.cpp` | 206 MB |
| pip katmanları toplamı | torch 6,11 + paddle 4,95 + hizalama 1,94 + kalan 1,32 GB |
| Ana makinenin çekeceği (sıkıştırılmış) | **10,75 GB** (ilk CI koşusu) |

Katman toplamı canlı venv'den ~3,3 GB büyük: paddle katmanı torch'un cuDNN
9.10'unu siliyor, hizalama katmanı da paddle'ın 9.5'ini — silinen dosyalar
önceki katmanlarda ÖLÜ olarak taşınıyor. Çok aşamalı bir build bunu atardı;
yalnız ölçülen çekme süresi sorun çıkarırsa yapılacak.

`nvidia/nccl` (410 MB) ve `nvidia/cusparselt` (432 MB) tek GPU'lu makinede
fiilen kullanılmıyor ama torch onları `==` ile pinliyor; ~%3 kazanç için
torch'un bağımlılık ağacını kırmaya değmez.

## Ölçümler (ilk ana makine: RunPod, RTX 2000 Ada 16 GB, 2026-09-26)

| Ölçüm | Hedef | Gerçekleşen |
|---|---|---|
| İlk imaj çekimi (oluştur → çalışıyor, 10,75 GB) | bir kez | **261-283 sn** |
| İlk açılış, boş disk (servisler → `/health` ok) | bir kez | **~24 dk** — neredeyse tamamı GGUF'un yavaş indirmesi (aşağıda) |
| **Sıcak başlatma** (durdur → başlat → `/health` ok) | < 4 dk | **68 sn** |
| **Analiz turu**, aynı 11 istemlik yük | < 120 sn | **35-36 sn** (pod içi) · **33-35 sn** (laptop → pod) · yerel 110-124 sn |
| VRAM, üç servis yüklü | < kart | **8,5 / 16 GB** (llama 3,1 · RAG 3,3 · OCR 2,0) |
| OCR, anonim sınav görseli | — | **4,1 sn/görsel** (5 görsel 20,3 sn, 5/5 satır) |
| Kod değişikliği → çalışır hâle gelme | < 60 sn | ölçülmedi |

**Nereden kazanıldı** (aynı yük, RAG servisi günlüğü):

| Aşama, istem başına | Yerel (RTX 4050, reranker CPU) | Ana makine (RTX 2000 Ada) |
|---|---|---|
| rerank | 7.986 ms | **188 ms** (42×) |
| gömme | 297 ms | 21 ms |
| LLM üretimi | ~2-3 sn | 2,8 sn |

Turdaki ~88 sn'lik CPU reranker payı ~2 sn'ye indi; kalan darboğaz LLM
üretimi (turun ~31/36 sn'si). RTX 2000 Ada'nın bellek bant genişliği dizüstü
kartına yakın olduğu için o kısım hızlanmadı — daha güçlü bir kart ancak onu
kısaltır.

**GGUF'un yavaş indirmesi.** Python tarafındaki modeller (bge-m3, reranker,
PaddleOCR-VL) HF'nin Xet yolundan ~1 dakikada indi; llama.cpp'nin kendi
indiricisi kimliksiz HF isteğiyle **~1,7 MB/s**'de kaldı ("set a HF_TOKEN to
enable higher rate limits"). Bir kez ödeniyor (model kalıcı diskte), ama yeni
bir diske taşınmada ilk açılışı belirleyen bu.

**Ev hattından büyük yanıtlar arada bir takıldı.** Laptop'tan pod'a üç tam
analiz turundan biri hiç dönmedi: pod `200 OK` yazdı, istemci yanıtı okuyamadı
(54 dk askıda; `timeout=600` her okuma işlemine ayrı uygulandığı için hiç
tetiklenmedi). SSH ile 2 MB'lık bir transfer de bir kez ~600 KB'de takıldı,
tekrarı 3 MB'ı sorunsuz taşıdı. Boşta bekleyen bağlantılar ise 150 sn'de bile
düşmedi (idle-NAT değil). Ev hattının MTU'su 1500'den küçük (yönlendirici
"fragment needed" dönüyor). Üretimde web katmanı VPS'te olacağı için bu yol
üretim yolu değil; ama `-Kip bulut` (web laptop'ta) bu yoldan geçer.

### Yerel taban çizgisi (aynı yükle, 2026-09-26)

Karşılaştırma için **aynı** yük hem yerelde hem ana makinede koşulur: gerçek
TDE 9 kataloğundan 10 kazanım, 20 soru, 25 anonim öğrenci → **11 istem**
(tarihsel kayıttaki turla aynı boy). Gerçek `/mahir-analyze` rotası, başsız bir
backend üzerinden; süre yanıttaki `trace.llmRound.durationMs`.

| Koşu (RTX 4050 6 GB, reranker CPU'da) | LLM turu |
|---|---|
| yalnız LLM GPU'da | 124,1 sn |
| OCR işçisi de açık (VRAM 3,2 → 5,2 GB) | 109,9 sn |
| tarihsel kayıt (2026-09-24, gerçek bir sınav) | 247,7 sn — bu yükle **yeniden üretilemedi** |

Süre nereye gidiyor (RAG servisi günlüğü, 22 getirme): istem başına **rerank
7.986 ms** (CPU), gömme 297 ms, arama 8 ms. Yani yerel turun **~88 sn'si
(%70-80) CPU'daki reranker**; kalanı LLM üretimi. Ana makinede reranker GPU'da
— asıl kazancın beklendiği yer. Hedef < 120 sn yerelde zaten tutuyor; ana
makinenin sorusu "ne kadar daha hızlı".

VRAM: yerelde llama-server tek başına ~3,2 GB, OCR yüklüyken ~5,2 GB.

## Bilinen tuzaklar

Önceki denemede zaman kaybettirenler ve bugünkü karşılıkları (sağlayıcıya
özgü olanlar kendi dosyalarında):

| Tuzak | Bugün |
|---|---|
| PaddleOCR-VL Triton ile çalışma anında kernel derliyor, `gcc` yok | **Kapandı ve ÖLÇÜLDÜ:** imajda `gcc`/`g++` var ve Triton GPU kernel'i gerçekten derleyip koşuyor. `OCR_ENGINE=paddle_dynamic` artık yalnız yedek |
| vLLM `flashinfer` Python ≥3.12 istiyordu | vLLM projeden çıktı; llama.cpp binary'si Python sürümüne duyarsız |
| PEP 668 "externally-managed-environment" | İmaj `/opt/mahir-venv` kullanıyor |
| `docker push` büyük katmanlarda düşüyordu | **Hâlâ düşüyor** (ölçüldü, yukarıda) — artık imajı CI derleyip itiyor, geliştirme makinesi yükleme yolunda değil |
| CRLF'li kabuk betiği Linux'ta "bad interpreter" | `.gitattributes` `*.sh` için LF zorluyor |
| — (bu denemede **yeni**) torch ve paddle Linux'ta uzlaşmaz nvidia pinleri istiyor; ayrı katmanlar çakışmayı gizleyip kırık torch üretiyor | Yeniden hizalama katmanı + süzülmüş `-r` adımı + `pip check` kapısı + doğrulama betiğinin 4. kontrolü |
| — (bu denemede **yeni**) PaddleX model önbelleği konteyner diskine gidiyordu | `PADDLE_PDX_CACHE_HOME` imajda `/workspace/.paddlex` |
