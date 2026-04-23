# NOTEPAD

Short reference for the current codebase.

## Runtime

- `root-proxy` routes `ai.nextinsol.com` to `ai-proxy-frontend:8080`
- frontend NGINX serves the SPA and proxies `/api/*` and `/health` to `proxy-api:8000`
- backend depends on PostgreSQL, Redis, Vertex AI, OpenAI, and Anthropic
- PostgreSQL schema is managed by Alembic migrations at backend startup

## Entry Order

- frontend boot: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `frontend/src/auth/useAuthSession.ts` -> `GET /api/v1/auth/me`
- guest login: `frontend/src/auth/authApi.ts` -> `POST /api/v1/auth/login/guest`
- microsoft login: `frontend/src/auth/authRedirects.ts` -> `GET /api/v1/auth/login/microsoft` -> Microsoft -> `GET /api/v1/auth/callback/microsoft`
- session conflict recovery: `frontend/src/auth/authApi.ts` -> `POST /api/v1/auth/session-conflicts/resolve`
- model discovery: `frontend/src/pages/chat/hooks/useChatModelSelection.ts` -> `GET /api/v1/models`
- history list/load/delete: `frontend/src/chat/api/chatHistoryApi.ts` -> `/api/v1/chat/histories`
- chat: `frontend/src/pages/ChatPage.tsx` -> `frontend/src/chat/api/streamChatApi.ts` -> `POST /api/v1/chat/completions`

## Auth Rules

- browser auth uses only HttpOnly cookies
- `session_id` stores the raw session key; DB stores only `session_key_hash`
- `session_conflict_id` stores a short-lived raw conflict ticket; DB stores only `ticket_hash`
- guest users are keyed by raw IP address in `guest_identities`
- local Docker usually shows guest IP as a Docker bridge address, for example `172.18.0.1`
- guest max sessions default: `2`
- Microsoft max sessions default: `4`
- every protected chat/history endpoint validates the backend session; frontend state is not trusted

## Chat History Rules

- `chat_histories` owns each persisted conversation
- `chat_messages` stores both user and assistant messages
- `users -> chat_histories -> chat_messages` is FK cascade
- `DELETE /api/v1/chat/histories/{id}` deletes the history and cascades messages
- `POST /api/v1/chat/completions` auto-creates a history when `chat_history_id` is absent
- SSE `start` returns `chat_history_id`, `user_message_id`, and `assistant_message_id`
- stream failures are persisted for rendering but marked `excluded_from_context=true`
- future provider payload excludes failed/error messages

## Frontend Transcript Rules

Transcript message shape in the UI:

- role: `user | assistant`
- each send creates one pending user message and one empty assistant placeholder
- saved DB messages are mapped back into this local shape when a history is loaded
- failed exchanges remain visible but are excluded from future request context

Where it happens:

- create user message: `createPendingUserMessage()` in `frontend/src/pages/chat/state/transcript.ts`
- create assistant placeholder: `createStreamingAssistantMessage()` in `frontend/src/pages/chat/state/transcript.ts`
- map DB messages: `mapHistoryMessagesToTranscript()` in `frontend/src/pages/chat/state/transcript.ts`
- build request transcript: `buildRequestMessages()` in `frontend/src/pages/chat/state/transcript.ts`
- submit flow and SSE append flow: `frontend/src/pages/ChatPage.tsx`
- browser request body assembly: `frontend/src/chat/api/streamChatApi.ts`

## Browser Request JSON

The frontend sends:

```json
{
  "chat_history_id": "6aa8a9a4-3ef2-4f3c-a3f4-1b63a7d063aa",
  "model_id": "gemini-2.5-flash",
  "tool_ids": ["web_search"],
  "messages": [
    {"role":"user","content":"hi"},
    {"role":"assistant","content":"hello"},
    {"role":"user","content":"who are you"}
  ]
}
```

Important backend behavior:

- `model_id` must select an available backend catalog model
- `tool_ids` must be supported by that model
- the last message must be a `user` message
- when `chat_history_id` exists, backend provider context is rebuilt from PostgreSQL and the request's last user message is appended as the new turn

## Backend Chat Assembly

Current path:

1. request JSON -> `proxy-api/app/schemas/chat.py`
2. auth dependency -> `proxy-api/app/api/v1/dependencies/session.py`
3. route resolution -> `proxy-api/app/services/chat/preparation.py`
4. history ownership/load -> `proxy-api/app/services/chat/history_queries.py`
5. turn persistence -> `proxy-api/app/services/chat/turns.py`
6. provider context rebuild -> `proxy-api/app/services/chat/provider_context.py`
7. Redis in-flight/rate limits -> `proxy-api/app/db/redis/chat_coordination.py`
8. provider dispatch -> `proxy-api/app/providers/dispatcher.py`
9. provider mapping/config/tools -> `proxy-api/app/providers/<provider>/`
10. SSE response -> `proxy-api/app/services/chat/stream.py`

