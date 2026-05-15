# Local Deploy

Run the stack directly on `localhost` without sibling `root-proxy`.

## Assumptions
- commands are run from `deploy/`
- local env file lives at repo root as `../.env.local`
- `frontend` is published on `http://localhost:8080`
- local override keeps `AUTH_COOKIE_SECURE=false`

## First-Time Setup

```powershell
cd deploy
```

If `../.env.local` does not exist yet, create it from the repo-root template and fill in real local values.

## Commands

Start:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

Stop:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml down -v
```

Restart:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml restart
```

Logs:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml logs -f
```

## Notes
- Microsoft local login should use the local Entra app registration and the local redirect URI.
- Recommended local redirect URI: `http://localhost:8080/api/v1/auth/callback/microsoft`
- `docker-compose.local.yml` is the only place that should expose port `8080` to the host.
