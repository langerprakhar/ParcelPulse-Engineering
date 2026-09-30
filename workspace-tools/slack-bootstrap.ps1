<#
.SYNOPSIS
    Creates the ParcelPulse Slack channels that do not exist yet.

.DESCRIPTION
    Thin wrapper around infra\slack\bootstrap-channels.ps1, which holds the
    logic and the channel list (infra\slack\channels.json).

    Needs a bot token in the SLACK_BOT_TOKEN environment variable, from a Slack
    app created from infra\slack\manifest.yaml with the scopes
    channels:manage, channels:read and channels:join. Without the token nothing
    is changed and the setup steps are printed; that is not an error.

    The token is never printed, logged or written to disk.

.PARAMETER WhatIf
    Show what would be created without changing the workspace.

.EXAMPLE
    $env:SLACK_BOT_TOKEN = '<bot token>'
    .\slack-bootstrap.ps1 -WhatIf
    .\slack-bootstrap.ps1
#>
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

try {
    $script = Join-Path (Get-ComponentPath infra) 'slack\bootstrap-channels.ps1'
    if (-not (Test-Path -LiteralPath $script)) { throw "Not found: $script" }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

if ($WhatIfPreference) { & $script -WhatIf } else { & $script }
exit $LASTEXITCODE
