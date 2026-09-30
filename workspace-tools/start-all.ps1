<#
.SYNOPSIS
    Builds and starts the whole ParcelPulse stack and waits until it is healthy.

.DESCRIPTION
    Runs 'docker compose up -d --build --wait' in infra: PostgreSQL,
    Redis, the mail sink, the database migration job, the API, the notification
    worker and sweeper, the web dashboard and the carrier simulator.

.PARAMETER NoBuild
    Start from the existing images without rebuilding them.

.PARAMETER Fresh
    Remove the stack and its data volumes first, so the database is built from
    zero by the migrations. Destroys all local ParcelPulse data.

.EXAMPLE
    .\start-all.ps1
    .\start-all.ps1 -Fresh
#>
[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$Fresh
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

try {
    Assert-DockerRunning
    $infra = Get-ComponentPath infra
    # The Compose file builds from the component directories; fail early if one is missing.
    foreach ($name in 'api', 'worker', 'web') { Get-ComponentPath $name | Out-Null }

    if ($Fresh) {
        Write-Host 'Removing the existing stack and its data volumes ...'
        $code = Invoke-Streaming -CommandLine 'docker compose down --volumes --remove-orphans' -WorkingDirectory $infra
        if ($code -ne 0) { throw "docker compose down failed with exit code $code." }
    }

    $command = 'docker compose up -d --wait'
    if (-not $NoBuild) { $command += ' --build' }
    Write-Host "Starting ParcelPulse ($command) ..."
    $started = Get-Date
    $code = Invoke-Streaming -CommandLine $command -WorkingDirectory $infra
    if ($code -ne 0) {
        Write-Host ''
        Write-Host 'The stack did not become healthy. Service status:'
        Invoke-Streaming -CommandLine 'docker compose ps -a' -WorkingDirectory $infra | Out-Null
        throw "docker compose up failed with exit code $code. Inspect a service with: docker compose logs <service>"
    }

    $urls = Get-StackUrls
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    Write-Host ''
    Write-Host "ParcelPulse is up (${seconds}s)."
    Write-Host "  Dashboard          $($urls.Web)"
    Write-Host "  Developer tools    $($urls.Web)/dev"
    Write-Host "  API (OpenAPI)      $($urls.Api)/docs"
    Write-Host "  Carrier simulator  $($urls.Simulator)/docs"
    Write-Host "  Mail sink          $($urls.Mail)"
    Write-Host ''
    Write-Host 'Next: .\smoke-test.ps1 to verify it end to end, .\stop-all.ps1 to stop it.'
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
