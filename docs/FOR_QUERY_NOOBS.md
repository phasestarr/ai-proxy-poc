# PostgreSQL Query Cheat Sheet

This file is for developers inspecting the real PostgreSQL database from Docker
Compose. It follows the current schema. For operator-facing spend and reject
audit queries, use `docs/FOR_AUDIT_QUERY.md`.

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

- Before any `DELETE`, first run a `SELECT` with the same `WHERE` clause.
- Prefer deleting cascade roots such as `users`, `auth_sessions`, and
  `chat_histories`.
- Do not casually delete child rows such as `chat_messages`,
  `chat_message_attachments`, `auth_provider_sessions`, or
  `guest_identities`.
- `usage_ledger_events` is append-only audit data. Do not delete it to change
  product chat state.
- Guest users are keyed by raw IP address. In server deployment this is expected
  to be the sanitized remote address supplied by sibling `root-proxy`.
- Local Docker may report a bridge IP such as `172.18.0.1`.

## Current Tables

Product/runtime tables:

1. `users`
2. `ms_identities`
3. `guest_identities`
4. `auth_sessions`
5. `auth_provider_sessions`
6. `auth_conflict_tickets`
7. `oauth_transactions`
8. `chat_histories`
9. `chat_messages`
10. `stored_files`
11. `stored_file_provider_states`
12. `chat_history_files`
13. `chat_message_attachments`
14. `chat_context_checkpoints`
15. `chat_operations`
16. `chat_drafts`
17. `chat_draft_files`

Audit/operator tables:

18. `operator_events`
19. `usage_ledger_events`
20. `user_usage_caps`

Legacy/reserved:

21. `chat_history_memories`
   - current runtime compaction uses `chat_context_checkpoints`
   - leave this table alone unless intentionally removing the legacy model path

Migration metadata:

22. `alembic_version`

## Whole-Database Inspect

List tables:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
```

Row counts:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'users' AS table_name, COUNT(*) FROM users UNION ALL SELECT 'ms_identities', COUNT(*) FROM ms_identities UNION ALL SELECT 'guest_identities', COUNT(*) FROM guest_identities UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'auth_provider_sessions', COUNT(*) FROM auth_provider_sessions UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets UNION ALL SELECT 'oauth_transactions', COUNT(*) FROM oauth_transactions UNION ALL SELECT 'chat_histories', COUNT(*) FROM chat_histories UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages UNION ALL SELECT 'stored_files', COUNT(*) FROM stored_files UNION ALL SELECT 'stored_file_provider_states', COUNT(*) FROM stored_file_provider_states UNION ALL SELECT 'chat_history_files', COUNT(*) FROM chat_history_files UNION ALL SELECT 'chat_message_attachments', COUNT(*) FROM chat_message_attachments UNION ALL SELECT 'chat_context_checkpoints', COUNT(*) FROM chat_context_checkpoints UNION ALL SELECT 'chat_operations', COUNT(*) FROM chat_operations UNION ALL SELECT 'chat_drafts', COUNT(*) FROM chat_drafts UNION ALL SELECT 'chat_draft_files', COUNT(*) FROM chat_draft_files UNION ALL SELECT 'operator_events', COUNT(*) FROM operator_events UNION ALL SELECT 'usage_ledger_events', COUNT(*) FROM usage_ledger_events UNION ALL SELECT 'user_usage_caps', COUNT(*) FROM user_usage_caps UNION ALL SELECT 'chat_history_memories', COUNT(*) FROM chat_history_memories ORDER BY table_name;"
```

Foreign-key cascade rules:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' ORDER BY tc.table_name, kcu.column_name;"
```

## Common Workflows

### Inspect one user's chat data

Find the user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

Use the copied `users.id`:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, ch.title, ch.pin_order, ch.lifecycle_state, co.state AS operation_state, co.operation_type, ch.created_at, ch.updated_at, ch.last_message_at FROM chat_histories ch LEFT JOIN chat_operations co ON co.id = ch.active_operation_id WHERE ch.user_id = 'PUT_USER_ID_HERE' ORDER BY ch.pin_order NULLS LAST, COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

Use the copied `chat_histories.id`:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, first_response_at, deadline_at, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Inspect real text:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT sequence, role, status, result_code, result_message, content, error_detail FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

### Inspect one guest by IP

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.id, gi.user_id, gi.ip_address, u.display_name, u.created_at, u.last_seen_at FROM guest_identities gi JOIN users u ON u.id = gi.user_id ORDER BY gi.created_at DESC;"
```

### Delete one chat history safely

