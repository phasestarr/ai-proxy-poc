# PostgreSQL Query Cheat Sheet

Docker Compose 기준으로 실제 PostgreSQL을 inspect할 때 쓰는 문서입니다.

접속:

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
```

비대화형 실행:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT NOW();"
```

## Safety Rules

- 직접 특정 row를 지우는 `DELETE` 예시는 FK cascade root인 `users`, `auth_sessions`, `chat_histories`에만 둡니다.
- `ms_identities`, `guest_identities`, `auth_provider_sessions`, `auth_conflict_tickets`, `oauth_transactions`, `chat_messages`는 보통 부모 row 삭제나 앱 cleanup으로 정리합니다.
- 운영 DB에서 `DELETE` 전에는 같은 `WHERE`로 `SELECT`를 먼저 실행하세요.
- guest user는 IP 기준 identity를 재사용합니다. 로컬 Docker에서는 실제 LAN IP가 아니라 nginx가 보는 Docker bridge IP, 예: `172.18.0.1`, 로 보일 수 있습니다.

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

`chat_request.py`, `usage_log.py`는 scaffold-only라 현재 테이블을 만들지 않습니다.

## Whole-Database Inspect

테이블 목록:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
```

row count:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'users' AS table_name, COUNT(*) FROM users UNION ALL SELECT 'ms_identities', COUNT(*) FROM ms_identities UNION ALL SELECT 'guest_identities', COUNT(*) FROM guest_identities UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'auth_provider_sessions', COUNT(*) FROM auth_provider_sessions UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets UNION ALL SELECT 'oauth_transactions', COUNT(*) FROM oauth_transactions UNION ALL SELECT 'chat_histories', COUNT(*) FROM chat_histories UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages ORDER BY table_name;"
```

FK cascade 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' ORDER BY tc.table_name, kcu.column_name;"
```

Alembic head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

## 1. users

역할:

- guest와 Microsoft human user의 공통 parent table
- guest는 `guest_identities.ip_address`와 1:1로 묶임
- Microsoft user는 `ms_identities`와 1:1로 묶임
- user 삭제 시 identity, session, chat history가 cascade로 삭제됨

좀비 가능성:

- guest orphan 가능성은 낮음. session 삭제 시 orphan guest 정리 로직이 있음.
- human user는 자동 삭제하지 않음. 오래 남아도 의도된 계정 데이터입니다.
- user가 사라지면 하위 row는 FK cascade 대상입니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, updated_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

user별 하위 row count:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.account_type, u.display_name, u.email, COUNT(DISTINCT s.id) AS sessions, COUNT(DISTINCT ch.id) AS chat_histories, COUNT(DISTINCT mi.id) AS ms_identity_count, COUNT(DISTINCT gi.id) AS guest_identity_count FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id LEFT JOIN ms_identities mi ON mi.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY u.id ORDER BY u.created_at DESC;"
```

guest orphan 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_histories ch ON ch.user_id = u.id WHERE u.account_type = 'guest' AND s.id IS NULL AND gi.id IS NULL AND ch.id IS NULL ORDER BY u.created_at DESC;"
```

특정 user 삭제:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM users WHERE id = 'PUT_USER_ID_HERE' RETURNING id, account_type, display_name, email;"
```

cascade 영향:

- `ms_identities`
- `guest_identities`
- `auth_sessions`
- `auth_provider_sessions`, via `auth_sessions`
- `auth_conflict_tickets`
- `chat_histories`
- `chat_messages`, via `chat_histories`

## 2. ms_identities

역할:

- Microsoft account와 내부 `users` row를 묶는 영구 identity table
- `(provider, tenant_id, subject)` unique
- `user_id`는 unique라 현재 구조에서는 user당 Microsoft identity 1개

좀비 가능성:

- 낮음. `users.id` FK `ON DELETE CASCADE`.
- 앱이 human user를 자동 삭제하지 않으므로 오래된 Microsoft identity는 계정 보존 데이터로 남습니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, provider, tenant_id, subject, home_account_id, preferred_username, created_at, updated_at FROM ms_identities ORDER BY created_at DESC;"
```

FK 이상 징후:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT mi.* FROM ms_identities mi LEFT JOIN users u ON u.id = mi.user_id WHERE u.id IS NULL;"
```

