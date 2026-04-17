# NOTEPAD

Short reference for the current codebase.

## Runtime
- `root-proxy` routes `ai.nextinsol.com` to `ai-proxy-frontend:8080`
- frontend NGINX proxies `/api/*` and `/health` to `proxy-api:8000`
- backend depends on PostgreSQL, Redis, and Vertex AI

## Entry Order
- frontend boot: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `GET /api/v1/auth/me`
- model discovery: `frontend/src/pages/ChatPage.tsx` -> `GET /api/v1/models`
- guest login: `frontend/src/services/authService.ts` -> `POST /api/v1/auth/login/guest`
- microsoft login: `frontend/src/services/authService.ts` -> `GET /api/v1/auth/login/microsoft` -> Microsoft -> `GET /api/v1/auth/callback/microsoft`
- chat: `frontend/src/pages/ChatPage.tsx` -> `frontend/src/services/chatService.ts` -> `POST /api/v1/chat/completions`

## Gemini Chat Assembly

Current Gemini path is:
- frontend transcript state -> request JSON -> backend schema validation -> provider route resolution -> Vertex `contents` and `config` assembly -> `google.genai` `generate_content_stream(...)`

Relevant code:
- transcript state helpers: `frontend/src/pages/chat-page-state.ts`
- submit flow and SSE append flow: `frontend/src/pages/ChatPage.tsx`
- browser request body assembly: `frontend/src/services/chatService.ts`
- API request schema: `proxy-api/app/schemas/chat.py`
- route resolution: `proxy-api/app/services/chat/preparation.py`
- model/tool routing: `proxy-api/app/providers/catalog.py`
- Vertex mapping: `proxy-api/app/providers/vertex/mapper.py`
- Vertex tool mapping: `proxy-api/app/providers/vertex/tools.py`
- Vertex request execution: `proxy-api/app/providers/vertex/stream.py`

## Frontend Transcript Rules

Transcript message shape in the UI:
- role: `user | assistant`
- no frontend `system` message is currently created
- each send creates one pending user message and one empty assistant placeholder

Where it happens:
- create user message: `createPendingUserMessage()` in `frontend/src/pages/chat-page-state.ts`
- create assistant placeholder: `createStreamingAssistantMessage()` in `frontend/src/pages/chat-page-state.ts`
- build request transcript for the backend: `buildRequestMessages()` in `frontend/src/pages/chat-page-state.ts`
- append both to current screen state before the request returns: `setMessages([...current, userMessage, assistantMessage])` in `frontend/src/pages/ChatPage.tsx`
- append streamed assistant text: `appendAssistantDelta()` in `frontend/src/pages/chat-page-state.ts`
- mark assistant complete: `completeAssistantMessage()` in `frontend/src/pages/chat-page-state.ts`

Example transcript before request build:

```json
[
  {"id":1,"role":"user","content":"안녕"},
  {"id":2,"role":"assistant","content":"안녕하세요","status":"done"}
]
```

If the next user prompt is `RAG가 뭐야`, request messages become:

```json
[
  {"role":"user","content":"안녕"},
  {"role":"assistant","content":"안녕하세요"},
  {"role":"user","content":"RAG가 뭐야"}
]
```

## Browser Request JSON

The frontend sends:

```json
{
  "model_id": "gemini",
  "tool_ids": ["rag"],
  "messages": [
    {"role":"user","content":"안녕"},
    {"role":"assistant","content":"안녕하세요"},
    {"role":"user","content":"RAG가 뭐야"}
  ]
}
```

Where it is assembled:
- `frontend/src/services/chatService.ts`
- body keys: `model_id`, `tool_ids`, `messages`

## Backend Validation and Route Resolution

Incoming request schema:
- `ChatMessage.role`: `system | user | assistant`
- `ChatMessage.content`: trimmed non-blank string
- at least one `user` message is required
- last message must be `user`

Where it is validated:
- `proxy-api/app/schemas/chat.py`

Provider route resolution:
- public model ids like `gemini-2.5-flash` resolve to provider `vertex_ai`
- Vertex runtime model id and location come from backend-owned provider metadata
- public tool id `rag` is validated here as a backend-owned alias

Where it is resolved:
- `proxy-api/app/services/chat/preparation.py`
- `proxy-api/app/providers/catalog.py`
- `proxy-api/app/providers/vertex/provider.py`

Internal route shape after resolution:

```json
{
  "route": {
    "model": {
      "public_id": "gemini-2.5-flash",
      "provider": "vertex_ai"
    },
    "tool_ids": ["rag"]
  },
  "messages": [
    {"role":"user","content":"안녕"},
    {"role":"assistant","content":"안녕하세요"},
    {"role":"user","content":"RAG가 뭐야"}
  ]
}
```

