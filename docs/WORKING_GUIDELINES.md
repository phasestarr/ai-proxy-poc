# Working Guidelines

## Package Boundaries
- Keep `proxy-api/app/api/v1/endpoints/` limited to HTTP routing and response mapping.
- Keep `proxy-api/app/api/v1/dependencies/` limited to FastAPI request, auth, and DB injection helpers.
- Keep `proxy-api/app/api/v1/presenters/` limited to API response mapping.
- Keep public request and response contracts in `proxy-api/app/schemas/`.
- Keep business rules in `proxy-api/app/services/`.
- Keep authentication business rules in `proxy-api/app/auth/`.
- Keep PostgreSQL wiring and ORM models in `proxy-api/app/db/postgres/`.
- Keep PostgreSQL schema changes in Alembic migrations under `proxy-api/alembic/versions/`.
- Keep Redis wiring and coordination in `proxy-api/app/db/redis/`.
- Keep provider-neutral routing in `proxy-api/app/providers/`.
- Keep Vertex SDK code inside `proxy-api/app/providers/vertex/`.

## Change Rules
- Prefer small, explicit changes.
- Do not move provider SDK logic into routers.
- Do not put storage client setup into endpoint files.
- When a module is scaffold-only, say so clearly in code or docs.
- Keep `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, and `docs/ENVIRONMENT.md` aligned with the real runtime.

## Verification
- After backend Python changes, run `python -m compileall app` from `proxy-api/`.
- After frontend TypeScript changes, run `npm run typecheck` from `frontend/`.
- After frontend build-affecting changes, run `npm run build` from `frontend/`.
- After backend API changes, re-check `docs/API.md`.
- After backend routing changes, confirm `proxy-api/app/api/v1/api.py` still registers the intended endpoints.
- After auth changes, verify `GET /health`, `GET /api/v1/models`, `GET /api/v1/auth/me`, unauthenticated chat, and authenticated guest chat.
- After database model changes, add an Alembic migration and re-check `docs/FOR_QUERY_NOOBS.md`.
- After chat history changes, verify history list/load/delete plus a continued chat send.

## Model and Tool Extension Rule
- Backend model/tool exposure starts in `proxy-api/app/providers/catalog.py`.
- Vertex public model definitions currently live in `proxy-api/app/providers/vertex/models.py`.
- Provider-specific wiring belongs under `proxy-api/app/providers/<provider>/`.
- `GET /api/v1/models` is the frontend source of truth for selectable public models and tools.
- If a new public model or tool is added, update backend exposure first and keep the frontend mapping aligned with that response contract.
- Do not reintroduce frontend-side default model selection; model choice should come from the backend catalog and explicit user selection.
- Keep `docs/VENDOR_EXTENSION.md` updated when changing provider, model, or tool integration rules.
