param(
    [string]$OpenClawHome = "$env:USERPROFILE\.openclaw",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[acl] $Message"
}

function Invoke-Icacls {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$IgnoreExitCode
    )
    $argString = @($Path) + $Arguments
    if ($DryRun) {
        Write-Host "DRYRUN> icacls $($argString -join ' ')"
        return
    }
    & icacls $argString | Out-Host
    if ($LASTEXITCODE -ne 0) {
        if ($IgnoreExitCode) {
            Write-Step "Non-zero icacls exit code ignored ($LASTEXITCODE) for: $Path"
            return
        }
        throw "icacls failed for path: $Path"
    }
}

function Harden-PathAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Step "Skip (not found): $Path"
        return
    }

    $isDir = $false
    try {
        $item = Get-Item -LiteralPath $Path -Force
        $isDir = $item.PSIsContainer
    } catch {
        Write-Step "Could not inspect item type (access denied?): $Path. Assuming file ACL format."
    }
    $userPrincipal = "$env:USERDOMAIN\$env:USERNAME"

    Write-Step "Hardening: $Path"
    Invoke-Icacls -Path $Path -Arguments @("/inheritance:r")
    if ($isDir) {
        Invoke-Icacls -Path $Path -Arguments @("/grant:r", "${userPrincipal}:(OI)(CI)F", "SYSTEM:(OI)(CI)F")
    } else {
        Invoke-Icacls -Path $Path -Arguments @("/grant:r", "${userPrincipal}:F", "SYSTEM:F")
    }
    Invoke-Icacls -Path $Path -Arguments @("/remove:g", "Users", "Authenticated Users", "Everyone", "BUILTIN\Users") -IgnoreExitCode
}

$targets = @(
    "$OpenClawHome",
    "$OpenClawHome\openclaw.json",
    "$OpenClawHome\credentials",
    "$OpenClawHome\agents\main\agent\auth-profiles.json",
    "$OpenClawHome\agents\main\sessions\sessions.json"
)

try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Step "Warning: not running elevated. Some ACL updates may fail; rerun in elevated PowerShell if needed."
    }
} catch {
    Write-Step "Could not determine elevation status."
}

Write-Step "OpenClaw ACL hardening started. DryRun=$DryRun"
foreach ($target in $targets) {
    Harden-PathAcl -Path $target
}
Write-Step "Done. Verify with: openclaw status"
