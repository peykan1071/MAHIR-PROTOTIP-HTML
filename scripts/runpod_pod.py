"""MAHİR - RunPod pod yardımcısı (yalnız standart kütüphane).

Bu depoda RunPod'a ÖZGÜ tek parça. Sağlayıcıdan bağımsız olan her şey
docs/deploy/README.md'de; başka bir sağlayıcıya taşınırken bu dosyanın
karşılığı yazılır, gerisi değişmez.

Neden var: RunPod'da dış port eşlemeleri her yeniden başlatmada değişiyor
("External port mappings change whenever your Pod resets" - RunPod belgesi).
Bu yüzden local/.env.bulut'taki `IP:port` her oturumda eskir. Bu betik güncel
eşlemeyi API'den okuyup yazar; günlük kullanım tek komuta iner:

    py scripts/runpod_pod.py start --wait-health   # oturumu aç, .env.bulut'u güncelle
    py scripts/runpod_pod.py stop                  # GPU ücretini durdur
    py scripts/runpod_pod.py ssh "cd /workspace/MAHIR-PROTOTIP-HTML && git pull && scripts/gpu_services.sh restart"

Bir kez:

    py scripts/runpod_pod.py init-secrets          # local/.env.bulut + iki parola
    py scripts/runpod_pod.py availability          # hangi merkezde hangi GPU var
    py scripts/runpod_pod.py create --image ghcr.io/...:<sha> --dc EU-RO-1

Kimlik: `RUNPOD_API_KEY` ya da ~/.runpod/config.toml (`apikey = "..."`,
runpodctl'in de kullandığı yer). Pod ve disk kimlikleri ~/.runpod/mahir.json'da -
depo DIŞINDA. API anahtarı ve parolalar HİÇBİR çıktıda basılmaz; pod'un API
yanıtı ortam değişkenlerini (parolaları) taşıdığı için yanıt asla bütünüyle
yazdırılmaz.
"""

from __future__ import annotations

import argparse
import codecs
import copy
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "local" / ".env.bulut"
ENV_TEMPLATE = REPO_ROOT / "local" / ".env.bulut.example"
RUNPOD_DIR = Path.home() / ".runpod"
CONFIG_FILE = RUNPOD_DIR / "config.toml"
STATE_FILE = RUNPOD_DIR / "mahir.json"
SSH_PUBLIC_KEY_FILE = Path.home() / ".ssh" / "id_ed25519.pub"

REST_URL = "https://rest.runpod.io/v1"
GRAPHQL_URL = "https://api.runpod.io/graphql"

SSH_PORT, RAG_PORT, OCR_PORT = 22, 8001, 8002
SECRET_KEYS = ("MAHIR_RAG_SHARED_SECRET", "MAHIR_OCR_SHARED_SECRET")
URL_KEYS = ("MAHIR_RAG_URL", "MAHIR_OCR_URL")

# Öncelik sırasıyla: RunPod listeyi `gpuTypePriority: custom` ile BU sırada
# dener ve ilk boştakini kiralar. Ucuzdan pahalıya. VRAM tahmini ~9,1 GB
# (ölçülmedi); 20 GB altı ve 0,30 $/sa üstü yalnız elle (`--gpu`) eklenir.
# Stok dakikalar içinde değişiyor (2026-09-26'da iki sorgu arasında tersine
# döndü) - bu yüzden tek kart değil, sıralı liste.
DEFAULT_GPUS = ("NVIDIA RTX A4500", "NVIDIA RTX A5000", "NVIDIA RTX 4000 Ada Generation")
CANDIDATE_GPUS = (
    "NVIDIA RTX A5000",
    "NVIDIA RTX A4500",
    "NVIDIA RTX 4000 Ada Generation",
    "NVIDIA RTX A4000",
    "NVIDIA L4",
    "NVIDIA A40",
    "NVIDIA RTX A6000",
)
# Türkiye'ye yakınlık sırası - yalnız sıralama için; ağ diski desteği API'den okunur.
PREFERRED_DATA_CENTERS = ("EU-RO-1", "EU-FR-1", "EU-NL-1", "EUR-NO-1", "EUR-NO-2", "EUR-IS-1", "EUR-IS-3")
# İmajın temel imajı CUDA 12.8 runtime: sürücü en az bunu desteklemeli.
ALLOWED_CUDA_VERSIONS = ("12.8", "12.9", "13.0")


class RunPodError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class PodNotReady(RuntimeError):
    """Pod henüz IP ya da port eşlemesi almadı."""


