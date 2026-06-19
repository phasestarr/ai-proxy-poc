# Maintenance

Change points that matter when extending or debugging the current stack.

## Model and Tool Source Of Truth
- backend owns the public model catalog
- frontend reads `GET /api/v1/models`
- model order in the UI follows backend catalog order
- tool support is model-specific

## Where To Change Models

For an existing provider, model changes should usually touch:

1. `backend/app/providers/<provider>/models.py`
   - public model ids
   - provider runtime model ids
   - display names
   - availability
   - supported tool ids
2. `backend/app/providers/<provider>/config.py`
   - model to preset mapping
   - provider request preset values

Current provider model files:
- `backend/app/providers/vertex/models.py`
- `backend/app/providers/openai/models.py`
- `backend/app/providers/anthropic/models.py`

## Generic Model Defaults

Keep backend-owned generic helper work pinned to these lighter tiers unless a specific call site has a reason to override:

- Vertex: `gemini-3-flash-preview`
- OpenAI: `gpt-5.4-mini`
- Anthropic: `claude-haiku-4-5`

Current generic-helper call sites:
- internal context compression -> `backend/app/compression/service.py`
- internal context compression output size is instruction-targeted, not backend `maxOutputTokens` capped
- OpenAI attachment token counting -> `backend/app/providers/openai/attachments.py`
- Anthropic attachment token counting -> `backend/app/providers/anthropic/attachments.py`
- Vertex attachment token counting -> `backend/app/providers/vertex/attachments.py`

## Where To Change Tools

For an existing provider, tool changes should usually touch:

1. `backend/app/providers/<provider>/tools.py`
   - public tool metadata
   - provider-native hosted tool payloads
   - any provider-native tool beta/header logic
2. `backend/app/providers/<provider>/models.py`
   - assign supported tool ids to each model
3. `backend/app/config/providers/<provider>.py`
   - only if the tool needs env-backed configuration

## Provider Package Shape
- `models.py`
  - provider model catalog
- `config.py`
  - request presets and model-to-preset mapping
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
  - actual provider call and error mapping

## Current Public Models

Vertex:
- `gemini-3.1-pro-preview`
- `gemini-3-flash-preview`
- `gemini-3.1-flash-lite-preview`

OpenAI:
- `gpt-5.4`
- `gpt-5.4-mini`
- `gpt-5.4-nano`

Anthropic:
- `claude-opus-4-7`
- `claude-sonnet-4-6`
- `claude-haiku-4-5`

## Current Public Tools

Vertex:
- `web_search`
- `retrieval`
- `code_execution`
- `url_context`

OpenAI:
- `web_search`
- `retrieval`
- `code_execution`

Anthropic:
- `web_search`
- `code_execution`

## Output Cap Rule
- output token caps live in provider preset config
- env does not own provider output caps
- OpenAI caps live in `backend/app/providers/openai/config.py`
- Anthropic caps live in `backend/app/providers/anthropic/config.py`
- Vertex caps live in `backend/app/providers/vertex/config.py`

## Current Tool Mapping

Vertex:
- `web_search` -> `google_search`
- `retrieval` -> `retrieval.vertex_rag_store`
- `code_execution` -> `code_execution`
- `url_context` -> `url_context`

OpenAI:
- `web_search` -> Responses API `web_search`
- `retrieval` -> Responses API `file_search`
- `code_execution` -> Responses API `code_interpreter`

Anthropic:
- `web_search` -> Messages API `web_search_20250305`
- `code_execution` -> Messages API `code_execution_20250825`

## Payload Assembly And Chat Execution Path
1. request schema validation
   - `backend/app/schemas/chat.py`
2. route resolution
   - `backend/app/services/chat/completions/route_selection.py`
3. preflight checks
   - `backend/app/services/chat/completions/preflight.py`
4. orchestration and lease ownership
   - `backend/app/services/chat/completions/orchestrator.py`
   - acquires the `chat_history_id` Redis lease
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
   - injects checkpoint summary as a `system` message when present
   - includes only raw messages after `covered_through_sequence`
   - appends the latest user request message as the final turn
8. provider-native payload build
   - OpenAI: `backend/app/providers/openai/mapper.py` + `backend/app/providers/openai/config.py`
   - Anthropic: `backend/app/providers/anthropic/mapper.py` + `backend/app/providers/anthropic/config.py`
   - Vertex: `backend/app/providers/vertex/mapper.py` + `backend/app/providers/vertex/config.py`
9. local estimate and exact-count gate
   - heuristic estimate is attached in `backend/app/providers/<provider>/stream.py`
   - threshold constants live in `backend/app/services/chat/completions/context/budget.py`
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
13. usage normalization and history rollup
   - `backend/app/providers/<provider>/usage.py`
   - `backend/app/services/chat/histories/usage_summary.py`

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
- provider-managed file delete happens when the last logical history reference is removed; the DB row is kept if remote delete fails
- provider-managed remote copies are also deleted after `CHAT_ATTACHMENT_REMOTE_TTL_HOURS` without use
- attachment limits are separate from text compaction
  - text compaction is still text-only
  - attachment token totals are checked separately per provider

## Attachment Runtime Semantics
- refresh does not restore draft or selected history from browser storage
- the frontend does not auto-recover interrupted SSE
- Redis inflight lease is the effective concurrency guard
- `interaction_state` is a UI hint, not the only concurrency authority
- delete behavior uses the Redis lease heuristic
  - if the lease is still active, delete is blocked
  - if the lease has expired, delete may proceed even if stale UI state still says `validating` or `waiting`

## Attachment Provider Cleanup

Attachment provider lifecycle and cleanup commands live in docs/ATTACHMENT_PROVIDER_FILES.md.

## Context Compaction Conditions
- soft threshold: `50000` input tokens
- exact-count trigger starts at `40000` estimated input tokens
- below `40000`: heuristic estimate only
- at or above `40000`: provider-native count-tokens API may run
- if the final budget token count is above `50000`, compaction starts
- after compaction, the backend rebuilds the provider payload from DB and checks again

## Before You Add A New Env Var
1. add it to the correct settings module
2. pass it through `deploy/docker-compose.yml`
3. add it to `.env.example`
4. update `docs/ENVIRONMENT.md`
5. if it changes runtime behavior, mention it in `docs/ARCHITECTURE.md` or here
