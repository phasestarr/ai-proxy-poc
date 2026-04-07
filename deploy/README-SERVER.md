# Server Deploy

Run the stack behind sibling `root-proxy` on `edge-net`.

## Assumptions
- commands are run from `deploy/`
- server env file lives at repo root as `../.env`
- sibling `root-proxy` is already deployed
- external Docker network `edge-net` already exists
- `root-proxy` routes `ai.nextinsol.com` to `ai-proxy-frontend:8080`

## First-Time Setup

```bash
cd deploy
```

Before first startup:
- set real values in `../.env`
- keep `AUTH_COOKIE_SECURE=true`
- keep `AI_PROXY_CONTAINER_NAME=ai-proxy-frontend` unless sibling `root-proxy` changes too
- confirm the Microsoft production app registration includes redirect URI `https://ai.nextinsol.com/api/v1/auth/callback/microsoft`

## Commands

Start:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml up --build -d
```

Stop:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml down
```

Restart:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml restart
```

Logs:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml logs -f
```

## Notes
- `docker-compose.server.yml` is the only place that should attach `frontend` to `edge-net`.
- The backend, PostgreSQL, and Redis remain internal to this stack.
- This repo does not terminate TLS. TLS stays in sibling `root-proxy`.