# --- Saf yardımcılar (tests/test_runpod_pod.py) ----------------------------


def parse_api_key(text: str) -> str:
    """config.toml içinden `apikey`/`api_key`/`apiKey` değerini döndürür; yoksa ""."""

    match = re.search(r"""^\s*api_?key\s*=\s*["']?([^"'\s#]+)["']?""", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else ""


def read_env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def set_env_values(text: str, updates: dict[str, str]) -> str:
    """`KEY=...` satırlarını yerinde değiştirir, eksikleri sona ekler.

    Diğer her satır (yorumlar, parolalar) bayt bayt korunur; satır sonu biçimi
    (CRLF/LF) dosyanınkiyle aynı kalır.
    """

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    remaining = dict(updates)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in remaining:
            lines[index] = f"{key}={remaining.pop(key)}"
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
    return newline.join(lines) + newline


def fill_missing_secrets(text: str, generate: Callable[[], str]) -> tuple[str, list[str]]:
    """Boş parola satırlarını doldurur; dolu olanlara DOKUNMAZ. Doldurulan adları döndürür."""

    values = read_env_values(text)
    missing = [key for key in SECRET_KEYS if not values.get(key)]
    if not missing:
        return text, []
    return set_env_values(text, {key: generate() for key in missing}), missing


def _mapped_port(pod: dict[str, Any], port: int) -> int | None:
    mappings = pod.get("portMappings") or {}
    value = mappings.get(str(port), mappings.get(port))
    return int(value) if value else None


def service_urls(pod: dict[str, Any]) -> dict[str, str]:
    """Pod yanıtından `.env.bulut` adreslerini üretir."""

    ip = pod.get("publicIp")
    rag, ocr = _mapped_port(pod, RAG_PORT), _mapped_port(pod, OCR_PORT)
    if not ip or not rag or not ocr:
        raise PodNotReady(f"IP/port henüz yok (publicIp={ip!r}, {RAG_PORT}->{rag}, {OCR_PORT}->{ocr}).")
    return {"MAHIR_RAG_URL": f"http://{ip}:{rag}/agents", "MAHIR_OCR_URL": f"http://{ip}:{ocr}"}


def ssh_target(pod: dict[str, Any]) -> tuple[str, int]:
    ip, port = pod.get("publicIp"), _mapped_port(pod, SSH_PORT)
    if not ip or not port:
        raise PodNotReady(f"SSH için IP/port henüz yok (publicIp={ip!r}, {SSH_PORT}->{port}).")
    return ip, port


def build_volume_body(name: str, size_gb: int, data_center: str) -> dict[str, Any]:
    return {"name": name, "size": size_gb, "dataCenterId": data_center}


def build_pod_body(
    *,
    name: str,
    image: str,
    data_center: str,
    gpu_ids: list[str],
    volume_id: str,
    env: dict[str, str],
) -> dict[str, Any]:
    """Pod spesifikasyonu - RunPod'daki kurulumun TEK kaynağı.

    Secure Cloud zorunlu: ağ diski yalnız orada ("Network volumes are only
    available for Pods in the Secure Cloud"). `volumeInGb` 0: kalıcı veri ağ
    diskinde, ayrıca pod diski açılmaz. HTTP portu yok: RunPod'un HTTP vekili
    100 sn'de kesiyor, analiz turu daha uzun sürebiliyor.
    """

    return {
        "name": name,
        "cloudType": "SECURE",
        "computeType": "GPU",
        "gpuCount": 1,
        "gpuTypeIds": list(gpu_ids),
        # "custom": listeyi VERİLEN sırayla dene. Varsayılan "availability"
        # RunPod'un o anki tercihine göre seçer - pahalı bir kart gelebilir.
        "gpuTypePriority": "custom",
        "dataCenterIds": [data_center],
        "networkVolumeId": volume_id,
        "volumeMountPath": "/workspace",
        "volumeInGb": 0,
        "containerDiskInGb": 50,
        "imageName": image,
        "ports": [f"{SSH_PORT}/tcp", f"{RAG_PORT}/tcp", f"{OCR_PORT}/tcp"],
        "allowedCudaVersions": list(ALLOWED_CUDA_VERSIONS),
        "env": dict(env),
    }


def masked(body: dict[str, Any]) -> dict[str, Any]:
    """Ekrana basılabilir kopya: parolalar `***`, SSH anahtarı kısaltılmış."""

    safe = copy.deepcopy(body)
    env = safe.get("env") or {}
    for key in list(env):
        if key in SECRET_KEYS:
            env[key] = "***"
        elif key == "SSH_PUBLIC_KEY":
            env[key] = env[key][:24] + "…"
    return safe


def scrub(text: str, hidden: list[str]) -> str:
    for value in hidden:
        if value:
            text = text.replace(value, "***")
    return text


# --- G/Ç --------------------------------------------------------------------


def api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if not key and CONFIG_FILE.exists():
        key = parse_api_key(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    if not key:
        sys.exit(
            "RunPod API anahtarı bulunamadı. RunPod -> Settings -> API Keys'ten (Read/Write) oluşturup\n"
            "PowerShell'de kaydedin (anahtar ekrana/sohbete yazılmasın):\n"
            "    New-Item -ItemType Directory -Force $HOME\\.runpod | Out-Null\n"
            "    Set-Content -Encoding ascii $HOME\\.runpod\\config.toml 'apikey = \"ANAHTAR\"'"
        )
    return key


def _hidden_values() -> list[str]:
    hidden = [os.environ.get("RUNPOD_API_KEY", "")]
    if CONFIG_FILE.exists():
        hidden.append(parse_api_key(CONFIG_FILE.read_text(encoding="utf-8-sig")))
    if ENV_FILE.exists():
        values = read_env_values(_read_text(ENV_FILE))
        hidden += [values.get(key, "") for key in SECRET_KEYS]
    return [value for value in hidden if value]


# RunPod'un API'si Cloudflare arkasında ve Cloudflare Python'un varsayılan
# `Python-urllib/3.x` User-Agent'ını 403 "error code: 1010" ile REDDEDİYOR
# (2026-09-26'da ölçüldü; 2026-08 denemesinde de aynı tuzak vardı). Kendi
# adımızı göndermek yetiyor.
USER_AGENT = "mahir-runpod-pod/1.0"


def build_request(method: str, url: str, body: Any, key: str) -> urllib.request.Request:
    data = None if body is None else json.dumps(body).encode("utf-8")
    return urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )


def _http(method: str, url: str, body: Any = None) -> Any:
    request = build_request(method, url, body, api_key())
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:600]
        raise RunPodError(error.code, scrub(f"HTTP {error.code} {method} {url}: {detail}", _hidden_values())) from None
    except urllib.error.URLError as error:
        raise RunPodError(0, f"{method} {url}: {error.reason}") from None
    return json.loads(raw) if raw.strip() else {}