Inspect first:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, ch.title, ch.lifecycle_state, co.state AS operation_state, co.operation_type, ch.created_at, ch.updated_at, ch.last_message_at FROM chat_histories ch LEFT JOIN chat_operations co ON co.id = ch.active_operation_id WHERE ch.id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Optional child-row check:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, length(content) AS content_length FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Delete the parent row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

That cascades messages, logical attachments, message attachment snapshots,
context checkpoints, operations, and the legacy memory row.

## Friendly Table Queries

### users

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, updated_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

### auth_sessions

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, persistent, created_ip, last_ip, created_at, last_seen_at, expires_at, expired_at, expired_reason_code FROM auth_sessions ORDER BY created_at DESC LIMIT 100;"
```

### oauth_transactions

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, state, return_to, requester_ip, created_at, expires_at, consumed_at FROM oauth_transactions ORDER BY created_at DESC LIMIT 100;"
```

### chat_histories

Role:

- Parent table for persisted conversations.
- `active_operation_id` points to the currently live operation, if any.
- There is no `usage_summary` column; use `usage_ledger_events` for spend.

All histories with owner info:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, COALESCE(gi.ip_address, u.email, u.display_name) AS owner, ch.title, ch.pin_order, ch.lifecycle_state, co.state AS operation_state, co.operation_type, ch.created_at, ch.updated_at, ch.last_message_at, COUNT(cm.id) AS message_count FROM chat_histories ch JOIN users u ON u.id = ch.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_operations co ON co.id = ch.active_operation_id LEFT JOIN chat_messages cm ON cm.chat_history_id = ch.id GROUP BY ch.id, gi.ip_address, u.email, u.display_name, co.state, co.operation_type ORDER BY ch.pin_order NULLS LAST, COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

Histories for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, ch.title, ch.pin_order, ch.lifecycle_state, co.state AS operation_state, co.operation_type, ch.created_at, ch.updated_at, ch.last_message_at FROM chat_histories ch LEFT JOIN chat_operations co ON co.id = ch.active_operation_id WHERE ch.user_id = 'PUT_USER_ID_HERE' ORDER BY ch.pin_order NULLS LAST, COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

### chat_messages

Role:

- Persisted user/assistant transcript rows.
- Assistant rows can be `done`, `streaming`, or `error`.
- Usage and price are not stored here; use `usage_ledger_events`.

Recent messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, first_response_at, deadline_at, completed_at, created_at, updated_at FROM chat_messages ORDER BY created_at DESC LIMIT 100;"
```

Stale streaming rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, length(content) AS content_length, model_id, provider, result_code, first_response_at, deadline_at, created_at, updated_at FROM chat_messages WHERE status = 'streaming' AND deadline_at IS NOT NULL AND deadline_at < NOW() ORDER BY deadline_at;"
```

Error outcome summary:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, result_code, finish_reason, COUNT(*) FROM chat_messages WHERE status = 'error' GROUP BY provider, result_code, finish_reason ORDER BY COUNT(*) DESC, provider, result_code;"
```

### chat_operations

Role:

- Token-fenced operation rows for chat sends, attachment mutations, history
  deletion, and metadata updates.
- Live states are `running` and `provider_streaming`.
- Terminal states are `succeeded`, `failed`, and `timed_out`.
- Exactly one of `chat_history_id` or `draft_id` is set.

Live operations:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_session_id, chat_history_id, draft_id, operation_type, state, deadline_at, provider_started_at, first_provider_event_at, last_provider_event_at, provider_max_deadline_at, result_code, created_at, updated_at FROM chat_operations WHERE state IN ('running', 'provider_streaming') ORDER BY deadline_at, created_at;"
```

Recent operations:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, draft_id, operation_type, state, result_code, deadline_at, completed_at, created_at FROM chat_operations ORDER BY created_at DESC LIMIT 100;"
```

### chat_context_checkpoints

Role:

- Active context-compaction checkpoint table.
- One row per `chat_history_id`.
- `covered_through_sequence` means the summary replaces all chat turns up to and
  including that sequence number.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, covered_through_sequence, model_id, provider, completed_at, created_at, updated_at FROM chat_context_checkpoints ORDER BY updated_at DESC;"
```

One checkpoint with summary text:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, chat_history_id, covered_through_sequence, model_id, provider, completed_at, summary_text FROM chat_context_checkpoints WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

### stored_files

Role:

- Backend-owned attachment blob store in PostgreSQL.
- Deduplicated per user by `sha256`.
- Same visible filename does not mean the same blob.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, sha256, mime_type, byte_size, lifecycle_state, delete_attempt_count, delete_error, delete_last_attempt_at, delete_next_attempt_at, created_at, updated_at FROM stored_files ORDER BY created_at DESC;"
```

Blob references:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT sf.id, sf.sha256, sf.mime_type, sf.byte_size, sf.lifecycle_state, sf.delete_attempt_count, COUNT(chf.id) AS history_refs, COUNT(cdf.id) AS draft_refs FROM stored_files sf LEFT JOIN chat_history_files chf ON chf.stored_file_id = sf.id LEFT JOIN chat_draft_files cdf ON cdf.stored_file_id = sf.id GROUP BY sf.id ORDER BY sf.created_at DESC;"
```

