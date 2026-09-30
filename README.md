# parcelpulse-infra

Local infrastructure for ParcelPulse, a package tracking and delivery
notification platform.

## Backing services

```powershell
docker compose up -d --wait
```

| Service    | Image                        | Host address                                   |
| ---------- | ---------------------------- | ---------------------------------------------- |
| PostgreSQL | `postgres:17.11-alpine`      | `localhost:15432` (user/password/db `parcelpulse`) |
| Redis      | `redis:7.4.11-alpine`        | `localhost:6379`                               |
| Mailpit    | `axllent/mailpit:v1.31.3`    | SMTP `localhost:1025`, UI <http://localhost:8025> |

Defaults work without configuration. To change ports or credentials, copy
`.env.example` to `.env` and edit it.

```powershell
docker compose down        # stop, keep data
docker compose down -v     # stop and delete the database and queue volumes
```