def rest(method: str, path: str, body: Any = None) -> Any:
    return _http(method, REST_URL + path, body)


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _http("POST", GRAPHQL_URL, {"query": query, "variables": variables or {}})
    if payload.get("errors"):
        raise RunPodError(200, scrub(f"GraphQL: {payload['errors'][0].get('message')}", _hidden_values()))
    return payload.get("data") or {}


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def _write_text(path: Path, text: str) -> None:
    """Dosyanın BOM durumunu koruyarak yazar (PowerShell 5.1 BOM'a duyarlı)."""

    bom = path.exists() and path.read_bytes().startswith(codecs.BOM_UTF8)
    path.write_bytes((codecs.BOM_UTF8 if bom else b"") + text.encode("utf-8"))


def load_state() -> dict[str, Any]:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def save_state(state: dict[str, Any]) -> None:
    RUNPOD_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _pod_id() -> str:
    pod_id = load_state().get("podId")
    if not pod_id:
        sys.exit(f"Kayıtlı pod yok ({STATE_FILE}). Önce: py scripts/runpod_pod.py create ...")
    return pod_id


def get_pod() -> dict[str, Any]:
    return rest("GET", f"/pods/{_pod_id()}")


def write_env_urls(pod: dict[str, Any]) -> dict[str, str]:
    urls = service_urls(pod)
    if not ENV_FILE.exists():
        sys.exit(f"{ENV_FILE} yok. Önce: py scripts/runpod_pod.py init-secrets")
    _write_text(ENV_FILE, set_env_values(_read_text(ENV_FILE), urls))
    return urls


