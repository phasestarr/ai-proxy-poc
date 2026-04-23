# Vendor Extension Guide

This guide explains where to change the code when adding or modifying models,
tools, or providers.

## Principles

- The frontend does not know provider internals.
- `GET /api/v1/models` is the frontend source of truth for model and tool choices.
- Shared provider code only knows public model ids, provider ids, display names,
  availability, and exposed tool ids.
- Provider-native request details stay inside `proxy-api/app/providers/<provider>/`.
- SDK client creation, request assembly, tool payloads, response mapping, and
  provider error handling belong to the provider package.
- Chat outcome strings are backend-owned. Success messages and error messages
  are selected in `proxy-api/app/config/chat_outcomes.py` and persisted on
  `chat_messages`.

## Package Boundaries

Shared provider layer:

- `proxy-api/app/providers/types.py`
  - shared dataclasses for models, tools, routes, stream chunks, and usage
- `proxy-api/app/providers/catalog.py`
  - exposes the public model catalog
  - validates requested `model_id` and `tool_ids`
  - creates `ProviderRoute`
- `proxy-api/app/providers/dispatcher.py`
  - checks provider readiness
  - dispatches stream execution to Vertex, OpenAI, or Anthropic
  - maps provider errors into shared execution errors

Chat orchestration layer:

- `proxy-api/app/services/chat/stream.py`
  - creates backend-owned chat turns
  - starts background provider execution
  - emits live SSE events when the browser is still connected
  - persists final success or error outcomes
- `proxy-api/app/services/chat/turns.py`
  - stores user/assistant messages
  - updates assistant rows with final content, result code, result message,
    usage, finish reason, and structured error fields
- `proxy-api/app/services/chat/provider_context.py`
  - rebuilds provider context from stored non-error messages
- `proxy-api/app/services/chat/history_queries.py`
  - lists, loads, creates, and deletes chat histories

Frontend integration points:

- `frontend/src/chat/api/modelApi.ts`
  - parses `/api/v1/models`
- `frontend/src/chat/api/streamChatApi.ts`
  - sends chat requests and reads SSE events
- `frontend/src/pages/ChatPage.tsx`
  - coordinates submit, live deltas, and history refresh
- `frontend/src/pages/chat/state/transcript.ts`
  - maps persisted messages into the local transcript shape
- `frontend/src/pages/chat/components/Composer.tsx`
  - renders model and tool selection

## Provider Packages

Vertex:

- `proxy-api/app/providers/vertex/models.py`
  - public model id to Vertex runtime model id, location, and supported tools
- `proxy-api/app/providers/vertex/client.py`
  - `google.genai.Client(vertexai=True, ...)`
- `proxy-api/app/providers/vertex/config.py`
  - `GenerateContentConfig` assembly
- `proxy-api/app/providers/vertex/stream.py`
  - runtime model resolution
  - `generate_content_stream(...)`
  - Vertex API error mapping
- `proxy-api/app/providers/vertex/mapper.py`
  - internal chat messages to Vertex contents
  - Vertex chunks to shared stream chunks
- `proxy-api/app/providers/vertex/tools.py`
  - backend tool ids to Vertex hosted tool payloads
- `proxy-api/app/providers/vertex/functions.py`
  - custom function declaration scaffold

OpenAI:

- `proxy-api/app/providers/openai/models.py`
  - public model id to OpenAI Responses API runtime model id and supported tools
- `proxy-api/app/providers/openai/client.py`
  - `AsyncOpenAI(...)`
- `proxy-api/app/providers/openai/config.py`
  - Responses API request kwargs assembly
- `proxy-api/app/providers/openai/stream.py`
  - `responses.create(..., stream=True)`
  - OpenAI API error mapping
- `proxy-api/app/providers/openai/mapper.py`
  - internal chat messages to OpenAI input
  - OpenAI events to shared stream chunks
- `proxy-api/app/providers/openai/tools.py`
  - backend tool ids to OpenAI hosted tools

Anthropic:

- `proxy-api/app/providers/anthropic/models.py`
  - public model id to Anthropic Messages API runtime model id and supported tools
- `proxy-api/app/providers/anthropic/client.py`
  - `AsyncAnthropic(...)`
- `proxy-api/app/providers/anthropic/config.py`
  - Messages API request kwargs assembly
- `proxy-api/app/providers/anthropic/stream.py`
  - `beta.messages.create(..., stream=True)`
  - Anthropic API error mapping
- `proxy-api/app/providers/anthropic/mapper.py`
  - internal chat messages to Anthropic system/messages payload
  - Anthropic events to shared stream chunks
- `proxy-api/app/providers/anthropic/tools.py`
  - backend tool ids to Anthropic hosted tools and beta headers

## Chat Request Flow

1. The frontend sends `chat_history_id`, `model_id`, `tool_ids`, and `messages`.
2. `services/chat/turns.py` creates a user message and an assistant placeholder.
3. `services/chat/stream.py` starts a background task for provider execution.
4. `services/chat/preparation.py` resolves `model_id` and `tool_ids`.
5. `providers/catalog.py` validates the public model and selected tools.
6. `services/chat/turns.py` updates the persisted turn with the resolved route.
7. `db/redis/chat_coordination.py` enforces one in-flight request per session and
   per-user rate limits.
8. `providers/dispatcher.py` checks provider readiness and dispatches execution.
9. The selected provider package maps messages, config, tools, and SDK calls.
10. Provider chunks are normalized into shared stream chunks.
11. `services/chat/stream.py` emits live SSE deltas to connected clients.
12. On success, the assistant row is updated with content, usage, finish reason,
    `result_code="success"`, and a backend-selected `result_message`.
