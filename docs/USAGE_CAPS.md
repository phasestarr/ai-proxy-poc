# Usage Caps

Operators can cap estimated user spend without cron or time windows.

## Rule

- Default cap: `USAGE_DEFAULT_CAP_USD` (`100` in `.env.example`)
- If a user has no `user_usage_caps` row, the default cap applies from zero.
- `set-cap` creates or updates a user's cap.
- `reset-cap` moves `baseline_estimated_price_usd` to the user's current stored usage, effectively unlocking them while keeping the same cap.
- Enforcement happens before a provider request is sent.
- Usage is based on stored assistant message price snapshots in `chat_messages.usage->price_estimate->total_cost_usd`.

## Commands

List users by effective usage, descending:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps list --limit 50
```

Set one user's cap:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps set-cap PUT_USER_ID_HERE 100 --reason "default deployment cap"
```

Reset one user's cap baseline:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps reset-cap --user-id PUT_USER_ID_HERE --reason "operator approved reset"
```

Reset every user's cap baseline:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps reset-cap --all --reason "monthly operator reset"
```

Disable one user's cap:

```powershell
docker exec ai-proxy-api python -m app.maintenance.usage_caps disable-cap PUT_USER_ID_HERE --reason "temporary operator override"
```

## User-Facing Error

When a user reaches the effective cap, the backend rejects before provider dispatch with:

- `result_code`: `usage_cap_exceeded`
- HTTP status: `429`
- message: `Usage cap reached. Ask the operator to reset or raise the cap.`

The frontend already renders this as a normal send error.
