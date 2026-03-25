# Deploy

This directory holds the Docker Compose runtime files for the project.

## Files
- `docker-compose.yml`: local stack definition for `frontend`, `proxy-api`, `postgres`, and `redis`
- `.env.example`: committed template for Compose variables
- `.env`: local-only runtime file copied from `.env.example`
- `deploy.sh`: deployment stub

## Usage
1. Copy `deploy/.env.example` to `deploy/.env`
2. Fill in the real values you need
3. Run Compose with `--env-file deploy/.env`

## Notes
- `deploy/.env` is ignored and should stay local
- `deploy/.env.example` is intentionally committed as a dummy template
