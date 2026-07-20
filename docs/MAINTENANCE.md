# Maintenance

Change points that matter when extending or debugging the current stack.

## Configuration Ownership
- `.env` owns deployment-specific policy, credentials, and external resource ids
- `backend/app/config/*.py` owns version-controlled application policy and algorithm constants
- `backend/app/providers/<provider>/config.py` owns provider catalogs, capabilities, versions, helper models, and pricing
- `backend/app/providers/<provider>/options.py` owns frequently adjusted request payload values
- a setting must have one owner; provider options do not fall back between Python config and environment values

## Model and Tool Source Of Truth
- backend owns the public model catalog
- frontend reads `GET /api/v1/models`
- model order in the UI follows backend catalog order
- tool support is model-specific

## Where To Change Models

For an existing provider, model changes should touch:

1. `backend/app/providers/<provider>/config.py`
   - public model ids
   - provider runtime model ids
   - display names
   - availability
   - supported tool ids
   - model capabilities and price cards
2. `backend/app/providers/<provider>/options.py`
   - model to preset mapping
   - thinking/reasoning options and output caps

## Generic Model Defaults

Backend-owned generic helper ids are declared in each provider's `config.py`.

Current generic-helper call sites:
- internal context compression -> `backend/app/compression/service.py`
- internal context compression output size is instruction-targeted, not backend `maxOutputTokens` capped
- OpenAI attachment token counting -> `backend/app/providers/openai/attachments.py`
- Anthropic attachment token counting -> `backend/app/providers/anthropic/attachments.py`
- Vertex attachment token counting -> `backend/app/providers/vertex/attachments.py`

## Where To Change Tools

For an existing provider, tool changes should usually touch:

1. `backend/app/providers/<provider>/config.py`
   - public tool metadata, availability, and versions
   - per-model supported tool ids
2. `backend/app/providers/<provider>/options.py`
   - provider-native tool request options
3. `backend/app/providers/<provider>/tools.py`
   - provider-native hosted tool payloads
   - any provider-native tool beta/header logic
4. `backend/app/providers/<provider>/settings.py`
   - only if the tool needs credentials or an external resource id

## Provider Package Shape
- `config.py`
  - operator-facing models, tools, capabilities, versions, helper ids, and pricing
- `options.py`
  - request defaults, presets, output caps, thinking settings, and hosted-tool options
- `settings.py`
  - provider credentials and external resource binding
- `provider.py`
  - provider request coordination and prepared-request construction
- `models.py`
  - runtime model definitions derived from config
- `tools.py`
  - tool metadata and hosted tool payload builders
- `client.py`
  - SDK client creation and readiness checks
- `mapper.py`
  - request/response mapping
- `usage.py`
  - provider usage normalization
  - provider price estimation
- `count_tokens.py`
  - provider-native exact input token counting
- `stream.py`
  - raw SDK transport and provider error mapping

## Current Public Surface

Use `GET /api/v1/models` for runtime model/tool exposure, provider `config.py`
for catalogs, and provider `options.py` for request behavior. Do not duplicate
those lists here.

## Output Cap Rule
- output token caps live in provider request options
- env does not own provider output caps
- OpenAI caps live in `backend/app/providers/openai/options.py`
- Anthropic caps live in `backend/app/providers/anthropic/options.py`
- Vertex caps live in `backend/app/providers/vertex/options.py`

## Current Tool Mapping

Provider tool versions live in `config.py`, request options live in `options.py`,
and provider-native payload construction lives in `tools.py`.

## Payload Assembly And Chat Execution Path
1. request schema validation
   - `backend/app/schemas/chat.py`
2. route resolution
   - `backend/app/services/chat/completions/route_selection.py`
3. send validation checks
   - `backend/app/services/chat/completions/validation.py`
   - enforces per-user usage caps before provider execution
4. orchestration and lease ownership
   - `backend/app/services/chat/completions/orchestrator.py`
   - starts a token-fenced `chat_operations` row for the target history, creating a history first for text-only new chats
   - emits pre-provider SSE status messages
5. persisted context rebuild and request preparation
   - `backend/app/services/chat/completions/request_builder.py`
   - reloads the owned history
   - calls `build_chat_context`
   - assembles the provider payload
   - conditionally resolves exact input-token counts
6. system instruction ownership
   - `backend/app/config/chat_instructions.py`
   - backend-owned default system instruction
7. context assembly
   - `backend/app/services/chat/completions/context/pipeline.py`
   - injects checkpoint summary as a `user` message when present
   - includes only raw messages after `covered_through_sequence`
   - appends the latest user request message as the final turn
