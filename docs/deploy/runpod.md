# RunPod dağıtımı — operasyon rehberi

GPU katmanı (RAG, OCR, LLM) bir RunPod pod'unda; web arayüzü (`:8000`) ayrı
bir VPS'te. Yerel çalışma bundan etkilenmez: `MAHIR_BASLAT.cmd` hâlâ her şeyi
bu makinede açar (bkz. README, "Yerel mi, bulut mu?").

> **Durum:** kod tarafı hazır ve sınandı. **Aşama 2 (imaj) tamam:**
> `hknrgl/mahir-gpu:latest` derlendi ve yerel kartla `--gpus all` altında
> doğrulandı (aşağıdaki doğrulama tablosu). Docker Hub'a **push edilmedi**.
> **Aşama 3 (pod) henüz yapılmadı;** panel adımları ilk koşuda doğrulanacak ve
> gerçek değerlerle (pod kimliği, IP, port) güncellenecek.

## Neden bu biçim

Bu projede RunPod bir kez denendi ve terk edildi — mimari yüzünden değil,
**her düzeltmenin 15-20 dakikalık `docker build + push` gerektirmesi**
yüzünden. Bu düzen tam olarak onu hedefliyor:

| Katman | İçerik | Değişim sıklığı | Maliyeti |
|---|---|---|---|
| İmaj | torch, paddle, docling, llama-server binary'si | `local/requirements.txt` değişince | 15-20 dk |
| Ağ diski `/workspace` | **uygulama kodu** (git), model önbellekleri | her kod değişikliğinde | **~10 sn** |

Kod imaja **girmez**. Döngü: `git pull && scripts/gpu_services.sh restart`.

## Aşama 2 — imaj

```bash
docker build -t <kullanici>/mahir-gpu:latest .
docker push  <kullanici>/mahir-gpu:latest
```

`Dockerfile` ilk satırlarda `ghcr.io/ggml-org/llama.cpp:server-cuda`
imajından `/app`'i kopyalar. Bu COPY **bilerek en başta**: imaj adı ya da yol
yanlışsa build saniyeler içinde düşsün, 10 GB'lık pip kurulumundan sonra
değil.

### İlk build'de ölçülenler

Üçü de varsayım olarak yazılmıştı; build sırasında **ölçüldü** ve ikisi
Dockerfile'ı değiştirdi:

| Varsayım | Ölçüm | Sonuç |
|---|---|---|
| Temel imaj `nvidia/cuda:12.6.x` yeter | `ldd /app/libggml-cuda.so` → `libcudart.so.12`, `libcublas.so.12` **`/app`'te değil**, `/usr/local/cuda/lib64`'ten geliyor; llama.cpp imajı CUDA **12.8** taşıyor | Temel imaj `12.8.1-runtime-ubuntu24.04`'e çekildi + `LD_LIBRARY_PATH` eklendi |
| llama.cpp binary'si 24.04'te koşar | llama.cpp imajı **zaten** Ubuntu 24.04 / glibc 2.39 | Uyumsuzluk riski yokmuş; glibc varsayımına gerek kalmadı |
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

### İmaj doğrulaması (yerelde, `--gpus all` ile — pod beklemeden)

Docker Desktop yerel kartı konteynere verebildiği için bu doğrulamaların
tamamı **pod kurulmadan** yapıldı. Sonuçlar:

