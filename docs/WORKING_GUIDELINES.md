# Working Guidelines

## Boundaries
- Keep `proxy-api/app/api/v1/endpoints/` thin.
- Keep business rules in `proxy-api/app/services/`.
- Keep auth logic in `proxy-api/app/auth/`.
- Keep provider-neutral routing in `proxy-api/app/providers/`.
- Keep provider SDK details inside `proxy-api/app/providers/<provider>/`.
- Keep env-backed runtime settings in:
  - `proxy-api/app/config/settings.py`
  - `proxy-api/app/config/providers/<provider>.py`

## Runtime Rule
- Docker Compose is the primary runtime path.
- If code reads a new env var, wire it through:
  - `deploy/docker-compose.yml`
  - `.env.example`
  - `docs/ENVIRONMENT.md`
- Do not leave runtime env behavior depending on an unmounted `.env` file inside the container.

## Provider Rule
- Public model ids and tool exposure start in `proxy-api/app/providers/catalog.py`.
- For an existing provider, most day-to-day changes should stay inside:
  - `models.py`
  - `config.py`
  - `tools.py`
- Keep provider request presets small and human-editable.
- Treat output token caps as provider preset config, not env config.

## Docs Rule
- Keep these docs aligned with the real runtime:
  - `docs/ARCHITECTURE.md`
  - `docs/ENVIRONMENT.md`
  - `docs/API.md`
  - `docs/MAINTENANCE.md`
- `docs/FOR_QUERY_NOOBS.md` is query help; keep it practical and DB-focused.

## Verification
- After backend Python changes:
  - run `python -m compileall app` from `proxy-api/`
- After frontend TypeScript changes:
  - run `npm run typecheck` from `frontend/`
- After frontend build-affecting changes:
  - run `npm run build` from `frontend/`
- After provider model/tool changes:
  - re-check `GET /api/v1/models`
- After env-surface changes:
  - re-check `deploy/docker-compose.yml`, `.env.example`, and `docs/ENVIRONMENT.md`
- After API contract changes:
  - re-check `docs/API.md`
