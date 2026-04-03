# Environment Variables

## Source of Truth
- Host-side runtime variables live in the repo-root `.env`.
- Docker Compose injects backend container variables from `deploy/docker-compose.yml`.
- Direct local backend `.env` files are not part of the supported workflow.

## Variables In `.env`

### Frontend
- `AI_PROXY_CONTAINER_NAME`: frontend container name. Default `ai-proxy-frontend`
- `AI_PROXY_HTTP_PORT`: host port that receives upstream proxy traffic and direct local HTTP testing. Default `8081`

### Database
- `POSTGRES_DB`: PostgreSQL database name. Default `ai_proxy`
- `POSTGRES_USER`: PostgreSQL user. Default `postgres`
- `POSTGRES_PASSWORD`: PostgreSQL password. Default `postgres`

### App
- `APP_NAME`: backend app name. Default `AI Proxy API`
- `APP_ENV`: backend app environment. Default `dev`
- `AUTH_COOKIE_SECURE`: whether session cookies require HTTPS. Default `true`

### Vertex / GCP
- `GOOGLE_APPLICATION_CREDENTIALS`: in-container path to the mounted JSON credential file
- `GOOGLE_CLOUD_PROJECT`: GCP project id used for Vertex
- `GOOGLE_CLOUD_LOCATION`: Vertex location. Default `global`
- `VERTEX_AI_MODEL`: public default provider model binding. Default `gemini-2.5-flash`
- `VERTEX_AI_API_VERSION`: Vertex API version. Default `v1`
- `VERTEX_AI_RAG_CORPORA`: optional comma-separated or JSON-array list of Vertex AI RAG corpus resource names
- `VERTEX_AI_RAG_SIMILARITY_TOP_K`: optional retrieval depth for RAG grounding. Default `5`
- `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`: optional minimum similarity threshold passed to Vertex RAG retrieval

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
- `AUTH_COOKIE_SECURE` is passed through from `.env` and defaults to `true`.
- The backend, PostgreSQL, and Redis containers are not directly published on host ports.

## Runtime Notes
- Direct host receive port is `http://localhost:8081` with the current `.env`.
- In the integrated deployment, upstream TLS is terminated by the sibling `root-proxy` stack before traffic reaches this repo.
- Leave `AUTH_COOKIE_SECURE=true` when traffic arrives through an HTTPS edge proxy. Set it to `false` only for plain HTTP local debugging.
- RAG mode stays off unless `VERTEX_AI_RAG_CORPORA` contains at least one corpus resource name.
- This repo currently assumes the RAG corpus already exists; control-plane corpus creation/import is still an external step.
