# Purpose:
# - Provide short aliases for the documented Docker Compose workflows.

.PHONY: server-up server-down server-logs local-up local-down local-logs

server-up:
	docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.server.yml up --build -d

server-down:
	docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.server.yml down

server-logs:
	docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.server.yml logs -f

local-up:
	docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up --build -d

local-down:
	docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml down

local-logs:
	docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml logs -f
