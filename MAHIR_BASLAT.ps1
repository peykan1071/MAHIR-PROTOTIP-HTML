$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverScript = Join-Path $projectRoot "backend\run_file_receiver.py"
$secretsFile = Join-Path $projectRoot "secrets.local.txt"

if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
    throw "MAHİR sunucu dosyası bulunamadı: $serverScript"
}

# Yerel OCR/RAG anahtarlarını yalnız bu süreç için yükler. Değerler ekrana
# yazdırılmaz ve yalnızca beklenen iki değişkene izin verilir.
if (Test-Path -LiteralPath $secretsFile -PathType Leaf) {
    $allowedSecrets = @("MAHIR_OCR_SHARED_SECRET", "MAHIR_RAG_SHARED_SECRET")
    foreach ($line in Get-Content -LiteralPath $secretsFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $separator = $trimmed.IndexOf("=")
        if ($separator -lt 1) {
            throw "secrets.local.txt içinde geçersiz bir satır var."
        }
        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim()
        if ($name -notin $allowedSecrets) {
            throw "secrets.local.txt içinde izin verilmeyen değişken var: $name"
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::1", "::") } |
    Select-Object -First 1
if ($listener) {
    $existingPid = [int]$listener.OwningProcess
    if ($existingPid -le 0) {
        throw "8000 portunun sahibi güvenli biçimde belirlenemedi. Bilgisayarı yeniden başlatıp tekrar deneyin."
    }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/index.html" -UseBasicParsing -TimeoutSec 3
        $serverHeader = [string]$response.Headers["Server"]
    }
    catch {
        $serverHeader = ""
    }

    if ($serverHeader -notmatch "MAHIRFileReceiver") {
        throw "8000 portu MAHİR dışında bir uygulama tarafından kullanılıyor (PID: $existingPid). Güvenlik için süreç kapatılmadı."
    }

    Write-Host "Önceki MAHİR sunucusu durduruluyor (PID: $existingPid)..." -ForegroundColor Yellow
    Stop-Process -Id $existingPid -ErrorAction Stop
    Start-Sleep -Milliseconds 800
}

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Executable @Arguments -c "import sys" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $previousErrorPreference
    }
}

$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pythonCommand -and (Test-PythonCommand -Executable $pythonCommand.Source -Arguments @("-3"))) {
    $pythonExecutable = $pythonCommand.Source
    $pythonArguments = @("-3", $serverScript)
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and (Test-PythonCommand -Executable $pythonCommand.Source)) {
        $pythonExecutable = $pythonCommand.Source
        $pythonArguments = @($serverScript)
    }
    else {
        $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if (-not (Test-Path -LiteralPath $bundledPython -PathType Leaf)) {
            throw "Çalışan bir Python 3 bulunamadı. Python kurulumunu kontrol edin."
        }
        $pythonExecutable = $bundledPython
        $pythonArguments = @($serverScript)
    }
}

Write-Host "MAHİR doğru proje klasöründen başlatılıyor:" -ForegroundColor Green
Write-Host $projectRoot
Write-Host "Tarayıcı adresi: http://127.0.0.1:8000/index.html" -ForegroundColor Cyan
Write-Host "Sunucuyu durdurmak için Ctrl+C kullanın.`n"

& $pythonExecutable @pythonArguments