8. provider-native payload build
   - provider coordination: `backend/app/providers/<provider>/provider.py`
   - message translation: `backend/app/providers/<provider>/mapper.py`
   - request values: `backend/app/providers/<provider>/options.py`
   - hosted tools: `backend/app/providers/<provider>/tools.py`
9. local estimate and exact-count gate
   - heuristic estimate is attached in `backend/app/providers/<provider>/provider.py`
   - threshold constants live in `backend/app/config/chat.py`
   - budget decisions live in `backend/app/services/chat/completions/context/budget.py`
   - exact token counters live in `backend/app/providers/<provider>/count_tokens.py`
10. compaction path
   - decision is made in `backend/app/services/chat/completions/context/budget.py`
   - stream status is emitted from `backend/app/services/chat/completions/orchestrator.py`
   - compaction source text comes from `backend/app/services/chat/completions/context/pipeline.py`
   - checkpoint persistence lives in `backend/app/services/chat/completions/context/checkpoints.py`
11. turn persistence
   - `backend/app/services/chat/completions/turn_persistence.py`
12. provider dispatch and execution
   - `backend/app/providers/dispatcher.py`
   - `backend/app/providers/<provider>/stream.py`
   - provider events must keep arriving before `CHAT_PROVIDER_EVENT_IDLE_TIMEOUT_SECONDS`
   - DB heartbeat writes are throttled; incoming chunks still check the operation token
   - total provider runtime is bounded by `CHAT_PROVIDER_MAX_RUNTIME_SECONDS`
13. completed provider block persistence
   - `backend/app/services/chat/completions/blocks.py`
   - `backend/app/services/chat/completions/turn_persistence.py`
   - block chunks are merged in memory and one `chat_message_blocks` row is written only when the block reaches `operation='end'`
   - persisted block rows are returned by history reads and are not replayed over the active SSE response
14. usage normalization and ledger writes
   - `backend/app/providers/<provider>/usage.py`
   - append-only usage ledger writes live in `backend/app/services/usage_ledger.py`
   - chat transcript rows do not store usage JSON; use `usage_ledger_events` for spend/token audit

## Attachment Change Points

Attachment flow is backend-owned. The frontend only uploads a file and renders backend responses.

Main files:
- `backend/app/services/chat/attachments/service.py`
  - attach/delete/history attachment operations
- `backend/app/services/chat/attachments/validation.py`
  - upload validation
  - user/history attachment limits
- `backend/app/services/chat/attachments/storage.py`
  - per-user blob deduplication
  - stored file lifecycle
- `backend/app/services/chat/attachments/payloads.py`
  - send-time provider payload injection
- `backend/app/services/chat/attachments/remote_files.py`
  - provider file upload/delete/existence checks
- `backend/app/db/postgres/models/chat_attachment.py`
  - `stored_files`
  - `stored_file_provider_states`
  - `chat_history_files`
  - `chat_message_attachments`
- `backend/app/api/v1/endpoints/chat.py`
  - `POST /api/v1/chat/files`
  - `GET /api/v1/chat/histories/{history_id}/files/{file_id}/content`
  - `PATCH /api/v1/chat/histories/{history_id}/files/{file_id}`
  - `DELETE /api/v1/chat/histories/{history_id}/files/{file_id}`
- `backend/app/providers/openai/attachments.py`
  - OpenAI token counting, upload, delete, and payload injection
- `backend/app/providers/anthropic/attachments.py`
  - Anthropic token counting, upload, delete, and payload injection
- `backend/app/providers/vertex/attachments.py`
  - Vertex GCS upload, token counting, delete, and payload injection
- `backend/app/workers/housekeeping.py`
  - startup and hourly housekeeping runner
- `backend/app/workers/chat_attachment_cleanup.py`
  - provider remote ref reconciliation and TTL cleanup
- `backend/app/api/v1/presenters/chat.py`
  - attachment limits and file view envelopes
- `frontend/src/pages/ChatPage.tsx`
  - upload queue and in-memory rendering only
- `frontend/src/pages/chat/components/AttachmentRail.tsx`
  - attachment rail UI
- `frontend/src/pages/chat/components/Composer.tsx`
  - prompt paste interception for clipboard images

## Current Attachment Rules
- supported MIME types:
  - `application/pdf`
  - `image/png`
  - `image/jpeg`
- same-history duplicate content is rejected
  - same user + same `sha256` + same history -> `409`
- cross-history duplicate content is allowed
  - backend reuses the same `stored_files` row for the same user hash
