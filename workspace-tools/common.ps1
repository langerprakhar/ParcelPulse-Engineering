# Shared helpers for the ParcelPulse workspace scripts. Dot-source it:
#   . (Join-Path $PSScriptRoot 'common.ps1')
#
# Written for Windows PowerShell 5.1 and PowerShell 7.

Set-StrictMode -Version Latest

$script:WorkspaceRoot = Split-Path -Parent $PSScriptRoot

$script:Components = [ordered]@{
    api    = 'api'
    web    = 'web'
    worker = 'worker'
    infra  = 'infra'
}

function Get-ComponentPath {
    <# Absolute path of one of the component directories (api, web, worker, infra). #>
    param([Parameter(Mandatory)] [ValidateSet('api', 'web', 'worker', 'infra')] [string]$Name)
    $path = Join-Path $script:WorkspaceRoot $script:Components[$Name]
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Component directory not found: $path. workspace-tools must sit at the root of the ParcelPulse repository."
    }
    return $path
}

function Test-CommandAvailable {
    param([Parameter(Mandatory)] [string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory)] [string]$Name, [string]$Hint = '')
    if (-not (Test-CommandAvailable $Name)) {
        $message = "Required command '$Name' was not found on PATH."
        if ($Hint) { $message += " $Hint" }
        throw $message
    }
}

function Assert-DockerRunning {
    <# Fails with a clear message when Docker is missing or its daemon is not running. #>
    Assert-CommandAvailable 'docker' 'Install Docker Desktop: https://www.docker.com/products/docker-desktop/'
    # cmd.exe does the redirection so that PowerShell 5.1 does not turn stderr into errors.
    cmd.exe /d /c 'docker info >nul 2>&1'
    if ($LASTEXITCODE -ne 0) {
        throw 'ENVIRONMENT BLOCKER: the Docker daemon is not running. Start Docker Desktop and try again.'
    }
}

function Invoke-Logged {
    <#
        Runs a command line in a directory through cmd.exe, with stdout and stderr
        written to a log file. Returns the exit code. Nothing is thrown for a
        non-zero exit code; the caller decides what it means.
    #>
    param(
        [Parameter(Mandatory)] [string]$CommandLine,
        [Parameter(Mandatory)] [string]$WorkingDirectory,
        [Parameter(Mandatory)] [string]$LogFile
    )
    $logDirectory = Split-Path -Parent $LogFile
    if (-not (Test-Path -LiteralPath $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }
    Push-Location -LiteralPath $WorkingDirectory
    try {
        # Parentheses make the redirection apply to the whole line, not just its last command.
        cmd.exe /d /c "( $CommandLine ) > `"$LogFile`" 2>&1"
        return $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

function Invoke-Streaming {
    <# Runs a command line in a directory with its output shown live. Returns the exit code. #>
    param(
        [Parameter(Mandatory)] [string]$CommandLine,
        [Parameter(Mandatory)] [string]$WorkingDirectory
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        # Out-Host keeps the command's output out of this function's return value.
        cmd.exe /d /c "$CommandLine 2>&1" | Out-Host
        return $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

function Get-StackUrls {
    <# Where the local stack is published, honouring overrides in infra\.env. #>
    $ports = @{
        WEB_HOST_PORT        = '3000'
        API_HOST_PORT        = '8000'
        SIMULATOR_HOST_PORT  = '8100'
        MAILPIT_UI_HOST_PORT = '8025'
    }
    $envFile = Join-Path (Get-ComponentPath infra) '.env'
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match '^\s*([A-Z_]+)\s*=\s*(\d+)\s*$' -and $ports.ContainsKey($Matches[1])) {
                $ports[$Matches[1]] = $Matches[2]
            }
        }
    }
    return [ordered]@{
        Web       = "http://localhost:$($ports.WEB_HOST_PORT)"
        Api       = "http://localhost:$($ports.API_HOST_PORT)"
        Simulator = "http://localhost:$($ports.SIMULATOR_HOST_PORT)"
        Mail      = "http://localhost:$($ports.MAILPIT_UI_HOST_PORT)"
    }
}
