# RunPod dağıtımı — operasyon rehberi

GPU katmanı (RAG, OCR, LLM) bir RunPod pod'unda; web arayüzü (`:8000`) ayrı
bir VPS'te. Yerel çalışma bundan etkilenmez: `MAHIR_BASLAT.cmd` hâlâ her şeyi
bu makinede açar (bkz. README, "Yerel mi, bulut mu?").

> **Durum:** bu belgedeki kod tarafı hazır ve sınandı. İmaj derlemesi ve pod
> kurulumu (Aşama 2-3) HENÜZ YAPILMADI; aşağıdaki panel adımları ilk koşuda
> doğrulanacak ve gerçek değerlerle (pod kimliği, IP, port) güncellenecek.

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

İlk build'de doğrulanacaklar:
- `nvidia/cuda:12.6.3-runtime-ubuntu24.04` etiketi geçerli mi (değilse
  `--build-arg CUDA_IMAGE=...`)
- `/opt/llama.cpp/llama-server --version` çalışıyor mu (22.04'te derlenmiş
  binary 24.04'te koşmalı; glibc geriye uyumlu)
- `paddle` ve `torch` aynı ortamda import edilebiliyor mu

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
| PaddleOCR-VL Triton ile çalışma anında kernel derliyor, `gcc` yok | İmajda `gcc`/`g++` var; ayrıca `OCR_ENGINE=paddle_dynamic` Triton'a hiç dokunmuyor |
| vLLM `flashinfer` Python ≥3.12 istiyordu | vLLM projeden çıktı; llama.cpp binary'si Python sürümüne duyarsız |
| PEP 668 "externally-managed-environment" | İmaj `/opt/mahir-venv` kullanıyor |
| `docker push` büyük katmanlarda düşüyordu | torch / paddle / kalanı ayrı katmanlar |
| RunPod vekili `Python-urllib` UA'sını 403'lüyordu | TCP kullanılıyor, vekil devrede değil |
| CRLF'li kabuk betiği Linux'ta "bad interpreter" | `.gitattributes` `*.sh` için LF zorluyor |
