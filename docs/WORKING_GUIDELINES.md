# Working Guidelines

## Package Boundaries
- Keep `proxy-api/app/api/v1/endpoints/` limited to HTTP routing and response mapping.
- Keep `proxy-api/app/api/v1/dependencies/` limited to FastAPI request, auth, and DB injection helpers.
- Keep public request and response contracts in `proxy-api/app/schemas/`.
- Keep business rules in `proxy-api/app/services/`.
- Keep PostgreSQL wiring and ORM models in `proxy-api/app/db/postgres/`.
- Keep Redis wiring and Redis-backed coordination in `proxy-api/app/db/redis/`.
- Keep Vertex SDK code inside `proxy-api/app/providers/vertex/`.
- Keep `proxy-api/app/core/` for shared config, security, logging, and exception primitives only.

## Change Rules
- Prefer small, explicit changes over broad speculative refactors.
- Do not move provider SDK logic into routers or services that are not provider-specific.
- Do not put HTTP request parsing logic into service modules.
- Do not put storage client setup into endpoint files.
- When a module is scaffold-only, describe it as scaffolded rather than implemented.

## Verification
- After backend Python changes, run `python -m compileall proxy-api/app`.
- Prefer Docker Compose based verification over direct local runs.
- After backend API changes, re-check `docs/API.md`.
- After backend routing changes, confirm `proxy-api/app/api/v1/api.py` still registers the intended endpoints.
- After auth changes, verify:
  - `GET /health`
  - `GET /api/v1/models`
  - `GET /api/v1/auth/me`
  - unauthenticated `POST /api/v1/chat/completions`
  - authenticated guest-session `POST /api/v1/chat/completions`

## Session and Provider Rules
- Backend session state is the source of truth.
- Browser auth uses only the `HttpOnly` `session_id` cookie.
- Guest session baseline:
  - idle timeout: `6 hours`
  - absolute lifetime: `24 hours`
- Expired sessions should be rejected and cleaned up at request time.
- Background cleanup should remove expired auth rows.
- Fail clearly when Vertex configuration is missing; do not silently mock responses.

## Documentation Rules
- Keep `docs/API.md`, `docs/ARCHITECTURE.md`, and `docs/ENVIRONMENT.md` aligned with the real Compose runtime.
- Keep `docs/NOTEPAD.md` as a short reference, not a second full architecture document.
