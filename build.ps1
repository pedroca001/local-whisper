<#
.SYNOPSIS
    Build LocalWhisper: PyInstaller bundle plus Inno Setup installer.

.PARAMETER VenvPath
    Virtualenv containing PyInstaller and the runtime dependencies. Defaults to
    .venv in the repository.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
#>

[CmdletBinding()]
param(
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host ""
Write-Host "LocalWhisper build" -ForegroundColor Cyan
Write-Host ""

$Venv = if ($VenvPath) {
    if ([System.IO.Path]::IsPathRooted($VenvPath)) {
        $VenvPath
    } else {
        Join-Path $Root $VenvPath
    }
} else {
    Join-Path $Root ".venv"
}
$venvPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "Virtual environment not found. Expected: $venvPy"
    exit 1
}
Write-Host "Python: $venvPy"

$versionMatch = [regex]::Match(
    (Get-Content (Join-Path $Root "pyproject.toml") -Raw),
    '(?m)^version\s*=\s*"([^"]+)"'
)
if (-not $versionMatch.Success) {
    Write-Error "Could not read the project version from pyproject.toml."
    exit 1
}
$version = $versionMatch.Groups[1].Value
Write-Host "Version: $version"

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

$setupExe = Join-Path $Root "dist\LocalWhisper-Setup-$version.exe"
$setupSize = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)

Write-Host ""
Write-Host "Installer ready: dist\LocalWhisper-Setup-$version.exe" -ForegroundColor Green
Write-Host "Size: $setupSize MB"
Write-Host ""
