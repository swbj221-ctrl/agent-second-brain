param(
    [int]$Port = 18789,
    [switch]$Detached = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Set-Location -LiteralPath $repoRoot
    Write-Host "[ops] Restart OpenClaw: stop -> kill conflicts -> start -> status" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\stop-openclaw.ps1" -Port $Port -KillConflicts | Out-Host
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Detached) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\start-openclaw.ps1" -Port $Port -Detached -KillConflicts | Out-Host
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\start-openclaw.ps1" -Port $Port -KillConflicts | Out-Host
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & powershell -NoProfile -ExecutionPolicy Bypass -File ".\ops\status-openclaw.ps1" -Port $Port | Out-Host
    exit $LASTEXITCODE
} catch {
    Write-Host "[ops] Error restart-openclaw: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
