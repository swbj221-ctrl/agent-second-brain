param(
    [int]$Port = 18789
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Details
    )
    $status = if ($Ok) { "OK" } else { "FAIL" }
    Write-Host ("[{0}] {1} - {2}" -f $status, $Name, $Details)
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

Add-PathEntry -Entry "C:\Program Files\nodejs"
Add-PathEntry -Entry "$env:APPDATA\npm"

$repoRoot = Split-Path -Parent $PSScriptRoot

$openclawCmd = Get-Command openclaw -ErrorAction SilentlyContinue
if ($openclawCmd) {
    Write-Check -Name "openclaw command" -Ok $true -Details $openclawCmd.Source
} else {
    $fallback = "$env:APPDATA\npm\openclaw.cmd"
    Write-Check -Name "openclaw command" -Ok (Test-Path -LiteralPath $fallback) -Details $fallback
}

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Write-Check -Name "gateway port" -Ok $true -Details "listening on $Port (PID=$($conn.OwningProcess))"
} else {
    Write-Check -Name "gateway port" -Ok $false -Details "not listening on $Port"
}

$healthOk = $false
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -Method Get -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
        $healthOk = $true
    }
} catch {
    $healthOk = $false
}
Write-Check -Name "gateway http probe" -Ok $healthOk -Details "http://127.0.0.1:$Port/"

$smokes = @(
    "scripts\openclaw_command_dispatch_smoke.py",
    "scripts\openclaw_voice_dispatch_smoke.py",
    "scripts\model_routing_smoke.py"
)
foreach ($rel in $smokes) {
    $path = Join-Path $repoRoot $rel
    Write-Check -Name "smoke file" -Ok (Test-Path -LiteralPath $path) -Details $rel
}