### stored_file_provider_states

Role:

- Provider-specific token counts and provider-managed remote refs.
- `token_count` is required.
- `provider_file_id` is nullable when the remote copy has been purged or has
  not been recreated yet.
- There are no `token_count_status` or `remote_file_status` columns.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, stored_file_id, token_count, provider_file_id, uploaded_at, last_used_at, count_model_id, created_at, updated_at FROM stored_file_provider_states ORDER BY provider, uploaded_at DESC NULLS LAST, id;"
```

Only rows with remote refs:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, stored_file_id, provider_file_id, uploaded_at, last_used_at FROM stored_file_provider_states WHERE provider_file_id IS NOT NULL ORDER BY provider, uploaded_at DESC NULLS LAST, id;"
```

### chat_history_files

Role:

- One logical attachment row inside one chat history.
- Same-history duplicate content is blocked by `UNIQUE(chat_history_id, stored_file_id)`.
- Different histories may point to the same `stored_file_id`.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, stored_file_id, display_name, mime_type, byte_size, is_active, created_at, updated_at FROM chat_history_files ORDER BY created_at DESC;"
```

One history's attachments:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT chf.id, chf.chat_history_id, chf.stored_file_id, chf.display_name, chf.mime_type, chf.byte_size, chf.is_active, chf.created_at FROM chat_history_files chf WHERE chf.chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY chf.created_at, chf.id;"
```

Provider metadata for one history's attachments:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT sps.provider, sps.stored_file_id, sps.provider_file_id, sps.token_count, sps.uploaded_at, sps.last_used_at, sps.count_model_id FROM stored_file_provider_states sps WHERE sps.stored_file_id IN (SELECT chf.stored_file_id FROM chat_history_files chf WHERE chf.chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE') ORDER BY sps.provider, sps.stored_file_id;"
```

### chat_message_attachments

Role:

- Snapshot of which attachments were sent with one persisted user turn.
- Useful when proving which provider file ids were in scope for a message.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_message_id, attachment_index, chat_history_file_id, stored_file_id, display_name, mime_type, provider, provider_file_id, token_count, created_at FROM chat_message_attachments ORDER BY created_at DESC;"
```

### usage_ledger_events

Role:

- Append-only usage/spend audit rows for successful assistant turns and
  context compression.
- Cap enforcement reads this table, not deletable chat transcript rows.
- Chat ids are snapshots; deleting a product chat does not remove ledger spend.

Recent ledger rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, provider, model_id, operation, result_code, total_tokens_reported, total_cost_usd, price_completeness, chat_history_id_snapshot, chat_message_id_snapshot, created_at FROM usage_ledger_events ORDER BY created_at DESC LIMIT 100;"
```

One user's ledger total:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT user_id, COUNT(*) AS ledger_events, SUM(COALESCE(total_tokens_reported, 0)) AS total_tokens_total, SUM(total_cost_usd) AS estimated_price_total_usd FROM usage_ledger_events WHERE user_id = 'PUT_USER_ID_HERE' AND status IN ('billable', 'adjustment') GROUP BY user_id;"
```

### operator_events

Role:

- Operator-facing event log for request rejects, usage-cap rejects, provider
  turn failures, stale execution cleanup, and attachment cleanup failures.

Recent events:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, severity, user_id, chat_history_id, chat_message_id, model_id, provider, operation, result_code, http_status, created_at FROM operator_events ORDER BY created_at DESC LIMIT 100;"
```

Stale operation cleanup events:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, user_id, chat_history_id, chat_message_id, result_code, detail, created_at FROM operator_events WHERE event_type IN ('chat_operation_timed_out', 'chat_execution_stale_closed') ORDER BY created_at DESC LIMIT 100;"
```

Attachment cleanup failures:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, event_type, stored_file_id, provider, result_code, detail, metadata, created_at FROM operator_events WHERE event_type LIKE 'attachment_%failed' ORDER BY created_at DESC LIMIT 100;"
```

## Legacy Reserved Table

### chat_history_memories

This table is still mapped in the current model, but no active runtime writer was
found in this repository. Current context compression uses
`chat_context_checkpoints`. Keep queries minimal and treat changes here as
schema cleanup work, not normal operations.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, source_last_message_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_history_memories ORDER BY created_at DESC;"
```
