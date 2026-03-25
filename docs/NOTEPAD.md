# NOTEPAD

Snapshot date: `2026-03-25`

## Entry Order

### Frontend Boot
`frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `frontend/src/services/authService.ts` -> `GET /api/v1/auth/me`

### Guest Login
`frontend/src/App.tsx` -> `frontend/src/services/authService.ts` -> `POST /api/v1/auth/login/guest` -> `proxy-api/app/api/v1/endpoints/auth.py` -> `proxy-api/app/services/auth.py`

### Chat
`frontend/src/pages/ChatPage.tsx` -> `frontend/src/services/chatService.ts` -> `POST /api/v1/chat/completions` -> `proxy-api/app/api/v1/endpoints/chat.py` -> `proxy-api/app/api/v1/dependencies/auth.py` -> `proxy-api/app/services/chat/preparation.py` -> `proxy-api/app/services/model_registry.py` -> `proxy-api/app/db/redis/chat_coordination.py` -> `proxy-api/app/providers/vertex/stream.py`

### Backend Startup
`proxy-api/app/main.py` -> `proxy-api/app/db/redis/client.py` -> `proxy-api/app/db/postgres/session.py` -> `proxy-api/app/services/auth.py`

## Files

### Root
- `README.md`: repo overview and Compose run guide
- `Makefile`: Docker Compose helper commands

### Deploy
- `deploy/docker-compose.yml`: full stack topology
- `deploy/.env.example`: Compose env template
- `deploy/deploy.sh`: deployment stub
- `secrets/README.md`: local secret placement note

### Frontend
- `frontend/Dockerfile`: frontend build and NGINX runtime image
- `frontend/package.json`: frontend package manifest
- `frontend/package-lock.json`: npm lockfile
- `frontend/vite.config.ts`: Vite build config
- `frontend/index.html`: SPA HTML shell
- `frontend/nginx/default.conf`: frontend reverse proxy and SPA serving config
- `frontend/nginx/40-generate-dev-cert.sh`: fallback self-signed cert generator
- `frontend/nginx/certs/README.md`: TLS cert placeholder note
- `frontend/src/main.tsx`: React entrypoint
- `frontend/src/App.tsx`: auth bootstrap and page switch
- `frontend/src/styles.css`: global styles
- `frontend/src/config/chatContent.ts`: UI copy pool
- `frontend/src/pages/LoginPage.tsx`: login screen
- `frontend/src/pages/login-page.css`: login styles
- `frontend/src/pages/ChatPage.tsx`: chat screen
- `frontend/src/pages/chat-page.css`: chat styles
- `frontend/src/pages/chat-page-state.ts`: chat transcript state helpers
- `frontend/src/services/authService.ts`: auth/session API wrapper
- `frontend/src/services/chatService.ts`: chat streaming API wrapper
- `frontend/src/services/sse.ts`: SSE parser

### Backend Runtime
- `proxy-api/Dockerfile`: backend image build
- `proxy-api/requirements.txt`: backend dependency list
- `proxy-api/app/main.py`: FastAPI entrypoint
- `proxy-api/app/api/health.py`: `/health` route
- `proxy-api/app/api/router.py`: `/api` router composition
- `proxy-api/app/api/v1/api.py`: v1 route composition
- `proxy-api/app/api/v1/dependencies/__init__.py`: dependency exports
- `proxy-api/app/api/v1/dependencies/auth.py`: session and capability dependencies
- `proxy-api/app/api/v1/dependencies/db.py`: DB session dependency
- `proxy-api/app/api/v1/endpoints/__init__.py`: endpoint package marker
- `proxy-api/app/api/v1/endpoints/auth.py`: auth endpoints
- `proxy-api/app/api/v1/endpoints/chat.py`: chat endpoint
- `proxy-api/app/api/v1/endpoints/models.py`: model listing endpoint
- `proxy-api/app/api/v1/endpoints/usage.py`: usage endpoint scaffold

### Backend Core
- `proxy-api/app/core/config.py`: env-backed settings
- `proxy-api/app/core/security.py`: session and cookie helpers
- `proxy-api/app/core/exceptions.py`: exception scaffold
- `proxy-api/app/core/logging.py`: logging scaffold

### Backend DB
- `proxy-api/app/db/__init__.py`: storage package marker
- `proxy-api/app/db/postgres/__init__.py`: postgres exports
- `proxy-api/app/db/postgres/base.py`: SQLAlchemy base
- `proxy-api/app/db/postgres/session.py`: engine, session factory, `create_all()`
- `proxy-api/app/db/postgres/models/__init__.py`: model exports
- `proxy-api/app/db/postgres/models/user.py`: `users` table
- `proxy-api/app/db/postgres/models/auth.py`: auth/session related tables
- `proxy-api/app/db/postgres/models/chat_request.py`: chat request model scaffold
- `proxy-api/app/db/postgres/models/usage_log.py`: usage log model scaffold
- `proxy-api/app/db/redis/__init__.py`: redis exports
- `proxy-api/app/db/redis/client.py`: Redis client
- `proxy-api/app/db/redis/chat_coordination.py`: chat lock and rate-limit logic

### Backend Services
- `proxy-api/app/services/__init__.py`: service package marker
- `proxy-api/app/services/auth.py`: guest session and auth lifecycle logic
- `proxy-api/app/services/model_registry.py`: public model registry
- `proxy-api/app/services/usage.py`: usage service scaffold
- `proxy-api/app/services/chat/__init__.py`: chat service exports
- `proxy-api/app/services/chat/preparation.py`: request validation and normalization
- `proxy-api/app/services/chat/stream.py`: chat orchestration and SSE mapping

### Backend Providers
- `proxy-api/app/providers/__init__.py`: provider package marker
- `proxy-api/app/providers/vertex/__init__.py`: Vertex package marker
- `proxy-api/app/providers/vertex/client.py`: Vertex config check and SDK client creation
- `proxy-api/app/providers/vertex/mapper.py`: schema-to-Vertex mapping
- `proxy-api/app/providers/vertex/stream.py`: Vertex streaming adapter
- `proxy-api/app/providers/vertex/types.py`: normalized provider chunk types

### Backend Schemas
- `proxy-api/app/schemas/__init__.py`: schema package marker
- `proxy-api/app/schemas/auth.py`: auth response schemas
- `proxy-api/app/schemas/chat.py`: chat request and SSE schemas
- `proxy-api/app/schemas/model.py`: model list schemas
- `proxy-api/app/schemas/usage.py`: usage schema scaffold

## Notes
- Active auth flow is guest login only.
- `usage` modules are scaffold-only and not registered.
- Microsoft auth-related fields exist, but the flow is not active yet.
- DB initialization still uses `create_all()` and `proxy-api/alembic/` is empty.