def wait_until_reachable(timeout: float, started: float) -> dict[str, Any]:
    """Pod RUNNING olup IP ve üç port eşlemesini alana kadar bekler."""

    deadline = time.monotonic() + timeout
    last = ""
    while True:
        pod = get_pod()
        status = pod.get("desiredStatus")
        try:
            if status == "RUNNING":
                service_urls(pod)
                ssh_target(pod)
                print(f"  RUNNING, IP ve portlar hazır: {time.monotonic() - started:.0f} sn")
                return pod
        except PodNotReady as error:
            note = str(error)
        else:
            note = f"durum {status}"
        if note != last:
            print(f"  bekleniyor ({time.monotonic() - started:.0f} sn): {note}")
            last = note
        if time.monotonic() > deadline:
            sys.exit(f"Zaman aşımı ({timeout:.0f} sn): {note}")
        time.sleep(5)


def wait_for_health(pod: dict[str, Any], timeout: float, started: float) -> None:
    ip, port = pod["publicIp"], _mapped_port(pod, RAG_PORT)
    url = f"http://{ip}:{port}/health"
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        note = ""
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read())
            if payload.get("ok"):
                reranker = (payload.get("reranker") or {}).get("device")
                embedder = (payload.get("embedder") or {}).get("device")
                print(f"  /health ok: {time.monotonic() - started:.0f} sn (embedder={embedder}, reranker={reranker})")
                return
            note = str(payload.get("message", "hazır değil"))[:120]
        except (urllib.error.URLError, OSError, ValueError) as error:
            note = f"ulaşılamıyor ({getattr(error, 'reason', error)})"
        if note != last:
            print(f"  /health bekleniyor ({time.monotonic() - started:.0f} sn): {note}")
            last = note
        if time.monotonic() > deadline:
            sys.exit(f"/health zaman aşımı ({timeout:.0f} sn): {note}")
        time.sleep(10)


# --- Komutlar -----------------------------------------------------------------


def cmd_availability(_args: argparse.Namespace) -> None:
    centers = graphql("query { dataCenters { id name storageSupport listed } }").get("dataCenters", [])
    eligible = [c["id"] for c in centers if c.get("storageSupport") and c.get("listed") and c["id"].startswith(("EU-", "EUR-"))]
    order = {dc: index for index, dc in enumerate(PREFERRED_DATA_CENTERS)}
    eligible.sort(key=lambda dc: (order.get(dc, len(order)), dc))
    query = (
        "query($dc: String) { gpuTypes { id memoryInGb securePrice "
        "lowestPrice(input: {gpuCount: 1, dataCenterId: $dc, secureCloud: true}) { uninterruptablePrice stockStatus } } }"
    )
    print(f"Ağ diski destekleyen AB merkezleri (Türkiye'ye yakınlık sırasıyla): {', '.join(eligible)}")
    print(f"{'merkez':10s} {'GPU':32s} {'VRAM':>5s} {'$/sa':>6s}  stok")
    for dc in eligible:
        for gpu in graphql(query, {"dc": dc}).get("gpuTypes", []):
            if gpu["id"] not in CANDIDATE_GPUS:
                continue
            lowest = gpu.get("lowestPrice") or {}
            price = lowest.get("uninterruptablePrice") or gpu.get("securePrice")
            stock = lowest.get("stockStatus") or "-"
            print(f"{dc:10s} {gpu['id']:32s} {gpu.get('memoryInGb', 0):>4}G {price or 0:>6.2f}  {stock}")


def cmd_init_secrets(_args: argparse.Namespace) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_bytes(ENV_TEMPLATE.read_bytes())
        print(f"{ENV_FILE} şablondan oluşturuldu.")
    text, filled = fill_missing_secrets(_read_text(ENV_FILE), lambda: secrets.token_urlsafe(32))
    if filled:
        _write_text(ENV_FILE, text)
        print(f"Üretildi (değerler basılmadı): {', '.join(filled)}")
    else:
        print("İki parola zaten dolu - dokunulmadı.")


