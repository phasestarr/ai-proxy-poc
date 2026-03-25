# Environment Variables

## Source of Truth
- Host-side runtime variables live in `deploy/.env`.
- Docker Compose injects backend container variables from `deploy/docker-compose.yml`.
- Direct local backend `.env` files are not part of the supported workflow.

## Variables In `deploy/.env`

### Ports
- `FRONTEND_HTTP_PORT`: host port for frontend HTTP. Default `8080`
- `FRONTEND_HTTPS_PORT`: host port for frontend HTTPS. Default `8443`
- `POSTGRES_PORT`: host port for PostgreSQL. Default `5432`

### Database
- `POSTGRES_DB`: PostgreSQL database name. Default `ai_proxy`
- `POSTGRES_USER`: PostgreSQL user. Default `postgres`
- `POSTGRES_PASSWORD`: PostgreSQL password. Default `postgres`

### App
- `APP_NAME`: backend app name. Default `AI Proxy API`
- `APP_ENV`: backend app environment. Default `dev`

### Vertex / GCP
- `GOOGLE_APPLICATION_CREDENTIALS`: in-container path to the mounted JSON credential file
- `GOOGLE_CLOUD_PROJECT`: GCP project id used for Vertex
- `GOOGLE_CLOUD_LOCATION`: Vertex location. Default `global`
- `VERTEX_AI_MODEL`: public default provider model binding. Default `gemini-2.5-flash`
- `VERTEX_AI_API_VERSION`: Vertex API version. Default `v1`

### Chat Limits
- `CHAT_INFLIGHT_LOCK_TTL_SECONDS`: Redis single-flight lock TTL. Default `180`
- `CHAT_RATE_LIMIT_PER_MINUTE`: per-user minute limit. Default `10`
- `CHAT_RATE_LIMIT_PER_HOUR`: per-user hour limit. Default `30`

### Startup
- `STARTUP_DEPENDENCY_MAX_ATTEMPTS`: startup retry count. Default `30`
- `STARTUP_DEPENDENCY_RETRY_SECONDS`: startup retry delay. Default `2`

### Image / Build Version Pins
- `PYTHON_VERSION`: backend Python base image version
- `PIP_VERSION`: backend pip version
- `NODE_VERSION`: frontend Node build image version
- `NPM_VERSION`: frontend npm version
- `POSTGRES_VERSION`: PostgreSQL image tag
- `NGINX_VERSION`: frontend NGINX image tag
- `REDIS_VERSION`: Redis image tag

## Compose-Derived Backend Variables
- `DATABASE_URL` is built inside Compose from the PostgreSQL settings.
- `REDIS_URL` is set inside Compose as `redis://redis:6379/0`.
- `AUTH_COOKIE_SECURE=true` is set inside Compose.
- The backend container is not directly published on a host port.

## Runtime Notes
- Host entrypoint is `https://localhost:8443`.
- `http://localhost:8080` redirects to HTTPS in the default stack.
- The frontend container generates a fallback self-signed certificate if real TLS files are not mounted.
