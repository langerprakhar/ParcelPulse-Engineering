<#
.SYNOPSIS
    Creates the ParcelPulse Slack channels that do not exist yet.

.DESCRIPTION
    Reads channels.json and, using the Slack Web API with the bot token in the
    SLACK_BOT_TOKEN environment variable:

      * creates each public channel that is missing,
      * sets its purpose if it has none,
      * joins the bot to it.

    The script is idempotent: channels that already exist are left as they are.
    It posts no messages.

    Without SLACK_BOT_TOKEN it changes nothing, explains what is missing and
    exits 0, so that it can be part of a larger setup run.

    The token is only ever sent to slack.com in the Authorization header. It is
    never written to the console, to a file or to the pipeline.

.PARAMETER ChannelsFile
    Path to the channel list. Defaults to channels.json next to this script.

.PARAMETER WhatIf
    Show what would be done without changing the workspace. Read-only API calls
    (auth.test, conversations.list) are still made.

.EXAMPLE
    $env:SLACK_BOT_TOKEN = '<bot token>'
    .\bootstrap-channels.ps1 -WhatIf
    .\bootstrap-channels.ps1

.NOTES
    Required bot scopes: channels:manage, channels:read, channels:join.
    Exit codes: 0 = done or skipped (no token); 1 = at least one channel failed;
    2 = the token was rejected or the channel list is unusable.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ChannelsFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# $PSScriptRoot is not available in parameter defaults in Windows PowerShell 5.1.
if (-not $ChannelsFile) { $ChannelsFile = Join-Path $PSScriptRoot 'channels.json' }
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$token = $env:SLACK_BOT_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host 'SLACK_BOOTSTRAP_STATUS: SKIPPED (SLACK_BOT_TOKEN is not set)'
    Write-Host ''
    Write-Host 'Nothing was changed. To create the channels:'
    Write-Host '  1. Create the Slack app from slack\manifest.yaml and install it (see slack\README.md).'
    Write-Host '  2. Put the Bot User OAuth Token in the environment for this session:'
    Write-Host '       $env:SLACK_BOT_TOKEN = "<bot token>"'
    Write-Host '  3. Run this script again.'
    exit 0
}

