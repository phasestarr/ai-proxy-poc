# PostgreSQL Query Cheat Sheet

This file is for developers inspecting the real PostgreSQL database from Docker
Compose, even if you are not comfortable with SQL yet.

Use this file when you need to answer questions like:

- who is this user
- which chat histories belong to them
- what messages are in one history
- which files are attached to one history
- which session row belongs to this browser
- what state the backend stored for mixed product/diagnostic rows

For operator-facing usage/spending and local reject audit queries, use
`docs/FOR_AUDIT_QUERY.md`.

The basic rule is:

1. run a table-friendly query first
2. copy the `id` you need
3. paste that `id` into the next query
4. only use raw text queries when you already know which row you want

Long text fields and JSON payloads are intentionally kept out of the default
table views. The raw-text and JSON queries are near the bottom.

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
- Do not casually delete child rows such as `chat_messages`,
  `chat_message_attachments`, `auth_provider_sessions`, or `guest_identities`.
- Prefer deleting cascade roots:
  - `users`
  - `auth_sessions`
  - `chat_histories`
- Guest users are keyed by raw IP address. In local Docker this is often a
  bridge IP such as `172.18.0.1`, not your LAN IP.
- Human users are intentional account data. They are not "zombie rows" just
  because they are old.
- If you need operator-facing usage/spending rollups or local reject audit
  queries, switch to `docs/FOR_AUDIT_QUERY.md`.

## Current Tables

Application and mixed tables you will usually touch from this file:

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
14. `chat_history_memories`
15. `chat_context_checkpoints`

Mostly-audit table:

16. `operator_events`
17. `usage_ledger_events`
18. `user_usage_caps`

Migration metadata:

19. `alembic_version`

## Whole-Database Inspect

List tables:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
```

Row counts:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'users' AS table_name, COUNT(*) FROM users UNION ALL SELECT 'ms_identities', COUNT(*) FROM ms_identities UNION ALL SELECT 'guest_identities', COUNT(*) FROM guest_identities UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'auth_provider_sessions', COUNT(*) FROM auth_provider_sessions UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets UNION ALL SELECT 'oauth_transactions', COUNT(*) FROM oauth_transactions UNION ALL SELECT 'chat_histories', COUNT(*) FROM chat_histories UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages UNION ALL SELECT 'stored_files', COUNT(*) FROM stored_files UNION ALL SELECT 'stored_file_provider_states', COUNT(*) FROM stored_file_provider_states UNION ALL SELECT 'chat_history_files', COUNT(*) FROM chat_history_files UNION ALL SELECT 'chat_message_attachments', COUNT(*) FROM chat_message_attachments UNION ALL SELECT 'chat_history_memories', COUNT(*) FROM chat_history_memories UNION ALL SELECT 'chat_context_checkpoints', COUNT(*) FROM chat_context_checkpoints UNION ALL SELECT 'operator_events', COUNT(*) FROM operator_events UNION ALL SELECT 'usage_ledger_events', COUNT(*) FROM usage_ledger_events UNION ALL SELECT 'user_usage_caps', COUNT(*) FROM user_usage_caps ORDER BY table_name;"
```

Foreign-key cascade rules:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' ORDER BY tc.table_name, kcu.column_name;"
```

Alembic head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

## Common Workflows

### Workflow A: inspect one user's chat data

1. Find the user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, display_name, email, created_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

2. Use the copied `users.id` in the next query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, interaction_state, busy_reason, created_at, updated_at, last_message_at, usage_summary FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

3. Use the copied `chat_histories.id` in the next query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, CASE WHEN usage IS NULL THEN NULL ELSE usage->'normalized' END AS usage_normalized, CASE WHEN usage IS NULL THEN NULL ELSE usage->'price_estimate' END AS usage_price_estimate, first_response_at, deadline_at, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

4. If you need the real text, use the same history id here:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT sequence, role, status, result_code, result_message, content, error_detail FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

### Workflow B: inspect one guest by IP

1. Find the guest identity:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.id, gi.user_id, gi.ip_address, u.display_name, u.created_at, u.last_seen_at FROM guest_identities gi JOIN users u ON u.id = gi.user_id ORDER BY gi.created_at DESC;"
```

2. Copy `guest_identities.user_id` and use it in the user-history query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, interaction_state, busy_reason, created_at, updated_at, last_message_at, usage_summary FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

