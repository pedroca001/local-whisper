<#
.SYNOPSIS
    Remove os atalhos do Desktop e da inicialização do Windows.
    Não apaga o source nem o .venv (faça isso manualmente se quiser).
#>

$ErrorActionPreference = "SilentlyContinue"

$desktop = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')

foreach ($lnk in @(
    (Join-Path $desktop "LocalWhisper.lnk"),
    (Join-Path $startup "LocalWhisper.lnk")
)) {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "Removido: $lnk" -ForegroundColor Yellow
    }
}

# Mata processo se estiver rodando
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*\LocalWhisper\.venv\*" } |
    Stop-Process -Force

Write-Host ""
Write-Host "Atalhos removidos. Para apagar tudo, delete a pasta do projeto." -ForegroundColor Cyan
