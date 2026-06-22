# Server Deploy

Run the stack behind sibling `root-proxy` on `edge-net`.

## Assumptions

- Commands are run from `ai-proxy/deploy`
- Server env file lives at repo root as `../.env`
- Sibling `root-proxy` is already deployed
- External Docker network `edge-net` exists or can be created by setup
- `root-proxy` routes `ai.example.com` to `ai-proxy:8080`
- Microsoft Entra production app registration includes redirect URI `https://ai.example.com/api/v1/auth/callback/microsoft` if Microsoft login is enabled
- Required server-local secret files are present under `../secrets/`

## First-Time Setup

```bash
cd ~/ai-proxy/deploy && sh deploy.sh
```

Before first startup:

- replace every `$your-...` placeholder in `../.env`
- keep `AUTH_COOKIE_SECURE=true`
- keep `AI_PROXY_CONTAINER_NAME=ai-proxy` unless sibling `root-proxy` changes too
- confirm `GOOGLE_APPLICATION_CREDENTIALS` points to a file mounted from `../secrets/`
- confirm Vertex AI, OpenAI, and Anthropic provider keys/settings are ready for deployment smoke

## Commands

Start:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml up --build -d
```

Stop:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.server.yml down -v
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

- `docker-compose.server.yml` is the only place that should attach `frontend` to `edge-net`
- `backend`, PostgreSQL, and Redis remain internal to this stack
- This repo does not terminate TLS; TLS stays in sibling `root-proxy`
- Missing required env values fail during Docker Compose interpolation before startup
- Optional blank env values must still be present in `.env` as blank lines such as `AUTH_COOKIE_DOMAIN=`
- Placeholder `$your-...` values are intentionally visible in `.env` until replaced
