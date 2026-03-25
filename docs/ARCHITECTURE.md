# Architecture

## Runtime
- Browser -> `frontend` NGINX container with TLS termination
- `frontend` NGINX -> `proxy-api` for `/api/*` and `/health`
- `proxy-api` -> PostgreSQL
- `proxy-api` -> Redis
- `proxy-api` -> Vertex AI

Active NGINX config:
- `frontend/nginx/default.conf`

Supported run mode:
- Docker Compose only

## Backend Layout
- `proxy-api/app/main.py`: FastAPI app entrypoint and startup/shutdown hooks
- `proxy-api/app/api/`: route composition
- `proxy-api/app/api/v1/dependencies/`: FastAPI dependency helpers
- `proxy-api/app/api/v1/endpoints/`: HTTP endpoints
- `proxy-api/app/schemas/`: API contracts
- `proxy-api/app/services/`: business logic
- `proxy-api/app/db/postgres/`: SQLAlchemy base, session, ORM models
- `proxy-api/app/db/redis/`: Redis client and Redis-backed coordination
- `proxy-api/app/providers/vertex/`: Vertex SDK adapter
- `proxy-api/app/core/`: shared config and security helpers

## Main Flows

### Guest Session
1. Frontend calls `GET /api/v1/auth/me`.
2. If no session exists, the login page is shown.
3. `POST /api/v1/auth/login/guest` creates a guest user and auth session in PostgreSQL.
4. Backend sets the `HttpOnly` `session_id` cookie.

### Chat Stream
1. `POST /api/v1/chat/completions` enters `app/api/v1/endpoints/chat.py`.
2. `app/api/v1/dependencies/auth.py` resolves the session and capability.
3. `app/services/chat/preparation.py` validates and normalizes the request.
4. `app/services/model_registry.py` resolves the public model id.
5. `app/db/redis/chat_coordination.py` acquires the single-flight lock and rate-limit state.
6. `app/providers/vertex/stream.py` opens the provider stream.
7. `app/services/chat/stream.py` maps provider chunks into SSE `start`, `delta`, `done`, `error`.

### Startup
1. `app/main.py` verifies Redis.
2. `app/db/postgres/session.py` runs `init_database()`.
3. `app/services/auth.py` purges expired auth data.
4. Background auth cleanup loop starts.

## Current Notes
- Active login mode is guest login only.
- `usage` endpoint/service/schema are scaffolded and not registered.
- Microsoft-related DB fields exist, but callback/login flow is not active.
- Database initialization still uses `Base.metadata.create_all()`.
- `proxy-api/alembic/` exists but is currently empty.