- provider token counts are resolved at attach time for OpenAI, Anthropic, and Vertex
- provider-managed file upload happens at attach time and may be recreated at send time if the stored remote id is missing or the remote copy was deleted out of band
- provider-managed file delete happens when the last logical history reference is removed; the DB row moves through `pending_delete` and `delete_failed` if remote delete fails
- `stored_files.delete_attempt_count`, `delete_error`, `delete_last_attempt_at`, and `delete_next_attempt_at` are the retry/audit fields for blob cleanup
- provider-managed remote copies are also deleted after `CHAT_ATTACHMENT_REMOTE_TTL_HOURS` without use
- attachment limits are separate from text compaction
  - text compaction is still text-only
  - attachment token totals are checked separately per provider

## Attachment Runtime Semantics
- refresh does not restore selected history from browser storage
- the frontend does not auto-recover interrupted SSE
- completed thinking/tool blocks already committed to `chat_message_blocks` render only after an explicit history load or page reload plus history selection
- `chat_operations.owner_token` plus the owner's active operation fields are the concurrency guard
- blank-page upload staging draft cleanup uses `CHAT_DRAFT_TTL_SECONDS`
- validation, compaction, upload/delete/toggle, and history-delete operations use `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`
- provider event liveness uses `CHAT_PROVIDER_EVENT_IDLE_TIMEOUT_SECONDS`; persisted heartbeat writes are throttled and only happen while provider chunks are arriving
- provider hard runtime uses `CHAT_PROVIDER_MAX_RUNTIME_SECONDS`
- provider output after the operation deadline is rejected by the token fence and the turn is treated as timed out
- housekeeping closes stale operations and streaming assistant rows whose operation/message deadline has passed
- delete behavior uses the active operation token
  - if a current operation is active, delete is blocked
  - if the operation deadline has expired, the next operation start or housekeeping can clear it

Crash and recovery behavior:
- attach/delete/toggle operations commit the product mutation before the endpoint marks the operation terminal
- if the backend process crashes in that gap, the mutation may be visible while the operation later times out
- housekeeping clears expired live operation tokens and writes `chat_operation_timed_out` when an operation row remains
- destructive deletes that remove the parent history cascade child operation rows, so there may be no stale operation for housekeeping to close
- chat send moves to `provider_streaming` before user/assistant rows are committed; a crash in that narrow gap leaves no turn rows, only an operation that housekeeping can time out
- this is an expected crash-only path, not a normal request failure path; product recovery is best-effort plus operator visibility
- `delete_stale_empty_histories` assumes `HOUSEKEEPING_INTERVAL_MINUTES` remains greater than `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS`
- if that timing invariant changes, add an active-operation guard before deleting empty histories

Attachment limit semantics:
- per-history duplicate-content protection is enforced by database uniqueness
- per-user attachment count is currently count-based before insert
- concurrent uploads to different histories can exceed the per-user count by a small amount
- use `docs/TO-DO.md` before treating `CHAT_ATTACHMENT_MAX_FILES_PER_USER` as a hard quota

## Attachment Provider Cleanup

Attachment provider lifecycle and cleanup commands live in docs/ATTACHMENT_PROVIDER_FILES.md.

## Operator Events And Usage Caps

- `operator_events` is the single operator-facing event log.
- request rejection events are stored in `operator_events`.
- Usage cap commands live in `docs/USAGE_CAPS.md`.
- Audit queries live in `docs/FOR_AUDIT_QUERY.md`.

## Deployment Smoke Readiness

When `DEPLOYMENT_SMOKE_REQUIRED=true`, backend `/health` runs the deployment
smoke check until it passes. `frontend` depends on backend health, so the public
UI container does not start until smoke succeeds.

Smoke code is isolated under `backend/app/deployment_smoke/`. It calls provider
clients and provider attachment upload-delete helpers directly. It does not use
the public auth/session/chat API, and it must not create user, session, chat,
stored-file, or operator-event rows.

Current smoke expects every exposed provider to be configured and ready:
Vertex AI, OpenAI, and Anthropic.

Manual smoke run from the backend container:

```powershell
docker exec ai-proxy-api python -m app.deployment_smoke
```

Smoke coverage:
- one direct text stream per exposed provider
- one direct attachment upload-delete path per provider
- no product sessions or chat rows are created
- file upload in the product also prepares all three providers at attach time by design

## Context Compaction Conditions
- latest prompt hard limit: `LATEST_PROMPT_MAX_TOKENS`
- text compaction threshold: `TEXT_CONTEXT_COMPACTION_TRIGGER`
- exact text-count trigger: `EXACT_TEXT_TOKEN_COUNT_TRIGGER`
- attachments have an independent per-history/provider token limit
- after compaction, the backend rebuilds the provider payload from DB and checks again

## Before You Add A New Env Var
1. add it to the correct settings module
2. pass it through `deploy/docker-compose.yml`
3. add it to `.env.example`
4. update `docs/ENVIRONMENT.md`
5. if it changes runtime behavior, mention it in `docs/ARCHITECTURE.md` or here