cleanup:

- 직접 삭제하지 말고 parent `users` row를 삭제하세요.

## 3. guest_identities

역할:

- guest IP와 내부 `users` row를 묶는 identity table
- IP는 해싱하지 않고 그대로 저장합니다.
- 같은 IP는 같은 guest user로 재사용합니다.

좀비 가능성:

- 낮음. `users.id` FK `ON DELETE CASCADE`.
- 로컬 Docker에서는 IP가 `172.18.0.1`처럼 Docker bridge 주소로 보일 수 있습니다.
- 컴퓨터 재부팅 후에도 Docker volume이 유지되고 같은 IP로 잡히면 같은 guest user로 재사용됩니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.id, gi.user_id, gi.provider, gi.ip_address, u.display_name, u.created_at AS user_created_at, gi.created_at, gi.updated_at FROM guest_identities gi JOIN users u ON u.id = gi.user_id ORDER BY gi.created_at DESC;"
```

IP별 active session:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, gi.user_id, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions, COUNT(s.id) AS total_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address, gi.user_id ORDER BY gi.ip_address;"
```

FK 이상 징후:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.* FROM guest_identities gi LEFT JOIN users u ON u.id = gi.user_id WHERE u.id IS NULL;"
```

cleanup:

- 직접 삭제하지 말고 parent `users` row를 삭제하세요.

## 4. auth_sessions

역할:

- `session_id` HttpOnly cookie의 서버측 session metadata
- DB에는 raw session key가 아니라 SHA-256 hash만 저장합니다.
- guest max sessions default는 `2`, Microsoft max sessions default는 `4`.
- limit 초과 시 기본 strategy는 `reject`; conflict resolve는 `evict_oldest`로 oldest active session을 revoke하고 새 session을 만듭니다.
- oldest 기준은 `last_seen_at ASC NULLS FIRST`, tie-breaker는 `created_at ASC`.

좀비 가능성:

- 낮음.
- logout, request-time validation, startup cleanup, background cleanup이 만료/비활성 session을 정리합니다.
- evicted session은 원인 추적을 위해 잠깐 `revoked`로 남고 cleanup 대상이 됩니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, persistent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code, superseded_by_session_id, created_ip, last_ip FROM auth_sessions ORDER BY created_at DESC;"
```

user/IP별 session count:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT COALESCE(gi.ip_address, u.email, u.display_name) AS owner, s.auth_type, s.state, COUNT(*) FROM auth_sessions s JOIN users u ON u.id = s.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id GROUP BY owner, s.auth_type, s.state ORDER BY owner, s.auth_type, s.state;"
```

만료 또는 revoked session:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at, revoked_at, revoked_reason_code FROM auth_sessions WHERE state <> 'active' OR idle_expires_at <= NOW() OR absolute_expires_at <= NOW() ORDER BY created_at DESC;"
```

특정 session 삭제:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_sessions WHERE id = 'PUT_SESSION_ID_HERE' RETURNING id, user_id, auth_type, state;"
```

cascade 영향:

- `auth_provider_sessions`
- `superseded_by_session_id`를 참조하는 다른 `auth_sessions` row는 `SET NULL`

## 5. auth_provider_sessions

역할:

- provider token cache 같은 provider artifact 저장용 table
- 현재는 Microsoft Graph API 확장을 위해 유지합니다.
- 현재 login flow는 provider artifacts를 아직 저장하지 않으므로 보통 비어 있습니다.

좀비 가능성:

- 현재는 row 생성 자체가 사실상 없습니다.
- 나중에 row가 생겨도 `auth_sessions.id` FK `ON DELETE CASCADE`.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT session_id, provider, token_cache_version, access_token_expires_at, refresh_token_expires_at, tenant_id, home_account_id, scope, last_refresh_at, last_refresh_error, created_at, updated_at FROM auth_provider_sessions ORDER BY created_at DESC;"
```

