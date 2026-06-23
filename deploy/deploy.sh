#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
repo_root=$(CDPATH= cd -- .. && pwd)

env_example="$repo_root/.env.example"
server_env="$repo_root/.env"
local_env="$repo_root/.env.local"

if [ ! -f "$server_env" ]; then
    cp "$env_example" "$server_env"
    echo "Created server env: $server_env"
else
    echo "Found existing server env: $server_env"
fi

if [ ! -f "$local_env" ]; then
    sed \
        -e 's/^AUTH_COOKIE_SECURE=.*/AUTH_COOKIE_SECURE=false/' \
        -e 's/^DEPLOYMENT_SMOKE_REQUIRED=.*/DEPLOYMENT_SMOKE_REQUIRED=false/' \
        "$env_example" > "$local_env"
    echo "Created local env: $local_env"
else
    echo "Found existing local env: $local_env"
fi

if docker network inspect edge-net >/dev/null 2>&1; then
    echo "Found Docker network edge-net"
else
    docker network create edge-net >/dev/null
    echo "Created Docker network edge-net"
fi

server_placeholders=$(grep -n '\$your-' "$server_env" || true)
local_placeholders=$(grep -n '\$your-' "$local_env" || true)

printf '\nai-proxy setup complete.\n\n'
printf 'Container status: not started\n'
printf 'Server env: %s\n' "$server_env"
printf 'Local env: %s\n' "$local_env"
printf 'Secrets dir: %s\n\n' "$repo_root/secrets"
printf 'Next steps:\n'
printf '1. Replace placeholder values in .env before server deployment.\n'
printf '2. Replace placeholder values in .env.local before local deployment.\n'
printf '3. Place any required server-local secret files in secrets/.\n'
printf '4. Use deploy/README-SERVER.md or deploy/README-LOCAL.md for Docker Compose commands.\n'

if [ -n "$server_placeholders" ]; then
    printf '\nServer placeholders still present:\n%s\n' "$server_placeholders"
fi

if [ -n "$local_placeholders" ]; then
    printf '\nLocal placeholders still present:\n%s\n' "$local_placeholders"
fi