13. On failure, the assistant row is updated with `status="error"`,
    `result_code`, `result_message`, `error_origin`, provider/status metadata,
    and `excluded_from_context=true`.

If the browser disconnects after the turn is created, provider execution continues
in the backend and the final outcome is still persisted.

## Adding A Model

For an existing provider, most model additions only touch the provider's
`models.py`.

Vertex:

1. Add an entry to `_VERTEX_MODELS` in `proxy-api/app/providers/vertex/models.py`.
2. Set `public_id`, `provider_model`, `display_name`, `location`, `available`,
   and `supported_tools`.
3. Update `docs/API.md` and `README.md` if the public catalog changes.
4. Only change `vertex/stream.py`, `vertex/config.py`, or `vertex/tools.py` when
   the model needs special runtime behavior.

OpenAI:

1. Add an entry to `_OPENAI_MODELS` in `proxy-api/app/providers/openai/models.py`.
2. Set `public_id`, `provider_model`, `display_name`, `available`, and
   `supported_tools`.
3. Update docs if the public catalog changes.
4. Only change OpenAI config/stream/tool files when the model needs special
   request assembly.

Anthropic:

1. Add an entry to `_ANTHROPIC_MODELS` in
   `proxy-api/app/providers/anthropic/models.py`.
2. Set `public_id`, `provider_model`, `display_name`, `available`, and
   `supported_tools`.
3. Update docs if the public catalog changes.
4. Only change Anthropic config/stream/tool files when the model needs special
   request assembly.

## Changing Model Order

The frontend shows models in the order returned by `GET /api/v1/models`.

Current order comes from:

- provider model tuple order in each provider's `models.py`
- provider concatenation order in `proxy-api/app/providers/catalog.py`

There is no extra frontend sort. To move a model higher in the UI, move it higher
in the backend catalog.

## Adding A Tool

Tools are model-specific, not global.

For an existing provider:

1. Add a `ProviderToolDefinition` in the provider's `models.py`.
2. Add it to `supported_tools` only for models that should expose it.
3. Add a backend tool-id to provider-native payload builder in the provider's
   `tools.py`.
4. Add provider settings in `proxy-api/app/config/providers/<provider>.py` if the
   tool needs env-backed configuration.
5. Update `docs/ENVIRONMENT.md` if new env vars are added.

The frontend only renders tools returned from `/api/v1/models`.

## Adding A Provider

Create a new provider package under `proxy-api/app/providers/<provider>/`.

Minimum files:

1. `provider.py`
   - public entry points for catalog and dispatcher imports
2. `client.py`
   - SDK client construction and readiness checks
3. `stream.py`
   - SDK streaming call and provider error mapping
4. `models.py`
   - provider runtime model metadata
5. `mapper.py`
   - internal messages to provider payloads and provider events to shared chunks
6. `tools.py`
   - provider-native hosted tool payloads, if supported

Shared-layer changes:

1. Add readiness and stream branches in `proxy-api/app/providers/dispatcher.py`.
2. Add provider model listing to `proxy-api/app/providers/catalog.py`.
3. Add provider config under `proxy-api/app/config/providers/` if needed.
4. Update docs and env documentation.

Only extend shared provider dataclasses when information truly has to cross
provider boundaries. Provider-native details should stay inside the provider
package.

## Error Mapping

Provider stream modules should preserve enough metadata for the dispatcher and
chat layer to classify failures.

Expected mapping targets:

- provider 429 -> `provider_rate_limited`
- provider 401/403 -> `provider_auth_failed`
- provider 4xx -> `provider_bad_request`
- provider 5xx/network -> `provider_unavailable`
- provider unknown -> `provider_failed`
- proxy/provider tool configuration -> `provider_not_configured`

The persisted assistant row should carry:

- `result_code`
- `result_message`
- `error_origin`
- `error_http_status`
- `provider_error_code`
- `retry_after_seconds`
- `error_detail`

## Checklists

After adding a model:

- Confirm it appears in `GET /api/v1/models`.
- Confirm unavailable models cannot be selected.
- Confirm supported tools are correct for that model.
- Run an actual provider request.
- Update docs that list public model ids.

After adding a tool:

- Confirm it appears only on supported models.
- Confirm unsupported selections fail before provider execution.
- Confirm provider-native payload shape is valid.
- Confirm required env/config is documented.

After adding a provider:

- Confirm readiness failures are provider-specific.
- Confirm dispatcher branches are connected.
- Confirm provider errors map into structured chat outcomes.
- Confirm final success/error outcomes are persisted in `chat_messages`.

## Current Runtime Entry Points

- Vertex models: `proxy-api/app/providers/vertex/models.py`
- Vertex SDK call: `proxy-api/app/providers/vertex/stream.py`
- OpenAI models: `proxy-api/app/providers/openai/models.py`
- OpenAI SDK call: `proxy-api/app/providers/openai/stream.py`
- Anthropic models: `proxy-api/app/providers/anthropic/models.py`
- Anthropic SDK call: `proxy-api/app/providers/anthropic/stream.py`
- Shared SSE/background orchestration: `proxy-api/app/services/chat/stream.py`
- Persisted chat turns and outcomes: `proxy-api/app/services/chat/turns.py`
- Outcome message catalog: `proxy-api/app/config/chat_outcomes.py`