부모 session 상태와 같이 보기:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT aps.session_id, aps.provider, s.user_id, s.auth_type, s.state, s.idle_expires_at, s.absolute_expires_at FROM auth_provider_sessions aps LEFT JOIN auth_sessions s ON s.id = aps.session_id ORDER BY aps.created_at DESC;"
```

cleanup:

- 직접 삭제하지 말고 parent `auth_sessions` row를 삭제하세요.

## 6. auth_conflict_tickets

역할:

- Microsoft callback에서 session limit에 걸렸을 때 짧게 살아있는 conflict ticket을 저장합니다.
- raw ticket은 `session_conflict_id` HttpOnly cookie에만 있고 DB에는 hash만 저장합니다.
- resolve endpoint가 ticket을 소비해 oldest session을 evict하고 새 session을 발급합니다.

좀비 가능성:

- 낮음.
- TTL default는 `5 minutes`.
- expired/consumed row는 startup/background auth cleanup에서 삭제됩니다.
- user 삭제 시 `ON DELETE CASCADE`.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, reason, return_to, created_at, expires_at, consumed_at, requester_ip FROM auth_conflict_tickets ORDER BY created_at DESC;"
```

cleanup 대상:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, expires_at, consumed_at FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

cleanup:

- 직접 삭제하지 말고 app cleanup을 기다리거나 앱을 재시작해 startup cleanup을 태우세요.
- 특정 계정 전체를 지울 때는 parent `users` row를 삭제하세요.

## 7. oauth_transactions

역할:

- Microsoft OAuth redirect 시작 시 state/nonce/PKCE verifier를 저장하는 짧은 수명 transaction table
- 정상 callback 성공/실패/취소 처리 시 삭제됩니다.

좀비 가능성:

- 낮음.
- 로그인 시작 후 callback이 오지 않으면 만료 전까지 남을 수 있습니다.
- expired/consumed row는 startup/background auth cleanup에서 삭제됩니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, state, return_to, created_at, expires_at, consumed_at, requester_ip FROM oauth_transactions ORDER BY created_at DESC;"
```

cleanup 대상:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, state, expires_at, consumed_at, return_to FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

cleanup:

- 직접 삭제하지 말고 app cleanup을 기다리거나 앱을 재시작해 startup cleanup을 태우세요.

## 8. chat_histories

역할:

- user별 chat history parent table
- 새 chat은 첫 `/api/v1/chat/completions` 요청에서 자동 생성됩니다.
- 프런트는 SSE `start` 이벤트의 `chat_history_id`를 저장해 다음 send에 이어 보냅니다.
- history 삭제 시 messages가 cascade 삭제됩니다.

좀비 가능성:

- 낮음.
- user가 삭제되면 history도 cascade 삭제됩니다.
- 사용자가 삭제하지 않은 history는 제품 데이터라 좀비가 아닙니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT ch.id, ch.user_id, COALESCE(gi.ip_address, u.email, u.display_name) AS owner, ch.title, ch.created_at, ch.updated_at, ch.last_message_at, COUNT(cm.id) AS message_count FROM chat_histories ch JOIN users u ON u.id = ch.user_id LEFT JOIN guest_identities gi ON gi.user_id = u.id LEFT JOIN chat_messages cm ON cm.chat_history_id = ch.id GROUP BY ch.id, gi.ip_address, u.email, u.display_name ORDER BY ch.updated_at DESC;"
```

특정 history 메시지 보기:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, sequence, role, status, excluded_from_context, left(content, 120) AS content_preview, model_id, provider, tool_ids, finish_reason, error_detail, created_at, updated_at FROM chat_messages WHERE chat_history_id = 'PUT_CHAT_HISTORY_ID_HERE' ORDER BY sequence;"
```

특정 chat history 삭제:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM chat_histories WHERE id = 'PUT_CHAT_HISTORY_ID_HERE' RETURNING id, user_id, title;"
```

cascade 영향:

