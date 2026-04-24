# Maintenance

Change points that matter when extending or debugging the current stack.

## Model and Tool Source Of Truth
- backend owns the public model catalog
- frontend reads `GET /api/v1/models`
- model order in the UI follows backend catalog order
- tool support is model-specific

## Where To Change Models

For an existing provider, model changes should usually touch:

1. `proxy-api/app/providers/<provider>/models.py`
   - public model ids
   - provider runtime model ids
   - display names
   - availability
   - supported tool ids
2. `proxy-api/app/providers/<provider>/config.py`
   - model to preset mapping
   - provider request preset values

Current provider model files:
- `proxy-api/app/providers/vertex/models.py`
- `proxy-api/app/providers/openai/models.py`
- `proxy-api/app/providers/anthropic/models.py`

## Where To Change Tools

For an existing provider, tool changes should usually touch:

1. `proxy-api/app/providers/<provider>/tools.py`
   - public tool metadata
   - provider-native hosted tool payloads
   - any provider-native tool beta/header logic
2. `proxy-api/app/providers/<provider>/models.py`
   - assign supported tool ids to each model
3. `proxy-api/app/config/providers/<provider>.py`
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
- output token caps now live in provider preset config
- env does not own provider output caps
- preset names are normalized as much as possible:
  - all providers: `none`, `low`, `normal`, `high`
  - OpenAI also supports `xhigh`
  - Anthropic also supports `xhigh`, `max`

Current cap convention:
- `none`: `1024`
- `low`: `2048`
- `normal`: `4096`
- OpenAI and Vertex `high` and above: omit the field and use provider defaults
- Anthropic `high` and above: set `max_tokens` to the model's documented max output limit

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

## Chat Execution Path
1. request validation: `proxy-api/app/schemas/chat.py`
2. route resolution: `proxy-api/app/services/chat/preparation.py`
3. model/tool validation: `proxy-api/app/providers/catalog.py`
4. turn persistence: `proxy-api/app/services/chat/turns.py`
5. live orchestration: `proxy-api/app/services/chat/stream.py`
6. provider dispatch: `proxy-api/app/providers/dispatcher.py`
7. provider-native execution: `proxy-api/app/providers/<provider>/stream.py`

## Before You Add A New Env Var
1. add it to the correct settings module
2. pass it through `deploy/docker-compose.yml`
3. add it to `.env.example`
4. update `docs/ENVIRONMENT.md`
5. if it changes runtime behavior, mention it in `docs/ARCHITECTURE.md` or here
