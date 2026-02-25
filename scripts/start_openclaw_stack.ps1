param(
    [switch]$Detached,
    [int]$Port = 18789
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[start] $Message"
}

function Add-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Entry)
    $Entry = ($Entry -replace '^[\"\s]+|[\"\s]+$', '')
    if (-not [string]::IsNullOrWhiteSpace($Entry) -and (Test-Path -LiteralPath $Entry)) {
        $parts = @($env:PATH -split ";")
        if ($parts -notcontains $Entry) {
            $env:PATH = "$Entry;$env:PATH"
        }
    }
}

function Normalize-ProcessPath {
    $parts = @()
    foreach ($part in ($env:PATH -split ";")) {
        if ([string]::IsNullOrWhiteSpace($part)) {
            continue
        }
        $clean = ($part -replace '^[\"\s]+|[\"\s]+$', '')
        if (-not [string]::IsNullOrWhiteSpace($clean)) {
            $parts += $clean
        }
    }
    $env:PATH = ($parts -join ";")
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

function Resolve-RequiredCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$FallbackPath = ""
    )
    try {
        $cmd = Get-Command $Name -ErrorAction Stop
        return $cmd.Source
    } catch {
        if ($FallbackPath -and (Test-Path -LiteralPath $FallbackPath)) {
            return $FallbackPath
        }
        throw "Required command '$Name' was not found in PATH. PATH=$env:PATH"
    }
}

function Invoke-OpenClaw {
    param(
        [Parameter(Mandatory = $true)][string]$CommandPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    if ($CommandPath.ToLowerInvariant().EndsWith(".ps1")) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $CommandPath @Arguments
    } else {
        & $CommandPath @Arguments
    }
}

function Start-OpenClawDetached {
    param(
        [Parameter(Mandatory = $true)][string]$CommandPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    if ($CommandPath.ToLowerInvariant().EndsWith(".ps1")) {
        $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $CommandPath) + $Arguments
        return Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WorkingDirectory $WorkingDirectory -PassThru
    }
    return Start-Process -FilePath $CommandPath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -PassThru
}

function Get-PortProcess {
    param([int]$TargetPort)
    $conn = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        return Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    }
    return $null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

Write-Step "Preparing PATH entries for Node and npm globals."
Normalize-ProcessPath
Add-PathEntry -Entry "C:\Program Files\nodejs"
Add-PathEntry -Entry "$env:APPDATA\npm"

$venvActivate = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path -LiteralPath $venvActivate) {
    Write-Step "Activating venv: $venvActivate"
    . $venvActivate
} else {
    Write-Step "No .venv found, continuing with current interpreter."
}

$env:PYTHONPATH = "src"
$env:D_BRAIN_TELEGRAM_DISABLED = "1"
Write-Step "Set PYTHONPATH=src and D_BRAIN_TELEGRAM_DISABLED=1"

$nodeCmd = Resolve-RequiredCommand -Name "node"
$openclawCmd = Resolve-RequiredCommand -Name "openclaw" -FallbackPath "$env:APPDATA\npm\openclaw.cmd"
Write-Step "Detected node.exe: $nodeCmd"
Write-Step "Using OpenClaw command: $openclawCmd"

$portOwner = Get-PortProcess -TargetPort $Port
if ($portOwner) {
    throw "Port $Port is already in use by PID $($portOwner.Id) ($($portOwner.ProcessName)). Stop it first."
}

Write-Step "Starting OpenClaw gateway on port $Port"
if ($Detached) {
    $proc = Start-OpenClawDetached -CommandPath $openclawCmd -Arguments @("gateway", "--port", "$Port") -WorkingDirectory $repoRoot
    Start-Sleep -Seconds 2
    $running = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($running) {
        Write-Step "Detached mode started. PID=$($proc.Id)"
        $bound = $false
        for ($i = 0; $i -lt 6; $i++) {
            if (Get-PortProcess -TargetPort $Port) {
                $bound = $true
                break
            }
            Start-Sleep -Seconds 1
        }
        if ($bound) {
            Write-Step "Gateway is listening on port $Port."
        } else {
            Write-Step "Detached process started, but port $Port is not listening yet."
            Write-Step "Check logs with: openclaw logs --follow"
        }
    } else {
        Write-Step "Detached process exited early. Check logs with: openclaw logs --follow"
        Write-Step "Try foreground mode: powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1"
    }
} else {
    Write-Step "Foreground mode. Press Ctrl+C to stop."
    Invoke-OpenClaw -CommandPath $openclawCmd -Arguments @("gateway", "--port", "$Port")
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        throw "OpenClaw gateway exited with code $LASTEXITCODE in foreground mode."
    }
}

if ($Detached) {
    Write-Host ""
    Write-Host "Hints:"
    Write-Host "- Dashboard: http://127.0.0.1:$Port"
    Write-Host "- Verify status: openclaw status"
    Write-Host "- Stop gateway: scripts\stop_openclaw_stack.ps1"
}
