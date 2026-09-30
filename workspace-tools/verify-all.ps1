<#
.SYNOPSIS
    Runs every check of every ParcelPulse component and reports each one.

.DESCRIPTION
    For api, worker, web and infra: lint, formatting, type checks and tests,
    with every test suite run and reported separately. Also: git working tree
    state, Compose validation, GitHub Actions YAML sanity, a search for
    committed secrets and, with -Smoke, the end-to-end smoke test.

    Nothing is skipped silently. A check that cannot run because a tool is
    missing is reported as BLOCKED with the reason, not as passed.

    Output of every check is written to workspace-tools\logs\verify-<time>\.

.PARAMETER Setup
    Create missing virtual environments and install dependencies first
    (py -3.12 -m venv, pip install -e ".[dev]", npm ci).

.PARAMETER Smoke
    Also run the end-to-end smoke test. The stack must be running (start-all.ps1).

.PARAMETER SkipBuild
    Skip the web production build.

.PARAMETER KeepTestDatabases
    Leave the throwaway PostgreSQL/Redis containers of the API and worker test
    suites running afterwards.

.EXAMPLE
    .\verify-all.ps1 -Setup
    .\verify-all.ps1 -Smoke

.NOTES
    Exit codes: 0 = all checks passed; 1 = at least one check failed or was blocked.
#>
[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$Smoke,
    [switch]$SkipBuild,
    [switch]$KeepTestDatabases
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$api = Get-ComponentPath api
$web = Get-ComponentPath web
$worker = Get-ComponentPath worker
$infra = Get-ComponentPath infra
$simulator = Join-Path $infra 'carrier-simulator'

$logRoot = Join-Path $PSScriptRoot ("logs\verify-{0:yyyyMMdd-HHmmss}" -f (Get-Date))
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param([string]$Area, [string]$Check, [string]$Status, [double]$Seconds = 0, [string]$Detail = '')
    $results.Add([pscustomobject]@{
            Area = $Area; Check = $Check; Status = $Status
            Seconds = [Math]::Round($Seconds, 1); Detail = $Detail
        })
    $colour = switch ($Status) { 'PASS' { 'Green' } 'FAIL' { 'Red' } default { 'Yellow' } }
    $line = '  {0,-7} {1,-8} {2}' -f $Status, $Area, $Check
    if ($Detail -and $Status -ne 'PASS') { $line += "  [$Detail]" }
    Write-Host $line -ForegroundColor $colour
}

function Invoke-Check {
    <# Runs one command; PASS on exit code 0, FAIL otherwise, with the log file named in the detail. #>
    param(
        [Parameter(Mandatory)] [string]$Area,
        [Parameter(Mandatory)] [string]$Check,
        [Parameter(Mandatory)] [string]$CommandLine,
        [Parameter(Mandatory)] [string]$WorkingDirectory
    )
    $slug = (("$Area-$Check") -replace '[^A-Za-z0-9]+', '-').Trim('-').ToLowerInvariant()
    $logFile = Join-Path $logRoot "$slug.log"
    $started = Get-Date
    $code = Invoke-Logged -CommandLine $CommandLine -WorkingDirectory $WorkingDirectory -LogFile $logFile
    $seconds = ((Get-Date) - $started).TotalSeconds
    if ($code -eq 0) { Add-Result $Area $Check 'PASS' $seconds }
    else { Add-Result $Area $Check 'FAIL' $seconds "exit $code, see logs\$(Split-Path -Leaf $logRoot)\$slug.log" }
}

function Add-Blocked {
    param([string]$Area, [string]$Check, [string]$Reason)
    Add-Result $Area $Check 'BLOCKED' 0 $Reason
}

# --- Prerequisites ------------------------------------------------------------

$hasDocker = $false
try { Assert-DockerRunning; $hasDocker = $true }
catch { Write-Host $_.Exception.Message -ForegroundColor Yellow }
$hasPy = Test-CommandAvailable 'py'
$hasNpm = Test-CommandAvailable 'npm'
$hasGit = Test-CommandAvailable 'git'

