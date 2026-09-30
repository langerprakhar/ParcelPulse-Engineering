<#
.SYNOPSIS
    Stops the ParcelPulse stack.

.DESCRIPTION
    Runs 'docker compose down' in infra. Data in PostgreSQL and
    Redis is kept unless -RemoveData is given.

.PARAMETER RemoveData
    Also delete the database and queue volumes. Destroys all local ParcelPulse data.

.PARAMETER IncludeTestDatabases
    Also stop the throwaway PostgreSQL/Redis containers that the API and worker
    test suites use (their docker-compose.dev.yml projects).

.EXAMPLE
    .\stop-all.ps1
    .\stop-all.ps1 -RemoveData -IncludeTestDatabases
#>
[CmdletBinding()]
param(
    [switch]$RemoveData,
    [switch]$IncludeTestDatabases
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

try {
    Assert-DockerRunning
    $failed = $false

    $command = 'docker compose down --remove-orphans'
    if ($RemoveData) { $command += ' --volumes' }
    Write-Host "Stopping ParcelPulse ($command) ..."
    $code = Invoke-Streaming -CommandLine $command -WorkingDirectory (Get-ComponentPath infra)
    if ($code -ne 0) {
        Write-Host "docker compose down failed with exit code $code." -ForegroundColor Red
        $failed = $true
    }

    if ($IncludeTestDatabases) {
        foreach ($name in 'api', 'worker') {
            $repo = Get-ComponentPath $name
            if (Test-Path -LiteralPath (Join-Path $repo 'docker-compose.dev.yml')) {
                Write-Host "Stopping the test dependencies of $name ..."
                $code = Invoke-Streaming -CommandLine 'docker compose -f docker-compose.dev.yml down' -WorkingDirectory $repo
                if ($code -ne 0) { $failed = $true }
            }
        }
    }

    if ($failed) { exit 1 }
    if ($RemoveData) { Write-Host 'Stopped. Data volumes were removed.' }
    else { Write-Host 'Stopped. Data volumes were kept; use -RemoveData to delete them.' }
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
