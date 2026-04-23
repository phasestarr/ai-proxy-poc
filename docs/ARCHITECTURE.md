# Architecture

Current integrated runtime for `ai-proxy-poc`.

## Edge Path
- Browser -> `root-proxy` on `80/443`
- `root-proxy` terminates TLS
- `root-proxy` routes `ai.nextinsol.com` to `http://ai-proxy-frontend:8080`
- `frontend` NGINX serves the SPA and proxies `/api/*` and `/health` to `proxy-api:8000`
- `proxy-api` uses PostgreSQL, Redis, Vertex AI, OpenAI, and Anthropic

## Frontend Flow
1. `frontend/src/App.tsx` delegates auth bootstrapping to `frontend/src/auth/useAuthSession.ts`, which calls `GET /api/v1/auth/me`.
2. Anonymous users stay on `LoginPage`.
3. Guest login flows through `frontend/src/auth/authApi.ts` and calls `POST /api/v1/auth/login/guest`.
4. Microsoft login flows through `frontend/src/auth/authRedirects.ts` and redirects the whole page to `GET /api/v1/auth/login/microsoft`.
5. The backend redirects to Microsoft, handles the callback, and returns to the SPA after issuing a local session cookie or a short-lived session-conflict ticket.
6. Authenticated users land on `ChatPage`; session conflict UI is rendered by `frontend/src/components/auth/SessionConflictDialog.tsx`.
7. `ChatPage` uses `frontend/src/pages/chat/hooks/useChatModelSelection.ts` to load the backend-owned model catalog from `GET /api/v1/models`.
8. The frontend leaves model selection empty until the user explicitly chooses one from the catalog.
9. `ChatPage` loads chat history summaries from `GET /api/v1/chat/histories` through `frontend/src/chat/api/chatHistoryApi.ts`.
10. `ChatPage` sends `POST /api/v1/chat/completions` through `frontend/src/chat/api/streamChatApi.ts` with the active `chat_history_id`, selected `model_id`, selected `tool_ids`, and latest transcript, then reads SSE events `start`, `delta`, `done`, and `error`.
11. The SSE `start` event returns `chat_history_id`, `user_message_id`, and `assistant_message_id`; the frontend uses that id to continue the same chat history.

## Backend Flow
1. `proxy-api/app/main.py` starts FastAPI, verifies Redis, runs Alembic migrations, purges expired auth data, and starts auth cleanup.
2. Auth routes are split by responsibility:
   - `proxy-api/app/api/v1/endpoints/session_endpoints.py` handles current session lookup, session-conflict resolution, and logout.
   - `proxy-api/app/api/v1/endpoints/guest_login.py` handles guest login.
   - `proxy-api/app/api/v1/endpoints/microsoft_login.py` handles Microsoft login redirects and callbacks.
3. `proxy-api/app/api/v1/endpoints/models.py` exposes the backend model catalog.
4. `proxy-api/app/api/v1/endpoints/chat.py` exposes chat history CRUD, validates chat requests, and enforces authenticated capability `chat:send`.
5. `proxy-api/app/services/chat/preparation.py` resolves `model_id` and `tool_ids` into a provider route.
6. Chat persistence is split between `proxy-api/app/services/chat/history_queries.py`, `proxy-api/app/services/chat/turns.py`, and `proxy-api/app/services/chat/provider_context.py`.
7. `proxy-api/app/db/redis/chat_coordination.py` enforces one in-flight chat per session plus per-user rate limits.
8. `proxy-api/app/providers/dispatcher.py` dispatches to the selected provider.
9. Provider tool modules map backend-owned tool ids like `web_search`, `retrieval`, `code_execution`, and `url_context` into provider-native hosted tool payloads.
10. Provider stream modules call Vertex, OpenAI, or Anthropic and normalize provider chunks into common stream chunks.

## Auth and Data
- Browser auth uses only the `HttpOnly` `session_id` cookie.
- Backend stores a hash of the raw session key, not the raw key.
- Backend stores raw guest IP addresses in `guest_identities` for inspectability.
- Backend stores session-conflict ticket hashes, not raw conflict tickets.
- Guest session idle timeout: `6 hours`
- Guest session absolute lifetime: `24 hours`
- Guest max active sessions: `2`
- Microsoft max active sessions: `4`
- Database schema is managed by Alembic migrations, not `Base.metadata.create_all()`.
- Chat history data is owned by PostgreSQL: `users -> chat_histories -> chat_messages`.

## Active and Inactive Areas
- Active: guest login, backend-owned Microsoft login, session conflict recovery, model listing, chat history, explicit Gemini/OpenAI/Claude model selection, streaming chat, model-specific hosted tools
- Scaffold only: usage schemas, services, and models

## Important Files
- `frontend/nginx/default.conf`
- `frontend/src/App.tsx`
- `frontend/src/auth/useAuthSession.ts`
- `frontend/src/auth/authApi.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/pages/chat/components/`
- `frontend/src/chat/api/`
- `proxy-api/app/main.py`
- `proxy-api/app/auth/`
- `proxy-api/app/api/v1/endpoints/session_endpoints.py`
- `proxy-api/app/api/v1/endpoints/guest_login.py`
- `proxy-api/app/api/v1/endpoints/microsoft_login.py`
- `proxy-api/app/services/chat/stream.py`
- `proxy-api/app/services/chat/turns.py`
- `proxy-api/app/services/chat/history_queries.py`
- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/dispatcher.py`
- `proxy-api/app/providers/vertex/`
- `proxy-api/app/providers/openai/`
- `proxy-api/app/providers/anthropic/`
