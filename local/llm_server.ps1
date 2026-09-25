<#
.SYNOPSIS
  MAHİR yerel LLM sunucusu: llama.cpp llama-server ile Qwen3-4B-Instruct-2507 GGUF Q4_K_M.

.DESCRIPTION
  local/.env'deki LLAMA_SERVER_EXE, LLM_HF_REPO / LLM_GGUF_PATH, LLM_GPU_LAYERS,
  LLM_CONTEXT_WINDOW, LLM_PORT, LLM_KV_CACHE_TYPE, LLM_THREADS ve MODEL_NAME
  ayarlarını okur; kabukta zaten tanımlı bir değişken .env'i ezer. Sunucu ön
  planda çalışır (Ctrl+C durdurur) ve http://127.0.0.1:<LLM_PORT>/v1 altında
  OpenAI uyumlu /chat/completions ve /models sunar - rag_service.py'nin
  LLM_BASE_URL'i buraya bakar.

  Varsayılan model 4 GB VRAM'e tek başına sığar (ölçüldü: 3,1 GB ayrılmış bellek;
  36 katman GPU'da, KV 8k q8_0 ≈ 0,6 GB). Tüm katmanlar GPU'da (-ngl 99), KV
  önbelleği q8_0 + flash attention, tek yuva (--parallel 1) ki 8k pencere
  bölünmesin, küçük tamponlar (-b 512 -ub 256). Başlangıçta "CUDA out of memory"
  görürseniz LLM_GPU_LAYERS'ı düşürün (katman başına ≈ 85 MB ağırlık + KV).

.PARAMETER DryRun
  Komutu çalıştırmadan yalnız yazdırır.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File local/llm_server.ps1
  powershell -ExecutionPolicy Bypass -File local/llm_server.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$LocalDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- .env'i yükle (kabuktaki değerler öncelikli) ---
$EnvFile = Join-Path $LocalDir ".env"
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $eq = $trimmed.IndexOf("=")
        if ($eq -lt 1) { continue }
        $key = $trimmed.Substring(0, $eq).Trim()
        $value = $trimmed.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if (-not (Test-Path "Env:$key")) { Set-Item -Path "Env:$key" -Value $value }
    }
}

function Get-Setting([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($null -eq $value -or $value.Trim() -eq "") { return $Default }
    return $value.Trim()
}

# --- llama-server.exe ---
$Exe = Get-Setting "LLAMA_SERVER_EXE" ""
if ($Exe -eq "") { $Exe = Join-Path $LocalDir "llama.cpp/llama-server.exe" }
# Göreli yol (.env'de "local/llama.cpp/...") repo köküne göre çözülür - betiğin
# hangi dizinden çağrıldığı fark etmez.
if (-not [System.IO.Path]::IsPathRooted($Exe)) { $Exe = Join-Path (Split-Path -Parent $LocalDir) $Exe }
if (-not (Test-Path $Exe)) {
    Write-Error @"
llama-server.exe bulunamadı: $Exe
İndirme: https://github.com/ggml-org/llama.cpp/releases (b10976 ve üstü)
  1) llama-bNNNNN-bin-win-cuda-12.4-x64.zip
  2) cudart-llama-bin-win-cuda-12.4-x64.zip   (CUDA runtime DLL'leri)
İkisini de local/llama.cpp/ klasörüne açın ya da .env'de LLAMA_SERVER_EXE ile yolu verin.
"@
    exit 1
}

# --- Model kaynağı ---
$GgufPath = Get-Setting "LLM_GGUF_PATH" ""
$HfRepo = Get-Setting "LLM_HF_REPO" "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
if ($GgufPath -ne "") {
    if (-not [System.IO.Path]::IsPathRooted($GgufPath)) { $GgufPath = Join-Path (Split-Path -Parent $LocalDir) $GgufPath }
    if (-not (Test-Path $GgufPath)) { Write-Error "LLM_GGUF_PATH bulunamadı: $GgufPath"; exit 1 }
    $ModelArgs = @("-m", $GgufPath)
    $ModelLabel = $GgufPath
} else {
    # `-hf depo:kuant`: llama.cpp dosyayı HF'den indirip önbelleğe alır (tek seferlik ~2,5 GB).
    $ModelArgs = @("-hf", $HfRepo)
    $ModelLabel = "hf:$HfRepo"
}

# --- Çalışma parametreleri ---
$Port = Get-Setting "LLM_PORT" "8080"
$Ctx = Get-Setting "LLM_CONTEXT_WINDOW" "8192"
$GpuLayers = Get-Setting "LLM_GPU_LAYERS" "99"
$KvType = Get-Setting "LLM_KV_CACHE_TYPE" "q8_0"
$Alias = Get-Setting "MODEL_NAME" "qwen3-4b-instruct-2507-q4_k_m"
$Threads = Get-Setting "LLM_THREADS" "0"
if ([int]$Threads -le 0) {
    $physical = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum
    if (-not $physical -or $physical -lt 1) { $physical = [Math]::Max(1, [Environment]::ProcessorCount / 2) }
    $Threads = [string][int]$physical
}

$Args = @(
    "--host", "127.0.0.1",
    "--port", $Port,
    "-c", $Ctx,
    "-ngl", $GpuLayers,
    "-t", $Threads,
    "-fa", "on",                       # q8_0 V-önbelleği flash attention gerektirir
    "--cache-type-k", $KvType,
    "--cache-type-v", $KvType,
    "--parallel", "1",                 # tek yuva: -c bölünmesin, KV bütçesi öngörülebilir kalsın
    "-b", "512", "-ub", "256",         # küçük hesap tamponları (VRAM)
    "--jinja",                         # GGUF'a gömülü Qwen2.5 sohbet şablonunu tam uygular
    "--alias", $Alias,                 # /v1/models bu adı döndürür (rag_service /health)
    "--no-webui"
) + $ModelArgs

Write-Host "llama-server: $Exe"
Write-Host "model       : $ModelLabel"
Write-Host "ayar        : port=$Port ctx=$Ctx ngl=$GpuLayers kv=$KvType threads=$Threads alias=$Alias"
Write-Host "komut       : `"$Exe`" $($Args -join ' ')"
if ($DryRun) { exit 0 }

& $Exe @Args
exit $LASTEXITCODE
