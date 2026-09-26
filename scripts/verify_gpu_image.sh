#!/usr/bin/env bash
# MAHİR GPU imajı doğrulaması - HER YENİ ANA MAKİNEDE İLK KOMUT.
#
# Altı kontrol: llama-server çalışıyor mu, paddle ve torch aynı süreçte
# yükleniyor mu, torch GPU'yu görüyor mu, iki çerçeve de doğru cuDNN'i
# yüklüyor mu, paddle GPU'da doğru hesaplıyor mu, Triton çalışma anında
# kernel derleyebiliyor mu. Her biri bu imajın ÖLÇÜLMÜŞ bir kırılma
# noktasından türedi (bkz. Dockerfile, scripts/verify_gpu_image.py).
#
# Kullanımı:
#
#   Ana makinede (pod, VM), depo kökünden:
#       scripts/verify_gpu_image.sh
#
#   Dizüstünde (Windows, Git Bash) - bir imajı YEREL GPU ile sınamak:
#       MSYS_NO_PATHCONV=1 docker run --rm --gpus all \
#           -v "$(pwd -W):/workspace/MAHIR" <imaj> \
#           bash /workspace/MAHIR/scripts/verify_gpu_image.sh
#   MSYS_NO_PATHCONV şart: Git Bash `/opt/...` gibi konteyner yollarını
#   `C:/Program Files/Git/opt/...` diye çeviriyor ve komut yanıltıcı bir
#   "No such file or directory" ile düşüyor (ölçüldü).
#
# Çıkış kodu: 0 = hepsi geçti; aksi hâlde düşen kontrol sayısı.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON="${MAHIR_PYTHON:-python3}"
# gpu_services.sh ile aynı koruma: yorumlayıcı yoksa sonraki her kontrol
# anlamsız biçimde düşer - baştan ve açıkça söyle.
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python yorumlayıcısı bulunamadı: $PYTHON" >&2
    echo "MAHIR_PYTHON ile yolunu veriniz (imajda: /opt/mahir-venv/bin/python)." >&2
    exit 127
fi
LLAMA="${LLAMA_SERVER_EXE:-/opt/llama.cpp/llama-server}"

echo "MAHİR GPU imajı doğrulaması ($REPO_ROOT)"
echo

echo "== GPU"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader \
        | sed 's/^/   /'
else
    echo "   nvidia-smi yok - GPU konteynere verilmemiş olabilir (docker run --gpus all)"
fi

freeze="$(dirname "$(dirname "$PYTHON")")/freeze.txt"
if [ -f "$freeze" ]; then
    echo "   imaj kilidi: $freeze ($(wc -l < "$freeze") paket)"
else
    echo "   imaj kilidi yok ($freeze) - bu imaj freeze.txt eklenmeden önce derlenmiş"
fi
echo

failures=0

echo "== 1/6 llama-server"
if output="$("$LLAMA" --version 2>&1)"; then
    echo "$output" | grep -E "^version|built with" | sed 's/^/   /'
    echo "   TAMAM"
else
    echo "$output" | tail -3 | sed 's/^/   /'
    echo "   DÜŞTÜ  $LLAMA --version"
    failures=$((failures + 1))
fi

"$PYTHON" "$REPO_ROOT/scripts/verify_gpu_image.py"
failures=$((failures + $?))

echo
if [ "$failures" -eq 0 ]; then
    echo "SONUÇ: altı kontrolün hepsi geçti."
else
    echo "SONUÇ: $failures kontrol düştü - servisleri başlatmadan önce çözünüz." >&2
fi
exit "$failures"
