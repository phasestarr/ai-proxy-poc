# AI Proxy PoC

Monorepo proof of concept for an internal AI proxy.

## Supported Run Mode
- Docker Compose only
- Direct local backend/frontend runs are not part of the supported workflow

## Stack
- `frontend/`: React app built with Vite and served by containerized NGINX
- `proxy-api/`: FastAPI backend
- `deploy/`: Docker Compose and env templates
- `docs/`: reference docs
- `secrets/`: local secret mount point for containerized runs

## Current Scope
Implemented now:
- guest login
- server-side session storage in PostgreSQL
- `HttpOnly` `session_id` cookie
- protected chat route
- Redis-backed single-flight chat coordination
- Redis-backed request rate limits for chat
- model listing
- Vertex AI streaming chat integration when configured

Planned next:
- Microsoft SSO with MSAL-compatible backend flow
- usage reporting and richer quota tracking

## Host Prerequisites
- Docker Engine `29.2.1`
- Docker Compose `v5.0.2`
- Git `2.53.0.windows.1`

## Docker Compose
Create the env file:

```powershell
Copy-Item deploy/.env.example deploy/.env
```

Before first startup:
- set `GOOGLE_CLOUD_PROJECT` in `deploy/.env`
- confirm `GOOGLE_APPLICATION_CREDENTIALS` points at a real file under `secrets/`
- put the service account JSON at `secrets/gcp-service-account.json` unless you change the path

Start the stack:

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up --build -d
```

Host entrypoints:
- `http://localhost:8080` redirects to HTTPS
- `https://localhost:8443` serves the frontend
- `https://localhost:8443/health` proxies backend health
- `https://localhost:8443/api/v1/...` proxies the backend API

Default smoke test:
1. Open `https://localhost:8443`
2. Accept the self-signed certificate warning if the fallback dev cert is being used
3. Wait for the login card
4. Click `Guest Login`
5. Send a prompt
6. Click `Log Out`

Stop the stack:

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml down
```
