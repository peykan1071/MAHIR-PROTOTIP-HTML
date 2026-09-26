# RunPod — sağlayıcıya özgü adımlar

Bu dosya yalnız **RunPod'a özgü** olanları içerir. İmaj, ana makine sözleşmesi,
doğrulama betiği, geliştirme döngüsü ve ölçümler sağlayıcıdan bağımsızdır:
bkz. [README.md](README.md). Başka bir sağlayıcıya taşınırken bu dosyanın
yanına onunki yazılır; README değişmez.

> **Durum (2026-09-26):** pod henüz kurulmadı. Aşağıdaki panel adımları ilk
> koşuda doğrulanacak ve gerçek değerlerle (pod kimliği, IP, port)
> güncellenecek.

## Kurulum (bir kez)

**Ağ diski:** EU-RO-1 (Romanya — Türkiye'ye en yakın bölge), **30 GB**.
Ağ diski şart: pod durdurulunca GPU serbest kalır ve yeniden başlatmada
"Zero GPU Pods" hatası gelebilir — pod fiziksel makineye bağlıdır, ağ diski
veriyi makineden ayırır. 30 GB yeterli, çünkü venv imajın içinde; diskte yalnız
kod ve ~13 GB model var (RunPod ağ diskini sonradan büyütmeye izin veriyor —
ilk kurulumda doğrulanacak).

**Pod:**

| Alan | Değer |
|---|---|
| GPU | RTX A5000 24 GB, Community (0,27 $/sa) |
| Konteyner imajı | `ghcr.io/peykan1071/mahir-gpu:<git-sha>` — CI özetindeki etiket; `latest` DEĞİL |
| Allowed CUDA versions | **≥ 12.8** (imajın temel imajı CUDA 12.8 runtime) |
| Ağ diski | yukarıdaki, `/workspace`'e bağlı |
| Expose TCP ports | `8001`, `8002` — `8080` **açılmaz** |
| Ortam değişkenleri | `MAHIR_RAG_SHARED_SECRET`, `MAHIR_OCR_SHARED_SECRET` — başka hiçbir şey |

**GHCR erişimi:** imaj **kimlik bilgisi olmadan çekilebiliyor** — ölçüldü
(2026-09-26, ilk CI koşusundan hemen sonra, `ghcr.io` için hiçbir kayıtlı
kimlik yokken `docker manifest inspect` başarılı). Public bir deponun iş
akışından itilen paket okunabilir açıldı; pod'a registry kimliği vermek
gerekmez. Paket bir gün özele çekilirse: RunPod'un "Container Registry
Credentials" alanına `read:packages` yetkili bir GHCR token'ı verilir.
(Paket ayarlarını yalnız depo sahibi `peykan1071` değiştirebilir.)

> RunPod'un HTTP vekili (`*.proxy.runpod.net`) KULLANILMAZ. Kendi belgeleri
> *"If your service takes longer than 100 seconds to respond, consider using
> TCP"* diyor; analiz turu bundan uzun sürebiliyor. TCP portları Cloudflare
> katmanını da atlıyor (önceki denemede o katman `Python-urllib` UA'sını
> 403'lüyordu).

Pod açıldıktan sonra kurulum komutları sağlayıcıdan bağımsız: README,
"Yeni bir ana makinede kurulum".

## Günlük kullanım

```bash
# Oturum başlat  (~1,5-3 dk ısınma tahmini: modeller ağ diskinden yüklenir)
runpodctl start pod <pod-id>

# Kod değişikliği  (imaja DOKUNMADAN)
ssh <pod> 'cd /workspace/MAHIR-PROTOTIP-HTML && git pull && scripts/gpu_services.sh restart'

# Durum
ssh <pod> 'cd /workspace/MAHIR-PROTOTIP-HTML && scripts/gpu_services.sh status'

# Oturum bitir  (GPU ücreti durur, yalnız disk işler)
runpodctl stop pod <pod-id>
```

**Konteyner diski pod durunca silinir** (yalnız `/workspace` kalıcı). Önbellek
yolları bu yüzden imajda `/workspace` altına tanımlı. Pod'da denemek için
`pip install X` yapılırsa bir sonraki oturumda yoktur; kalıcı bir bağımlılık
`local/requirements.txt` + CI ile imaja girer.

## Maliyet

Doğrulanmış birim fiyatlar (RunPod resmî belgeleri, Eylül 2026):

| Kalem | Birim | Not |
|---|---|---|
| RTX A5000 24 GB, Community | **0,27 $/sa** | saniye bazlı faturalama |
| Ağ diski (<1 TB) | 0,07 $/GB/ay | pod dururken de aynı |
| Konteyner diski | 0,10 $/GB/ay | pod dururken **ücretsiz** |
| Veri giriş/çıkış | **0 $** | |

**Durdurulmuş pod'da GPU ücreti işlemez** (RunPod resmî belgesi); yalnız disk.

| Aylık (günde 4 saat) | |
|---|---:|
| GPU: 120 sa × 0,27 $ | 32,40 $ |
| Ağ diski 30 GB | 2,10 $ |
| VPS + alan adı | ~6-11 $ |
| **Toplam** | **~41-46 $** |

İmajın derlenmesi ve barındırılması 0 $: depo public olduğu için GitHub
Actions dakikaları ve GHCR public paketi ücretsiz.

## RunPod'a özgü tuzaklar

| Tuzak | Karşılığı |
|---|---|
| HTTP vekili 100 sn'de kesiyor | TCP portları |
| Cloudflare vekili `Python-urllib` UA'sını 403'lüyor | TCP portları, vekil devrede değil |
| Yeniden başlatmada "Zero GPU Pods" | ağ diski; gerekirse aynı diskle başka makinede yeni pod |
| Konteyner diski durunca siliniyor | her kalıcı şey `/workspace`'te; önbellek yolları imajda |
