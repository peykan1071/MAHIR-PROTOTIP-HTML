#!/usr/bin/env bash
# MAHIR OCR işçisini Google Cloud Run'a (GPU) dağıtır.
#
# Google Cloud Shell'de (https://shell.cloud.google.com) çalıştırın - gcloud
# ve Docker önceden kurulu gelir, yerel bilgisayarda hiçbir şey kurmanıza
# gerek yok. `gcloud run deploy --source .` derlemeyi de Cloud Build
# üzerinde sunucu tarafında yaptığı için Cloud Shell'de bile Docker'ı elle
# çalıştırmanıza gerek kalmaz.
#
# Kullanım:
#   git clone --branch ocr-isleri <repo-url> mahir && cd mahir
#   export MAHIR_OCR_SHARED_SECRET="uzun-rastgele-bir-parola"
#   ./cloud-run/deploy.sh
#
# İlk çalıştırmada gcloud sizden proje/bölge seçmenizi isteyebilir; GPU
# desteği için bölgenin NVIDIA L4 sunan bir Cloud Run bölgesi olması gerekir
# (ör. us-central1, europe-west1, europe-west4 - güncel liste için
# `gcloud run regions list` veya resmi Cloud Run GPU belgelerine bakın).
#
# Not: Aşağıdaki bayrak adları bu planın yazıldığı tarihteki resmi Cloud Run
# GPU hızlı başlangıç belgelerine dayanıyor. İlk gerçek dağıtımda gcloud
# sürümünüze göre küçük düzeltmeler gerekebilir (Colab'daki gibi).

set -euo pipefail

SERVICE_NAME="${MAHIR_OCR_SERVICE_NAME:-mahir-ocr-worker}"
REGION="${MAHIR_OCR_REGION:-us-central1}"

if [[ -z "${MAHIR_OCR_SHARED_SECRET:-}" ]]; then
  echo "MAHIR_OCR_SHARED_SECRET ortam değişkenini ayarlayın (worker'ı herkese açık şekilde koruyan parola)." >&2
  exit 1
fi

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --dockerfile cloud-run/Dockerfile \
  --region "$REGION" \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --no-gpu-zonal-redundancy \
  --cpu=4 \
  --memory=16Gi \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=600 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --set-env-vars="MAHIR_OCR_SHARED_SECRET=${MAHIR_OCR_SHARED_SECRET}"

echo
echo "Dağıtım tamamlandı. Yukarıdaki 'Service URL' değerini MAHIR_OCR_REMOTE_URL olarak kullanın."
