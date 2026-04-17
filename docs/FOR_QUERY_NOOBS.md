## PostgreSQL Quick Context

Runtime 기준 실제 Postgres ORM 테이블은 아래 5개입니다.

1. `users`
2. `auth_identities`
3. `auth_sessions`
4. `auth_provider_sessions`
5. `oauth_transactions`

`chat_request.py`, `usage_log.py`는 현재 placeholder라서 테이블이 생성되지 않습니다.

코드 기준 근거:
- `Base.metadata.create_all()`로 현재 ORM 모델만 생성함
- `auth`/`user` 모델 파일에만 실제 컬럼 정의가 있음

접속:

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
```

비대화형으로 바로 실행하려면 아래 형식 그대로 쓰면 됩니다.

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT NOW();"
```

## 1. users

역할:
- 게스트 사용자와 Microsoft 로그인 사용자 모두 저장
- 게스트는 `POST /api/v1/auth/login/guest` 때 생성
- Microsoft 사용자는 첫 로그인 성공 시 생성

좀비 적체 가능성:
- `guest`는 낮음
- 세션 삭제 시 `_delete_orphan_guest_user()`가 세션/identity 없는 guest user를 같이 삭제함
- 세션 정리는 요청 처리 중에도 되고, startup/백그라운드 cleanup 루프에서도 됨
- `human`은 앱에서 자동 삭제하지 않음
- 따라서 "안 쓰는 human user"는 남을 수 있지만, 현재 로직상 의도된 영속 데이터에 가깝고 좀비라고 보긴 애매함

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, account_type, status, display_name, email, created_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

고아 guest user 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN auth_identities i ON i.user_id = u.id WHERE u.account_type = 'guest' AND s.id IS NULL AND i.id IS NULL ORDER BY u.created_at DESC;"
```

세션도 identity도 없는 human user 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.email, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN auth_identities i ON i.user_id = u.id WHERE u.account_type = 'human' AND s.id IS NULL AND i.id IS NULL ORDER BY u.created_at DESC;"
```

cleanup:
- guest orphan만 안전하게 일괄 삭제 가능
- human user는 제품 정책 없이 지우면 안 됨

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM users u WHERE u.account_type = 'guest' AND NOT EXISTS (SELECT 1 FROM auth_sessions s WHERE s.user_id = u.id) AND NOT EXISTS (SELECT 1 FROM auth_identities i WHERE i.user_id = u.id) RETURNING u.id, u.display_name;"
```

## 2. auth_identities

역할:
- Microsoft 계정과 내부 `users` row를 묶는 영구 바인딩
- 첫 Microsoft 로그인 성공 시 생성
- 같은 `(provider, tenant_id, subject)` 조합은 unique

좀비 적체 가능성:
- 일반적인 의미의 zombie 가능성은 매우 낮음
- `users.id` FK + `ON DELETE CASCADE`라서 user 삭제 시 같이 삭제됨
- 앱 로직에는 identity 자동 삭제가 없으므로, 오래된 human identity는 계속 남을 수 있음
- 다만 이건 현재 로그인 재연결을 위해 의도된 보존 데이터에 가깝다

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT i.id, i.user_id, i.provider, i.tenant_id, i.subject, i.preferred_username, i.created_at, i.updated_at FROM auth_identities i ORDER BY i.created_at DESC;"
```

FK 상으론 거의 없어야 하는 이상 징후 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT i.* FROM auth_identities i LEFT JOIN users u ON u.id = i.user_id WHERE u.id IS NULL;"
```

cleanup:
- 보통 bulk cleanup 하지 말 것
- 특정 퇴사자/테스트 계정 정리처럼 명확한 사유가 있을 때만 user 기준으로 지우는 편이 안전함
- user를 먼저 지우면 cascade로 같이 사라짐

특정 user의 identity만 삭제:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_identities WHERE user_id = 'PUT_USER_ID_HERE' RETURNING id, user_id, preferred_username;"
```

## 3. auth_sessions

역할:
- 브라우저 쿠키의 실제 서버측 세션 메타데이터
- guest 로그인 성공 시 생성
- Microsoft 로그인 완료 시 생성

좀비 적체 가능성:
- 낮음
- 삭제 경로가 3개 있음
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me` 또는 보호 API 접근 시 `resolve_session()`이 만료/비활성 세션 즉시 삭제
- 앱 startup 1회 + 백그라운드 cleanup 루프가 만료 세션 정리
- 다만 앱이 오래 꺼져 있거나, 만료 후 아무 요청이 없고 cleanup 주기 전이면 잠깐 쌓일 수는 있음

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, created_at, last_seen_at, idle_expires_at, absolute_expires_at FROM auth_sessions ORDER BY created_at DESC;"
```

이미 만료됐는데 아직 남아 있는 세션:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at FROM auth_sessions WHERE idle_expires_at <= NOW() OR absolute_expires_at <= NOW() ORDER BY created_at DESC;"
```

cleanup:
- 만료 세션 삭제는 안전
- guest user orphan는 후속 정리 한 번 더 돌리는 것이 안전

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_sessions WHERE idle_expires_at <= NOW() OR absolute_expires_at <= NOW() RETURNING id, user_id, auth_type;"
```

