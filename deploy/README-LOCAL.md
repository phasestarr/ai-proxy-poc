# Local Deploy

Run the stack directly on `localhost` without sibling `root-proxy`.

## Assumptions

- Commands are run from `ai-proxy/deploy`
- Local env file lives at repo root as `../.env.local`
- Frontend is published on `http://localhost:8080`
- Local runtime uses local provider credentials and local Microsoft app registration when those features are enabled
- Deployment smoke requires Vertex AI, OpenAI, and Anthropic when `DEPLOYMENT_SMOKE_REQUIRED=true`
- Local env keeps `AUTH_COOKIE_SECURE=false`
- Local env keeps `DEPLOYMENT_SMOKE_REQUIRED=false`

## First-Time Setup

```powershell
cd ~/ai-proxy/deploy && sh deploy.sh
```

Before first startup:

- replace every `$your-...` placeholder in `../.env.local`
- keep `AUTH_COOKIE_SECURE=false`
- keep `DEPLOYMENT_SMOKE_REQUIRED=false` unless you intentionally want provider smoke checks to gate local health
- confirm the Microsoft local app registration includes redirect URI `http://localhost:8080/api/v1/auth/callback/microsoft` if Microsoft login is enabled
- place local-only secret files under `../secrets/` when using providers that need mounted files

## Commands

Start:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

Stop:

```powershell
docker compose --env-file ../.env.local -f docker-compose.yml -f docker-compose.local.yml down
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

- `docker-compose.local.yml` is the only place that should expose port `8080` to the host
- Local runtime does not require sibling `root-proxy`
- `backend`, PostgreSQL, and Redis remain internal to this stack
- Missing required env values fail during Docker Compose interpolation before startup
- Optional blank env values must still be present in `.env.local` as blank lines such as `AUTH_COOKIE_DOMAIN=`
- Placeholder `$your-...` values are intentionally visible in `.env.local` until replaced
