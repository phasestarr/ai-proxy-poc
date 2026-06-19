# PostgreSQL Audit Query Cheat Sheet

This file is for operators inspecting mostly-audit data in the real PostgreSQL
database from Docker Compose.

Use this file when you need to answer questions like:

- how much usage one user generated
- how much estimated spend one user generated
- which chat histories are driving that usage
- which assistant messages stored pricing snapshots
- which local requests were rejected before a turn even started

For developer-facing product, session, chat, file, and mixed-table inspection,
use `docs/FOR_QUERY_NOOBS.md`.

The basic rule is:

1. start from per-user or per-history rollups
2. drill down to per-message rows only when needed
3. treat stored prices as backend estimates, not invoice truth
4. use raw JSON only after you already know the row you want

## Connect

Interactive shell:

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
```

Run one query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT NOW();"
```

Expanded output for one row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT version_num FROM alembic_version;"
```

## Safety Rules

- Start read-only. Most audit tasks should be `SELECT` only.
- Before any `DELETE`, first run a `SELECT` with the same `WHERE` clause.
- `chat_histories.usage_summary` is a backend-maintained cache.
- `chat_messages.usage` is the per-assistant-turn stored payload.
- `price_estimate` is an internal estimate. It is not the provider billing
  system of record.
- `provider_raw` usage is provider-specific and may differ across providers.

## Current Tables

Mostly-audit data in scope for this file:

1. `chat_request_rejections`
2. `chat_messages` usage and price fields
3. `chat_histories` usage summary cache

Useful lookup table:

4. `chat_histories`

Migration metadata:

5. `alembic_version`

## Whole-Database Audit Inspect

Counts for audit-heavy surfaces:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'chat_request_rejections' AS bucket, COUNT(*) FROM chat_request_rejections UNION ALL SELECT 'assistant_messages_with_usage', COUNT(*) FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL UNION ALL SELECT 'histories_with_usage_summary', COUNT(*) FROM chat_histories WHERE usage_summary IS NOT NULL ORDER BY bucket;"
```

Alembic head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

## Common Workflows

### Workflow A: inspect one user's whole usage/spending

1. Per-history rollup for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.title, COALESCE((ch.usage_summary->>'input_tokens_reported_total')::bigint, 0) AS input_tokens_total, COALESCE((ch.usage_summary->>'output_tokens_reported_total')::bigint, 0) AS output_tokens_total, COALESCE((ch.usage_summary->>'total_tokens_reported_total')::bigint, 0) AS total_tokens_total, COALESCE((ch.usage_summary->>'estimated_price_total_usd')::numeric, 0) AS estimated_price_total_usd, ch.usage_summary->>'last_aggregated_at' AS last_aggregated_at FROM chat_histories ch WHERE ch.user_id = 'PUT_USER_ID_HERE' ORDER BY COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

