# MAHİR uzak dağıtım — sağlayıcıdan bağımsız rehber

GPU katmanı (RAG `:8001`, OCR `:8002`, LLM `:8080`) GPU'lu bir **ana makinede**,
web arayüzü (`:8000`) ayrı bir VPS'te çalışır. Bu belge, ana makinenin hangi
sağlayıcıda olduğundan bağımsız olan her şeyi anlatır. Sağlayıcıya özgü adımlar
kendi dosyalarında:

- [runpod.md](runpod.md) — RunPod (bugünkü hedef)

Yerel çalışma bundan etkilenmez: `MAHIR_BASLAT.cmd` hâlâ her şeyi bu makinede
açar (bkz. kök README, "Yerel mi, bulut mu?").

> **Durum (2026-09-26):** kod tarafı hazır ve sınandı. İmaj yerelde derlendi ve
> yerel kartla `--gpus all` altında doğrulandı. İmajı artık GitHub Actions
> derleyip GHCR'a itiyor (aşağıya bakınız). Henüz hiçbir ana makine
> kurulmadı; ölçüm tablosu ilk kurulumda doldurulacak.

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
| Ortam değişkenleri | `MAHIR_RAG_SHARED_SECRET`, `MAHIR_OCR_SHARED_SECRET` — başka hiçbir şey |
| İmaj | `ghcr.io/peykan1071/mahir-gpu:<git-sha>` — değişmez etiket, `latest` değil |

Parolalar zorunlu: verilmezse uçlar korumasız açılır. Üretmek için
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

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
koşuda iner (~13 GB, tek seferlik; kalıcı diskte kalır).

`/health`'te `"ok": true` ve `reranker.device == "cuda"` görülmeli. `cuda`
yerine `cpu` yazıyorsa asıl gecikme kazancı kaçıyor demektir.

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
| Ana makinenin çekeceği (sıkıştırılmış) | CI özetinde; ilk koşuda buraya yazılacak |

Katman toplamı canlı venv'den ~3,3 GB büyük: paddle katmanı torch'un cuDNN
9.10'unu siliyor, hizalama katmanı da paddle'ın 9.5'ini — silinen dosyalar
önceki katmanlarda ÖLÜ olarak taşınıyor. Çok aşamalı bir build bunu atardı;
yalnız ölçülen çekme süresi sorun çıkarırsa yapılacak.

`nvidia/nccl` (410 MB) ve `nvidia/cusparselt` (432 MB) tek GPU'lu makinede
fiilen kullanılmıyor ama torch onları `==` ile pinliyor; ~%3 kazanç için
torch'un bağımlılık ağacını kırmaya değmez.

## Ölçülecekler (ilk ana makine kurulumunda doldurulacak)

| Ölçüm | Hedef | Gerçekleşen |
|---|---|---|
| İlk imaj çekimi | bir kez | — |
| Oturum ısınması (başlat → `/health` ok) | < 4 dk | — |
| Analiz turu (`LLM turu: ... sure=Xs`) | < 120 sn | — |
| Kod değişikliği → çalışır hâle gelme | < 60 sn | — |

Yerelde bugünkü tur ~249 sn ve bunun ~88 sn'si reranker (istem başına ~8 sn,
CPU'da). Ana makinede reranker GPU'ya alınıyor; beklenti 40-80 sn ama bu bir
**tahmin**, ölçülecek.

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
