# Install Guide

## Supported Workflow
- Docker Compose only
- Direct local backend/frontend runs are out of scope

## Required Tools
- Docker Engine `29.2.1`
- Docker Compose `v5.0.2`
- Git

## 1. Create the Compose env file
```powershell
Copy-Item deploy/.env.example deploy/.env
```

Edit `deploy/.env` before first startup:
- set `GOOGLE_CLOUD_PROJECT` to your GCP project ID
- confirm `GOOGLE_APPLICATION_CREDENTIALS` points to a real file under `secrets/`
- adjust ports only if `8080`, `8443`, or `5432` are already taken

## 2. Add the local secret file
- Put the Vertex service account JSON at `secrets/gcp-service-account.json`
- Or change `GOOGLE_APPLICATION_CREDENTIALS` in `deploy/.env` to match a different filename

## 3. Start the stack
```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up --build -d
```

## 4. Verify the stack
- Open `https://localhost:8443`
- If the frontend generated a fallback cert, accept the browser warning
- Confirm `https://localhost:8443/health` returns the backend health response
- Wait for the login card
- Click `Guest Login`
- Send a prompt and confirm the response streams back
- Click `Log Out`

## 5. Stop the stack
```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml down
```

## Notes
- Compose reads `deploy/.env`
- If `GOOGLE_CLOUD_PROJECT` is blank, chat requests return backend `503`
- The `frontend` image bundles NGINX, terminates TLS, serves the SPA, and proxies `/api`
- `http://localhost:8080` redirects to `https://localhost:8443`
