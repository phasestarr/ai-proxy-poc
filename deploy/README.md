# Deploy

Container commands for `ai-proxy-poc`.

## First Run

```bash
cd ~/ai-proxy-poc
cp .env.example .env
mkdir -p secrets
chmod +x deploy/deploy.sh
cd deploy
docker compose --env-file ../.env -f docker-compose.yml up --build -d
```

Before first run:

- copy repo-root `.env.example` to repo-root `.env`
- set `GOOGLE_CLOUD_PROJECT`
- confirm `GOOGLE_APPLICATION_CREDENTIALS` points to a real file under `secrets/`
- place the service account JSON under `secrets/`
- set `AI_PROXY_CONTAINER_NAME` to match the sibling `root-proxy` route
- keep `AUTH_COOKIE_SECURE=true` when traffic arrives through HTTPS `root-proxy`

## Start

```bash
docker compose --env-file ../.env -f docker-compose.yml up -d
```

## Stop

```bash
docker compose --env-file ../.env -f docker-compose.yml down
```

## Restart

```bash
docker compose --env-file ../.env -f docker-compose.yml restart
```

## Logs

```bash
docker compose --env-file ../.env -f docker-compose.yml logs -f
```
