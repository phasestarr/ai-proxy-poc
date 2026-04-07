# AI Proxy PoC

Internal AI proxy stack behind sibling `root-proxy`.

## Runtime
- Public entrypoint: `root-proxy`
- Public host: `ai.nextinsol.com`
- Edge upstream: `ai-proxy-frontend:8080` on external Docker network `edge-net`
- Frontend: NGINX serving the SPA and proxying `/api/*` and `/health`
- Backend: FastAPI
- State: PostgreSQL for auth/session data, Redis for chat coordination and rate limits
- Model execution: Vertex AI

## Active Scope
- guest login
- optional Microsoft login through backend-owned OAuth redirect flow
- `HttpOnly` `session_id` cookie auth
- protected streaming chat endpoint
- Redis-backed single in-flight chat per session
- Redis-backed minute and hourly chat rate limits
- public model catalog at `/api/v1/models`
- Vertex-backed `gemini` public model
- optional Vertex RAG tool exposed as `rag`

## In Repo
- `frontend/`: Vite + React frontend packaged behind NGINX
- `proxy-api/`: FastAPI backend
- `deploy/`: container deployment files for this stack
- `docs/`: architecture, API, environment, and extension notes
- `secrets/`: mounted secret files such as the GCP service account JSON

## Required Setup
1. Copy `.env.example` to `.env`.
2. Set `GOOGLE_CLOUD_PROJECT`.
3. If needed, adjust `GOOGLE_CLOUD_LOCATION`, `VERTEX_AI_MODEL`, and `VERTEX_AI_RAG_*`.
4. Place the service account JSON under `secrets/`.
5. Keep `GOOGLE_APPLICATION_CREDENTIALS` aligned with that mounted file path.
6. Keep `AI_PROXY_CONTAINER_NAME=ai-proxy-frontend` unless the sibling `root-proxy` upstream name changes too.

## Notes
- This repo does not terminate TLS.
- Server deployment assumes sibling `root-proxy` is the only public entrypoint.
- Current `root-proxy` route is `ai.nextinsol.com -> ai-proxy-frontend:8080`.
- Microsoft login remains optional until the Microsoft env vars are configured.
- usage logging remains scaffold-only.

## Docs
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)
- [docs/WORKING_GUIDELINES.md](docs/WORKING_GUIDELINES.md)
- [docs/NOTEPAD.md](docs/NOTEPAD.md)
- [docs/VENDOR_EXTENSION.md](docs/VENDOR_EXTENSION.md)
- [docs/FOR_QUERY_NOOBS.md](docs/FOR_QUERY_NOOBS.md)
