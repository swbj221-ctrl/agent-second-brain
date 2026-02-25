Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Add-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Entry)
    if ([string]::IsNullOrWhiteSpace($Entry)) { return }
    if (-not (Test-Path -LiteralPath $Entry)) { return }
    $parts = @($env:PATH -split ";")
    if ($parts -notcontains $Entry) {
        $env:PATH = "$Entry;$env:PATH"
    }
}

function Test-Cmd {
    param([Parameter(Mandatory = $true)][string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

try {
    Add-PathEntry -Entry "C:\Program Files\nodejs"
    Add-PathEntry -Entry "$env:APPDATA\npm"

    $node = Test-Cmd -Name "node"
    $npm = Test-Cmd -Name "npm"
    $openclaw = Test-Cmd -Name "openclaw"

    Write-Host "[ops] PATH session fix applied (current shell only)." -ForegroundColor Cyan
    Write-Host "[ops] node: " -NoNewline
    Write-Host ($(if ($node) { "OK ($node)" } else { "NOT FOUND" })) -ForegroundColor $(if ($node) { "Green" } else { "Yellow" })
    Write-Host "[ops] npm: " -NoNewline
    Write-Host ($(if ($npm) { "OK ($npm)" } else { "NOT FOUND" })) -ForegroundColor $(if ($npm) { "Green" } else { "Yellow" })
    Write-Host "[ops] openclaw: " -NoNewline
    Write-Host ($(if ($openclaw) { "OK ($openclaw)" } else { "NOT FOUND" })) -ForegroundColor $(if ($openclaw) { "Green" } else { "Yellow" })

    if (-not $openclaw) {
        $fallback = "$env:APPDATA\npm\openclaw.cmd"
        if (Test-Path -LiteralPath $fallback) {
            Write-Host "[ops] Hint: openclaw.cmd exists at $fallback (PATH may need refresh)." -ForegroundColor Yellow
        } else {
            Write-Host "[ops] Hint: install/openclaw CLI and reopen terminal." -ForegroundColor Yellow
        }
    }

    Write-Host "[ops] Permanent PATH hint (User scope):" -ForegroundColor Cyan
    Write-Host '[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\nodejs;$env:APPDATA\npm", "User")'
    exit 0
} catch {
    Write-Host "[ops] Ошибка PATH fix: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

