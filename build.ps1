<#
.SYNOPSIS
    Build LocalWhisper: PyInstaller bundle plus Inno Setup installer.

.EXAMPLE
    .\build.ps1
#>

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host ""
Write-Host "LocalWhisper build" -ForegroundColor Cyan
Write-Host ""

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "Virtual environment not found. Expected: $venvPy"
    exit 1
}
Write-Host "Python: $venvPy"

Write-Host ""
Write-Host "[1/2] Running PyInstaller..." -ForegroundColor Yellow
& $venvPy -m PyInstaller localwhisper.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit $LASTEXITCODE)."
    exit 1
}

$bundleSize = (Get-ChildItem "$Root\dist\LocalWhisper" -Recurse | Measure-Object Length -Sum).Sum
$bundleMB = [math]::Round($bundleSize / 1MB, 1)
Write-Host "Bundle ready: dist\LocalWhisper ($bundleMB MB)" -ForegroundColor Green

Write-Host ""
Write-Host "[2/2] Building installer with Inno Setup..." -ForegroundColor Yellow
$iscc = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 not found; skipping installer step." -ForegroundColor Yellow
    Write-Host "The standalone app folder is already at: dist\LocalWhisper"
    exit 0
}

& $iscc "$Root\installer.iss"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup failed (exit $LASTEXITCODE)."
    exit 1
}

$setupExe = Join-Path $Root "dist\LocalWhisper-Setup.exe"
$setupSize = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)

Write-Host ""
Write-Host "Installer ready: dist\LocalWhisper-Setup.exe" -ForegroundColor Green
Write-Host "Size: $setupSize MB"
Write-Host ""
