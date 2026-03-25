# Local Secrets

Place local-only credential files for development here.

- Default Vertex AI service account file name: `gcp-service-account.json`
- Docker Compose mounts this directory into `proxy-api` at `/run/secrets`
- The repository ignores all other files under this directory
- Replace this local JSON file with Workload Identity Federation when moving to the server
