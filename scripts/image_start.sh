#!/usr/bin/env bash
# MAHİR GPU imajının başlangıç betiği - Dockerfile'daki CMD.
#
# Üç iş yapar; hepsi isteğe bağlı ve HİÇBİRİ konteyneri düşürmez (bir adım
# başarısız olursa uyarı basılır, konteyner yine açık kalır ki SSH ya da web
# terminaliyle içeri girilip bakılabilsin):
#
#   1. SSH. `SSH_PUBLIC_KEY` ya da `PUBLIC_KEY` (RunPod bunu hesaptaki
#      anahtarlardan kendisi enjekte ediyor) tanımlıysa anahtar
#      authorized_keys'e yazılır ve sshd başlar. Anahtar yoksa sshd HİÇ
#      başlamaz: parolası kapalı, anahtarsız bir sshd yalnız saldırı yüzeyidir.
#      Neden tam SSH: RunPod'un proxy SSH'si SCP/SFTP'yi desteklemiyor ve
#      uzaktan komutu (`ssh pod 'git pull && ...'`) garanti etmiyor; geliştirme
#      döngüsü tam olarak buna dayanıyor. Ayrıca her sağlayıcıda çalışır.
#
#   2. Host anahtarları KALICI diskte. Konteyner diski her oturumda silindiği
#      için açılışta üretilen anahtar her seferinde değişir ve istemci
#      "REMOTE HOST IDENTIFICATION HAS CHANGED" diyerek bağlanmayı reddederdi.
#
#   3. MAHIR_AUTOSTART=1 ve kod kalıcı diskteyse GPU servisleri başlar.
#      `git pull` YAPILMAZ: yeni kodu dağıtmak bilinçli bir eylem kalmalı.
#
# Sonunda `sleep infinity` ile konteyner açık tutulur.

set -uo pipefail

WORKSPACE="${MAHIR_WORKSPACE:-/workspace}"
REPO_DIR="${MAHIR_REPO_DIR:-$WORKSPACE/MAHIR-PROTOTIP-HTML}"
HOST_KEY_DIR="${MAHIR_SSH_HOST_KEY_DIR:-$WORKSPACE/.ssh-host-keys}"
SSHD=/usr/sbin/sshd

log() { echo "[mahir-start] $*"; }

start_sshd() {
    local keys=""
    local candidate
    for candidate in "${SSH_PUBLIC_KEY:-}" "${PUBLIC_KEY:-}"; do
        [ -n "$candidate" ] && keys+="$candidate"$'\n'
    done
    if [ -z "$keys" ]; then
        log "SSH anahtarı yok (SSH_PUBLIC_KEY / PUBLIC_KEY) - sshd başlatılmadı."
        return 0
    fi
    if [ ! -x "$SSHD" ]; then
        log "UYARI: $SSHD yok - SSH atlandı (imajda openssh-server kurulu değil)."
        return 0
    fi

    mkdir -p /root/.ssh /run/sshd
    chmod 700 /root/.ssh
    touch /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    # Tekrarsız ekle: aynı anahtar her açılışta çoğalmasın. RunPod'un
    # PUBLIC_KEY'i birden çok satır taşıyabilir.
    local key
    while IFS= read -r key; do
        key="${key%$'\r'}"
        [ -z "$key" ] && continue
        grep -qxF -- "$key" /root/.ssh/authorized_keys \
            || printf '%s\n' "$key" >> /root/.ssh/authorized_keys
    done <<< "$keys"

    if ls "$HOST_KEY_DIR"/ssh_host_*_key >/dev/null 2>&1; then
        cp "$HOST_KEY_DIR"/ssh_host_* /etc/ssh/
        log "host anahtarları kalıcı diskten alındı ($HOST_KEY_DIR)."
    else
        ssh-keygen -A >/dev/null
        if mkdir -p "$HOST_KEY_DIR" 2>/dev/null && cp /etc/ssh/ssh_host_* "$HOST_KEY_DIR"/ 2>/dev/null; then
            chmod 700 "$HOST_KEY_DIR"
            log "host anahtarları üretildi ve saklandı ($HOST_KEY_DIR)."
        else
            log "UYARI: host anahtarları saklanamadı - sonraki açılışta değişecek."
        fi
    fi
    chmod 600 /etc/ssh/ssh_host_*_key

    if "$SSHD"; then
        log "sshd başladı (:22)."
    else
        log "UYARI: sshd başlamadı."
    fi
}

autostart_services() {
    if [ "${MAHIR_AUTOSTART:-0}" != "1" ]; then
        return 0
    fi
    local services="$REPO_DIR/scripts/gpu_services.sh"
    if [ ! -f "$services" ]; then
        log "MAHIR_AUTOSTART=1 ama kod yok ($REPO_DIR) - ilk kurulumda beklenen durum."
        return 0
    fi
    mkdir -p "$REPO_DIR/logs"
    log "GPU servisleri başlatılıyor (log: $REPO_DIR/logs/autostart.log)."
    bash "$services" start >> "$REPO_DIR/logs/autostart.log" 2>&1 &
}

start_sshd
autostart_services
exec sleep infinity
