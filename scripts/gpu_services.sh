#!/usr/bin/env bash
# MAHİR GPU katmanı (Linux / RunPod pod'u): llama-server, RAG servisi, OCR işçisi.
#
# `MAHIR_BASLAT.ps1`in GPU kısmının karşılığıdır, aynı toleransla: bir servis
# zaten çalışıyorsa (portu dinleniyorsa) atlanır ve hiçbir arıza betiği
# düşürmez - eksik servis, öğretmenin göreceği anlaşılır bir hataya dönüşür.
#
# Kullanımı (pod içinde, depo kökünden):
#     scripts/gpu_services.sh start      # eksik olanları başlat
#     scripts/gpu_services.sh status     # hangi port dinleniyor
#     scripts/gpu_services.sh stop       # bu betiğin başlattıklarını durdur
#     scripts/gpu_services.sh restart    # kod çekildikten sonraki döngü
#
# Geliştirme döngüsü (asıl amaç - imaja HİÇ dokunmadan):
#     git pull && scripts/gpu_services.sh restart
#
# NOT: Web katmanı (:8000) burada BAŞLATILMAZ. O, VPS'te çalışır ve pod'a
# `MAHIR_RAG_URL` / `MAHIR_OCR_URL` ile bağlanır.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${MAHIR_PYTHON:-python3}"
# Yorumlayıcı BAŞTA doğrulanır. Aksi hâlde `port_open` çağrıları 127 ile
# düşer ve bu "port kapalı" gibi okunur: `status` her şeyi kapalı gösterir,
# `stop` portların boşaldığını sanır, `restart` da "zaten çalışıyor" deyip
# yeni kodu HİÇ yüklemez. Sessiz ve pahalı bir tuzak - önden kapatıyoruz.
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python yorumlayıcısı bulunamadı: $PYTHON" >&2
    echo "MAHIR_PYTHON ile yolunu veriniz (ör. MAHIR_PYTHON=python)." >&2
    exit 127
fi
LOG_DIR="${MAHIR_LOG_DIR:-$REPO_ROOT/logs}"
RUN_DIR="${MAHIR_RUN_DIR:-$REPO_ROOT/logs/run}"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Pod varsayılanları: servisler konteyner dışından erişilebilir olmalı.
# Kodun varsayılanı 127.0.0.1 - ağa açılmak AÇIK bir karar (bkz.
# `backend/run_ocr_worker.py`, `local/rag_common.py`).
export RAG_SERVICE_HOST="${RAG_SERVICE_HOST:-0.0.0.0}"
export MAHIR_OCR_WORKER_HOST="${MAHIR_OCR_WORKER_HOST:-0.0.0.0}"

# GPU'da 24 GB var: gömme ve reranker CPU'da kalmasın. Yerelde (6 GB kart)
# bunlar CPU'ya zorlanıyor; asıl gecikme kazancı burada (reranker istem
# başına ~8 sn -> ~0,2 sn). `local/.env` bu değerleri EZEBİLİR.
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-cuda}"
export RERANKER_DEVICE="${RERANKER_DEVICE:-cuda}"

RAG_PORT="${RAG_SERVICE_PORT:-8001}"
OCR_PORT="${MAHIR_OCR_WORKER_PORT:-8002}"
LLM_PORT_VALUE="${LLM_PORT:-8080}"

port_open() {  # port_open <port>
    "$PYTHON" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(1.0)
    sys.exit(0 if probe.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

start_one() {  # start_one <ad> <port> <log-adi> <komut...>
    local name="$1" port="$2" logname="$3"
    shift 3
    if port_open "$port"; then
        echo "  $name zaten çalışıyor (:$port), atlanıyor."
        return 0
    fi
    local log="$LOG_DIR/$logname.log"
    local pidfile="$RUN_DIR/$logname.pid"
    nohup "$@" >>"$log" 2>&1 &
    echo $! >"$pidfile"
    echo "  $name başlatıldı (:$port, pid $(cat "$pidfile"), log $log)"
}

cmd_start() {
    echo "MAHİR GPU katmanı başlatılıyor ($REPO_ROOT)"
    start_one "LLM" "$LLM_PORT_VALUE" "llama-server" bash "$REPO_ROOT/local/llm_server.sh"
    start_one "RAG" "$RAG_PORT" "rag-service" "$PYTHON" "$REPO_ROOT/local/rag_service.py"
    start_one "OCR" "$OCR_PORT" "ocr-worker" "$PYTHON" "$REPO_ROOT/backend/run_ocr_worker.py"
    echo
    echo "Modeller arka planda yükleniyor (LLM ~10-20 sn, RAG ~1 dk, OCR ~1-2 dk)."
    echo "Hazır olduğunda:  curl -s http://127.0.0.1:$RAG_PORT/health"
}

cmd_stop() {
    echo "MAHİR GPU katmanı durduruluyor"
    local stopped=0
    for pidfile in "$RUN_DIR"/*.pid; do
        [ -e "$pidfile" ] || continue
        local pid
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # Süreç ağacı: llm_server.sh `exec` ettiği için tek pid yeter,
            # Python servisleri de alt süreç doğurmuyor.
            kill "$pid" 2>/dev/null && echo "  durduruldu: $(basename "$pidfile" .pid) (pid $pid)"
            stopped=$((stopped + 1))
        fi
        rm -f "$pidfile"
    done
    [ "$stopped" -eq 0 ] && echo "  (bu betiğin başlattığı çalışan servis yok)"
    # Portların gerçekten boşalmasını bekle; aksi hâlde restart "zaten
    # çalışıyor" deyip yeni kodu HİÇ yüklemez - sessiz ve can sıkıcı bir tuzak.
    local waited=0
    while [ "$waited" -lt 15 ]; do
        if ! port_open "$RAG_PORT" && ! port_open "$OCR_PORT" && ! port_open "$LLM_PORT_VALUE"; then
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "  UYARI: 15 sn sonra hâlâ dinlenen port var; elle kontrol ediniz (status)." >&2
}

cmd_status() {
    for entry in "LLM:$LLM_PORT_VALUE" "RAG:$RAG_PORT" "OCR:$OCR_PORT"; do
        local name="${entry%%:*}" port="${entry##*:}"
        if port_open "$port"; then
            echo "  $name  :$port  DINLENIYOR"
        else
            echo "  $name  :$port  kapalı"
        fi
    done
}

case "${1:-start}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop; cmd_start ;;
    status)  cmd_status ;;
    *)
        echo "Kullanım: $0 {start|stop|restart|status}" >&2
        exit 2
        ;;
esac
