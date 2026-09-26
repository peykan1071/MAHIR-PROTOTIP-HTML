# RunPod — sağlayıcıya özgü adımlar

Bu dosya yalnız **RunPod'a özgü** olanları içerir. İmaj, ana makine sözleşmesi,
doğrulama betiği, geliştirme döngüsü ve ölçümler sağlayıcıdan bağımsızdır:
bkz. [README.md](README.md). Başka bir sağlayıcıya taşınırken bu dosyanın
yanına onunki yazılır; README değişmez. Depodaki RunPod'a özgü tek kod parçası
[scripts/runpod_pod.py](../../scripts/runpod_pod.py).

> **Durum (2026-09-26):** kurulu ve doğrulandı, **durdurulmuş**. EU-RO-1'de
> 30 GB ağ diski; çalışan pod RTX 2000 Ada 16 GB (0,24 $/sa). İlk pod'un
> makinesi GPU arızalı çıktı ve "Zero GPU Pods"a düştü; aynı diskle yeni pod
> açıldı. Ölçümler: [README.md](README.md#ölçümler-ilk-ana-makine-runpod-rtx-2000-ada-16-gb-2026-09-26).
> Kurulum günü toplam GPU harcaması ~0,65 $.

## İlk kurulumda yaşananlar (2026-09-26, ölçüldü)

| Olay | Ölçüm | Sonuç |
|---|---|---|
| **Stok gerçeği** | Ağ diski destekleyen AB merkezlerinde **A5000 hiç listelenmiyor**; EU-RO-1'de A4500/A4000/4000 Ada listeli ama boş. İki sorgu arasında (dakikalar) boştaki kartlar tersine döndü: önce 4090 + PRO 4500, sonra yalnız L4 | Tek kart değil, ucuzdan pahalıya **sıralı liste** + `gpuTypePriority: "custom"`. Onaylanan tavan 0,49 $/sa → **L4 24 GB** geldi |
| **Cloudflare** | API, Python'un varsayılan `Python-urllib` UA'sını **403 "error code: 1010"** ile reddetti (2026-08'deki tuzağın aynısı) | `runpod_pod.py` kendi UA'sını gönderiyor |
| İlk açılış | create → RUNNING + IP/portlar: **283 sn** (10,75 GB imaj çekimi dahil) | beklenenden hızlı |
| SSH | etkileşimsiz komut çalıştı; PID 1 `image_start.sh`, sshd dinliyor, host anahtarları ağ diskinde | tam SSH doğru karar |
| **Makine GPU'su arızalı** | `nvidia-smi` → "Failed to initialize NVML: Unknown Error"; `/dev/nvidia7` yerinde ama torch/paddle GPU görmüyor (sürücü 570.195.03, L4) | `verify_gpu_image.sh` servisler başlamadan **yakaladı** (3/6). Autostart artık `nvidia-smi -L` başarısızsa servisleri başlatmıyor |
| **SSH oturumu ortamsız** | sshd oturumu Docker ortamından değil sıfırdan kuruyor: `env` boş | `gpu_services.sh restart` servisleri **parolasız** kaldırırdı. `image_start.sh` ortamı `/etc/environment`'a yazıyor (PAM her oturumda yüklüyor) |
| **Zero GPU Pods, canlı** | durdurduktan ~1 dk sonra `start` → "There are not enough free GPUs on the host machine" | Veri ağ diskinde güvende; `create --new-pod` ile aynı diskle yeni pod |
| Yeni pod için stok | onaylı ucuz liste (≤ 0,28 $) iki denemede "no instances"; dakikada bir yeniden denemeyle **~7,5 dk** sonra RTX 2000 Ada yakalandı | ikinci pod bu; aynı makinede sonraki **3/3** durdur/başlat sorunsuz |
| **API eski port eşlemesini döndürüyor** | `start`tan sonra API bir süre ÖNCEKİ oturumun `portMappings`'ini veriyor; betik 2-3 sn'de "hazır" deyip eski portları yazdı. `lastStartedAt` işaret değil (ilk saniyede güncelleniyor) | `runpod_pod.py` artık eşlenen portun **gerçekten cevap vermesini** bekliyor; doğrulandı (42. sn'de yeni portlar, 68. sn'de `/health`) |
| IP / port | IP üç yeniden başlatmada da aynı; portlar her seferinde değişti (25679 → 13719 → 29595 → 35412) | belgenin iddiası doğrulandı |

## Kurulumu belirleyen üç RunPod kısıtı

Hepsi RunPod belgelerinden, kurulumdan **önce** doğrulandı:

| Kısıt | Belge | Sonucu |
|---|---|---|
| Ağ diski yalnız **Secure Cloud**'da | "Network volumes are only available for Pods in the Secure Cloud" | Pod Secure Cloud'da. Önceki planda yazan "A5000 Community 0,27 $/sa" etiketi yanlıştı: **0,27 $ Secure fiyatı**, Community 0,16 $ ama ağ diskine bağlanamıyor |
| Dış port eşlemeleri her yeniden başlatmada **değişiyor**; Secure'da genel IP sabit | "External port mappings change whenever your Pod resets" | `local/.env.bulut`'taki `IP:port` her oturumda eskir → `runpod_pod.py start` güncel eşlemeyi API'den okuyup yazıyor |
| Proxy SSH (`ssh.runpod.io`) SCP/SFTP'yi desteklemiyor, uzaktan komutu garanti etmiyor | "Basic SSH … does not support commands like SCP or SFTP" | İmajda **tam SSH** (`sshd`, `22/tcp`); anahtarı `image_start.sh` yazıyor |

**Community + pod diski** ucuz bir alternatif (~9 $/ay daha az), ama pod
fiziksel makineye bağlı kalıyor: makinenin GPU'su başkasına verilirse
("Zero GPU Pods") pod açılamıyor ve pod diskindeki modeller/kod yeni pod'a
taşınamıyor. Öğretmenin kullandığı bir oturum için öngörülebilirlik tercih edildi.

## Kurulum (bir kez)

Önkoşul: RunPod API anahtarı (Settings → API Keys, **Read/Write**) ve hesapta
bakiye. Anahtar sohbete ya da depoya yazılmaz:

```powershell
New-Item -ItemType Directory -Force $HOME\.runpod | Out-Null
Set-Content -Encoding ascii $HOME\.runpod\config.toml 'apikey = "ANAHTAR"'
```

```bash
py scripts/runpod_pod.py init-secrets     # local/.env.bulut + iki parola (değerler basılmaz)
py scripts/runpod_pod.py availability     # ağ diski destekleyen AB merkezlerinde GPU stoku
py scripts/runpod_pod.py create --image ghcr.io/peykan1071/mahir-gpu:<git-sha> --dc <merkez> --dry-run
py scripts/runpod_pod.py create --image ghcr.io/peykan1071/mahir-gpu:<git-sha> --dc <merkez>
```

`--dry-run` oluşturulacak gövdeyi parolalar gizli olarak gösterir. Pod
spesifikasyonu betikte kodlu (`build_pod_body`):

| Alan | Değer |
|---|---|
| Bulut | `SECURE` (ağ diski şartı) |
| GPU | sıralı liste, `gpuTypePriority: "custom"` (RunPod verilen sırayla dener, ilk boştakini kiralar). Varsayılan: A4500 (20 GB, 0,25) → A5000 (24 GB, 0,27) → 4000 Ada (20 GB, 0,28). Daha pahalı ya da < 20 GB kartlar yalnız `--gpu` ile bilinçli eklenir; ilk kurulumda onaylanan liste bunlara A4000 (16 GB, 0,25) ve L4 (24 GB, 0,49) ekledi |
| Ağ diski | 30 GB, `/workspace`'e bağlı; pod diski yok (`volumeInGb 0`) |
| Konteyner diski | 50 GB (yalnız çalışırken ücretli) |
| İmaj | `ghcr.io/peykan1071/mahir-gpu:<git-sha>` — CI özetindeki etiket; `latest` DEĞİL |
| CUDA | `allowedCudaVersions` 12.8, 12.9, 13.0 (imajın temel imajı CUDA 12.8) |
| TCP portları | `22`, `8001`, `8002` — HTTP portu yok, `8080` açılmaz |
| Ortam | iki parola (`local/.env.bulut`'tan), `SSH_PUBLIC_KEY` (`~/.ssh/id_ed25519.pub`), `MAHIR_AUTOSTART=1` |

Pod ve disk kimlikleri `~/.runpod/mahir.json`'da tutulur — depoya yazılmaz.
Başka bir merkezde kayıtlı bir disk varken `create` durur; sessizce ikinci
(ücretli) bir disk açmaz.

**GHCR erişimi:** imaj **kimlik bilgisi olmadan çekilebiliyor** — ölçüldü
(2026-09-26, `ghcr.io` için hiçbir kayıtlı kimlik yokken `docker manifest
inspect` başarılı). Public bir deponun iş akışından itilen paket okunabilir
açıldı; pod'a registry kimliği vermek gerekmez. Paket bir gün özele çekilirse:
RunPod'un "Container Registry Credentials" alanına `read:packages` yetkili bir
GHCR token'ı verilir. (Paket ayarlarını yalnız depo sahibi `peykan1071`
değiştirebilir.)

Pod açıldıktan sonra kodun indirilmesi ve doğrulama sağlayıcıdan bağımsız:
README, "Yeni bir ana makinede kurulum". SSH için:

```bash
py scripts/runpod_pod.py ssh "cd /workspace && git clone https://github.com/peykan1071/MAHIR-PROTOTIP-HTML.git"
```

## Günlük kullanım

```bash
# Oturum başlat: pod açılır, güncel IP:port local/.env.bulut'a yazılır,
# servisler MAHIR_AUTOSTART ile kendiliğinden kalkar, /health beklenir.
py scripts/runpod_pod.py start --wait-health

# Kod değişikliği (imaja DOKUNMADAN)
py scripts/runpod_pod.py ssh "cd /workspace/MAHIR-PROTOTIP-HTML && git pull && scripts/gpu_services.sh restart"

# Durum, IP, portlar
py scripts/runpod_pod.py status

# Oturum bitir: GPU ücreti durur, yalnız ağ diski işler
py scripts/runpod_pod.py stop
```

**Konteyner diski pod durunca silinir** (yalnız `/workspace` kalıcı). Önbellek
yolları bu yüzden imajda `/workspace` altına tanımlı; SSH host anahtarları da
`/workspace/.ssh-host-keys`'te, yani her oturumda aynı. Pod'da denemek için
`pip install X` yapılırsa bir sonraki oturumda yoktur; kalıcı bir bağımlılık
`local/requirements.txt` + CI ile imaja girer.

## Maliyet

Doğrulanmış birim fiyatlar (RunPod fiyat sayfası ve GraphQL kataloğu, Eylül 2026):

| Kalem | Birim | Not |
|---|---|---|
| RTX A4500 20 GB, Secure | 0,25 $/sa | listenin başı; EU-RO-1'de listeli, kurulum günü boşta değildi |
| RTX A5000 24 GB, **Secure** | 0,27 $/sa | Community 0,16 $ ama ağ diski yok; ağ diskli AB merkezlerinde listelenmiyor |
| **L4 24 GB, Secure** | **0,49 $/sa** | kurulum günü EU-RO-1'de boştaki tek ucuz kart - ilk pod bu |
| Ağ diski (<1 TB) | 0,07 $/GB/ay | pod dururken de aynı; büyütülebilir, küçültülemez |
| Konteyner diski | 0,10 $/GB/ay | pod dururken **ücretsiz** |
| Veri giriş/çıkış | **0 $** | |

**Durdurulmuş pod'da GPU ücreti işlemez** (RunPod resmî belgesi); yalnız disk.

| Aylık (günde 4 saat) | A4500 / A5000 | L4 (bugün) |
|---|---:|---:|
| GPU: 120 sa | 30-32 $ | **58,80 $** |
| Ağ diski 30 GB | 2,10 $ | 2,10 $ |
| VPS + alan adı | ~6-11 $ | ~6-11 $ |
| **Toplam** | **~39-46 $** | **~67-72 $** |

Planın ~41-46 $'ı ucuz kartlara dayanıyordu; kurulum günü onlar boşta değildi.
Ucuz kart boşalınca aynı diskle `create --new-pod --gpu "NVIDIA RTX A4500" ...`
ile geçilir (eski pod panelden sonlandırılır).

İmajın derlenmesi ve barındırılması 0 $: depo public olduğu için GitHub
Actions dakikaları ve GHCR public paketi ücretsiz.

## RunPod'a özgü tuzaklar

| Tuzak | Karşılığı |
|---|---|
| Ağ diski Community Cloud'da yok | pod Secure Cloud'da |
| Dış portlar her oturumda değişiyor | `runpod_pod.py start` `.env.bulut`'u güncelliyor |
| HTTP vekili 100 sn'de kesiyor | yalnız TCP portları |
| Cloudflare vekili `Python-urllib` UA'sını 403'lüyor | TCP portları, vekil devrede değil |
| Proxy SSH uzaktan komutu garanti etmiyor | imajda tam SSH |
| Yeniden başlatmada "Zero GPU Pods" (**canlı yaşandı**, durdurduktan ~1 dk sonra) | ağ diski; `create --new-pod` ile aynı diskle başka makinede yeni pod (eski pod otomatik silinmez) |
| Makinenin GPU'su arızalı olabilir (NVML "Unknown Error" - yaşandı) | her yeni makinede önce `verify_gpu_image.sh`; autostart GPU görünmezse servisleri başlatmıyor |
| Cloudflare `Python-urllib` UA'sını API'de de 403'lüyor (1010) | `runpod_pod.py` kendi UA'sını gönderiyor |
| Boştaki kartlar dakikalar içinde değişiyor | sıralı GPU listesi + `gpuTypePriority: "custom"` |
| `start`tan sonra API eski port eşlemesini döndürüyor | hazır sayılmak için eşlenen port gerçekten cevap vermeli (`readiness` + TCP yoklaması) |

## Erişilebilirlik: oturum bazlı düzen güvenilir değil (ölçüldü)

Durdurulmuş bir pod GPU'yu **tutmaz** — RunPod'un belgesi yalnız çalışan
pod'un kaynaklarının "başkası tarafından alınamayacağını" söylüyor. Kurulum
günü: bir makinede durdurduktan ~1 dk sonra GPU gitti; ucuz kartlar EU-RO-1'de
dakikalar içinde gelip gidiyor, yeni pod için ~7,5 dk beklendi. Yani her
"oturum başlat" bir piyango: ucuz kart olmayabilir. Seçenekler (karar
kullanıcıda, 2026-09-26 itibarıyla açık):

| Düzen | Kart garantisi | Aylık GPU |
|---|---|---|
| Oturum bazlı (bugünkü) | yok | ~29 $ (2000 Ada, günde 4 sa) |
| Pod hiç durdurulmaz (7/24) | çalıştığı sürece var | ~175 $ (2000 Ada) |
| Aylık kiralık GPU sunucusu | makine sizin | sağlayıcıya göre (doğrulanmadı) |

Yerel kip (`MAHIR_BASLAT.cmd`) her zaman çalışır (110-124 sn/tur), yani
uygulama hiçbir düzende tamamen durmaz; kaybedilen şey uzaktan erişim ve hız.
| Konteyner diski durunca siliniyor | her kalıcı şey `/workspace`'te; önbellek yolları ve SSH host anahtarları dahil |
