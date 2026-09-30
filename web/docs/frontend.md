# Frontend

How the dashboard is put together and why.

## Screens

| Route                           | Screen                                                                       |
| ------------------------------- | ---------------------------------------------------------------------------- |
| `/`                             | Tracking search, add-a-shipment form, five most recent shipments             |
| `/shipments`                    | All shipments with a status filter and pagination                            |
| `/shipments/{id}`               | Status, estimate, last update, and the event timeline                        |
| `/shipments/{id}/notifications` | Notification preferences and the history of notifications for the shipment   |
| `/dev`                          | Developer tools for the carrier simulator (only with `ENABLE_DEV_TOOLS=true`) |
| `/api/health`, `/api/ready`     | Liveness and readiness for orchestration                                     |

## Data flow

```
browser ──HTML / Server Action POST──▶ Next.js server ──HTTP/JSON──▶ parcelpulse-api
                                            └────────────────────▶ carrier simulator (/dev only)
```

The browser never calls the API. Pages are React Server Components that fetch
from `parcelpulse-api` while rendering, and forms submit to Server Actions that
call the API and then redirect or re-render. Consequences:

- No CORS configuration, and the API does not need to be reachable from
  the browser.
- `API_BASE_URL` and the other settings are read on the server at request
  time. One built image runs in any environment; nothing is baked into the
  client bundle.
- Every request to the API uses `cache: "no-store"`. Tracking data is never
  served from a cache, and every route is rendered on demand.

| Layer                  | Location           | Notes                                                        |
| ---------------------- | ------------------ | ------------------------------------------------------------ |
| Pages and route handlers | `src/app/`       | Server Components; `error.tsx` and `not-found.tsx` at the root |
| Server Actions         | `src/actions/`     | Validate, call the API, map errors to form state             |
| API client             | `src/lib/api.ts`   | `server-only`; typed functions; `ApiError`, `ApiUnavailableError` |
| Simulator client       | `src/lib/simulator.ts` | `server-only`; used by the developer tools                |
| Types                  | `src/lib/types.ts` | Mirror the API's JSON field names exactly                    |
| Formatting             | `src/lib/format.ts` | Status wording and tones, locations, UTC time, tracking numbers |
| Components             | `src/components/`  | Client components only where interaction needs them          |

## Behaviour worth knowing

**Timeline order.** The shipment page asks the API for events newest first.
The API orders by the carrier's event time, not arrival, so a late event
appears at its true position. Each entry shows the event time and the time
ParcelPulse received it, and events the API marked `arrived_out_of_order` get
a "Reported late" tag.

**Times.** `LocalTime` renders UTC on the server and on the first client
render, then switches to the viewer's time zone once hydrated. The UTC value
stays in the tooltip and the `datetime` attribute. This avoids a hydration
mismatch without guessing the time zone on the server.

**Live updates.** `AutoRefresh` calls `router.refresh()` every ten seconds
while the tab is visible, which re-fetches the page's server data. There is no
WebSocket or polling API.

**Forms.** Forms use `useActionState`. They keep what the user typed when the
server rejects a submission, show field errors next to the fields and general
errors in a live region, and work with keyboard only.

**Search.** A tracking number that is not tracked offers to add it and
prefills the add form. Adding a parcel that is already tracked opens the
existing shipment instead of reporting an error.

**Failure handling.** If the API is unreachable, the home page still renders
and says so; forms report the outage in place; other pages fall through to the
error boundary, which offers a retry. A shipment id that does not exist, or is
not a UUID, renders the not-found page with HTTP 404.

**Unknown statuses.** A status this version does not know (from a newer API)
is shown as the API sent it, in a neutral colour, rather than crashing.

## Developer tools

`/dev` creates simulated shipments (registered in ParcelPulse) and sends their
events: next event, resend (duplicate), hold and release (delayed), swap
(out of order), delivery exception, or the rest of the journey. Each action
shows how ParcelPulse answered every webhook.

The page returns 404 and its Server Actions refuse to run unless
`ENABLE_DEV_TOOLS=true`. The actions check the flag themselves because Server
Functions can be invoked directly, not only through the page.

## Styling

One stylesheet, `src/app/globals.css`, with CSS custom properties for colour,
radius and type. Light and dark schemes follow the operating system setting.
No CSS framework and no web fonts (system font stack), so the build needs no
network access for assets.

Status colours carry meaning and are always paired with text: neutral (not
moving yet), blue (moving), amber (out for delivery, retrying), green
(delivered, sent), red (exception, returned, failed).

## Testing

Vitest with React Testing Library, run with `npm test`.

| Area            | Files                        | Approach                                                          |
| --------------- | ---------------------------- | ----------------------------------------------------------------- |
| API client      | `src/lib/*.test.ts`          | `fetch` replaced by a mock; checks URLs, bodies and error mapping |
| Server Actions  | `src/actions/*.test.ts`      | API module and `next/navigation` mocked; checks each outcome      |
| Components      | `src/components/*.test.tsx`  | Rendered in jsdom; actions mocked to check what forms submit      |
| Route handlers  | `src/app/api/**/route.test.ts` | Called directly                                                 |

Async Server Components (the pages themselves) are not unit tested; Vitest
does not support them. They are exercised by the full-stack smoke test in
`parcelpulse-infra`, which requests the rendered pages from a running stack.
There is no browser-driven end-to-end suite in this repository yet.

`server-only` is aliased to an empty module in `vitest.config.mts` so that
server modules can be imported by tests.

## Known limitations

- No authentication: anyone who can reach the dashboard can see and change
  every shipment.
- The timeline shows the 100 most recent events and the notification history
  the 50 most recent.
- Carrier names are shown as their codes.
- English only.
