param(
    [int]$GatewayPort = 18789,
    [int]$LogTailLines = 120
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
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    [pscustomobject]@{
        Port = $Port
        Pid = $proc.Id
        ProcessName = $proc.ProcessName
        Path = $proc.Path
    }
}

function Redact-SensitiveText {
    param([string[]]$Lines)
    if (-not $Lines) { return @() }
    $joined = ($Lines -join "`n")
    $patterns = @(
        '(?i)(token|api[_-]?key|authorization|bearer)\s*[:=]\s*([^\s`"'';,]+)',
        '(?i)(telegram_bot_token|openai_api_key|deepgram_api_key)\s*[:=]\s*([^\s`"'';,]+)'
    )
    foreach ($p in $patterns) {
        $joined = [regex]::Replace($joined, $p, '$1=[REDACTED]')
    }
    return ($joined -split "`r?`n")
}

function Get-OpenClawStatusSafe {
    $cmd = Get-Command openclaw -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return @("[capture] openclaw command not found in PATH.")
    }
    try {
        $out = & $cmd.Source status 2>&1 | Out-String
        if ([string]::IsNullOrWhiteSpace($out)) { $out = "(no output)" }
        return ($out -split "`r?`n")
    } catch {
        return @("[capture] openclaw status failed: $($_.Exception.Message)")
    }
}

function Get-OpenClawLogsTailSafe {
    param([int]$Lines)
    $cmd = Get-Command openclaw -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return @("[capture] openclaw command not found; logs tail unavailable.")
    }
    try {
        $out = & $cmd.Source logs --tail $Lines 2>&1 | Out-String
        if ([string]::IsNullOrWhiteSpace($out)) { $out = "(no output)" }
        return ($out -split "`r?`n")
    } catch {
        return @(
            "[capture] openclaw logs tail failed or unsupported: $($_.Exception.Message)",
            "[capture] Operator may paste a manual gateway log tail below."
        )
    }
}

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Set-Location -LiteralPath $repoRoot
    Add-PathEntry -Entry "C:\Program Files\nodejs"
    Add-PathEntry -Entry "$env:APPDATA\npm"

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stampIso = (Get-Date).ToString("s")
    $outDir = Join-Path $repoRoot "artifacts\signoff"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $outFile = Join-Path $outDir ("live-signoff-{0}.md" -f $timestamp)

    $owner = Get-PortOwner -Port $GatewayPort
    $statusLines = Redact-SensitiveText (Get-OpenClawStatusSafe)
    $logLines = Redact-SensitiveText (Get-OpenClawLogsTailSafe -Lines $LogTailLines)

    $ownerSummary = if ($owner) {
@"
- Gateway listen port: $($owner.Port)
- Gateway process: $($owner.ProcessName) (PID=$($owner.Pid))
- Gateway path: $($owner.Path)
"@
    } else {
@"
- Gateway listen port: $GatewayPort (not detected as LISTEN in this shell)
"@
    }

    $content = @"
# Live Telegram Sign-off Evidence Capture

- Timestamp (local): $stampIso
- Host: $env:COMPUTERNAME
- Repo: $repoRoot
- Script: ops/capture-live-signoff.ps1

## Gateway Status Snapshot
$ownerSummary

## `openclaw status` (sanitized)
```text
$($statusLines -join "`n")
```

## Recent Gateway Logs Tail (sanitized)
```text
$($logLines -join "`n")
```

## Manual Telegram Acceptance Results (Operator Fill)
- Telegram channel status snapshot:
- /help: PASS/FAIL
- /status: PASS/FAIL
- /plan list: PASS/FAIL
- /plan add Test live: PASS/FAIL
- /diag: PASS/FAIL
- /ping: PASS/FAIL
- /version: PASS/FAIL
- RU voice note: PASS/FAIL
- TTS media send path (valid media): PASS/FAIL/N/A
- TTS fallback path (empty/error -> text, non-fatal): PASS/FAIL/N/A
- Transcript-only warning (no media): PASS/FAIL
- Media > transcript priority: PASS/FAIL
- Final live acceptance result: PASS/FAIL
- Notes:

## Final Sign-off Gating (Reference)
- `GO` requires: live Telegram channel verified + manual command acceptance + manual voice acceptance.
- Otherwise use `GO WITH KNOWN LIMITATIONS` or `NO-GO`.
"@

    Set-Content -LiteralPath $outFile -Value $content -Encoding UTF8
    Write-Host "[capture] Evidence file created: $outFile" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "[capture] Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
