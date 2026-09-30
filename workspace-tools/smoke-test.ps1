<#
.SYNOPSIS
    Runs the end-to-end smoke test against the running ParcelPulse stack.

.DESCRIPTION
    Executes infra\tests\smoke\smoke_test.py. It creates a shipment,
    has the carrier simulator send events (including a duplicate and a late,
    out-of-order event), and verifies the API timeline, the shipment status,
    that each notification was delivered exactly once, webhook authentication
    and the health endpoints of the API and the web dashboard.

    By default the test runs in a container on the Compose network
    ('docker compose run --rm smoke'), which needs no Python on this machine.

.PARAMETER FromHost
    Run the test with Python 3.12 on this machine through the published ports
    instead. Also checks that the ports are reachable from the host.

.PARAMETER JsonReport
    With -FromHost: also write the results to this file.

.EXAMPLE
    .\smoke-test.ps1
    .\smoke-test.ps1 -FromHost -JsonReport .\logs\smoke.json

.NOTES
    Exit codes: 0 = every check passed; 1 = at least one check failed;
    2 = the test could not be run (stack not running, Docker or Python missing).
#>
[CmdletBinding()]
param(
    [switch]$FromHost,
    [string]$JsonReport
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

try {
    Assert-DockerRunning
    $infra = Get-ComponentPath infra

    # The smoke test needs the stack; say so plainly instead of failing on a connection error.
    Push-Location -LiteralPath $infra
    try { $running = @(cmd.exe /d /c 'docker compose ps --services --status running 2>nul') }
    finally { Pop-Location }
    $required = 'api', 'web', 'worker', 'carrier-simulator', 'mailpit'
    $missing = @($required | Where-Object { $running -notcontains $_ })
    if ($missing.Count -gt 0) {
        Write-Host "The stack is not running (missing: $($missing -join ', ')). Start it with .\start-all.ps1" -ForegroundColor Red
        exit 2
    }

    if ($FromHost) {
        $urls = Get-StackUrls
        $python = $null
        if (Test-CommandAvailable 'py') { $python = 'py -3.12' }
        elseif (Test-CommandAvailable 'python') { $python = 'python' }
        else {
            Write-Host 'ENVIRONMENT BLOCKER: Python 3.12 was not found. Run without -FromHost to use a container instead.' -ForegroundColor Red
            exit 2
        }
        $command = "$python tests\smoke\smoke_test.py --api-url $($urls.Api) --web-url $($urls.Web) --simulator-url $($urls.Simulator) --mail-url $($urls.Mail)"
        if ($JsonReport) {
            $reportPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($JsonReport)
            $reportDirectory = Split-Path -Parent $reportPath
            if ($reportDirectory -and -not (Test-Path -LiteralPath $reportDirectory)) {
                New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
            }
            $command += " --json `"$reportPath`""
        }
    }
    else {
        if ($JsonReport) { Write-Host 'Note: -JsonReport is only used together with -FromHost.' }
        $command = 'docker compose run --rm smoke'
    }

    $code = Invoke-Streaming -CommandLine $command -WorkingDirectory $infra
    Write-Host ''
    if ($code -eq 0) {
        Write-Host 'SMOKE_TEST_RESULT: PASS' -ForegroundColor Green
        exit 0
    }
    Write-Host "SMOKE_TEST_RESULT: FAIL (exit code $code)" -ForegroundColor Red
    exit 1
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}
