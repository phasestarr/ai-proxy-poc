# PostgreSQL Audit Query Cheat Sheet

Operator-facing audit data now centers on `operator_events`, raw assistant
usage snapshots, and `user_usage_caps`.

## Connect

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT NOW();"
```

## Current Audit Tables

1. `operator_events`
   - request rejects, usage cap rejects, provider failures, stale execution cleanup, attachment cleanup failures
2. `user_usage_caps`
   - per-user cap override, baseline, enabled state
3. `chat_messages`
   - assistant usage and price snapshots
4. `chat_histories`
   - usage summary cache and owner lookup
5. `alembic_version`

## Whole-Audit Counts

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'operator_events' AS bucket, COUNT(*) FROM operator_events UNION ALL SELECT 'usage_caps', COUNT(*) FROM user_usage_caps UNION ALL SELECT 'assistant_messages_with_usage', COUNT(*) FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL UNION ALL SELECT 'histories_with_usage_summary', COUNT(*) FROM chat_histories WHERE usage_summary IS NOT NULL ORDER BY bucket;"
```

## Operator Events

Recent events:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, severity, user_id, chat_history_id, chat_message_id, model_id, provider, operation, result_code, http_status, created_at FROM operator_events ORDER BY created_at DESC LIMIT 100;"
```

One event in full:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT * FROM operator_events WHERE id = 'PUT_OPERATOR_EVENT_ID_HERE';"
```

Counts by event and result:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT event_type, result_code, severity, COUNT(*) FROM operator_events GROUP BY event_type, result_code, severity ORDER BY COUNT(*) DESC, event_type, result_code;"
```

Recent failures:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, severity, user_id, provider, result_code, message, created_at FROM operator_events WHERE severity IN ('error', 'critical') ORDER BY created_at DESC LIMIT 100;"
```

Usage-cap rejects:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, draft_chat_id, model_id, provider, detail, created_at FROM operator_events WHERE event_type = 'usage_cap_exceeded' ORDER BY created_at DESC LIMIT 100;"
```

Stale execution cleanup:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, chat_message_id, model_id, provider, result_code, detail, created_at FROM operator_events WHERE event_type IN ('chat_execution_stale_closed', 'chat_execution_state_recovered') ORDER BY created_at DESC LIMIT 100;"
```

Attachment cleanup failures:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, stored_file_id, provider, result_code, detail, metadata, created_at FROM operator_events WHERE event_type LIKE 'attachment_remote_%failed' ORDER BY created_at DESC LIMIT 100;"
```

## Usage And Caps

List users by current/effective usage:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps list --limit 50
```

Raw SQL top users by assistant-turn estimated spend:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.user_id, COUNT(cm.id) AS assistant_turns, SUM(COALESCE((cm.usage->'normalized'->>'total_tokens_reported')::bigint, 0)) AS total_tokens_total, SUM(COALESCE((cm.usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE cm.role = 'assistant' AND cm.usage IS NOT NULL GROUP BY ch.user_id ORDER BY estimated_price_total_usd DESC, total_tokens_total DESC LIMIT 50;"
```

One user's usage total:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.user_id, COUNT(cm.id) AS assistant_turns, SUM(COALESCE((cm.usage->'normalized'->>'input_tokens_reported')::bigint, 0)) AS input_tokens_total, SUM(COALESCE((cm.usage->'normalized'->>'output_tokens_reported')::bigint, 0)) AS output_tokens_total, SUM(COALESCE((cm.usage->'normalized'->>'total_tokens_reported')::bigint, 0)) AS total_tokens_total, SUM(COALESCE((cm.usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE ch.user_id = 'PUT_USER_ID_HERE' AND cm.role = 'assistant' AND cm.usage IS NOT NULL GROUP BY ch.user_id;"
```

One user's cap row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT * FROM user_usage_caps WHERE user_id = 'PUT_USER_ID_HERE';"
```

Recent assistant pricing snapshots:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT cm.id, cm.chat_history_id, cm.sequence, cm.provider, cm.model_id, cm.usage->'normalized' AS usage_normalized, cm.usage->'price_estimate' AS price_estimate, cm.completed_at FROM chat_messages cm JOIN chat_histories ch ON ch.id = cm.chat_history_id WHERE ch.user_id = 'PUT_USER_ID_HERE' AND cm.role = 'assistant' AND cm.usage IS NOT NULL ORDER BY cm.completed_at DESC NULLS LAST, cm.created_at DESC LIMIT 100;"
```

## Quick Checks

Migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

Provider spend in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, COUNT(*) AS assistant_turns, SUM(COALESCE((usage->'price_estimate'->>'total_cost_usd')::numeric, 0)) AS estimated_price_total_usd FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL AND created_at >= NOW() - INTERVAL '24 hours' GROUP BY provider ORDER BY estimated_price_total_usd DESC, assistant_turns DESC;"
```

Operator errors in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT event_type, result_code, COUNT(*) FROM operator_events WHERE created_at >= NOW() - INTERVAL '24 hours' AND severity IN ('error', 'critical') GROUP BY event_type, result_code ORDER BY COUNT(*) DESC, event_type, result_code;"
```

Stale streaming messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, model_id, provider, result_code, updated_at FROM chat_messages WHERE status = 'streaming' AND updated_at < NOW() - INTERVAL '10 minutes' ORDER BY updated_at;"
```
