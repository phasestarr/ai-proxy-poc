# PostgreSQL Audit Query Cheat Sheet

Operator-facing audit data now centers on `operator_events`,
`usage_ledger_events`, and `user_usage_caps`.

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
3. `usage_ledger_events`
   - append-only successful-turn spend and token snapshots
4. `chat_messages`
   - product transcript rows with provider/result metadata
5. `chat_message_blocks`
   - completed backend-merged thinking/tool blocks for assistant transcript rows
6. `chat_histories`
   - owner and active-operation lookup
7. `alembic_version`

## Whole-Audit Counts

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'operator_events' AS bucket, COUNT(*) FROM operator_events UNION ALL SELECT 'usage_caps', COUNT(*) FROM user_usage_caps UNION ALL SELECT 'usage_ledger_events', COUNT(*) FROM usage_ledger_events UNION ALL SELECT 'assistant_error_messages', COUNT(*) FROM chat_messages WHERE role = 'assistant' AND status = 'error' UNION ALL SELECT 'live_operations', COUNT(*) FROM chat_operations WHERE state IN ('running', 'provider_streaming') ORDER BY bucket;"
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
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, model_id, provider, detail, created_at FROM operator_events WHERE event_type = 'usage_cap_exceeded' ORDER BY created_at DESC LIMIT 100;"
```

Stale execution cleanup:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, user_id, chat_history_id, chat_message_id, model_id, provider, result_code, detail, created_at FROM operator_events WHERE event_type IN ('chat_operation_timed_out', 'chat_execution_stale_closed') ORDER BY created_at DESC LIMIT 100;"
```

Attachment cleanup failures:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, stored_file_id, provider, result_code, detail, metadata, created_at FROM operator_events WHERE event_type LIKE 'attachment_%failed' ORDER BY created_at DESC LIMIT 100;"
```

## Usage And Caps

List users by current/effective usage:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps list --limit 50
```

Raw SQL top users by ledger spend:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT user_id, COUNT(*) AS ledger_events, SUM(COALESCE(total_tokens_reported, 0)) AS total_tokens_total, SUM(total_cost_usd) AS estimated_price_total_usd FROM usage_ledger_events WHERE status IN ('billable', 'adjustment') GROUP BY user_id ORDER BY estimated_price_total_usd DESC, total_tokens_total DESC LIMIT 50;"
```

One user's usage total:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT user_id, COUNT(*) AS ledger_events, SUM(COALESCE(input_tokens_reported, 0)) AS input_tokens_total, SUM(COALESCE(output_tokens_reported, 0)) AS output_tokens_total, SUM(COALESCE(total_tokens_reported, 0)) AS total_tokens_total, SUM(total_cost_usd) AS estimated_price_total_usd FROM usage_ledger_events WHERE user_id = 'PUT_USER_ID_HERE' AND status IN ('billable', 'adjustment') GROUP BY user_id;"
```

Recent ledger events for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, model_id, result_code, total_tokens_reported, total_cost_usd, price_completeness, chat_history_id_snapshot, chat_message_id_snapshot, created_at FROM usage_ledger_events WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC LIMIT 100;"
```

One user's cap row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT * FROM user_usage_caps WHERE user_id = 'PUT_USER_ID_HERE';"
```

Recent ledger pricing snapshots:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, model_id, result_code, total_tokens_reported, total_cost_usd, price_estimate, chat_history_id_snapshot, chat_message_id_snapshot, created_at FROM usage_ledger_events WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC LIMIT 100;"
```

## Quick Checks

Migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

Provider spend in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, COUNT(*) AS ledger_events, SUM(total_cost_usd) AS estimated_price_total_usd FROM usage_ledger_events WHERE status IN ('billable', 'adjustment') AND created_at >= NOW() - INTERVAL '24 hours' GROUP BY provider ORDER BY estimated_price_total_usd DESC, ledger_events DESC;"
```

Operator errors in the last 24 hours:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT event_type, result_code, COUNT(*) FROM operator_events WHERE created_at >= NOW() - INTERVAL '24 hours' AND severity IN ('error', 'critical') GROUP BY event_type, result_code ORDER BY COUNT(*) DESC, event_type, result_code;"
```

Stale streaming messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, model_id, provider, result_code, first_response_at, deadline_at, updated_at FROM chat_messages WHERE status = 'streaming' AND deadline_at IS NOT NULL AND deadline_at < NOW() ORDER BY deadline_at;"
```

Attachment blobs waiting for remote delete retry:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, lifecycle_state, delete_attempt_count, delete_error, delete_last_attempt_at, delete_next_attempt_at, updated_at FROM stored_files WHERE lifecycle_state IN ('pending_delete', 'delete_failed') ORDER BY delete_next_attempt_at NULLS FIRST, updated_at;"
```
