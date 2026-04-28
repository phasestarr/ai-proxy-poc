# PostgreSQL Query Cheat Sheet

This file is for inspecting the real PostgreSQL database from Docker Compose,
even if you are not comfortable with SQL yet.

The queries below prefer short, table-friendly columns. Long text fields such as
chat content, stored error detail, and JSON payloads are kept out of the default
tables and have a separate inspection section.

## Connect

Interactive shell:

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
```

Run one query:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT NOW();"
```

## Safety Rules

- Do not delete rows casually from child tables.
- The only direct `DELETE` examples in this document target cascade roots:
  `users`, `auth_sessions`, and `chat_histories`.
- `ms_identities`, `guest_identities`, `auth_provider_sessions`,
  `auth_conflict_tickets`, `oauth_transactions`, and `chat_messages` are usually
  cleaned up by parent-row cascade or app cleanup.
- Before any production `DELETE`, run a `SELECT` with the same `WHERE` clause.
- Guest users are keyed by raw IP address. In local Docker this is often a
  bridge IP such as `172.18.0.1`, not your LAN IP.

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

Migration metadata:

10. `alembic_version`

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
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'users' AS table_name, COUNT(*) FROM users UNION ALL SELECT 'ms_identities', COUNT(*) FROM ms_identities UNION ALL SELECT 'guest_identities', COUNT(*) FROM guest_identities UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'auth_provider_sessions', COUNT(*) FROM auth_provider_sessions UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets UNION ALL SELECT 'oauth_transactions', COUNT(*) FROM oauth_transactions UNION ALL SELECT 'chat_histories', COUNT(*) FROM chat_histories UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages ORDER BY table_name;"
```

Foreign-key cascade rules:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' ORDER BY tc.table_name, kcu.column_name;"
```

Alembic head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

## 1. users

Role:

- Parent table for guest and Microsoft users.
- Guest users are linked one-to-one with `guest_identities.ip_address`.
- Microsoft users are linked one-to-one with `ms_identities`.
- Deleting a user cascades identities, sessions, conflict tickets, chat
  histories, and chat messages.

Zombie risk:

- Low for guest users. Guest cleanup removes orphaned guest users when sessions
  are gone.
- Human users are intentionally retained. Old human users are account data, not
  zombies.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, updated_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

Rows owned by each user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.account_type, u.display_name, u.email, COUNT(DISTINCT s.id) AS sessions, COUNT(DISTINCT ch.id) AS chat_histories, COUNT(DISTINCT mi.id) AS ms_identity_count, COUNT(DISTINCT gi.id) AS guest_identity_count FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id LEFT JOIN ms_identities mi ON mi.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY u.id ORDER BY u.created_at DESC;"
```

Guest orphans:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id WHERE u.account_type = 'guest' AND s.id IS NULL AND gi.id IS NULL AND ch.id IS NULL ORDER BY u.created_at DESC;"
```

Delete one user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM users WHERE id = 'PUT_USER_ID_HERE' RETURNING id, account_type, display_name, email;"
```

Cascade impact:

- `ms_identities`
- `guest_identities`
- `auth_sessions`
- `auth_provider_sessions`, through `auth_sessions`
- `auth_conflict_tickets`
- `chat_histories`
- `chat_messages`, through `chat_histories`

## 2. ms_identities

Role:

- Links a Microsoft account to one internal `users` row.
- `(provider, tenant_id, subject)` is unique.
- `user_id` is unique, so the current model has one Microsoft identity per user.

Zombie risk:

- Low. `users.id` has `ON DELETE CASCADE`.
- Old rows can exist because human users are retained intentionally.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, provider, tenant_id, subject, home_account_id, preferred_username, created_at, updated_at FROM ms_identities ORDER BY created_at DESC;"
```

Missing parent user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT mi.* FROM ms_identities mi LEFT JOIN users u ON u.id = mi.user_id WHERE u.id IS NULL;"
```

Cleanup:

- Delete the parent `users` row, not this child row directly.

## 3. guest_identities

Role:

- Links a guest IP address to one internal `users` row.
- IP addresses are stored raw, not hashed.
- The same IP reuses the same guest user.

Zombie risk:

- Low. `users.id` has `ON DELETE CASCADE`.
- Local Docker often shows the bridge IP, such as `172.18.0.1`.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.id, gi.user_id, gi.provider, gi.ip_address, u.display_name, u.created_at AS user_created_at, gi.created_at, gi.updated_at FROM guest_identities gi JOIN users u ON u.id = gi.user_id ORDER BY gi.created_at DESC;"
```

Active sessions by guest IP:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, gi.user_id, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions, COUNT(s.id) AS total_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address, gi.user_id ORDER BY gi.ip_address;"
```

Missing parent user:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.* FROM guest_identities gi LEFT JOIN users u ON u.id = gi.user_id WHERE u.id IS NULL;"
```

Cleanup:

- Delete the parent `users` row, not this child row directly.

## 4. auth_sessions

Role:

- Server-side metadata for the `session_id` HttpOnly cookie.
- The database stores only a SHA-256 hash of the raw session key.
- Guest max sessions default: `2`.
- Microsoft max sessions default: `4`.
- Default session-limit strategy is `reject`; conflict resolution explicitly uses
  `evict_oldest`.
- Oldest active session is selected by `last_seen_at ASC NULLS FIRST`, then
  `created_at ASC`.

Zombie risk:

- Low. Logout, request-time validation, startup cleanup, and background cleanup
  remove expired or inactive sessions.