- `chat_messages`

## 9. chat_messages

역할:

- chat history 하위 message table
- user/assistant turn을 모두 저장합니다.
- stream 실패 시 화면 렌더링은 위해 저장하되 `excluded_from_context=true`로 표시해 다음 provider payload에서 제외합니다.

좀비 가능성:

- 낮음.
- parent `chat_histories` 삭제 시 cascade 삭제됩니다.
- `status='streaming'`이 오래 남으면 중단된 stream 흔적일 수 있으니 inspect해야 합니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, status, excluded_from_context, left(content, 120) AS content_preview, model_id, provider, tool_ids, finish_reason, error_detail, usage, created_at, updated_at FROM chat_messages ORDER BY created_at DESC LIMIT 100;"
```

상태별 count:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT status, excluded_from_context, COUNT(*) FROM chat_messages GROUP BY status, excluded_from_context ORDER BY status, excluded_from_context;"
```

오래 남은 streaming row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, role, length(content) AS content_length, created_at, updated_at FROM chat_messages WHERE status = 'streaming' AND updated_at < NOW() - INTERVAL '10 minutes' ORDER BY updated_at;"
```

cleanup:

- 직접 삭제하지 말고 parent `chat_histories` row를 삭제하세요.
- 특정 failed/streaming message만 수동 수정하는 것은 대화 재구성 순서를 깨뜨릴 수 있어 권장하지 않습니다.

## 10. alembic_version

역할:

- Alembic migration head를 기록하는 metadata table
- 앱 startup에서 `alembic upgrade head`가 실행됩니다.

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

cleanup:

- 직접 삭제하지 마세요.

## Quick Smoke Checks

현재 DB 상태가 정상인지 빠르게 보려면 아래만 확인하면 됩니다.

1. migration head:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT version_num FROM alembic_version;"
```

2. guest IP별 active session:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT gi.ip_address, COUNT(s.id) FILTER (WHERE s.state = 'active') AS active_sessions FROM guest_identities gi LEFT JOIN auth_sessions s ON s.user_id = gi.user_id GROUP BY gi.ip_address ORDER BY gi.ip_address;"
```

3. 만료/revoked sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at, revoked_reason_code FROM auth_sessions WHERE state <> 'active' OR idle_expires_at <= NOW() OR absolute_expires_at <= NOW();"
```

4. expired/consumed OAuth/conflict rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT 'oauth_transactions' AS table_name, COUNT(*) FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL UNION ALL SELECT 'auth_conflict_tickets', COUNT(*) FROM auth_conflict_tickets WHERE expires_at <= NOW() OR consumed_at IS NOT NULL;"
```

5. stale streaming messages:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, chat_history_id, sequence, updated_at FROM chat_messages WHERE status = 'streaming' AND updated_at < NOW() - INTERVAL '10 minutes';"
```

## Code Pointers

- PostgreSQL migrations: `proxy-api/alembic/versions/`
- migration runner: `proxy-api/app/db/postgres/migrations.py`
- auth/user models: `proxy-api/app/db/postgres/models/auth_sessions.py`, `proxy-api/app/db/postgres/models/auth_conflicts.py`, `proxy-api/app/db/postgres/models/identities.py`, `proxy-api/app/db/postgres/models/oauth_transactions.py`, `proxy-api/app/db/postgres/models/user.py`
- chat history models: `proxy-api/app/db/postgres/models/chat_history.py`
- auth/session logic: `proxy-api/app/auth/session_lifecycle.py`, `proxy-api/app/auth/guest_sessions.py`, `proxy-api/app/auth/conflict_tickets.py`
- Microsoft OAuth logic: `proxy-api/app/auth/microsoft_oauth.py`
- auth cleanup logic: `proxy-api/app/auth/cleanup.py`
- chat persistence logic: `proxy-api/app/services/chat/history_queries.py`, `proxy-api/app/services/chat/turns.py`, `proxy-api/app/services/chat/provider_context.py`
- chat stream orchestration: `proxy-api/app/services/chat/stream.py`
