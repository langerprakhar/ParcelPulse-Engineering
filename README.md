# parcelpulse-web

Web dashboard for ParcelPulse, a package tracking and delivery notification
platform. Built with Next.js (App Router), React and TypeScript.

## Requirements

- Node.js 22 or newer

## Setup

```powershell
npm ci
Copy-Item .env.example .env.local
npm run dev
```

The app is served on <http://localhost:3000>.

## Checks

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```