2. One-line total across all assistant turns for that user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.user_id, COUNT(cm.id) AS assistant_turns, SUM(COALESCE((cm.usage->'normalized'->>'input_tokens_reported')::bigint, 0)) AS input_tokens_total, SUM(COALESCE((cm.usage->'normalized'->>'output_tokens_reported')::bigint, 0)) AS output_tokens_total, SUM(COALESCE((cm.usage->'normalized'->>'total_tokens_reported')::bigint, 0)) AS total_tokens_total, SUM(COALESCE((cm.usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE ch.user_id = 'PUT_USER_ID_HERE' AND cm.role = 'assistant' AND cm.usage IS NOT NULL GROUP BY ch.user_id;"
```

3. Recent assistant-turn pricing rows for that user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT cm.id, cm.chat_history_id, cm.sequence, cm.provider, cm.model_id, cm.usage->'normalized' AS usage_normalized, cm.usage->'price_estimate' AS price_estimate, cm.completed_at FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE ch.user_id = 'PUT_USER_ID_HERE' AND cm.role = 'assistant' AND cm.usage IS NOT NULL ORDER BY cm.completed_at DESC NULLS LAST, cm.created_at DESC LIMIT 100;"
```

### Workflow B: inspect one chat history's usage/spending

1. Inspect the history-level rollup cache:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, title, usage_summary FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

2. Inspect assistant messages inside that history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, provider, model_id, usage->'normalized' AS usage_normalized, usage->'price_estimate' AS price_estimate, completed_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' AND role = 'assistant' AND usage IS NOT NULL ORDER BY sequence;"
```

### Workflow C: inspect recent local request rejects

1. List recent local rejects:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_session_id, chat_history_id, draft_chat_id, model_id, provider, error_code, http_status, retry_after_seconds, created_at FROM chat_request_rejections ORDER BY created_at DESC LIMIT 100;"
```

2. Copy `chat_request_rejections.id` and inspect full detail:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, auth_session_id, chat_history_id, draft_chat_id, model_id, provider, error_code, http_status, retry_after_seconds, detail, created_at FROM chat_request_rejections WHERE id = 'PUT_REJECTION_ID_HERE';"
```

3. Reject counts by code:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT error_code, COUNT(*) FROM chat_request_rejections GROUP BY error_code ORDER BY COUNT(*) DESC, error_code;"
```

## Friendly Table Queries

### chat_histories

Usage rollup overview:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, COALESCE((usage_summary->>'input_tokens_reported_total')::bigint, 0) AS input_tokens_total, COALESCE((usage_summary->>'output_tokens_reported_total')::bigint, 0) AS output_tokens_total, COALESCE((usage_summary->>'total_tokens_reported_total')::bigint, 0) AS total_tokens_total, COALESCE((usage_summary->>'estimated_price_total_usd')::numeric, 0) AS estimated_price_total_usd, usage_summary->>'last_aggregated_at' AS last_aggregated_at FROM chat_histories WHERE usage_summary IS NOT NULL ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT 100;"
```

Top users by cached estimated price:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT user_id, SUM(COALESCE((usage_summary->>'estimated_price_total_usd')::numeric, 0)) AS estimated_price_total_usd, SUM(COALESCE((usage_summary->>'total_tokens_reported_total')::bigint, 0)) AS total_tokens_total, COUNT(*) AS history_count FROM chat_histories WHERE usage_summary IS NOT NULL GROUP BY user_id ORDER BY estimated_price_total_usd DESC, total_tokens_total DESC LIMIT 50;"
```

### chat_messages

Recent assistant turns with usage and price:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, provider, model_id, usage->'normalized' AS usage_normalized, usage->'price_estimate' AS price_estimate, completed_at, updated_at FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL ORDER BY completed_at DESC NULLS LAST, created_at DESC LIMIT 100;"
```

Top users by stored assistant-turn estimated price:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.user_id, COUNT(cm.id) AS assistant_turns, SUM(COALESCE((cm.usage->'normalized'->>'total_tokens_reported')::bigint, 0)) AS total_tokens_total, SUM(COALESCE((cm.usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE cm.role = 'assistant' AND cm.usage IS NOT NULL GROUP BY ch.user_id ORDER BY estimated_price_total_usd DESC, total_tokens_total DESC LIMIT 50;"
```

### chat_request_rejections

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_session_id, chat_history_id, draft_chat_id, model_id, provider, error_code, http_status, retry_after_seconds, created_at FROM chat_request_rejections ORDER BY created_at DESC LIMIT 100;"
```

One user's recent local rejects:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, auth_session_id, chat_history_id, draft_chat_id, model_id, provider, error_code, http_status, retry_after_seconds, created_at FROM chat_request_rejections WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC;"
```

Counts by error code:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT error_code, COUNT(*) FROM chat_request_rejections GROUP BY error_code ORDER BY COUNT(*) DESC, error_code;"
```

## Raw Text / JSON

Use this section only after a friendly query told you which row you want.

Usage JSON for one assistant message:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, usage FROM chat_messages WHERE id = 'PUT_CHAT_MESSAGE_ID_HERE';"
```

History usage summary cache for one chat:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, title, usage_summary FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Raw reject detail:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, auth_session_id, chat_history_id, draft_chat_id, model_id, provider, error_code, http_status, retry_after_seconds, detail, created_at FROM chat_request_rejections WHERE id = 'PUT_REJECTION_ID_HERE';"
```

## Quick Smoke Checks

1. Migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

2. Recent assistant pricing snapshots:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, provider, model_id, usage->'price_estimate' AS price_estimate FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL ORDER BY updated_at DESC LIMIT 20;"
```

3. Estimated spend by provider in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, COUNT(*) AS assistant_turns, SUM(COALESCE((usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL AND created_at >= NOW() - INTERVAL '24 hours' GROUP BY provider ORDER BY estimated_price_total_usd DESC, assistant_turns DESC;"
```

4. Local reject counts by code in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT error_code, COUNT(*) FROM chat_request_rejections WHERE created_at >= NOW() - INTERVAL '24 hours' GROUP BY error_code ORDER BY COUNT(*) DESC, error_code;"
```

5. Top users by estimated spend:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.user_id, SUM(COALESCE((cm.usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd, SUM(COALESCE((cm.usage->'normalized'->>'total_tokens_reported')::bigint, 0)) AS total_tokens_total, COUNT(cm.id) AS assistant_turns FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE cm.role = 'assistant' AND cm.usage IS NOT NULL GROUP BY ch.user_id ORDER BY estimated_price_total_usd DESC, total_tokens_total DESC LIMIT 20;"
```

## Code Pointers

- Usage summary cache builder:
  `backend/app/services/chat/histories/usage_summary.py`
- Assistant turn persistence:
  `backend/app/services/chat/completions/turn_persistence.py`
- Local reject audit persistence:
  `backend/app/services/chat/completions/request_audit.py`
- Usage/pricing mappers:
  `backend/app/providers/openai/usage.py`,
  `backend/app/providers/anthropic/usage.py`,
  `backend/app/providers/vertex/usage.py`

