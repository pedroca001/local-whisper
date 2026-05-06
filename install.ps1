<#
.SYNOPSIS
    LocalWhisper - one-click installer from source.

.DESCRIPTION
    Idempotent: safe to run multiple times.
    - Checks for Python 3.10-3.12.
    - Creates .venv if missing.
    - Detects NVIDIA GPU and installs the right PyTorch (cu128 / cu121 / CPU).
    - Installs the app in editable mode plus the "diarize" extra.
    - Creates a Desktop shortcut.
    - Adds a shortcut to the Windows Startup folder (skip with -NoStartup).

.PARAMETER NoShortcut
    Do not create the Desktop shortcut.

.PARAMETER NoStartup
    Do not add to Windows Startup.

.PARAMETER ForceCpu
    Force PyTorch CPU build even if an NVIDIA GPU is present.

.PARAMETER CudaIndex
    Custom PyTorch wheel index URL (default: auto-detect).
    Examples: https://download.pytorch.org/whl/cu128
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
Step "Checking Python"
$pyExe = $null
foreach ($cmd in @("py -3.12", "py -3.11", "py -3.10", "python")) {
    try {
        $parts = $cmd -split ' '
        $ver = & $parts[0] $parts[1..($parts.Length-1)] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match '^3\.(1[0-2])$') {
            $pyExe = $cmd
            Info "Found: $cmd ($ver)"
            break
        }
    } catch {}
}
if (-not $pyExe) {
    Write-Error "Python 3.10-3.12 not found. Install from https://www.python.org/downloads/ and check 'Add to PATH'."
    exit 1
}

# ---------- 2) venv ----------
Step "Setting up virtualenv (.venv)"
if (-not (Test-Path $VenvPy)) {
    Info "Creating .venv with $pyExe ..."
    $parts = $pyExe -split ' '
    & $parts[0] $parts[1..($parts.Length-1)] -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed."; exit 1 }
    Ok "venv created."
} else {
    Ok ".venv already exists."
}
& $VenvPy -m pip install --quiet --upgrade pip

# ---------- 3) Pick PyTorch index ----------
Step "Selecting PyTorch build"
$torchIndex = $CudaIndex
if (-not $torchIndex) {
    if ($ForceCpu) {
        $torchIndex = "https://download.pytorch.org/whl/cpu"
        Info "Forced CPU build."
    } else {
        $hasNvidia = $false
        $smi = $null
        try {
            $smi = nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
            if ($LASTEXITCODE -eq 0 -and $smi) {
                $hasNvidia = $true
                Info "GPU detected: $smi"
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
            Warn "No NVIDIA GPU detected - installing CPU PyTorch."
        }
    }
}
Info "PyTorch index: $torchIndex"

# ---------- 4) torch (only if missing) ----------
$torchInstalled = $false
& $VenvPy -c "import torch" 2>$null
if ($LASTEXITCODE -eq 0) {
    $torchInstalled = $true
    Ok "torch already installed."
}
if (-not $torchInstalled) {
    Info "Installing torch + torchaudio..."
    & $VenvPy -m pip install --index-url $torchIndex torch torchaudio
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to install torch."; exit 1 }
    Ok "torch installed."
}

# ---------- 5) App + diarize ----------
Step "Installing LocalWhisper (editable) + diarize extra"
& $VenvPy -m pip install -e "$Root[diarize]"
if ($LASTEXITCODE -ne 0) { Write-Error "pip install -e .[diarize] failed."; exit 1 }
Ok "App + diarization installed."

# ---------- 6) Smoke test ----------
Step "Smoke testing imports"
& $VenvPy -c "import localwhisper, faster_whisper, PySide6, pyannote.audio; print('imports OK')"
if ($LASTEXITCODE -ne 0) { Warn "Imports failed - check the log above." }

# ---------- 7) Shortcuts ----------
function New-Shortcut {
    # NOTE: $Args is an automatic variable in PowerShell; using $ArgList instead.
    param([string]$Path, [string]$Target, [string]$ArgList, [string]$WorkDir, [string]$Icon)
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Path)
    $sc.TargetPath = $Target
    $sc.Arguments  = $ArgList
    $sc.WorkingDirectory = $WorkDir
    if ($Icon -and (Test-Path $Icon)) { $sc.IconLocation = $Icon }
    $sc.Save()
}

if (-not $NoShortcut) {
    Step "Creating Desktop shortcut"
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnk = Join-Path $desktop "LocalWhisper.lnk"
    New-Shortcut -Path $lnk -Target $VenvPyw -ArgList "`"$RunPy`"" -WorkDir $Root -Icon $IconIco
    Ok "Shortcut: $lnk"
}

if (-not $NoStartup) {
    Step "Adding to Windows Startup"
    $startup = [Environment]::GetFolderPath('Startup')
    $lnk = Join-Path $startup "LocalWhisper.lnk"
    New-Shortcut -Path $lnk -Target $VenvPyw -ArgList "`"$RunPy`"" -WorkDir $Root -Icon $IconIco
    Ok "Startup: $lnk"
}

Write-Host ""
Write-Host "Installation complete." -ForegroundColor Green
Write-Host ""
Write-Host "Run now:" -ForegroundColor Cyan
Write-Host "    & `"$VenvPyw`" `"$RunPy`""
Write-Host ""
Write-Host "Update later:" -ForegroundColor Cyan
Write-Host "    git pull"
Write-Host "    .\install.ps1   # reapplies deps if pyproject changed"
Write-Host ""
