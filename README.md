# AI Proxy PoC

Monorepo proof of concept for an internal AI proxy.

## Supported Run Mode
- Docker Compose only
- Direct local backend/frontend runs are not part of the supported workflow

## Stack
- `frontend/`: React app built with Vite and served by containerized NGINX
- `proxy-api/`: FastAPI backend
- `deploy/`: Docker Compose runtime files
- `.env.example`: Compose env template copied to repo-root `.env`
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
- optional Vertex AI RAG Engine grounding when one or more RAG corpora are configured

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
Copy-Item .env.example .env
```

Before first startup:
- set `GOOGLE_CLOUD_PROJECT` in `.env`
- confirm `GOOGLE_APPLICATION_CREDENTIALS` points at a real file under `secrets/`
- put the service account JSON at `secrets/gcp-service-account.json` unless you change the path
- set `AI_PROXY_CONTAINER_NAME` in `.env` to match your edge routing plan
- if you want grounded RAG responses, create a Vertex AI RAG corpus separately and set
  `VERTEX_AI_RAG_CORPORA` to one or more corpus resource names

Operational commands:
- [deploy/README.md](deploy/README.md)
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)

Host entrypoints:
- `root-proxy` is the public entrypoint for this stack
- in the integrated deployment, sibling `root-proxy` terminates TLS and forwards HTTPS traffic to `http://ai-proxy-frontend:8080` over `edge-net`
- the frontend is no longer published directly on a host port

Default smoke test:
1. Start `root-proxy`
2. Open the upstream HTTPS host
3. Wait for the login card
4. Click `Guest Login`
5. Send a prompt
6. Click `Log Out`
