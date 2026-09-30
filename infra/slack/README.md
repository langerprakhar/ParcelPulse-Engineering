# Slack

The ParcelPulse team talks in Slack. This directory holds everything needed to
set the workspace up the same way every time: the app manifest, the list of
channels and the explanation of what the app is allowed to do.

| File                     | Purpose                                                        |
| ------------------------ | -------------------------------------------------------------- |
| `manifest.yaml`          | Slack app manifest: bot user, permissions, event subscriptions |
| `channels.json`          | The project's channels and their purposes                      |
| `bootstrap-channels.ps1` | Creates the channels that are missing (idempotent)             |

Nothing here contains a secret, and nothing here posts messages on anyone's
behalf.

## Channels

| Channel              | For                                                                  |
| -------------------- | -------------------------------------------------------------------- |
| `#general`           | Announcements and anything that concerns everyone                    |
| `#product`           | Requirements, priorities and scope                                   |
| `#engineering`       | Architecture, contracts between services, tooling                    |
| `#backend`           | `parcelpulse-api` and `parcelpulse-worker`                           |
| `#frontend`          | `parcelpulse-web`                                                    |
| `#incidents`         | Something is wrong for users; report here first                      |
| `#release`           | Release preparation, checklist status, announcements                 |
| `#customer-feedback` | What users and pilot customers tell us                               |

Slack is for discussion. Decisions and work items are recorded in GitHub (see
`docs/team-workflow.md`).

## Setup

You need to be allowed to install apps in the workspace.

1. **Create the app.** Open <https://api.slack.com/apps>, choose *Create New
   App*, then *From an app manifest*. Pick the workspace, paste the contents of
   `manifest.yaml` and create the app.
2. **Install it.** On the app's *Install App* page, install it to the
   workspace and approve the permissions listed below.
3. **Copy the bot token.** On *OAuth & Permissions*, copy the *Bot User OAuth
   Token*. It starts with `xoxb-`.
4. **Create an app-level token** (only needed for receiving events). On *Basic
   Information*, under *App-Level Tokens*, generate a token with the
   `connections:write` scope. It starts with `xapp-`.
5. **Provide the tokens through the environment**, for the current PowerShell
   session only:

   ```powershell
   $env:SLACK_BOT_TOKEN = Read-Host -AsSecureString "Bot token" | ConvertFrom-SecureString -AsPlainText
   ```

   (`-AsPlainText` needs PowerShell 7. In Windows PowerShell 5.1, assign the
   token directly: `$env:SLACK_BOT_TOKEN = "<token>"`, and clear your history
   afterwards.) Never put a token in a file that is committed, in a script, or
   in a chat message.
6. **Create the channels.** From the root of this repository:

   ```powershell
   .\slackootstrap-channels.ps1 -WhatIf    # show what would be done
   .\slackootstrap-channels.ps1            # do it
   ```

   It creates the channels in `channels.json` that do not exist yet, sets their
   purpose and joins the bot to them. It is safe to run again: existing
   channels are left alone. Without `SLACK_BOT_TOKEN` it changes nothing and
   says what is missing.

## Environment variables

| Variable          | Used by                          | Value                                             |
| ----------------- | -------------------------------- | ------------------------------------------------- |
| `SLACK_BOT_TOKEN` | Channel bootstrap; posting       | Bot User OAuth Token (`xoxb-...`)                 |
| `SLACK_APP_TOKEN` | A Socket Mode event listener     | App-level token with `connections:write` (`xapp-...`). Not needed for the bootstrap |

Both are secrets. They are read from the environment and are never written to
disk or printed by the project's scripts.

## Permissions

The app asks for the smallest set of bot scopes that covers channel setup,
posting and receiving events in public channels.

| Scope               | Why the app has it                                                          | Used today |
| ------------------- | --------------------------------------------------------------------------- | ---------- |
| `channels:manage`   | Create the public channels above and set their purpose                      | Bootstrap  |
| `channels:read`     | List existing public channels so the bootstrap only creates missing ones    | Bootstrap  |
| `channels:join`     | Join the public channels so the bot can post in them                        | Bootstrap  |
| `chat:write`        | Post messages as the bot                                                    | Not yet    |
| `channels:history`  | Required by the `message.channels` event: read messages in public channels the bot is a member of | Not yet |
| `app_mentions:read` | Required by the `app_mention` event: be told when someone @-mentions the bot | Not yet   |

What the app cannot do: read private channels or direct messages, read
channels it has not joined, act as a user, or manage members.

If the workspace restricts channel creation to admins, `conversations.create`
fails with `restricted_action`. Either a workspace admin creates the channels
by hand, or the restriction is lifted for the app. The bootstrap script reports
this case and continues with the remaining channels.

## Event subscriptions

The manifest enables Socket Mode and subscribes the bot to two events:

| Event              | Delivered when                                                   |
| ------------------ | ---------------------------------------------------------------- |
| `app_mention`      | Someone @-mentions the bot                                       |
| `message.channels` | A message is posted in a public channel the bot is a member of   |

**No event listener ships with v0.1.** Nothing in ParcelPulse consumes these
events yet, and the bot posts nothing on its own. The subscriptions are part of
the manifest so that a later integration can connect with `SLACK_APP_TOKEN`
without the app having to be reconfigured and re-approved. If that is not
wanted, delete the `event_subscriptions` block, the `socket_mode_enabled` line
and the `channels:history` and `app_mentions:read` scopes from the manifest
before creating the app.

Socket Mode is used because nothing is deployed: there is no public URL that
Slack could send events to.

## What is not automated

- Inviting people. Workspace membership is managed in Slack.
- Posting. There is no CI or release integration yet.
- Private channels.