$pythonProjects = [ordered]@{ api = $api; worker = $worker; simulator = $simulator }

if ($Setup) {
    Write-Host 'Setting up development environments ...'
    foreach ($name in $pythonProjects.Keys) {
        $dir = $pythonProjects[$name]
        if (-not $hasPy) { Add-Blocked 'setup' "$name virtual environment" 'Python launcher (py) not found'; continue }
        if (-not (Test-Path -LiteralPath (Join-Path $dir '.venv\Scripts\python.exe'))) {
            Invoke-Check 'setup' "$name create venv" 'py -3.12 -m venv .venv' $dir
        }
        Invoke-Check 'setup' "$name install" '.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"' $dir
    }
    if ($hasNpm) { Invoke-Check 'setup' 'web npm ci' 'npm ci' $web }
    else { Add-Blocked 'setup' 'web npm ci' 'npm not found' }
    Write-Host ''
}

function Test-Venv {
    param([string]$Directory)
    return Test-Path -LiteralPath (Join-Path $Directory '.venv\Scripts\python.exe')
}

# --- Git state ------------------------------------------------------------------

$repositoryRoot = Split-Path -Parent $PSScriptRoot

Write-Host 'Git working tree'
if (-not $hasGit) { Add-Blocked 'git' 'working tree clean' 'git not found' }
else {
    Push-Location -LiteralPath $repositoryRoot
    try {
        $dirty = @(cmd.exe /d /c 'git status --porcelain 2>nul')
        $branch = (cmd.exe /d /c 'git rev-parse --abbrev-ref HEAD 2>nul')
    }
    finally { Pop-Location }
    if ($dirty.Count -eq 0) { Add-Result 'git' "working tree clean (branch $branch)" 'PASS' }
    else { Add-Result 'git' "working tree clean (branch $branch)" 'FAIL' 0 "$($dirty.Count) uncommitted change(s)" }
}

# --- api -----------------------------------------------------------------------