그 다음 guest orphan 정리:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM users u WHERE u.account_type = 'guest' AND NOT EXISTS (SELECT 1 FROM auth_sessions s WHERE s.user_id = u.id) AND NOT EXISTS (SELECT 1 FROM auth_identities i WHERE i.user_id = u.id) RETURNING u.id, u.display_name;"
```

## 4. auth_provider_sessions

역할:
- provider token cache 등 provider session artifact 저장용
- 현재 설계상 Microsoft 세션 확장용 테이블

좀비 적체 가능성:
- 현재 코드 기준으로는 사실상 `0`
- `issue_session()`은 `provider_artifacts`가 있을 때만 이 row를 생성하는데, 현재 Microsoft 로그인 완료 경로는 `provider_artifacts`를 넘기지 않음
- 즉 현재 런타임에서는 테이블은 있어도 row가 안 쌓이는 상태로 보는 게 맞음
- 나중에 사용되더라도 `auth_sessions.id` FK + `ON DELETE CASCADE`라서 부모 세션 삭제 시 같이 삭제됨

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT session_id, provider, token_cache_version, access_token_expires_at, refresh_token_expires_at, tenant_id, home_account_id, created_at, updated_at FROM auth_provider_sessions ORDER BY created_at DESC;"
```

예상과 다르게 row가 있는지 count만 빠르게 확인:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT COUNT(*) AS provider_session_count FROM auth_provider_sessions;"
```

cleanup:
- 보통 이 테이블을 직접 지우지 말고 부모 `auth_sessions`를 지우는 게 맞음
- 부모 세션 삭제 시 cascade 처리됨
- 정말 실험 데이터만 비워야 하면 직접 삭제 가능

직접 비우기 전 inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT aps.session_id, aps.provider, s.auth_type, s.idle_expires_at, s.absolute_expires_at FROM auth_provider_sessions aps LEFT JOIN auth_sessions s ON s.id = aps.session_id ORDER BY aps.created_at DESC;"
```

직접 삭제:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM auth_provider_sessions RETURNING session_id, provider;"
```

## 5. oauth_transactions

역할:
- Microsoft OAuth redirect 시작 시 state/nonce/PKCE verifier 저장
- callback 성공/실패/취소 처리 전에 쓰는 짧은 수명 임시 테이블

좀비 적체 가능성:
- 낮음
- 생성은 로그인 redirect 시작 시 1회
- 정상 callback 성공 시 삭제
- callback error/cancel/invalid state 시도 삭제
- 만료되거나 `consumed_at`이 찍힌 row는 startup/백그라운드 cleanup 루프에서 삭제
- 실제로 쌓이더라도 최대한 짧게 남아야 정상
- 예외는 "로그인 시작만 하고 callback 안 옴" 케이스인데, 이것도 만료 시간 지나면 cleanup 대상

inspect:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, state, created_at, expires_at, consumed_at, return_to FROM oauth_transactions ORDER BY created_at DESC;"
```

이미 만료됐거나 consumed인데 아직 남아 있는 row:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, state, created_at, expires_at, consumed_at, return_to FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL ORDER BY created_at DESC;"
```

cleanup:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "DELETE FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL RETURNING id, state, expires_at, consumed_at;"
```

## Quick Smoke Checks

현재 로직이 정상인지 빠르게 보려면 이것만 보면 됩니다.

1. guest orphan user가 0건인지 확인

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN auth_identities i ON i.user_id = u.id WHERE u.account_type = 'guest' AND s.id IS NULL AND i.id IS NULL;"
```

2. 만료 auth session이 남아 있는지 확인

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, idle_expires_at, absolute_expires_at FROM auth_sessions WHERE idle_expires_at <= NOW() OR absolute_expires_at <= NOW();"
```

3. 만료 또는 consumed OAuth transaction이 남아 있는지 확인

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, state, expires_at, consumed_at FROM oauth_transactions WHERE expires_at <= NOW() OR consumed_at IS NOT NULL;"
```

4. `auth_provider_sessions`가 비어 있는지 확인

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT COUNT(*) AS provider_session_count FROM auth_provider_sessions;"
```

## Code Pointers

로직 추적할 때 보면 되는 파일:
- `proxy-api/app/db/postgres/models/user.py`
- `proxy-api/app/db/postgres/models/auth.py`
- `proxy-api/app/services/auth.py`
- `proxy-api/app/services/microsoft_auth.py`
- `proxy-api/app/main.py`

핵심 포인트:
- guest user 생성: `create_guest_session()`
- auth session 생성: `issue_session()`
- 세션 만료/삭제 + guest orphan 정리: `resolve_session()`, `delete_session()`, `_delete_orphan_guest_user()`
- OAuth transaction 생성/삭제: `build_microsoft_authorization_url()`, `complete_microsoft_authorization()`, `_delete_transaction()`
- 주기 cleanup: `purge_expired_auth_data()`, `_auth_cleanup_loop()`
