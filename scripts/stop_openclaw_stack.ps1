param(
    [int]$Port = 18789
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[stop] $Message"
}

function Add-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Entry)
    if (-not [string]::IsNullOrWhiteSpace($Entry) -and (Test-Path -LiteralPath $Entry)) {
        $parts = @($env:PATH -split ";")
        if ($parts -notcontains $Entry) {
            $env:PATH = "$Entry;$env:PATH"
        }
    }
}

function Resolve-OpenClawCommand {
    $cmd = Get-Command openclaw -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $fallback = "$env:APPDATA\npm\openclaw.cmd"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }
    return $null
}

function Get-PortOwnerPid {
    param([int]$TargetPort)
    $conn = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        return [int]$conn.OwningProcess
    }
    return $null
}

Add-PathEntry -Entry "C:\Program Files\nodejs"
Add-PathEntry -Entry "$env:APPDATA\npm"

$openclawCmd = Resolve-OpenClawCommand
if ($openclawCmd) {
    Write-Step "Requesting graceful stop via: $openclawCmd gateway stop"
    try {
        & $openclawCmd gateway stop | Out-Host
    } catch {
        Write-Step "Graceful stop command failed: $($_.Exception.Message)"
    }
} else {
    Write-Step "OpenClaw command not found on PATH; continuing with port-based stop fallback."
}

Start-Sleep -Seconds 2
$ownerPid = Get-PortOwnerPid -TargetPort $Port
if ($ownerPid) {
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Step "Force stopping PID $ownerPid ($($proc.ProcessName)) on port $Port"
        Stop-Process -Id $ownerPid -Force
    }
}

Start-Sleep -Seconds 1
for ($i = 0; $i -lt 8; $i++) {
    $after = Get-PortOwnerPid -TargetPort $Port
    if (-not $after) {
        Write-Step "Gateway stopped."
        return
    }
    Start-Sleep -Seconds 1
}

Write-Step "Warning: port $Port is still listening after stop attempts. Re-run stop or inspect with openclaw logs --follow."