Write-Host ''
Write-Host 'api'
if (-not (Test-Venv $api)) {
    Add-Blocked 'api' 'all checks' 'no .venv; run with -Setup'
}
else {
    Invoke-Check 'api' 'ruff check' '.venv\Scripts\ruff.exe check .' $api
    Invoke-Check 'api' 'ruff format' '.venv\Scripts\ruff.exe format --check .' $api
    Invoke-Check 'api' 'mypy' '.venv\Scripts\mypy.exe' $api
    Invoke-Check 'api' 'unit tests' '.venv\Scripts\python.exe -m pytest tests/unit -q' $api

    if (-not $hasDocker) {
        Add-Blocked 'api' 'integration tests' 'Docker daemon not running (needed for the test PostgreSQL and Redis)'
    }
    else {
        Invoke-Check 'api' 'start test PostgreSQL and Redis' "docker compose -p $($TestProjects.api) -f docker-compose.dev.yml up -d --wait" $api
        $suites = [ordered]@{
            'shipments'           = 'test_shipments_api.py'
            'webhook ingestion'   = 'test_webhook_ingestion.py'
            'webhook idempotency' = 'test_webhook_idempotency.py'
            'event ordering'      = 'test_event_ordering.py'
            'timeline'            = 'test_timeline.py'
            'notifications'       = 'test_notifications.py'
            'queue publisher'     = 'test_queue_publisher.py'
            'operations'          = 'test_operations.py'
            'migrations'          = 'test_migrations.py'
        }
        foreach ($suite in $suites.Keys) {
            Invoke-Check 'api' "integration: $suite" ".venv\Scripts\python.exe -m pytest tests/integration/$($suites[$suite]) -q" $api
        }
        $testDatabase = 'postgresql+psycopg://parcelpulse:parcelpulse@localhost:25432/parcelpulse_test'
        Invoke-Check 'api' 'migrations: upgrade head and alembic check' "set `"DATABASE_URL=$testDatabase`"&& .venv\Scripts\alembic.exe upgrade head && .venv\Scripts\alembic.exe check" $api
    }
}

# --- worker -----------------------------------------------------------------------

Write-Host ''
Write-Host 'worker'
if (-not (Test-Venv $worker)) {
    Add-Blocked 'worker' 'all checks' 'no .venv; run with -Setup'
}
else {
    Invoke-Check 'worker' 'ruff check' '.venv\Scripts\ruff.exe check .' $worker
    Invoke-Check 'worker' 'ruff format' '.venv\Scripts\ruff.exe format --check .' $worker
    Invoke-Check 'worker' 'mypy' '.venv\Scripts\mypy.exe' $worker
    if (-not $hasDocker) {
        Add-Blocked 'worker' 'tests' 'Docker daemon not running (needed for the test PostgreSQL)'
    }
    else {
        Invoke-Check 'worker' 'start test PostgreSQL' "docker compose -p $($TestProjects.worker) -f docker-compose.dev.yml up -d --wait" $worker
        $suites = [ordered]@{
            'unit (config, logging, retry, email content)' = 'tests/test_config.py tests/test_logging.py tests/test_retry.py tests/test_email_content.py'
            'smtp sender'                                  = 'tests/test_smtp_sender.py'
            'delivery idempotency and retry'               = 'tests/test_delivery.py'
            'queue handling'                               = 'tests/test_actor.py'
            'sweeper'                                      = 'tests/test_sweeper.py'
            'healthcheck'                                  = 'tests/test_healthcheck.py'
        }
        foreach ($suite in $suites.Keys) {
            Invoke-Check 'worker' "tests: $suite" ".venv\Scripts\python.exe -m pytest $($suites[$suite]) -q" $worker
        }
    }
}

# --- web -----------------------------------------------------------------------

Write-Host ''
Write-Host 'web'
if (-not $hasNpm) {
    Add-Blocked 'web' 'all checks' 'npm not found'
}
elseif (-not (Test-Path -LiteralPath (Join-Path $web 'node_modules'))) {
    Add-Blocked 'web' 'all checks' 'no node_modules; run with -Setup'
}
else {
    Invoke-Check 'web' 'eslint' 'npm run lint' $web
    Invoke-Check 'web' 'typecheck' 'npm run typecheck' $web
    $suites = [ordered]@{
        'api client and formatting' = 'src/lib'
        'server actions'            = 'src/actions'
        'components'                = 'src/components'
        'route handlers'            = 'src/app'
    }
    foreach ($suite in $suites.Keys) {
        Invoke-Check 'web' "tests: $suite" "npx vitest run $($suites[$suite])" $web
    }
    if ($SkipBuild) { Add-Result 'web' 'production build' 'SKIPPED' 0 'requested with -SkipBuild' }
    else { Invoke-Check 'web' 'production build' 'npm run build' $web }
}

# --- infra -----------------------------------------------------------------------

Write-Host ''
Write-Host 'infra'
if ($hasDocker) { Invoke-Check 'infra' 'docker compose config' 'docker compose config --quiet' $infra }
else { Add-Blocked 'infra' 'docker compose config' 'Docker daemon not running' }

if (-not (Test-Venv $simulator)) {
    Add-Blocked 'infra' 'carrier simulator and script checks' 'no carrier-simulator\.venv; run with -Setup'
}
else {
    $python = 'carrier-simulator\.venv\Scripts\python.exe'
    $ruff = 'carrier-simulator\.venv\Scripts\ruff.exe'
    if ($hasDocker) { Invoke-Check 'infra' 'compose static checks' "$python -m pytest tests/test_compose.py -q" $infra }
    else { Add-Blocked 'infra' 'compose static checks' 'Docker CLI needed for docker compose config' }
    Invoke-Check 'infra' 'scripts: ruff check' "$ruff check tests loadtest" $infra
    Invoke-Check 'infra' 'scripts: ruff format' "$ruff format --check tests loadtest" $infra
    Invoke-Check 'infra' 'simulator: ruff check' '.venv\Scripts\ruff.exe check .' $simulator
    Invoke-Check 'infra' 'simulator: ruff format' '.venv\Scripts\ruff.exe format --check .' $simulator
    Invoke-Check 'infra' 'simulator: mypy' '.venv\Scripts\mypy.exe' $simulator
    Invoke-Check 'infra' 'simulator tests: webhook delivery and retries' '.venv\Scripts\python.exe -m pytest tests/test_sender.py -q' $simulator
    Invoke-Check 'infra' 'simulator tests: carrier behaviours' '.venv\Scripts\python.exe -m pytest tests/test_simulator.py -q' $simulator
    Invoke-Check 'infra' 'simulator tests: http api and cli' '.venv\Scripts\python.exe -m pytest tests/test_app.py -q' $simulator
}

# --- Whole-repository checks ----------------------------------------------------

Write-Host ''
Write-Host 'Whole repository'

# PowerShell scripts parse.
$parseErrors = @()
$scripts = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter *.ps1)
foreach ($name in 'api', 'web', 'worker', 'infra') {
    $scripts += @(Get-ChildItem -LiteralPath (Get-ComponentPath $name) -Recurse -Filter *.ps1 -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\(node_modules|\.venv|\.next)\\' })
}
foreach ($script in $scripts) {
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$null, [ref]$errors) | Out-Null
    if ($errors -and $errors.Count -gt 0) { $parseErrors += "$($script.Name): $($errors[0].Message)" }
}
if ($parseErrors.Count -eq 0) { Add-Result 'all' "PowerShell scripts parse ($($scripts.Count) files)" 'PASS' }
else { Add-Result 'all' 'PowerShell scripts parse' 'FAIL' 0 ($parseErrors -join '; ') }

# GitHub Actions workflows are valid YAML with jobs. Only workflows at the
# repository root count: GitHub does not read workflow files from subdirectories.
$workflowFiles = @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot '.github\workflows') -Filter *.yml -ErrorAction SilentlyContinue)
$yamlPython = Join-Path $api '.venv\Scripts\python.exe'
if ($workflowFiles.Count -eq 0) {
    Add-Blocked 'all' 'GitHub Actions workflows are valid YAML with jobs' 'no workflow files in .github\workflows at the repository root'
}
elseif (Test-Path -LiteralPath $yamlPython) {
    $workflowCheck = Join-Path $logRoot 'check_workflows.py'
    @'
import pathlib, sys, yaml
failed = False
paths = sorted(pathlib.Path(sys.argv[1], ".github", "workflows").glob("*.yml"))
for path in paths:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = document.get("jobs") or {}
        triggers = document.get("on", document.get(True))
        assert jobs, "no jobs"
        assert triggers, "no triggers"
        for name, job in jobs.items():
            assert job.get("runs-on"), f"job {name} has no runs-on"
            assert job.get("steps"), f"job {name} has no steps"
        print(f"ok  {path}  ({len(jobs)} jobs: {', '.join(jobs)})")
    except Exception as error:
        failed = True
        print(f"BAD {path}: {error}")
sys.exit(1 if failed or not paths else 0)
'@ | Set-Content -LiteralPath $workflowCheck -Encoding UTF8
    Invoke-Check 'all' "GitHub Actions workflows are valid YAML with jobs ($($workflowFiles.Count) files)" "`"$yamlPython`" `"$workflowCheck`" `"$repositoryRoot`"" $PSScriptRoot
}
else { Add-Blocked 'all' 'GitHub Actions workflows are valid YAML with jobs' 'needs the API virtual environment (PyYAML); run with -Setup' }

# No committed secrets: no real env files, no token-shaped strings.
if ($hasGit) {
    $tokenPattern = '(xox[abprs]-[0-9A-Za-z-]{10,}|xapp-[0-9A-Za-z-]{10,}|ghp_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
    Push-Location -LiteralPath $repositoryRoot
    try {
        $tracked = @(cmd.exe /d /c 'git ls-files 2>nul')
        $envFiles = @($tracked | Where-Object { $_ -match '(^|/)\.env(\.|$)' -and $_ -notmatch '\.env\.example$' })
        $tokens = @(cmd.exe /d /c "git grep -nIE `"$tokenPattern`" 2>nul")
    }
    finally { Pop-Location }
    $problems = @()
    if ($envFiles.Count -gt 0) { $problems += "tracked env file(s): $($envFiles -join ', ')" }
    # The example placeholder in the Slack docs is not a token.
    $tokens = @($tokens | Where-Object { $_ -and $_ -notmatch 'xox[bp]-\.\.\.|xapp-\.\.\.' })
    if ($tokens.Count -gt 0) { $problems += "$($tokens.Count) token-shaped string(s), first: $(($tokens[0] -split ':')[0..1] -join ':')" }
    $secretCheck = "no tracked env files or token-shaped strings ($($tracked.Count) tracked files)"
    if ($problems.Count -eq 0) { Add-Result 'secrets' $secretCheck 'PASS' }
    else { Add-Result 'secrets' $secretCheck 'FAIL' 0 ($problems -join '; ') }
}
else { Add-Blocked 'secrets' 'secret scan' 'git not found' }