- Revoked sessions may remain briefly for diagnostics and then get cleaned up.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, persistent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code, superseded_by_session_id, created_ip, last_ip FROM auth_sessions ORDER BY created_at DESC;"
```

Session count by owner:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT COALESCE(gi.ip_address, u.email, u.display_name) AS owner, s.auth_type, s.state, COUNT(*) FROM auth_sessions s JOIN users u ON u.id = s.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY owner, s.auth_type, s.state ORDER BY owner, s.auth_type, s.state;"
```

Expired or revoked sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code FROM auth_sessions WHERE state <> 'active' OR idle_expires_at <= NOW() OR absolute_expires_at <= NOW() ORDER BY created_at DESC;"
```

Delete one session:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_sessions WHERE id = 'PUT_SESSION_ID_HERE' RETURNING id, user_id, auth_type, state;"
```

Cascade impact:

- `auth_provider_sessions`
- Other `auth_sessions.superseded_by_session_id` references are set to `NULL`

## 5. auth_provider_sessions

Role:

- Storage for provider session artifacts such as future Microsoft token cache
  data.
- The current login flow usually leaves this table empty.

Zombie risk:

- Very low. Rows are rare today.
- If rows are added later, `auth_sessions.id` has `ON DELETE CASCADE`.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT session_id, provider, token_cache_version, access_token_expires_at, refresh_token_expires_at, tenant_id, home_account_id, scope, last_refresh_at, last_refresh_error, created_at, updated_at FROM auth_provider_sessions ORDER BY created_at DESC;"
```

Join parent session state:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT aps.session_id, aps.provider, s.user_id, s.auth_type, s.state, s.idle_expires_at, s.absolute_expires_at FROM auth_provider_sessions aps LEFT JOIN auth_sessions s ON s.id = aps.session_id ORDER BY aps.created_at DESC;"
```

Cleanup:

- Delete the parent `auth_sessions` row, not this child row directly.

## 6. auth_conflict_tickets

Role:

- Short-lived tickets used when Microsoft callback hits a session limit.
- The raw ticket is only in the `session_conflict_id` HttpOnly cookie.
- The database stores only the ticket hash.
- The resolve endpoint consumes the ticket, evicts the oldest active session, and
  issues a new session.

Zombie risk:

- Low.
- Default TTL is `5 minutes`.
- Expired or consumed rows are removed by startup/background cleanup.
- User deletion cascades these rows.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, reason, return_to, created_at, expires_at, consumed_at, requester_ip FROM auth_conflict_tickets ORDER BY created_at DESC;"
```

Cleanup candidates:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, expires_at, consumed_at FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

Cleanup:

- Let app cleanup handle it, or restart the app to run startup cleanup.
- To remove all data for one account, delete the parent `users` row.

## 7. oauth_transactions

Role:

- Short-lived Microsoft OAuth transaction table.
- Stores state, nonce, and PKCE verifier metadata for the redirect flow.
- Successful, failed, or canceled callbacks delete or consume the transaction.

Zombie risk:

- Low.
- If login starts and callback never returns, rows remain until expiration.
- Expired or consumed rows are removed by startup/background cleanup.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, state, return_to, created_at, expires_at, consumed_at, requester_ip FROM oauth_transactions ORDER BY created_at DESC;"
```

Cleanup candidates:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, state, expires_at, consumed_at, return_to FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

Cleanup:

- Let app cleanup handle it, or restart the app to run startup cleanup.

## 8. chat_histories

Role:

- Parent table for each persisted conversation.
- New chats are auto-created by the first `POST /api/v1/chat/completions` when
  `chat_history_id` is absent.
- The frontend stores the `chat_history_id` from the SSE `start` event to
  continue the same conversation.
- Deleting a history cascades messages.

Zombie risk:

- Low.
- User deletion cascades histories.
- Histories intentionally kept by users are product data, not zombies.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, COALESCE(gi.ip_address, u.email, u.display_name) AS owner, ch.title, ch.created_at, ch.updated_at, ch.last_message_at, COUNT(cm.id) AS message_count FROM chat_histories ch JOIN users u ON u.id = ch.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_messages cm ON cm.chat_history_id = ch.id GROUP BY ch.id, gi.ip_address, u.email, u.display_name ORDER BY ch.updated_at DESC;"
```

Short message list for one history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, completed_at, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

Delete one chat history:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

Cascade impact:

- `chat_messages`

## 9. chat_messages

Role:

- Child table for persisted chat history messages.
- Stores both user and assistant messages.
- After SEND, the backend owns provider execution and stores success or failure
  outcomes as `result_code` and `result_message`.
- Failure rows keep provider-specific terminal semantics instead of generic
  proxy error columns.
- Failed turns are kept renderable but marked `excluded_from_context=true`, so
  future provider payloads do not include them.

Zombie risk:

- Low.
- Parent `chat_histories` deletion cascades messages.
- Old `status='streaming'` rows can indicate incomplete background work and
  should be inspected.

Table-friendly inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, status, excluded_from_context, length(content) AS content_length, model_id, provider, tool_ids, finish_reason, result_code, result_message, completed_at, created_at, updated_at FROM chat_messages ORDER BY created_at DESC LIMIT 100;"
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
- Avoid manually editing individual failed or streaming messages unless you are
  intentionally repairing a known row.

## 10. alembic_version

Role:

- Records the current Alembic migration head.
- App startup runs `alembic upgrade head`.

Inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

Cleanup:

- Do not delete this row.

## Long Text Inspection

Use this section when a compact table query tells you which row you need. These
queries intentionally display long text or JSON and may be messy in a terminal.

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