## Provider Route Resolution

Public model ids currently exposed:

- `gemini-3-flash-preview`
- `gemini-3.1-pro-preview`
- `gemini-2.5-flash`
- `gpt-5.4`
- `gpt-5.4-mini`
- `gpt-5-mini`
- `claude-opus-4-7`, unavailable
- `claude-sonnet-4-6`
- `claude-haiku-4-5`

Public tool ids currently exposed on available Gemini models:

- `web_search`
- `retrieval`
- `code_execution`
- `url_context`

Public tool ids currently exposed on available OpenAI models:

- `web_search`
- `retrieval`
- `code_execution`

Public tool ids currently exposed on available Anthropic models:

- `web_search`
- `code_execution`

Where it is resolved:

- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/vertex/models.py`
- `proxy-api/app/providers/openai/models.py`
- `proxy-api/app/providers/anthropic/models.py`

## Vertex Tool Mapping

Public tool ids are backend-owned aliases:

- `web_search` -> Vertex `google_search`
- `retrieval` -> Vertex `retrieval.vertex_rag_store`
- `code_execution` -> Vertex `code_execution`
- `url_context` -> Vertex `url_context`

Where it is mapped:

- `proxy-api/app/providers/vertex/tools.py`

`retrieval` requires `VERTEX_AI_RAG_CORPORA`; without it, selecting `retrieval` fails provider readiness/configuration.

## OpenAI Tool Mapping

Public tool ids are backend-owned aliases:

- `web_search` -> OpenAI Responses API `web_search`
- `retrieval` -> OpenAI Responses API `file_search`
- `code_execution` -> OpenAI Responses API `code_interpreter`

Where it is mapped:

- `proxy-api/app/providers/openai/tools.py`

`retrieval` requires `OPENAI_VECTOR_STORE_IDS`; without it, selecting `retrieval` fails provider readiness/configuration.

## Anthropic Tool Mapping

Public tool ids are backend-owned aliases:

- `web_search` -> Anthropic Messages API `web_search_20250305`
- `code_execution` -> Anthropic Messages API `code_execution_20250825`

Where it is mapped:

- `proxy-api/app/providers/anthropic/tools.py`

Anthropic code execution requires the provider beta header `code-execution-2025-08-25`, which is attached by the Anthropic provider.

## Vertex Contents Mapping

Current mapper behavior:

- `system` messages are accumulated into one `system_instruction`
- `assistant` is converted to Vertex role `model`
- every non-system message becomes `parts: [{"text": "..."}]`
- no file/image/pdf parts are currently supported

Where it happens:

- `proxy-api/app/providers/vertex/mapper.py`

## Final `google.genai` Call Shape

The repo calls:

- `google.genai.Client(vertexai=True, project=..., location=..., http_options=...)`
- `aio_client.models.generate_content_stream(model=..., contents=..., config=...)`

Where it happens:

- client construction: `proxy-api/app/providers/vertex/client.py`
- request execution: `proxy-api/app/providers/vertex/stream.py`

Without tools, `config` may be `null`.

## Final OpenAI Responses Call Shape

The repo calls:

- `AsyncOpenAI(api_key=...)`
- `client.responses.create(model=..., instructions=..., input=..., tools=..., store=False, stream=True)`

Where it happens:

- client construction: `proxy-api/app/providers/openai/client.py`
- request execution: `proxy-api/app/providers/openai/stream.py`

OpenAI provider-side response state is not used; PostgreSQL remains the conversation source of truth.

## Final Anthropic Messages Call Shape

The repo calls:

- `AsyncAnthropic(api_key=..., default_headers={"anthropic-version": ...})`
- `client.beta.messages.create(model=..., system=..., messages=..., tools=..., max_tokens=..., betas=..., stream=True)`

Where it happens:

- client construction: `proxy-api/app/providers/anthropic/client.py`
- request execution: `proxy-api/app/providers/anthropic/stream.py`

Anthropic provider-side conversation state is not used; PostgreSQL remains the conversation source of truth.

## Current Public Surface

- auth: guest, optional Microsoft
- sessions: backend-owned, cookie-based, max-session enforced
- chat history: list/load/delete and persisted send flow
- models: Gemini, OpenAI, and Anthropic variants
- tools: model-specific `web_search`, `retrieval`, `code_execution`, and `url_context`

## Still Scaffolded

- usage schemas, services, and models
- `chat_request.py` model scaffold
