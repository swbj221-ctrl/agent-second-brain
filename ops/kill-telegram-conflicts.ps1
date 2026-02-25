param(
    [switch]$WhatIf,
    [switch]$StopAllOpenClawGateways
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-CandidateProcesses {
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    if (-not $all) { return @() }
    return @($all | Where-Object { $_.Name -match '^(python(\.exe)?|openclaw(\.exe)?)$' })
}

function Stop-ByCim {
    param([Parameter(Mandatory = $true)]$Proc)
    $msg = "PID=$($Proc.ProcessId) Name=$($Proc.Name)"
    if ($WhatIf) {
        Write-Host "[ops] WhatIf stop $msg" -ForegroundColor Yellow
        return $true
    }
    try {
        Stop-Process -Id ([int]$Proc.ProcessId) -Force -ErrorAction Stop
        Write-Host "[ops] Stopped $msg" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[ops] Failed stop $msg : $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

try {
    $items = Get-CandidateProcesses
    if (-not $items -or $items.Count -eq 0) {
        Write-Host "[ops] No poller conflicts found." -ForegroundColor Green
        exit 0
    }

    $pythonDb = @()
    $openclawGw = @()
    foreach ($p in $items) {
        $cmd = [string]($p.CommandLine)
        $cmdLower = $cmd.ToLowerInvariant()
        $nameLower = ([string]$p.Name).ToLowerInvariant()
        if ($nameLower.StartsWith("python") -and $cmdLower.Contains("d_brain")) {
            $pythonDb += $p
            continue
        }
        if ($nameLower.StartsWith("openclaw") -and $cmdLower.Contains("gateway")) {
            $openclawGw += $p
            continue
        }
    }

    $stopped = 0
    $failed = 0

    foreach ($p in $pythonDb) {
        if (Stop-ByCim -Proc $p) { $stopped++ } else { $failed++ }
    }

    if ($openclawGw.Count -gt 0) {
        $targets = @()
        if ($StopAllOpenClawGateways) {
            $targets = $openclawGw
        } elseif ($openclawGw.Count -gt 1) {
            $targets = @($openclawGw | Sort-Object ProcessId | Select-Object -Skip 1)
        }
        foreach ($p in $targets) {
            if (Stop-ByCim -Proc $p) { $stopped++ } else { $failed++ }
        }
        if (($openclawGw.Count -eq 1) -and (-not $StopAllOpenClawGateways)) {
            Write-Host "[ops] One openclaw gateway found: kept running (idempotent mode)." -ForegroundColor Cyan
        }
    }

    Write-Host "[ops] Result: stopped=$stopped failed=$failed" -ForegroundColor Cyan
    if ($failed -gt 0) { exit 1 }
    exit 0
} catch {
    Write-Host "[ops] Error kill-telegram-conflicts: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
