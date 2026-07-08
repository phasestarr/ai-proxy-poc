# Deploy

Deployment is split into one shared Compose file plus one environment-specific
override.

## Assumptions

- Commands are run from `ai-proxy/deploy`
- Docker Engine and the Docker Compose plugin are installed
- Repo-root `.env.example` exists
- Server deployment uses sibling `root-proxy`, which must overwrite `X-Real-IP`
  and all `X-Forwarded-*` headers before traffic reaches this stack
- Local deployment runs directly on `localhost`

## First-Time Setup

```bash
cd ~/ai-proxy/deploy && sh deploy.sh
```

Expected result: setup completes and prints a message. Containers are not
started by this command.

## Commands

Server runtime commands:

```text
README-SERVER.md
```

Local runtime commands:

```text
README-LOCAL.md
```

## Notes

- `deploy.sh` creates `.env` and `.env.local` from `.env.example` when they are missing
- `deploy.sh` sets `AUTH_COOKIE_SECURE=false` only in newly-created `.env.local`
- `deploy.sh` sets `DEPLOYMENT_SMOKE_REQUIRED=false` only in newly-created `.env.local`
- `deploy.sh` creates external Docker network `edge-net` when it is missing
- `deploy.sh` does not start, stop, restart, or rebuild containers
- `docker-compose.yml` is shared by server and local runtime
- `docker-compose.server.yml` attaches only the public frontend container to `edge-net`
- `docker-compose.local.yml` publishes the frontend on localhost
- Deployment smoke exercises direct text generation plus direct provider
  attachment upload-delete paths for Vertex AI, OpenAI, and Anthropic when
  `DEPLOYMENT_SMOKE_REQUIRED=true`
