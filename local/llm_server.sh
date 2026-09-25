#!/usr/bin/env bash
# MAHİR yerel LLM sunucusu (Linux): llama.cpp llama-server + Qwen3-4B-Instruct-2507 GGUF Q4_K_M.
#
# `local/llm_server.ps1`'in birebir karşılığıdır - AYNI ortam değişkenlerini
# okur ve AYNI llama-server bayraklarını kullanır. İkisi birbirinden sapmamalı:
# bir bayrak burada değişirse .ps1'de de değişmeli (ve tersi).
#
# Kullanımı:
#     local/llm_server.sh
#     local/llm_server.sh --dry-run     # komutu yalnız yazdır, çalıştırma
#
# Sunucu ÖN PLANDA çalışır (Ctrl+C durdurur) ve http://127.0.0.1:<LLM_PORT>/v1
# altında OpenAI uyumlu /chat/completions ve /models sunar - `rag_service.py`
# `LLM_BASE_URL` ile buraya bakar.

set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$LOCAL_DIR")"

# --- .env'i yükle (kabuktaki değerler ÖNCELİKLİ, .ps1 ile aynı kural) --------
ENV_FILE="$LOCAL_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#"${line%%[![:space:]]*}"}"          # baştaki boşluklar
        case "$line" in ""|'#'*) continue ;; esac
        key="${line%%=*}"
        value="${line#*=}"
        case "$line" in *=*) ;; *) continue ;; esac
        key="$(printf '%s' "$key" | tr -d '[:space:]')"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        # Tırnaklı değerleri soy ("..." ya da '...')
        case "$value" in
            '"'*'"') value="${value#\"}"; value="${value%\"}" ;;
            "'"*"'") value="${value#\'}"; value="${value%\'}" ;;
        esac
        [ -z "$key" ] && continue
        # Kabukta zaten tanımlıysa dokunma.
        if [ -z "${!key+x}" ]; then
            export "$key=$value"
        fi
    done < "$ENV_FILE"
fi

setting() {  # setting <AD> <varsayilan>
    local name="$1" default="$2" value
    value="${!name:-}"
    value="$(printf '%s' "$value" | tr -d '[:space:]')"
    if [ -z "$value" ]; then printf '%s' "$default"; else printf '%s' "${!name}"; fi
}

# --- llama-server ------------------------------------------------------------
EXE="$(setting LLAMA_SERVER_EXE "")"
if [ -z "$EXE" ]; then
    EXE="$LOCAL_DIR/llama.cpp/llama-server"
fi
# Göreli yol repo köküne göre çözülür - betiğin hangi dizinden çağrıldığı fark etmez.
case "$EXE" in /*) ;; *) EXE="$REPO_ROOT/$EXE" ;; esac
if [ ! -x "$EXE" ]; then
    cat >&2 <<EOF
llama-server bulunamadı (ya da çalıştırma izni yok): $EXE

Linux CUDA derlemesi:
  https://github.com/ggml-org/llama.cpp/releases  ->  llama-bNNNNN-bin-ubuntu-cuda-x64.zip
local/llama.cpp/ klasörüne açın ve chmod +x uygulayın, ya da .env'de
LLAMA_SERVER_EXE ile yolu verin.
EOF
    exit 1
fi

# --- Model kaynağı -----------------------------------------------------------
GGUF_PATH="$(setting LLM_GGUF_PATH "")"
HF_REPO="$(setting LLM_HF_REPO "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M")"
if [ -n "$GGUF_PATH" ]; then
    case "$GGUF_PATH" in /*) ;; *) GGUF_PATH="$REPO_ROOT/$GGUF_PATH" ;; esac
    if [ ! -f "$GGUF_PATH" ]; then
        echo "LLM_GGUF_PATH bulunamadı: $GGUF_PATH" >&2
        exit 1
    fi
    MODEL_ARGS=(-m "$GGUF_PATH")
    MODEL_LABEL="$GGUF_PATH"
else
    # `-hf depo:kuant`: llama.cpp dosyayı HF'den indirip önbelleğe alır
    # (tek seferlik ~2,5 GB). Pod'da HF_HOME ağ diskinde olmalı ki her
    # yeniden başlatmada tekrar inmesin.
    MODEL_ARGS=(-hf "$HF_REPO")
    MODEL_LABEL="hf:$HF_REPO"
fi

# --- Çalışma parametreleri ---------------------------------------------------
PORT="$(setting LLM_PORT "8080")"
CTX="$(setting LLM_CONTEXT_WINDOW "8192")"
GPU_LAYERS="$(setting LLM_GPU_LAYERS "99")"
KV_TYPE="$(setting LLM_KV_CACHE_TYPE "q8_0")"
ALIAS="$(setting MODEL_NAME "qwen3-4b-instruct-2507-q4_k_m")"
THREADS="$(setting LLM_THREADS "0")"
if [ "$THREADS" -le 0 ] 2>/dev/null; then
    # Fiziksel çekirdek sayısı; .ps1'deki aynı gerekçe (mantıksal sayıya
    # eşitlemek CPU çıkarımını genellikle yavaşlatır).
    if command -v lscpu >/dev/null 2>&1; then
        THREADS="$(lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l || true)"
    fi
    if [ -z "${THREADS:-}" ] || [ "$THREADS" -lt 1 ] 2>/dev/null; then
        THREADS="$(( $(nproc 2>/dev/null || echo 2) / 2 ))"
    fi
    [ "$THREADS" -lt 1 ] && THREADS=1
fi

# `--host 127.0.0.1` KASITLI: llama-server'a yalnız aynı makinedeki
# `rag_service.py` konuşur. Pod'da bile dışarı açılmaz - dışarıya açılan
# uçlar :8001 (RAG) ve :8002 (OCR), ikisi de paylaşılan parolayla korunur.
ARGS=(
    --host 127.0.0.1
    --port "$PORT"
    -c "$CTX"
    -ngl "$GPU_LAYERS"
    -t "$THREADS"
    -fa on                      # q8_0 V-önbelleği flash attention gerektirir
    --cache-type-k "$KV_TYPE"
    --cache-type-v "$KV_TYPE"
    --parallel 1                # tek yuva: -c bölünmesin, KV bütçesi öngörülebilir kalsın
    -b 512 -ub 256              # küçük hesap tamponları (VRAM)
    --jinja                     # GGUF'a gömülü sohbet şablonunu tam uygular
    --alias "$ALIAS"            # /v1/models bu adı döndürür (rag_service /health)
    --no-webui
    "${MODEL_ARGS[@]}"
)

echo "llama-server: $EXE"
echo "model       : $MODEL_LABEL"
echo "ayar        : port=$PORT ctx=$CTX ngl=$GPU_LAYERS kv=$KV_TYPE threads=$THREADS alias=$ALIAS"
echo "komut       : $EXE ${ARGS[*]}"
if [ "$DRY_RUN" -eq 1 ]; then
    exit 0
fi

exec "$EXE" "${ARGS[@]}"
