# Architecture

Current integrated runtime for `ai-proxy-poc`.

## Edge Path
- Browser -> `root-proxy` on `80/443`
- `root-proxy` terminates TLS
- `root-proxy` routes `ai.nextinsol.com` to `http://ai-proxy-frontend:8080`
- `frontend` NGINX serves the SPA and proxies `/api/*` and `/health` to `proxy-api:8000`
- `proxy-api` uses PostgreSQL, Redis, and Vertex AI

## Frontend Flow
1. `frontend/src/App.tsx` boots and calls `GET /api/v1/auth/me`.
2. Anonymous users stay on `LoginPage`.
3. Guest login calls `POST /api/v1/auth/login/guest`.
4. Microsoft login redirects the whole page to `GET /api/v1/auth/login/microsoft`.
5. The backend redirects to Microsoft, handles the callback, and returns to the SPA after issuing a local session cookie.
6. Authenticated users land on `ChatPage`.
7. `ChatPage` loads the backend-owned model catalog from `GET /api/v1/models`.
8. The frontend leaves model selection empty until the user explicitly chooses one from the catalog.
9. `ChatPage` sends `POST /api/v1/chat/completions` with the selected `model_id` and `tool_ids`, then reads SSE events `start`, `delta`, `done`, and `error`.

## Backend Flow
1. `proxy-api/app/main.py` starts FastAPI, verifies Redis, initializes PostgreSQL tables, purges expired sessions, and starts auth cleanup.
2. `proxy-api/app/api/v1/endpoints/auth.py` handles current session lookup, guest login, Microsoft login redirects, and logout.
3. `proxy-api/app/api/v1/endpoints/models.py` exposes the backend model catalog.
4. `proxy-api/app/api/v1/endpoints/chat.py` validates chat requests and enforces authenticated capability `chat:send`.
5. `proxy-api/app/services/chat/preparation.py` resolves `model_id` and `tool_ids` into a provider route.
6. `proxy-api/app/db/redis/chat_coordination.py` enforces one in-flight chat per session plus per-user rate limits.
7. `proxy-api/app/providers/dispatcher.py` dispatches to the selected provider.
8. `proxy-api/app/providers/vertex/tools.py` maps backend-owned tool ids like `web_search`, `retrieval`, and `code_execution` into Vertex tool payloads.
9. `proxy-api/app/providers/vertex/stream.py` streams Vertex output for the selected Gemini variant.

## Auth and Data
- Browser auth uses only the `HttpOnly` `session_id` cookie.
- Backend stores a hash of the raw session key, not the raw key.
- Guest session idle timeout: `6 hours`
- Guest session absolute lifetime: `24 hours`
- Database bootstrap currently uses `Base.metadata.create_all()`.

## Active and Inactive Areas
- Active: guest login, backend-owned Microsoft login, model listing, explicit Gemini variant selection, streaming chat, optional `web_search`, optional `retrieval`, optional `code_execution`
- Scaffold only: usage schemas, services, and models
- Placeholder only: public `gpt-4.2` model entry exists, but execution is not wired

## Important Files
- `frontend/nginx/default.conf`
- `frontend/src/App.tsx`
- `frontend/src/services/authService.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/services/chatService.ts`
- `proxy-api/app/main.py`
- `proxy-api/app/services/auth.py`
- `proxy-api/app/services/microsoft_auth.py`
- `proxy-api/app/services/chat/stream.py`
- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/dispatcher.py`
- `proxy-api/app/providers/vertex/`
