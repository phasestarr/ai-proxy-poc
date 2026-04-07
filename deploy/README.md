# Deploy

Deployment is split into one shared base compose file plus one environment-specific override.

## Files
- `docker-compose.yml`: shared base stack
- `docker-compose.server.yml`: server-only override for `edge-net`
- `docker-compose.local.yml`: local-only override for host port publishing and dev auth cookie settings

## Docs
- [README-SERVER.md](README-SERVER.md)
- [README-LOCAL.md](README-LOCAL.md)
