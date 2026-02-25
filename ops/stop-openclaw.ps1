param(
    [int]$Port = 18789,
    [switch]$KillConflicts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Set-Location -LiteralPath $repoRoot
    Write-Host "[ops] Stopping OpenClaw..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\stop_openclaw_stack.ps1" -Port $Port | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ops] stop_openclaw_stack.ps1 returned code $LASTEXITCODE" -ForegroundColor Yellow
    }
    if ($KillConflicts) {
        Write-Host "[ops] Cleaning conflicting pollers..." -ForegroundColor Cyan
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\kill-telegram-conflicts.ps1" -StopAllOpenClawGateways | Out-Host
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Host "[ops] Stop completed." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "[ops] Error stop-openclaw: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