# --- Smoke test -----------------------------------------------------------------

if ($Smoke) {
    Write-Host ''
    Write-Host 'End to end'
    if (-not $hasDocker) { Add-Blocked 'e2e' 'smoke test' 'Docker daemon not running' }
    else {
        $smokeLog = Join-Path $logRoot 'e2e-smoke-test.log'
        $started = Get-Date
        $code = Invoke-Logged -CommandLine 'docker compose run --rm smoke' -WorkingDirectory $infra -LogFile $smokeLog
        $seconds = ((Get-Date) - $started).TotalSeconds
        $summary = @(Get-Content -LiteralPath $smokeLog | Where-Object { $_ -match 'checks passed' }) | Select-Object -Last 1
        if ($code -eq 0) { Add-Result 'e2e' "smoke test ($summary)" 'PASS' $seconds }
        else { Add-Result 'e2e' 'smoke test' 'FAIL' $seconds "$summary; is the stack running? see logs\$(Split-Path -Leaf $logRoot)\e2e-smoke-test.log" }
    }
}

# --- Clean up and summarise -------------------------------------------------------

if ($hasDocker -and -not $KeepTestDatabases) {
    foreach ($name in 'api', 'worker') {
        Invoke-Logged -CommandLine "docker compose -p $($TestProjects[$name]) -f docker-compose.dev.yml down" `
            -WorkingDirectory (Get-ComponentPath $name) `
            -LogFile (Join-Path $logRoot "test-databases-down-$name.log") | Out-Null
    }
}

$passed = @($results | Where-Object Status -eq 'PASS').Count
$failed = @($results | Where-Object Status -eq 'FAIL').Count
$blocked = @($results | Where-Object Status -eq 'BLOCKED').Count
$skipped = @($results | Where-Object Status -eq 'SKIPPED').Count
$results | Export-Csv -LiteralPath (Join-Path $logRoot 'summary.csv') -NoTypeInformation -Encoding UTF8

Write-Host ''
Write-Host ("{0} passed, {1} failed, {2} blocked, {3} skipped. Logs: {4}" -f $passed, $failed, $blocked, $skipped, $logRoot)
if ($failed -gt 0 -or $blocked -gt 0) {
    Write-Host 'VERIFY_ALL_RESULT: FAIL' -ForegroundColor Red
    exit 1
}
Write-Host 'VERIFY_ALL_RESULT: PASS' -ForegroundColor Green
exit 0