| Doğrulama | Sonuç |
|---|---|
| `/opt/llama.cpp/llama-server --version` | `build 11176`, `built with GNU 14.2.0 for Linux x86_64`, çıkış 0 ✔ |
| `import paddle` + `import torch` (aynı süreç, paddle önce) | ikisi de yükleniyor ✔ |
| `torch.cuda.is_available()` | `True` ✔ |
| `torch.backends.cudnn.version()` | **91002** → çalışma anında 9.10.2 yüklü, hizalama tuttu ✔ |
| `paddle.utils.run_check()` | `PaddlePaddle works well on 1 GPU.` ✔ |
| Triton çalışma anı kernel derlemesi (GPU'da) | derlendi ve doğru sonucu üretti ✔ |

İki sonuç planı doğrudan değiştiriyor:

- **cuDNN uyumu artık argüman değil ölçüm.** `ldd libpaddle.so` →
  `libcudnn.so.9` (minor sürüm SONAME'de yok) ve bu bağ pip'in
  `nvidia/cudnn` paketine çözülüyor; `run_check` gerçek GPU kernel'i
  koşturuyor. Yani 9.5'e derlenmiş paddle, 9.10.2.21 ile çalışıyor.
- **Triton bloker değil.** Önceki denemede PaddleOCR-VL'nin `transformers`
  motoru çalışma anı derleme yüzünden tıkanmıştı; imajda derleme çalışıyor,
  yani `MAHIR_OCR_ENGINE=paddle_dynamic` kaçış yoluna **mecbur değiliz**
  (varsayılan `transformers` denenebilir).

Ayrıca `ldd` iki kütüphanenin temel imajdan geldiğini gösteriyor
(`libcudart.so.12`, `libcublas.so.12` → `/usr/local/cuda/lib64`) — llama.cpp'nin
`libggml-cuda.so`'su ile aynı yol. "runtime" temel imaj seçimi bu yüzden
doğru; "base" imajda cuBLAS yok.

### İmaj boyutu

| Ölçüm | Değer |
|---|---|
| `docker image ls` (sıkıştırılmamış) | **29,4 GB** |
| Canlı `/opt/mahir-venv` | 11 GB |
| `/opt/llama.cpp` | 206 MB |
| pip katmanları toplamı | torch 6,11 + paddle 4,95 + hizalama 1,94 + kalan 1,32 GB |

Katman toplamı canlı venv'den ~3,3 GB büyük: paddle katmanı torch'un cuDNN
9.10'unu siliyor, hizalama katmanı da paddle'ın 9.5'ini — silinen dosyalar
önceki katmanlarda ÖLÜ olarak taşınıyor. Bu bilinçli bir takas:
katmanları birleştirmek bu 3,3 GB'ı kurtarırdı ama ~12 GB'lık TEK bir katman
üretirdi ve `docker push`un önceki denemede düştüğü yer tam olarak büyük
katmanlardı.

`nvidia/nccl` (410 MB) ve `nvidia/cusparselt` (432 MB) tek GPU'lu pod'da
fiilen kullanılmıyor ama torch onları `==` ile pinliyor; ~%3 kazanç için
torch'un bağımlılık ağacını kırmaya değmez.

> **Push maliyeti.** Docker Hub'a giden veri sıkıştırılmış bloklar (kabaca
> 12-15 GB). Ev bağlantısının YÜKLEME hızı burada belirleyici; bu yüzden
> imajın ayda ~1 değişmesi planın bir gereği, süsü değil.

## Aşama 3 — pod

**Ağ diski:** EU-RO-1 (Romanya — Türkiye'ye en yakın bölge), 50 GB.
Ağ diski şart: pod durdurulunca GPU serbest kalır ve yeniden başlatmada
"Zero GPU Pods" hatası gelebilir; ağ diski veriyi makineden ayırır.

**Pod:** RTX A5000 24 GB (Community, 0,27 $/sa). VRAM bütçesi ~9,1 GB —
LLM 3,7 + OCR 3 + bge-m3 1,2 + reranker 1,2.

**TCP portları:** 8001 (RAG) ve 8002 (OCR) dışarı açılır. `:8080`
(llama-server) **açılmaz** — ona yalnız aynı kutudaki RAG servisi konuşur.

> RunPod'un HTTP vekili (`*.proxy.runpod.net`) KULLANILMAZ. Kendi belgeleri
> *"If your service takes longer than 100 seconds to respond, consider using
> TCP"* diyor; analiz turu bundan uzun sürebiliyor.

**Pod ortam değişkenleri** (panelden):

```
MAHIR_RAG_SHARED_SECRET=<uretilen-parola>
MAHIR_OCR_SHARED_SECRET=<uretilen-parola>
HF_HOME=/workspace/.cache/huggingface
XDG_CACHE_HOME=/workspace/.cache
```

Parolalar zorunlu: verilmezse uçlar korumasız açılır. Üretmek için
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.
`HF_HOME`/`XDG_CACHE_HOME` ağ diskinde olmalı, yoksa her yeniden başlatmada
~9 GB model yeniden iner.

**İlk kurulum (pod içinde, bir kez):**

```bash
cd /workspace
git clone <depo-url> MAHIR-PROTOTIP-HTML
cd MAHIR-PROTOTIP-HTML
scripts/gpu_services.sh start
```

`.env` gerekmez: gereken her şey pod ortam değişkenlerinden ve
`gpu_services.sh`'in varsayılanlarından geliyor. Modeller ilk koşuda iner
(~9 GB, tek seferlik).

**Hazır olduğunu doğrula:**

```bash
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
```

`"ok": true` ve `reranker.device == "cuda"` görülmeli. `cuda` yerine `cpu`
yazıyorsa asıl gecikme kazancı kaçıyor demektir.

## Aşama 4 — VPS

`local/.env.bulut.example` kopyalanıp doldurulur, sonra
`MAHIR_BASLAT_BULUT.cmd` ya da Linux VPS'te doğrudan
`backend/run_file_receiver.py` (`MAHIR_HOST=127.0.0.1`, önünde Caddy).

## Günlük kullanım

```bash
# Oturum başlat  (~1,5-3 dk ısınma: modeller ağ diskinden yüklenir)
runpodctl start pod <pod-id>

# Kod değişikliği  (imaja DOKUNMADAN)
ssh <pod> 'cd /workspace/MAHIR-PROTOTIP-HTML && git pull && scripts/gpu_services.sh restart'

# Durum
ssh <pod> 'cd /workspace/MAHIR-PROTOTIP-HTML && scripts/gpu_services.sh status'

# Oturum bitir  (GPU ücreti durur, yalnız disk işler)
runpodctl stop pod <pod-id>
```

**Durdurulmuş pod'da GPU ücreti işlemez** (RunPod resmî belgesi); yalnız
disk. Ağ diski 50 GB → 3,50 $/ay. Günde 4 saat kullanımda GPU ~32 $/ay.

## Ölçülecekler (Aşama 3'te doldurulacak)

| Ölçüm | Hedef | Gerçekleşen |
|---|---|---|
| Oturum ısınması (start → `/health` ok) | < 4 dk | — |
| Analiz turu (`LLM turu: ... sure=Xs`) | < 120 sn | — |
| Kod değişikliği → çalışır hâle gelme | < 60 sn | — |

Yerelde bugünkü tur ~249 sn ve bunun ~88 sn'si reranker (istem başına ~8 sn,
CPU'da). Pod'da reranker GPU'ya alınıyor; beklenti 40-80 sn ama bu bir
**tahmin**, ölçülecek. 100 sn'nin altına inerse RunPod'un HTTP vekili de
yedek yol olarak kullanılabilir hale gelir.

## Bilinen tuzaklar

Önceki denemede zaman kaybettirenler ve bugünkü karşılıkları:

| Tuzak | Bugün |
|---|---|
| PaddleOCR-VL Triton ile çalışma anında kernel derliyor, `gcc` yok | **Kapandı ve ÖLÇÜLDÜ:** imajda `gcc`/`g++` var ve Triton GPU kernel'i gerçekten derleyip koşuyor (yukarıdaki doğrulama tablosu). `OCR_ENGINE=paddle_dynamic` artık zorunlu kaçış yolu değil, yalnız yedek |
| vLLM `flashinfer` Python ≥3.12 istiyordu | vLLM projeden çıktı; llama.cpp binary'si Python sürümüne duyarsız |
| PEP 668 "externally-managed-environment" | İmaj `/opt/mahir-venv` kullanıyor |
| `docker push` büyük katmanlarda düşüyordu | torch / paddle / kalanı ayrı katmanlar |
| RunPod vekili `Python-urllib` UA'sını 403'lüyordu | TCP kullanılıyor, vekil devrede değil |
| CRLF'li kabuk betiği Linux'ta "bad interpreter" | `.gitattributes` `*.sh` için LF zorluyor |
| — (bu denemede **yeni**) torch ve paddle Linux'ta uzlaşmaz nvidia pinleri istiyor; ayrı katmanlar çakışmayı gizleyip kırık torch üretiyor | Yeniden hizalama katmanı + süzülmüş `-r` adımı + `pip check` kapısı (yukarıda) |
