# PostgreSQL Query Cheat Sheet

This file is for inspecting the real PostgreSQL database from Docker Compose,
even if you are not comfortable with SQL yet.

The basic rule is:

1. run a table-friendly query first
2. copy the `id` you need
3. paste that `id` into the next query
4. only use raw text queries when you already know which row you want

Long text fields such as chat content, stored error detail, and JSON payloads
are intentionally kept out of the default table views. Those have a separate
`Raw Text / JSON` section near the bottom.

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
  `chat_history_memories`, `auth_provider_sessions`, or `guest_identities`.
- Prefer deleting cascade roots:
  - `users`
  - `auth_sessions`
  - `chat_histories`
- Guest users are keyed by raw IP address. In local Docker this is often a
  bridge IP such as `172.18.0.1`, not your LAN IP.
- Human users are intentional account data. They are not "zombie rows" just
  because they are old.

## Current Tables

Application tables:

1. `users`
2. `ms_identities`
3. `guest_identities`
4. `auth_sessions`
5. `auth_provider_sessions`
6. `auth_conflict_tickets`
7. `oauth_transactions`
8. `chat_histories`
9. `chat_messages`
10. `chat_history_memories`

Migration metadata:

11. `alembic_version`

Scaffold-only models that do not create active tables:

- `chat_request.py`
- `usage_log.py`

## Whole-Database Inspect

List tables:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
```

Row counts:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'users' AS table_name, COUNT(*) FROM users UNION ALL SELECT 'ms_identities', COUNT(*) FROM ms_identities UNION ALL SELECT 'guest_identities', COUNT(*) FROM guest_identities UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'auth_provider_sessions', COUNT(*) FROM auth_provider_sessions UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets UNION ALL SELECT 'oauth_transactions', COUNT(*) FROM oauth_transactions UNION ALL SELECT 'chat_histories', COUNT(*) FROM chat_histories UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages UNION ALL SELECT 'chat_history_memories', COUNT(*) FROM chat_history_memories ORDER BY table_name;"
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
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, created_at, updated_at, last_message_at FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

3. Use the copied `chat_histories.id` in the next query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
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
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, created_at, updated_at, last_message_at FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

### Workflow C: delete one chat history safely

1. Inspect the history first:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, created_at, updated_at, last_message_at FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE';"
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
- `chat_history_memories`

## Friendly Table Queries

Use these first. They avoid long raw text and are much easier to read in a
terminal.

### users

Role:

- Parent table for guest and Microsoft users.
- Deleting a user cascades identities, sessions, conflict tickets, chat
  histories, chat messages, and remembered-chat placeholder rows.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, updated_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

Rows owned by each user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.account_type, u.display_name, u.email, COUNT(DISTINCT s.id) AS sessions, COUNT(DISTINCT ch.id) AS chat_histories, COUNT(DISTINCT chm.id) AS remembered_histories, COUNT(DISTINCT mi.id) AS ms_identity_count, COUNT(DISTINCT gi.id) AS guest_identity_count FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id LEFT JOIN chat_history_memories chm ON chm.user_id = u.id LEFT JOIN ms_identities mi ON mi.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY u.id ORDER BY u.created_at DESC;"
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
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, persistent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code, superseded_by_session_id, created_ip, last_ip FROM auth_sessions ORDER BY created_at DESC;"
```

Expired or revoked sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code FROM auth_sessions WHERE state <> 'active' OR idle_expires_at <= NOW() OR absolute_expires_at <= NOW() ORDER BY created_at DESC;"
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
- A deleted history cascades both messages and remembered-chat placeholder rows.