### Workflow C: delete one chat history safely

1. Inspect the history first:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, interaction_state, busy_reason, created_at, updated_at, last_message_at, usage_summary FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

2. Optional: inspect child rows before delete:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, length(content) AS content_length FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

3. Delete the parent row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

That delete cascades:

- `chat_messages`
- `chat_history_files`
- `chat_message_attachments`
- `chat_history_memories`
- `chat_context_checkpoints`

### Workflow D: inspect one history's attachments

1. Inspect logical attachments in the history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT chf.id, chf.chat_history_id, chf.stored_file_id, chf.display_name, chf.mime_type, chf.byte_size, chf.is_active, chf.created_at FROM chat_history_files chf WHERE chf.chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY chf.created_at, chf.id;"
```

2. Inspect the deduplicated stored blobs behind those attachments:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT sf.id, sf.user_id, sf.sha256, sf.mime_type, sf.byte_size, sf.lifecycle_state, sf.delete_attempt_count, sf.delete_error, sf.delete_next_attempt_at, sf.created_at FROM stored_files sf WHERE sf.id IN (SELECT chf.stored_file_id FROM chat_history_files chf WHERE chf.chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE') ORDER BY sf.created_at, sf.id;"
```

3. Inspect provider refs and token metadata for those blobs:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT sps.provider, sps.stored_file_id, sps.provider_file_id, sps.remote_file_status, sps.token_count_status, sps.token_count, sps.uploaded_at, sps.last_used_at FROM stored_file_provider_states sps WHERE sps.stored_file_id IN (SELECT chf.stored_file_id FROM chat_history_files chf WHERE chf.chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE') ORDER BY sps.provider, sps.stored_file_id;"
```

## Friendly Table Queries

Use these first. They avoid long raw text and are much easier to read in a
terminal.

### users

Role:

- Parent table for guest and Microsoft users.
- Deleting a user cascades identities, sessions, conflict tickets, chat
  histories, chat messages, files, and internal child rows.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, updated_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

Rows owned by each user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.account_type, u.display_name, u.email, COUNT(DISTINCT s.id) AS sessions, COUNT(DISTINCT ch.id) AS chat_histories, COUNT(DISTINCT chf.id) AS history_files, COUNT(DISTINCT chm.id) AS remembered_histories, COUNT(DISTINCT mi.id) AS ms_identity_count, COUNT(DISTINCT gi.id) AS guest_identity_count FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id LEFT JOIN chat_history_files chf ON chf.user_id = u.id LEFT JOIN chat_history_memories chm ON chm.user_id = u.id LEFT JOIN ms_identities mi ON mi.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY u.id ORDER BY u.created_at DESC;"
```

Delete one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM users WHERE id = 'PUT_USER_ID_HERE' RETURNING id, account_type, display_name, email;"
```

### ms_identities

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, provider, tenant_id, subject, home_account_id, preferred_username, created_at, updated_at FROM ms_identities ORDER BY created_at DESC;"
```

Cleanup:

- Delete the parent `users` row, not this child row directly.

### guest_identities

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.id, gi.user_id, gi.provider, gi.ip_address, u.display_name, u.created_at AS user_created_at, gi.created_at, gi.updated_at FROM guest_identities gi JOIN users u ON u.id = gi.user_id ORDER BY gi.created_at DESC;"
```

Active sessions by guest IP:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, gi.user_id, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions, COUNT(s.id) AS total_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address, gi.user_id ORDER BY gi.ip_address;"
```

Cleanup:

- Delete the parent `users` row, not this child row directly.

### auth_sessions

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, persistent, created_at, last_seen_at, expires_at, expired_at, expired_reason_code, superseded_by_session_id, created_ip, last_ip FROM auth_sessions ORDER BY created_at DESC;"
```

Expired sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, expires_at, expired_at, expired_reason_code FROM auth_sessions WHERE state <> 'active' OR expires_at <= NOW() ORDER BY created_at DESC;"
```

Delete one session:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_sessions WHERE id = 'PUT_SESSION_ID_HERE' RETURNING id, user_id, auth_type, state;"
```

### auth_provider_sessions

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT session_id, provider, token_cache_version, access_token_expires_at, refresh_token_expires_at, tenant_id, home_account_id, scope, last_refresh_at, last_refresh_error, created_at, updated_at FROM auth_provider_sessions ORDER BY created_at DESC;"
```

Cleanup:

- Delete the parent `auth_sessions` row, not this child row directly.

### auth_conflict_tickets

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, reason, return_to, created_at, expires_at, consumed_at, requester_ip FROM auth_conflict_tickets ORDER BY created_at DESC;"
```

Cleanup candidates:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, expires_at, consumed_at FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

### oauth_transactions

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, state, return_to, created_at, expires_at, consumed_at, requester_ip FROM oauth_transactions ORDER BY created_at DESC;"
```

Cleanup candidates:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, state, expires_at, consumed_at, return_to FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

### chat_histories

Role:

- Parent table for each persisted conversation.
- `title` is stored in DB.
- `pin_order` is `NULL` for unpinned histories.
- `usage_summary` is a backend-maintained rollup cache built from assistant
  `chat_messages.usage`.
- A deleted history cascades messages, remembered-chat rows, and context
  checkpoint rows.

All histories with owner info:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, COALESCE(gi.ip_address, u.email, u.display_name) AS owner, ch.title, ch.pin_order, ch.interaction_state, ch.busy_reason, ch.created_at, ch.updated_at, ch.last_message_at, ch.usage_summary, COUNT(cm.id) AS message_count FROM chat_histories ch JOIN users u ON u.id = ch.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_messages cm ON cm.chat_history_id = ch.id GROUP BY ch.id, gi.ip_address, u.email, u.display_name ORDER BY ch.pin_order NULLS LAST, COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

Histories for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, interaction_state, busy_reason, created_at, updated_at, last_message_at, usage_summary FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

Delete one chat history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

Attachment counts per history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.title, COUNT(chf.id) AS attachment_count, COALESCE(SUM(chf.byte_size), 0) AS attachment_bytes FROM chat_histories ch LEFT JOIN chat_history_files chf ON chf.chat_history_id = ch.id GROUP BY ch.id ORDER BY ch.created_at DESC;"
```

### chat_messages

Table-friendly inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, CASE WHEN usage IS NULL THEN NULL ELSE usage->'normalized' END AS usage_normalized, CASE WHEN usage IS NULL THEN NULL ELSE usage->'price_estimate' END AS usage_price_estimate, first_response_at, deadline_at, completed_at, created_at, updated_at FROM chat_messages ORDER BY created_at DESC LIMIT 100;"
```

Messages for one history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, CASE WHEN usage IS NULL THEN NULL ELSE usage->'normalized' END AS usage_normalized, CASE WHEN usage IS NULL THEN NULL ELSE usage->'price_estimate' END AS usage_price_estimate, first_response_at, deadline_at, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Status counts:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, excluded_from_context, COUNT(*) FROM chat_messages GROUP BY status, excluded_from_context ORDER BY status, excluded_from_context;"
```

Stale streaming rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, length(content) AS content_length, model_id, provider, result_code, first_response_at, deadline_at, created_at, updated_at FROM chat_messages WHERE status = 'streaming' AND deadline_at IS NOT NULL AND deadline_at < NOW() ORDER BY deadline_at;"
```

Error outcome summary:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, result_code, finish_reason, COUNT(*) FROM chat_messages WHERE status = 'error' GROUP BY provider, result_code, finish_reason ORDER BY COUNT(*) DESC, provider, result_code;"
```

Cleanup:

- Delete the parent `chat_histories` row.

### stored_files

Role:

- Backend-owned attachment blob store in PostgreSQL.
- Deduplicated per user by `sha256`.
- Same visible filename does not mean the same blob.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, sha256, mime_type, byte_size, lifecycle_state, delete_attempt_count, delete_error, delete_last_attempt_at, delete_next_attempt_at, created_at, updated_at FROM stored_files ORDER BY created_at DESC;"
```

Blob references:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT sf.id, sf.sha256, sf.mime_type, sf.byte_size, sf.lifecycle_state, sf.delete_attempt_count, COUNT(chf.id) AS history_refs FROM stored_files sf LEFT JOIN chat_history_files chf ON chf.stored_file_id = sf.id GROUP BY sf.id ORDER BY sf.created_at DESC;"
```

### stored_file_provider_states

Role:

- Provider-specific token counts and provider-managed remote file refs for one
  stored blob.
- `provider_file_id` is the actual unique remote identifier.
- `filename` is not stored here because it is not a safe identity key.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, stored_file_id, token_count_status, token_count, provider_file_id, remote_file_status, uploaded_at, last_used_at, count_model_id FROM stored_file_provider_states ORDER BY provider, uploaded_at DESC NULLS LAST, id;"
```

Only live remote refs:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, stored_file_id, provider_file_id, remote_file_status, uploaded_at, last_used_at FROM stored_file_provider_states WHERE provider_file_id IS NOT NULL ORDER BY provider, uploaded_at DESC NULLS LAST, id;"
```

### chat_history_files

Role:

- One logical attachment row inside one chat history.
- Same-history duplicate content is blocked.
- Different histories may point to the same `stored_file_id`.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, stored_file_id, display_name, mime_type, byte_size, is_active, created_at FROM chat_history_files ORDER BY created_at DESC;"
```

Histories sharing the same stored blob:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT stored_file_id, chat_history_id, display_name, created_at FROM chat_history_files WHERE stored_file_id = 'PUT_STORED_FILE_ID_HERE' ORDER BY created_at, id;"
```

### chat_message_attachments

Role:

- Snapshot of which attachments were sent with one persisted user turn.
- Useful when you need to prove which provider file ids were in scope for a
  given message.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_message_id, attachment_index, chat_history_file_id, stored_file_id, display_name, mime_type, provider, provider_file_id, token_count, created_at FROM chat_message_attachments ORDER BY created_at DESC;"
```

One message's attachment snapshot:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT attachment_index, chat_history_file_id, stored_file_id, display_name, mime_type, provider, provider_file_id, token_count FROM chat_message_attachments WHERE chat_message_id = 'PUT_CHAT_MESSAGE_ID_HERE' ORDER BY attachment_index;"
```

### usage_ledger_events

Role:

- Append-only usage/spend audit rows for successful assistant turns.
- Cap enforcement reads this table, not deletable chat transcript rows.
- Chat ids are snapshots; deleting a product chat does not remove ledger spend.

Inspect recent ledger rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, provider, model_id, result_code, total_tokens_reported, total_cost_usd, price_completeness, chat_history_id_snapshot, chat_message_id_snapshot, created_at FROM usage_ledger_events ORDER BY created_at DESC LIMIT 100;"
```

One user's ledger total:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT user_id, COUNT(*) AS ledger_events, SUM(COALESCE(total_tokens_reported, 0)) AS total_tokens_total, SUM(total_cost_usd) AS estimated_price_total_usd FROM usage_ledger_events WHERE user_id = 'PUT_USER_ID_HERE' AND status IN ('billable', 'adjustment') GROUP BY user_id;"
```

### chat_history_memories

Role:

- Placeholder table for remembered-chat summaries.
- One row per `chat_history_id`.
- Deleting the parent history cascades this row.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, source_last_message_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_history_memories ORDER BY created_at DESC;"
```

One user's remembered-chat rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, source_last_message_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_history_memories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC;"
```

One history's remembered-chat row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, source_last_message_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_history_memories WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

### chat_context_checkpoints

Role:

- Active context-compaction checkpoint table.
- One row per `chat_history_id`.
- `covered_through_sequence` means the summary replaces all chat turns up to and
  including that sequence number.
- At runtime, provider context uses:
  - the checkpoint `summary_text`
  - then only raw `chat_messages` with `sequence > covered_through_sequence`
- Deleting the parent history cascades this row.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, covered_through_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_context_checkpoints ORDER BY created_at DESC;"
```

One user's checkpoint rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, covered_through_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_context_checkpoints WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC;"
```

One history's checkpoint row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, chat_history_id, status, covered_through_sequence, model_id, provider, requested_at, completed_at, created_at, updated_at FROM chat_context_checkpoints WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Checkpoint summary raw text for one history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, chat_history_id, status, covered_through_sequence, summary_text, error_detail, usage FROM chat_context_checkpoints WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Checkpoint summary raw text for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, chat_history_id, status, covered_through_sequence, summary_text, error_detail, usage FROM chat_context_checkpoints WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY created_at DESC;"
```

## Provider-Managed Attachment Files

Attachment provider file inspection and cleanup commands live in
`docs/ATTACHMENT_PROVIDER_FILES.md`.

### alembic_version

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

Cleanup:

- Do not delete this row.

## Raw Text / JSON

Use this section only after a friendly query told you which row you want.

Full content for one chat message:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, role, status, content FROM chat_messages WHERE id = 'PUT_CHAT_MESSAGE_ID_HERE';"
```

Stored error detail for one failed message:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, provider, model_id, finish_reason, result_code, result_message, error_detail FROM chat_messages WHERE id = 'PUT_CHAT_MESSAGE_ID_HERE';"
```

Usage JSON for one assistant message:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, usage FROM chat_messages WHERE id = 'PUT_CHAT_MESSAGE_ID_HERE';"
```

History usage summary cache for one chat:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, title, usage_summary FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Recent assistant pricing snapshots:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, provider, model_id, usage->'price_estimate' AS price_estimate FROM chat_messages WHERE role = 'assistant' AND usage IS NOT NULL ORDER BY updated_at DESC LIMIT 20;"
```

Full conversation text for one history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT sequence, role, status, result_code, result_message, content, error_detail FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Recent failed messages with stored detail:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, chat_history_id, sequence, model_id, provider, finish_reason, result_code, result_message, error_detail FROM chat_messages WHERE status = 'error' ORDER BY updated_at DESC LIMIT 20;"
```

Remembered-chat summary raw text:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, chat_history_id, status, summary_text, error_detail, usage FROM chat_history_memories WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

Context checkpoint summary raw text:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -x -c "SELECT id, user_id, chat_history_id, status, covered_through_sequence, summary_text, error_detail, usage FROM chat_context_checkpoints WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE';"
```

## Quick Smoke Checks

1. Migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

2. Active guest sessions by IP:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address ORDER BY gi.ip_address;"
```

3. Expired sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, expires_at, expired_reason_code FROM auth_sessions WHERE state <> 'active' OR expires_at <= NOW();"
```

4. Expired or consumed OAuth/conflict rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'oauth_transactions' AS table_name, COUNT(*) FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL;"
```

5. Stale streaming messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, model_id, provider, first_response_at, deadline_at, updated_at FROM chat_messages WHERE status = 'streaming' AND deadline_at IS NOT NULL AND deadline_at < NOW();"
```

6. Recent chat errors by code:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, result_code, finish_reason, COUNT(*) FROM chat_messages WHERE status = 'error' GROUP BY provider, result_code, finish_reason ORDER BY COUNT(*) DESC, provider, result_code;"
```

7. Remembered-chat placeholder rows by status:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, COUNT(*) FROM chat_history_memories GROUP BY status ORDER BY status;"
```

8. Context checkpoint rows by status:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, COUNT(*) FROM chat_context_checkpoints GROUP BY status ORDER BY status;"
```

9. Attachment blobs waiting for remote delete retry:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, lifecycle_state, delete_attempt_count, delete_next_attempt_at FROM stored_files WHERE lifecycle_state IN ('pending_delete', 'delete_failed') ORDER BY delete_next_attempt_at NULLS FIRST, updated_at;"
```

## Code Pointers

- PostgreSQL migrations: `backend/alembic/versions/`
- Migration runner: `backend/app/db/postgres/migrations.py`
- Auth/user models: `backend/app/db/postgres/models/auth_sessions.py`,
  `backend/app/db/postgres/models/auth_conflicts.py`,
  `backend/app/db/postgres/models/identities.py`,
  `backend/app/db/postgres/models/oauth_transactions.py`,
  `backend/app/db/postgres/models/user.py`
- Chat history model: `backend/app/db/postgres/models/chat_history.py`
- Attachment models: `backend/app/db/postgres/models/chat_attachment.py`
- Auth/session logic: `backend/app/auth/session_lifecycle.py`,
  `backend/app/auth/guest_sessions.py`,
  `backend/app/auth/conflict_tickets.py`
- Microsoft OAuth logic: `backend/app/auth/microsoft_oauth.py`
- Auth cleanup logic: `backend/app/workers/auth_cleanup.py`
- Chat persistence logic: `backend/app/services/chat/histories/service.py`,
  `backend/app/services/chat/completions/turn_persistence.py`,
  `backend/app/services/chat/completions/context/pipeline.py`,
  `backend/app/services/chat/histories/usage_summary.py`
- Attachment service: `backend/app/services/chat/attachments/service.py`,
  `backend/app/services/chat/attachments/storage.py`,
  `backend/app/services/chat/attachments/payloads.py`
