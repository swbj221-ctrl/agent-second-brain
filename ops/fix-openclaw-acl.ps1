param(
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Set-Location -LiteralPath $repoRoot

    Write-Host "[ops] ACL quick-fix for OpenClaw files (no secrets shown)." -ForegroundColor Cyan
    Write-Host "[ops] Targets: %USERPROFILE%\\.openclaw, openclaw.json, credentials, auth-profiles.json" -ForegroundColor Cyan

    $args = @()
    if ($WhatIf) { $args += "-DryRun" }

    & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\harden_openclaw_acl.ps1" @args | Out-Host
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($WhatIf) {
        Write-Host "[ops] Dry-run completed (ACLs not changed)." -ForegroundColor Yellow
    } else {
        Write-Host "[ops] ACL fix completed. Verify with: openclaw status" -ForegroundColor Green
    }
    exit 0
} catch {
    Write-Host "[ops] Error fix-openclaw-acl: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