All histories with owner info:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, COALESCE(gi.ip_address, u.email, u.display_name) AS owner, ch.title, ch.pin_order, ch.created_at, ch.updated_at, ch.last_message_at, COUNT(cm.id) AS message_count FROM chat_histories ch JOIN users u ON u.id = ch.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_messages cm ON cm.chat_history_id = ch.id GROUP BY ch.id, gi.ip_address, u.email, u.display_name ORDER BY ch.pin_order NULLS LAST, COALESCE(ch.last_message_at, ch.created_at) DESC;"
```

Histories for one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, title, pin_order, created_at, updated_at, last_message_at FROM chat_histories WHERE user_id = 'PUT_USER_ID_HERE' ORDER BY pin_order NULLS LAST, COALESCE(last_message_at, created_at) DESC;"
```

Delete one chat history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

### chat_messages

Table-friendly inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, completed_at, created_at, updated_at FROM chat_messages ORDER BY created_at DESC LIMIT 100;"
```

Messages for one history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Status counts:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, excluded_from_context, COUNT(*) FROM chat_messages GROUP BY status, excluded_from_context ORDER BY status, excluded_from_context;"
```

Stale streaming rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, length(content) AS content_length, model_id, provider, created_at, updated_at FROM chat_messages WHERE status = 'streaming' AND updated_at < NOW() - INTERVAL '10 minutes' ORDER BY updated_at;"
```

Error outcome summary:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, result_code, finish_reason, COUNT(*) FROM chat_messages WHERE status = 'error' GROUP BY provider, result_code, finish_reason ORDER BY COUNT(*) DESC, provider, result_code;"
```

Cleanup:

- Delete the parent `chat_histories` row.

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

## Quick Smoke Checks

1. Migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

2. Active guest sessions by IP:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address ORDER BY gi.ip_address;"
```

3. Expired or revoked sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at, revoked_reason_code FROM auth_sessions WHERE state <> 'active' OR idle_expires_at <= NOW() OR absolute_expires_at <= NOW();"
```

4. Expired or consumed OAuth/conflict rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'oauth_transactions' AS table_name, COUNT(*) FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL;"
```

5. Stale streaming messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, model_id, provider, updated_at FROM chat_messages WHERE status = 'streaming' AND updated_at < NOW() - INTERVAL '10 minutes';"
```

6. Recent chat errors by code:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT provider, result_code, finish_reason, COUNT(*) FROM chat_messages WHERE status = 'error' GROUP BY provider, result_code, finish_reason ORDER BY COUNT(*) DESC, provider, result_code;"
```

7. Remembered-chat placeholder rows by status:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, COUNT(*) FROM chat_history_memories GROUP BY status ORDER BY status;"
```

## Code Pointers

- PostgreSQL migrations: `proxy-api/alembic/versions/`
- Migration runner: `proxy-api/app/db/postgres/migrations.py`
- Auth/user models: `proxy-api/app/db/postgres/models/auth_sessions.py`,
  `proxy-api/app/db/postgres/models/auth_conflicts.py`,
  `proxy-api/app/db/postgres/models/identities.py`,
  `proxy-api/app/db/postgres/models/oauth_transactions.py`,
  `proxy-api/app/db/postgres/models/user.py`
- Chat history model: `proxy-api/app/db/postgres/models/chat_history.py`
- Auth/session logic: `proxy-api/app/auth/session_lifecycle.py`,
  `proxy-api/app/auth/guest_sessions.py`,
  `proxy-api/app/auth/conflict_tickets.py`
- Microsoft OAuth logic: `proxy-api/app/auth/microsoft_oauth.py`
- Auth cleanup logic: `proxy-api/app/auth/cleanup.py`
- Chat persistence logic: `proxy-api/app/services/chat/history_queries.py`,
  `proxy-api/app/services/chat/turns.py`,
  `proxy-api/app/services/chat/provider_context.py`
- Chat stream/background orchestration: `proxy-api/app/services/chat/stream.py`
- Backend chat outcome messages:
  `proxy-api/app/providers/openai/outcomes.py`,
  `proxy-api/app/providers/anthropic/outcomes.py`,
  `proxy-api/app/providers/vertex/outcomes.py`
