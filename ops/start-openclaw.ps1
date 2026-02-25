param(
    [switch]$Detached = $true,
    [int]$Port = 18789,
    [switch]$KillConflicts
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
    Add-PathEntry -Entry "C:\Program Files\nodejs"
    Add-PathEntry -Entry "$env:APPDATA\npm"
    Write-Host "[ops] Preparing PATH..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\fix-path-node-openclaw.ps1" | Out-Host
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $existing = Get-PortOwner -TargetPort $Port
    if ($existing) {
        Write-Host "[ops] Gateway already listens on port ${Port} (PID=$($existing.Id), $($existing.ProcessName)). Start skipped." -ForegroundColor Green
        exit 0
    }

    if ($KillConflicts) {
        Write-Host "[ops] Cleaning conflicting pollers before start..." -ForegroundColor Cyan
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\kill-telegram-conflicts.ps1" | Out-Host
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    Write-Host "[ops] Starting OpenClaw (OpenClaw-first)..." -ForegroundColor Cyan
    if ($Detached) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_openclaw_stack.ps1" -Detached -Port $Port | Out-Host
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_openclaw_stack.ps1" -Port $Port | Out-Host
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
} catch {
    Write-Host "[ops] Error start-openclaw: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