function Invoke-Slack {
    <# Calls one Slack Web API method. Returns the parsed response; throws only on transport errors. #>
    param(
        [Parameter(Mandatory)] [string]$Method,
        [hashtable]$Body = @{}
    )
    $headers = @{ Authorization = "Bearer $token" }
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            return Invoke-RestMethod -Method Post -Uri "https://slack.com/api/$Method" `
                -Headers $headers -Body $Body -ContentType 'application/x-www-form-urlencoded'
        }
        catch {
            $response = $_.Exception.Response
            if ($null -ne $response -and [int]$response.StatusCode -eq 429) {
                # Rate limited: Slack says how long to wait.
                $retryAfter = 5
                try { $retryAfter = [int]$response.Headers['Retry-After'] } catch { }
                Write-Verbose "Rate limited by Slack on $Method; waiting $retryAfter s."
                Start-Sleep -Seconds ([Math]::Max(1, $retryAfter))
                continue
            }
            # Do not include the exception's request details: they contain the Authorization header.
            throw "Slack API call '$Method' failed: $($_.Exception.Message)"
        }
    }
    throw "Slack API call '$Method' was rate limited five times in a row."
}

function Get-ErrorAdvice {
    param([string]$ErrorCode)
    switch ($ErrorCode) {
        'missing_scope' { 'The app lacks a required scope. Reinstall it from slack\manifest.yaml (channels:manage, channels:read, channels:join).' }
        'restricted_action' { 'The workspace only lets admins create channels. Ask an admin to create it, or to allow the app to.' }
        'invalid_auth' { 'The token is not valid. Copy the Bot User OAuth Token again.' }
        'not_authed' { 'No token reached Slack. Check SLACK_BOT_TOKEN.' }
        'account_inactive' { 'The token belongs to a removed app or user. Reinstall the app.' }
        'token_revoked' { 'The token was revoked. Reinstall the app and use the new token.' }
        'invalid_name_specials' { 'Channel names may only contain lowercase letters, digits, hyphens and underscores.' }
        'is_archived' { 'The channel exists but is archived. Unarchive it in Slack if it should be used.' }
        default { '' }
    }
}

# --- Desired channels -------------------------------------------------------

if (-not (Test-Path -LiteralPath $ChannelsFile)) {
    Write-Error "Channel list not found: $ChannelsFile" -ErrorAction Continue
    exit 2
}
$desired = @((Get-Content -LiteralPath $ChannelsFile -Raw -Encoding UTF8 | ConvertFrom-Json).channels)
if ($desired.Count -eq 0) {
    Write-Error "No channels listed in $ChannelsFile" -ErrorAction Continue
    exit 2
}

# --- Who are we talking to? --------------------------------------------------

$auth = Invoke-Slack -Method 'auth.test'
if (-not $auth.ok) {
    Write-Host "SLACK_BOOTSTRAP_STATUS: FAILED (auth.test: $($auth.error))"
    $advice = Get-ErrorAdvice $auth.error
    if ($advice) { Write-Host $advice }
    exit 2
}
Write-Host "Workspace: $($auth.team)   Bot user: $($auth.user)"

# --- Existing public channels -------------------------------------------------

$existing = @{}
$cursor = ''
do {
    $page = Invoke-Slack -Method 'conversations.list' -Body @{
        types            = 'public_channel'
        exclude_archived = 'false'
        limit            = '200'
        cursor           = $cursor
    }
    if (-not $page.ok) {
        Write-Host "SLACK_BOOTSTRAP_STATUS: FAILED (conversations.list: $($page.error))"
        $advice = Get-ErrorAdvice $page.error
        if ($advice) { Write-Host $advice }
        exit 2
    }
    foreach ($channel in $page.channels) { $existing[$channel.name] = $channel }
    $cursor = ''
    if ($page.PSObject.Properties['response_metadata'] -and $page.response_metadata.next_cursor) {
        $cursor = $page.response_metadata.next_cursor
    }
} while ($cursor)

# --- Reconcile ----------------------------------------------------------------

$results = New-Object System.Collections.Generic.List[object]
function Add-Result {
    param([string]$Name, [string]$Outcome, [string]$Detail = '')
    $results.Add([pscustomobject]@{ Channel = "#$Name"; Outcome = $Outcome; Detail = $Detail })
}

foreach ($entry in $desired) {
    $name = [string]$entry.name
    $purpose = [string]$entry.purpose
    $channel = $existing[$name]

    if ($null -ne $channel) {
        if ($channel.is_archived) {
            Add-Result $name 'exists (archived)' (Get-ErrorAdvice 'is_archived')
            continue
        }
        $notes = @()
        if (-not $channel.is_member) {
            if ($PSCmdlet.ShouldProcess("#$name", 'Join the bot to the channel')) {
                $join = Invoke-Slack -Method 'conversations.join' -Body @{ channel = $channel.id }
                if ($join.ok) { $notes += 'bot joined' } else { $notes += "could not join: $($join.error)" }
            }
            else { $notes += 'would join' }
        }
        $hasPurpose = $channel.PSObject.Properties['purpose'] -and $channel.purpose.value
        if ($purpose -and -not $hasPurpose -and $name -ne 'general') {
            if ($PSCmdlet.ShouldProcess("#$name", 'Set the channel purpose')) {
                $set = Invoke-Slack -Method 'conversations.setPurpose' -Body @{ channel = $channel.id; purpose = $purpose }
                if ($set.ok) { $notes += 'purpose set' } else { $notes += "could not set purpose: $($set.error)" }
            }
            else { $notes += 'would set purpose' }
        }
        Add-Result $name 'exists' ($notes -join '; ')
        continue
    }

    if (-not $PSCmdlet.ShouldProcess("#$name", 'Create public channel')) {
        Add-Result $name 'would create'
        continue
    }

    $created = Invoke-Slack -Method 'conversations.create' -Body @{ name = $name; is_private = 'false' }
    if (-not $created.ok) {
        if ($created.error -eq 'name_taken') {
            # Created by someone else between listing and creating; that is what we wanted.
            Add-Result $name 'exists' 'created concurrently'
        }
        else {
            Add-Result $name 'FAILED' ("$($created.error). " + (Get-ErrorAdvice $created.error)).Trim()
        }
        continue
    }

    $notes = @()
    if ($purpose) {
        $set = Invoke-Slack -Method 'conversations.setPurpose' -Body @{ channel = $created.channel.id; purpose = $purpose }
        if (-not $set.ok) { $notes += "could not set purpose: $($set.error)" }
    }
    Add-Result $name 'created' ($notes -join '; ')
}

# --- Report -------------------------------------------------------------------

$results | Format-Table -AutoSize | Out-String | Write-Host
$failed = @($results | Where-Object { $_.Outcome -eq 'FAILED' })
if ($failed.Count -gt 0) {
    Write-Host "SLACK_BOOTSTRAP_STATUS: PARTIAL ($($failed.Count) of $($results.Count) channels failed)"
    exit 1
}
if ($WhatIfPreference) {
    Write-Host 'SLACK_BOOTSTRAP_STATUS: DRY RUN (nothing was changed)'
}
else {
    Write-Host "SLACK_BOOTSTRAP_STATUS: OK ($($results.Count) channels present)"
}
exit 0
