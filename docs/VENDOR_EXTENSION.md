# Vendor Extension Guide

Guide for adding or changing AI vendors, public models, and selectable tools.

## Current Shape
- Public model catalog is backend-owned.
- Provider-neutral model routing lives in `proxy-api/app/providers/catalog.py`.
- Provider dispatch lives in `proxy-api/app/providers/dispatcher.py`.
- Provider-specific code lives under `proxy-api/app/providers/<provider>/`.
- Frontend reads `GET /api/v1/models` for selectable public models and tools.
- Frontend chat requests send `model_id` and `tool_ids` to the backend.

## Current Providers
- Active: Vertex AI via `proxy-api/app/providers/vertex/`
- Placeholder only: OpenAI public model entry `chatgpt`

## When Adding A Public Model
1. Add or update the backend catalog entry in `proxy-api/app/providers/catalog.py`.
2. If the model belongs to a new provider, add provider-specific code under `proxy-api/app/providers/<provider>/`.
3. Update `proxy-api/app/providers/dispatcher.py` so the provider can be validated and streamed.
4. If request or response mapping differs, add mapper logic under that provider package.
5. If the `/api/v1/models` response shape changes, update `frontend/src/services/modelService.ts`.
6. Re-check `docs/API.md` and `README.md`.

## When Adding A Public Tool
1. Decide which public model ids support the tool.
2. Add the tool id to the backend model definition in `proxy-api/app/providers/catalog.py` or provider model source.
3. Implement provider-specific tool payload mapping under the provider package.
4. Keep the `/api/v1/models` tool metadata aligned with the backend-accepted `tool_ids`.
5. If the frontend needs new tool labels or flags, update `frontend/src/services/modelService.ts`.
6. Re-check validation behavior in `proxy-api/app/services/chat/preparation.py` and provider-specific execution.
7. Document any new env or secret requirements in `docs/ENVIRONMENT.md`.

## When Adding A New Provider
1. Create `proxy-api/app/providers/<provider>/`.
2. Add provider readiness validation.
3. Add provider stream execution.
4. Add provider request/response mapping.
5. Expose one or more public model definitions through the shared catalog.
6. Update dispatcher branches.
7. If provider-specific metadata changes the public response shape, update `frontend/src/services/modelService.ts`.

## Response Contract
The current `/api/v1/models` response is expected to contain, per model:
- `id`
- `provider`
- `display_name`
- `available`
- `default`
- `tools[]`

Each tool entry is expected to contain:
- `id`
- `display_name`
- `available`

These ids must line up directly with:
- request `model_id` in `POST /api/v1/chat/completions`
- request `tool_ids[]` in `POST /api/v1/chat/completions`

## Recommended Future Cleanup
- Keep provider implementation details out of frontend code.
- Keep public ids stable even if the vendor-specific model name changes.