## Vertex Contents Mapping

Current mapper behavior:
- `system` messages are accumulated into one `system_instruction`
- `assistant` is converted to Vertex role `model`
- every non-system message becomes `parts: [{"text": "..."}]`
- no file/image/pdf parts are currently supported in this repo

Where it happens:
- `proxy-api/app/providers/vertex/mapper.py`

Example mapped Vertex payload:

```json
{
  "system_instruction": null,
  "contents": [
    {"role":"user","parts":[{"text":"안녕"}]},
    {"role":"model","parts":[{"text":"안녕하세요"}]},
    {"role":"user","parts":[{"text":"RAG가 뭐야"}]}
  ]
}
```

If a system message existed:

```json
{
  "system_instruction": "Answer tersely.",
  "contents": [
    {"role":"user","parts":[{"text":"배포 경로 요약해줘"}]}
  ]
}
```

## Vertex Tool Mapping

Public tool id exposed by this repo:
- `rag`

This is not a native Gemini tool name.
- repo alias: `rag`
- actual Vertex tool field: `retrieval.vertex_rag_store`

Where it is mapped:
- `proxy-api/app/providers/vertex/provider.py` exposes public tool `rag`
- `proxy-api/app/providers/vertex/tools.py` maps `rag` -> Vertex retrieval payload

Current mapping logic:
- if `"rag"` is present in selected tool ids, build one Vertex `Tool`
- corpora come from `VERTEX_AI_RAG_CORPORA`
- `similarity_top_k` comes from `VERTEX_AI_RAG_SIMILARITY_TOP_K`
- optional `vector_distance_threshold` comes from `VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD`

Resulting Vertex tool payload:

```json
{
  "retrieval": {
    "vertex_rag_store": {
      "rag_resources": [
        {"rag_corpus":"projects/PROJECT/locations/LOCATION/ragCorpora/CORPUS_ID"}
      ],
      "similarity_top_k": 5,
      "vector_distance_threshold": 0.5
    }
  }
}
```

## Final `google.genai` Call Shape

The repo calls:
- `google.genai.Client(vertexai=True, project=..., location=..., http_options=...)`
- `aio_client.models.generate_content_stream(model=..., contents=..., config=...)`

Where it happens:
- client construction: `proxy-api/app/providers/vertex/client.py`
- request execution: `proxy-api/app/providers/vertex/stream.py`

Effective SDK call shape with RAG enabled:

```json
{
  "model": "gemini-2.5-flash",
  "contents": [
    {"role":"user","parts":[{"text":"안녕"}]},
    {"role":"model","parts":[{"text":"안녕하세요"}]},
    {"role":"user","parts":[{"text":"RAG가 뭐야"}]}
  ],
  "config": {
    "tools": [
      {
        "retrieval": {
          "vertex_rag_store": {
            "rag_resources": [
              {"rag_corpus":"projects/.../locations/.../ragCorpora/..."}
            ],
            "similarity_top_k": 5
          }
        }
      }
    ]
  }
}
```

Without tools, `config` may be `null`.

## Function Calling vs Retrieval

Current repo uses retrieval, not function calling.

Why:
- there is no `FunctionCall` handling loop in this repo
- there is no `FunctionResponse` second turn injection path in this repo
- `proxy-api/app/providers/vertex/tools.py` builds `retrieval`, not `functionDeclarations`

Function calling flow is different:
- request includes `tools: [{ functionDeclarations: [...] }]`
- model may return `FunctionCall`
- app executes external code or API call
- app sends `FunctionResponse` back on the next turn
- model then produces final natural-language output

Retrieval flow is different:
- request includes `tools: [{ retrieval: ... }]`
- system executes retrieval and presents the results to the model for generation
- no app-side manual function execution loop is required for the current repo's RAG path

## Official Docs

Core API shapes:
- Vertex `Tool` reference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/Tool
- Vertex `Content` reference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/Content
- Vertex `generateContent` reference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent
- Vertex `streamGenerateContent` reference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.publishers.models/streamGenerateContent

Function calling:
- intro: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling
- reference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/function-calling

RAG / retrieval:
- RAG quickstart: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-quickstart
- RAG corpus REST resource: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.ragCorpora
- RAG file import REST resource: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.ragCorpora.ragFiles/import

Google Gen AI Python SDK:
- SDK docs: https://googleapis.github.io/python-genai/

## Current Public Surface
- model: `gemini`
- placeholder model: `chatgpt`
- tool: `rag`
- auth: guest, optional Microsoft

## Still Scaffolded
- usage schemas, services, and models