def cmd_create(args: argparse.Namespace) -> None:
    values = read_env_values(_read_text(ENV_FILE)) if ENV_FILE.exists() else {}
    missing = [key for key in SECRET_KEYS if not values.get(key)]
    if missing:
        sys.exit(f"Parola eksik ({', '.join(missing)}). Önce: py scripts/runpod_pod.py init-secrets")
    ssh_key = Path(args.ssh_key).read_text(encoding="utf-8").strip()
    env = {key: values[key] for key in SECRET_KEYS}
    env.update({"SSH_PUBLIC_KEY": ssh_key, "MAHIR_AUTOSTART": "1"})

    state = load_state()
    if state.get("podId") and not args.new_pod:
        sys.exit(
            f"Kayıtlı bir pod var ({state['podId']}). Günlük kullanım: start/stop/status.\n"
            "Aynı diskle YENİ pod (ör. 'Zero GPU Pods'): --new-pod. Eski pod otomatik SİLİNMEZ."
        )
    if state.get("networkVolumeId") and state.get("dataCenterId") != args.dc:
        # Sessizce ikinci bir disk açmak, eskisinin kimliğini kayıttan düşürür
        # ama ücretini DURDURMAZ. Merkez değişikliği bilinçli yapılmalı.
        sys.exit(
            f"Kayıtlı ağ diski {state['networkVolumeId']} başka bir merkezde ({state['dataCenterId']}).\n"
            f"Pod ancak diskin merkezinde açılabilir: --dc {state['dataCenterId']}. Merkezi değiştirmek\n"
            "için eski diski panelden silip ~/.runpod/mahir.json'dan kaydını kaldırınız."
        )
    volume_id = state.get("networkVolumeId")
    volume_body = build_volume_body(f"{args.name}-workspace", args.volume_gb, args.dc)
    pod_body = build_pod_body(
        name=args.name, image=args.image, data_center=args.dc, gpu_ids=args.gpu,
        volume_id=volume_id or "<olusturulacak>", env=env,
    )
    if args.dry_run:
        if not volume_id:
            print("Ağ diski:", json.dumps(volume_body, ensure_ascii=False))
        print("Pod:", json.dumps(masked(pod_body), indent=2, ensure_ascii=False))
        return

    started = time.monotonic()
    if not volume_id:
        volume = rest("POST", "/networkvolumes", volume_body)
        volume_id = volume["id"]
        state.update({"networkVolumeId": volume_id, "dataCenterId": args.dc})
        save_state(state)
        print(f"Ağ diski oluşturuldu: {volume_id} ({args.volume_gb} GB, {args.dc})")
    pod_body["networkVolumeId"] = volume_id
    pod = rest("POST", "/pods", pod_body)
    state.update({"podId": pod["id"], "image": args.image, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S")})
    save_state(state)
    print(f"Pod oluşturuldu: {pod['id']} - imaj çekiliyor (ilk sefer 10,75 GB)")
    pod = wait_until_reachable(args.timeout, started)
    urls = write_env_urls(pod)
    print(f"local/.env.bulut güncellendi: {urls['MAHIR_RAG_URL']} , {urls['MAHIR_OCR_URL']}")


def cmd_status(_args: argparse.Namespace) -> None:
    pod = get_pod()
    machine = pod.get("machine") or {}
    print(f"pod       : {pod.get('id')}  ({pod.get('name')})")
    print(f"durum     : {pod.get('desiredStatus')}  - {pod.get('lastStatusChange', '')}")
    # `machine` pod hazırlanırken boş gelebiliyor (ölçüldü); ücret her zaman var.
    gpu = machine.get("gpuDisplayName") or machine.get("gpuTypeId") or "?"
    print(f"GPU       : {gpu}  makine: {pod.get('machineId', '?')}  $/sa: {pod.get('costPerHr', '?')}")
    print(f"imaj      : {pod.get('imageName')}")
    print(f"IP/portlar: {pod.get('publicIp') or '-'}  {pod.get('portMappings') or {}}")
    try:
        urls = service_urls(pod)
        print(f"adresler  : {urls['MAHIR_RAG_URL']} , {urls['MAHIR_OCR_URL']}")
    except PodNotReady:
        pass


def cmd_start(args: argparse.Namespace) -> None:
    started = time.monotonic()
    pod_id = _pod_id()
    try:
        rest("POST", f"/pods/{pod_id}/start")
    except RunPodError as error:
        if "not enough free GPUs" in str(error):
            # "Zero GPU Pods": pod fiziksel makineye bağlı ve o makinenin GPU'su
            # başkasına verildi. 2026-09-26'da durdurduktan ~1 dk sonra yaşandı.
            sys.exit(
                "Pod'un makinesinde boş GPU kalmadı (\"Zero GPU Pods\"). Veri ağ diskinde güvende.\n"
                "Aynı diskle başka bir makinede yeni pod:\n"
                "    py scripts/runpod_pod.py create --new-pod --image <aynı-imaj> --dc <aynı-merkez> [--gpu ...]\n"
                "Eski pod otomatik SİLİNMEZ; durmuş pod GPU ücreti yazmaz, panelden sonlandırılabilir."
            )
        if error.status != 404:
            raise
        graphql("mutation($id: String!) { podResume(input: {podId: $id, gpuCount: 1}) { id } }", {"id": pod_id})
    print(f"Pod başlatılıyor: {pod_id}")
    pod = wait_until_reachable(args.timeout, started)
    urls = write_env_urls(pod)
    print(f"local/.env.bulut güncellendi: {urls['MAHIR_RAG_URL']} , {urls['MAHIR_OCR_URL']}")
    if args.wait_health:
        wait_for_health(pod, args.health_timeout, started)


def cmd_stop(args: argparse.Namespace) -> None:
    pod_id = _pod_id()
    try:
        rest("POST", f"/pods/{pod_id}/stop")
    except RunPodError as error:
        if error.status != 404:
            raise
        graphql("mutation($id: String!) { podStop(input: {podId: $id}) { id } }", {"id": pod_id})
    deadline = time.monotonic() + args.timeout
    while get_pod().get("desiredStatus") != "EXITED":
        if time.monotonic() > deadline:
            sys.exit("Pod EXITED durumuna geçmedi - RunPod panelinden kontrol ediniz.")
        time.sleep(3)
    print(f"Pod durdu: {pod_id} - GPU ücreti durdu, yalnız ağ diski işliyor.")


def cmd_env(_args: argparse.Namespace) -> None:
    urls = write_env_urls(get_pod())
    print(f"local/.env.bulut güncellendi: {urls['MAHIR_RAG_URL']} , {urls['MAHIR_OCR_URL']}")


def cmd_ssh(args: argparse.Namespace) -> None:
    ip, port = ssh_target(get_pod())
    command = ["ssh", "-p", str(port), "-o", "StrictHostKeyChecking=accept-new", f"root@{ip}"]
    if args.command:
        # Komutlu (betikten) kullanımda anahtar reddedilirse parola istemine
        # düşüp asılı kalmasın; sshd zaten parolayı kabul etmiyor.
        command[1:1] = ["-o", "BatchMode=yes"]
        command.append(" ".join(args.command))
    sys.exit(subprocess.call(command))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MAHİR - RunPod pod yardımcısı")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("availability", help="ağ diski destekleyen AB merkezlerinde GPU stoku").set_defaults(func=cmd_availability)
    sub.add_parser("init-secrets", help="local/.env.bulut + iki parola").set_defaults(func=cmd_init_secrets)

    create = sub.add_parser("create", help="ağ diski + pod oluştur")
    create.add_argument("--image", required=True, help="ghcr.io/peykan1071/mahir-gpu:<git-sha> (latest DEĞİL)")
    create.add_argument("--dc", required=True, help="veri merkezi, ör. EU-RO-1")
    create.add_argument("--gpu", action="append", help="öncelik sırasıyla GPU kimliği (tekrarlanabilir)")
    create.add_argument("--volume-gb", type=int, default=30)
    create.add_argument("--name", default="mahir-gpu")
    create.add_argument("--ssh-key", default=str(SSH_PUBLIC_KEY_FILE))
    create.add_argument("--timeout", type=float, default=1800, help="RUNNING için bekleme (ilk çekim uzun sürer)")
    create.add_argument("--new-pod", action="store_true", help="kayıtlı pod varken aynı diskle yeni pod")
    create.add_argument("--dry-run", action="store_true", help="gövdeyi (parolalar gizli) göster, hiçbir şey oluşturma")
    create.set_defaults(func=cmd_create)

    start = sub.add_parser("start", help="pod'u başlat, .env.bulut'u güncelle")
    start.add_argument("--wait-health", action="store_true")
    start.add_argument("--timeout", type=float, default=900)
    start.add_argument("--health-timeout", type=float, default=1800)
    start.set_defaults(func=cmd_start)

    stop = sub.add_parser("stop", help="pod'u durdur (GPU ücreti durur)")
    stop.add_argument("--timeout", type=float, default=180)
    stop.set_defaults(func=cmd_stop)

    sub.add_parser("status", help="durum, IP, portlar").set_defaults(func=cmd_status)
    sub.add_parser("env", help="güncel adresleri local/.env.bulut'a yaz").set_defaults(func=cmd_env)

    ssh = sub.add_parser("ssh", help="güncel portla SSH (komut verilirse etkileşimsiz)")
    ssh.add_argument("command", nargs=argparse.REMAINDER)
    ssh.set_defaults(func=cmd_ssh)
    return parser


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if getattr(args, "gpu", "unset") is None:
        args.gpu = list(DEFAULT_GPUS)
    try:
        args.func(args)
    except (RunPodError, PodNotReady) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
