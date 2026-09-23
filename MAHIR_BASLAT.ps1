$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverScript = Join-Path $projectRoot "backend\run_file_receiver.py"

if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
    throw "MAHİR sunucu dosyası bulunamadı: $serverScript"
}

# --- Bağımlı yerel servisleri (Qdrant, llama-server, RAG, OCR) ayağa kaldır ---
# Her biri zaten çalışıyorsa (portu dinleniyorsa) atlanır - kullanıcının elle
# açtığı bir pencereye dokunulmaz. Hiçbiri burada hata fırlatmaz: bu servisler
# olmadan da MAHIR web arayüzü ve CSV/Excel akışı çalışır (bkz. README "Sorun
# mu var?" tablosu).
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Test-PortOpen {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::1", "::") } |
        Select-Object -First 1)
}

function Start-MahirWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Command
    )
    if (Test-PortOpen -Port $Port) {
        Write-Host "$Title zaten çalışıyor (:$Port), atlanıyor." -ForegroundColor DarkGray
        return
    }
    # Pencere başlığı, yürütülecek komuttan önce ayrı bir ifade olarak eklenir;
    # `` ` ``$ ile kaçış, bu ifadenin burada değil yeni pencerede çalışmasını sağlar.
    $wrapped = "`$host.ui.RawUI.WindowTitle = '$Title'; $Command"
    try {
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $wrapped
        Write-Host "$Title başlatıldı (:$Port, ayrı pencerede yükleniyor)." -ForegroundColor Cyan
    }
    catch {
        Write-Host "$Title başlatılamadı: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 1) Docker Desktop + Qdrant (:6333)
$dockerReady = $false
try {
    docker info *> $null
    $dockerReady = ($LASTEXITCODE -eq 0)
}
catch { $dockerReady = $false }

if (-not $dockerReady) {
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path -LiteralPath $dockerExe -PathType Leaf) {
        Write-Host "Docker Desktop başlatılıyor..." -ForegroundColor Yellow
        try { Start-Process -FilePath $dockerExe } catch { Write-Host "Docker Desktop başlatılamadı: $($_.Exception.Message)" -ForegroundColor Yellow }
        $deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $deadline -and -not $dockerReady) {
            Start-Sleep -Seconds 3
            try { docker info *> $null; $dockerReady = ($LASTEXITCODE -eq 0) } catch { $dockerReady = $false }
        }
    }
}

if ($dockerReady) {
    $composeFile = Join-Path $projectRoot "local\docker-compose.yml"
    try {
        docker compose -f $composeFile up -d
    }
    catch {
        Write-Host "docker compose başarısız oldu: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    Write-Host "Qdrant başlatılıyor (:6333)..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and -not (Test-PortOpen -Port 6333)) { Start-Sleep -Milliseconds 500 }
    if (Test-PortOpen -Port 6333) {
        Write-Host "Qdrant hazır (:6333)." -ForegroundColor Green
    }
    else {
        Write-Host "Qdrant henüz hazır değil, arka planda yükleniyor olabilir - 'docker compose -f local/docker-compose.yml ps' ile kontrol edin." -ForegroundColor Yellow
    }
}
else {
    Write-Host "Docker Desktop bulunamadı/başlatılamadı - Qdrant ve RAG servisi çalışmayacak (yalnız CSV/Excel akışı ve OCR kullanılabilir)." -ForegroundColor Yellow
}

# 2) llama-server (:8080) - ExecutionPolicy zaten bu pencerede Bypass, script
# doğrudan çağrılır (iç içe ikinci bir powershell süreci açmaya gerek yok).
Start-MahirWindow -Title "MAHIR - LLM (:8080)" -Port 8080 `
    -Command "Set-Location '$projectRoot'; & 'local\llm_server.ps1'"

# 3) RAG servisi (:8001) ve 4) OCR işçisi (:8002) - repo `.venv`'i gerekir
# (paddle/torch/fastapi); yoksa README "Sıfırdan kurulum" adımları izlenmeli.
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    Start-MahirWindow -Title "MAHIR - RAG (:8001)" -Port 8001 `
        -Command "Set-Location '$projectRoot'; & '$venvPython' 'local\rag_service.py'"

    Start-MahirWindow -Title "MAHIR - OCR (:8002)" -Port 8002 `
        -Command "Set-Location '$projectRoot'; & '$venvPython' 'backend\run_ocr_worker.py'"
}
else {
    Write-Host "$venvPython bulunamadı - RAG servisi ve OCR işçisi başlatılamadı. Kurulum için README'deki 'Sıfırdan kurulum' bölümüne bakın." -ForegroundColor Yellow
}

Write-Host "Modeller pencerelerinde arka planda yükleniyor (LLM ~10-20 sn, RAG ~1 dk, OCR ~1-2 dk) - pencereleri kapatmayın.`n" -ForegroundColor DarkGray

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
