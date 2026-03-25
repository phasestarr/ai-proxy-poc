# Purpose:
# - Provide short aliases for the Docker Compose workflow.
#
# Supported usage:
# - Start and stop the full stack
# - View service logs

.PHONY: docker-up docker-down docker-logs

docker-up:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml up --build -d

docker-down:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml down

docker-logs:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f
