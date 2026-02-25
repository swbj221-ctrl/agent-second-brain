param(
    [int]$Port = 18789
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Add-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Entry)
    if ([string]::IsNullOrWhiteSpace($Entry)) { return }
    if (-not (Test-Path -LiteralPath $Entry)) { return }
    $parts = @($env:PATH -split ";")
    if ($parts -notcontains $Entry) { $env:PATH = "$Entry;$env:PATH" }
}

function Get-PortOwner {
    param([int]$TargetPort)
    $conn = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    return Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
}

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Set-Location -LiteralPath $repoRoot

    Write-Host "[ops] OpenClaw status (local, no secrets)." -ForegroundColor Cyan

    Add-PathEntry -Entry "C:\Program Files\nodejs"
    Add-PathEntry -Entry "$env:APPDATA\npm"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "fix-path-node-openclaw.ps1") | Out-Host

    $owner = Get-PortOwner -TargetPort $Port
    if ($owner) {
        Write-Host "[ops] Port ${Port}: LISTEN (PID=$($owner.Id), $($owner.ProcessName))" -ForegroundColor Green
    } else {
        Write-Host "[ops] Port ${Port}: not listening" -ForegroundColor Yellow
    }

    $openclawCmd = Get-Command openclaw -ErrorAction SilentlyContinue
    if ($openclawCmd) {
        Write-Host "[ops] openclaw status:" -ForegroundColor Cyan
        & $openclawCmd.Source status | Out-Host
    } else {
        Write-Host "[ops] openclaw command not found (PATH issue or CLI not installed)." -ForegroundColor Yellow
    }

    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
    $env:PYTHONPATH = "src"
    Write-Host "[ops] d_brain diag:" -ForegroundColor Cyan
    & $python "scripts\ux_cli.py" diag | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ops] CLI diag returned exit code $LASTEXITCODE" -ForegroundColor Yellow
    }

    exit 0
} catch {
    Write-Host "[ops] Error status-openclaw: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
