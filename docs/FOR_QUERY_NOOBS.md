## Inspect PostgreSQL
If you want to check whether guest users and sessions are being cleaned up correctly, use the commands below.

Open an interactive PostgreSQL shell inside the running container:

```powershell
docker exec -it ai-proxy-postgres psql -U postgres -d ai_proxy
```

If you do not want to use the shell, run these copy-paste commands directly from PowerShell.

Show recent users:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, display_name, account_type, status, created_at, last_seen_at FROM users ORDER BY created_at DESC;"
```

Show recent auth sessions:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at FROM auth_sessions ORDER BY created_at DESC;"
```

Show guest users that have no remaining session or identity rows.
This is the easiest query for spotting zombie guest rows:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT u.id, u.display_name, u.account_type, u.created_at FROM users u LEFT JOIN auth_sessions s ON s.user_id = u.id LEFT JOIN auth_identities i ON i.user_id = u.id WHERE u.account_type = 'guest' AND s.id IS NULL AND i.id IS NULL;"
```

If the last query returns `0 rows`, there are currently no orphaned guest users.

## Cleanup Smoke Test
If you want to force a guest session to expire and then verify cleanup:

1. Find the guest `user_id` from the `Show recent users` command.
2. Expire that guest's session manually:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "UPDATE auth_sessions SET idle_expires_at = NOW() - INTERVAL '1 minute', absolute_expires_at = NOW() - INTERVAL '1 minute' WHERE user_id = 'PUT_USER_ID_HERE';"
```

3. In the browser, call `GET /api/v1/auth/me` again or send one chat request.
4. Run the two inspection commands again:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, display_name, account_type, status, created_at, last_seen_at FROM users ORDER BY created_at DESC;"
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, auth_type, state, idle_expires_at, absolute_expires_at FROM auth_sessions ORDER BY created_at DESC;"
```

Expected result:
- the expired `auth_sessions` row should be gone
- if that was a guest-only user with no other identities, the matching `users` row should also be gone
