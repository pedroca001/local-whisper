<#
.SYNOPSIS
    LocalWhisper — instalador "one-click" a partir do source.

.DESCRIPTION
    Idempotente: pode rodar quantas vezes quiser.
    - Verifica Python 3.10-3.12.
    - Cria .venv se não existir.
    - Detecta GPU NVIDIA e instala o PyTorch certo (cu128 / cu121 / CPU).
    - Instala o app em modo editable + extra "diarize".
    - Cria atalho no Desktop.
    - Adiciona à pasta Startup do Windows (toggle com -NoStartup).

.PARAMETER NoShortcut
    Não criar atalho no Desktop.

.PARAMETER NoStartup
    Não adicionar à inicialização do Windows.

.PARAMETER ForceCpu
    Forçar PyTorch CPU mesmo com GPU NVIDIA presente.

.PARAMETER CudaIndex
    URL do índice do PyTorch (default: auto-detect).
    Exemplos: https://download.pytorch.org/whl/cu128
              https://download.pytorch.org/whl/cu121
              https://download.pytorch.org/whl/cpu

.EXAMPLE
    .\install.ps1
    .\install.ps1 -NoStartup
    .\install.ps1 -ForceCpu
#>

[CmdletBinding()]
param(
    [switch]$NoShortcut,
    [switch]$NoStartup,
    [switch]$ForceCpu,
    [string]$CudaIndex
)

$ErrorActionPreference = "Stop"
$Root  = $PSScriptRoot
$Venv  = Join-Path $Root ".venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
$VenvPyw = Join-Path $Venv "Scripts\pythonw.exe"
$RunPy = Join-Path $Root "run.py"
$IconIco = Join-Path $Root "localwhisper\resources\icons\icon.ico"

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" -ForegroundColor Gray }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "LocalWhisper installer" -ForegroundColor Cyan
Write-Host "Repo: $Root"

# ---------- 1) Python ----------
Step "Verificando Python"
$pyExe = $null
foreach ($cmd in @("py -3.12", "py -3.11", "py -3.10", "python")) {
    try {
        $parts = $cmd -split ' '
        $ver = & $parts[0] $parts[1..($parts.Length-1)] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match '^3\.(1[0-2])$') {
            $pyExe = $cmd
            Info "Encontrado: $cmd ($ver)"
            break
        }
    } catch {}
}
if (-not $pyExe) {
    Write-Error "Python 3.10-3.12 não encontrado. Instale em https://www.python.org/downloads/ e marque 'Add to PATH'."
    exit 1
}

# ---------- 2) venv ----------
Step "Configurando virtualenv (.venv)"
if (-not (Test-Path $VenvPy)) {
    Info "Criando .venv com $pyExe ..."
    $parts = $pyExe -split ' '
    & $parts[0] $parts[1..($parts.Length-1)] -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Falhou ao criar venv."; exit 1 }
    Ok "venv criado."
} else {
    Ok ".venv já existe."
}
& $VenvPy -m pip install --quiet --upgrade pip

# ---------- 3) Detectar GPU e escolher torch ----------
Step "Detectando GPU para escolher PyTorch"
$torchIndex = $CudaIndex
if (-not $torchIndex) {
    if ($ForceCpu) {
        $torchIndex = "https://download.pytorch.org/whl/cpu"
        Info "Forçado CPU."
    } else {
        $hasNvidia = $false
        try {
            $smi = nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
            if ($LASTEXITCODE -eq 0 -and $smi) {
                $hasNvidia = $true
                Info "GPU detectada: $smi"
            }
        } catch { }
        if ($hasNvidia) {
            if ($smi -match 'RTX\s*50' -or $smi -match 'Blackwell') {
                $torchIndex = "https://download.pytorch.org/whl/cu128"
            } else {
                $torchIndex = "https://download.pytorch.org/whl/cu121"
            }
        } else {
            $torchIndex = "https://download.pytorch.org/whl/cpu"
            Warn "Nenhuma GPU NVIDIA detectada — instalando PyTorch CPU."
        }
    }
}
Info "PyTorch index: $torchIndex"

# ---------- 4) torch (só se faltar) ----------
$torchInstalled = $false
& $VenvPy -c "import torch" 2>$null
if ($LASTEXITCODE -eq 0) {
    $torchInstalled = $true
    Ok "torch já instalado."
}
if (-not $torchInstalled) {
    Info "Instalando torch + torchaudio..."
    & $VenvPy -m pip install --index-url $torchIndex torch torchaudio
    if ($LASTEXITCODE -ne 0) { Write-Error "Falha ao instalar torch."; exit 1 }
    Ok "torch instalado."
}

# ---------- 5) App + diarize ----------
Step "Instalando LocalWhisper (editable) + diarize"
& $VenvPy -m pip install -e "$Root[diarize]"
if ($LASTEXITCODE -ne 0) { Write-Error "pip install -e .[diarize] falhou."; exit 1 }
Ok "App + diarização instalados."

# ---------- 6) Smoke test ----------
Step "Smoke test de imports"
& $VenvPy -c "import localwhisper, faster_whisper, PySide6, pyannote.audio; print('imports OK')"
if ($LASTEXITCODE -ne 0) { Warn "Imports falharam — confira o log acima."; }

# ---------- 7) Atalhos ----------
function New-Shortcut {
    param([string]$Path, [string]$Target, [string]$Args, [string]$WorkDir, [string]$Icon)
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Path)
    $sc.TargetPath = $Target
    $sc.Arguments  = $Args
    $sc.WorkingDirectory = $WorkDir
    if ($Icon -and (Test-Path $Icon)) { $sc.IconLocation = $Icon }
    $sc.Save()
}

if (-not $NoShortcut) {
    Step "Criando atalho no Desktop"
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnk = Join-Path $desktop "LocalWhisper.lnk"
    New-Shortcut -Path $lnk -Target $VenvPyw -Args "`"$RunPy`"" -WorkDir $Root -Icon $IconIco
    Ok "Atalho: $lnk"
}

if (-not $NoStartup) {
    Step "Adicionando à inicialização do Windows"
    $startup = [Environment]::GetFolderPath('Startup')
    $lnk = Join-Path $startup "LocalWhisper.lnk"
    New-Shortcut -Path $lnk -Target $VenvPyw -Args "`"$RunPy`"" -WorkDir $Root -Icon $IconIco
    Ok "Startup: $lnk"
}

Write-Host ""
Write-Host "Instalação concluída." -ForegroundColor Green
Write-Host ""
Write-Host "Para abrir agora:" -ForegroundColor Cyan
Write-Host "    & `"$VenvPyw`" `"$RunPy`""
Write-Host ""
Write-Host "Para atualizar no futuro:" -ForegroundColor Cyan
Write-Host "    git pull"
Write-Host "    .\install.ps1   # reaplica deps se mudarem"
Write-Host ""
