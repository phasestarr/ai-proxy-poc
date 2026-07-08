# Chat Persistence State Model Audit

Scope: backend chat persistence, operations, drafts, attachments, compression checkpoints, deletion, and cleanup. Frontend rendering/button state is intentionally out of scope except where the backend API requires an id.

Source files used:

- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `backend/app/db/postgres/migrations.py`
- `backend/app/db/postgres/models/chat_history.py`
- `backend/app/db/postgres/models/chat_attachment.py`
- `backend/app/services/chat/operations.py`
- `backend/app/api/v1/endpoints/chat.py`
- `backend/app/services/chat/completions/*`
- `backend/app/services/chat/attachments/*`
- `backend/app/workers/chat_*cleanup.py`

## High-Level Verdict

The current model is close to the intended backend-owned flow, but `chat_operations` is not yet a fully authoritative production state machine.

It does fence the important mutating chat paths:

- send
- attach file to existing history
- blank-page file upload through an internal draft
- delete file
- toggle file active state
- delete history
- context compression and send-time attachment preparation during send

The backend also continues provider execution after SSE disconnect because the provider pipeline runs in an independent task and uses fresh DB sessions.

The weak spots are:

- operation state transitions are enforced by service convention, not by DB constraints
- no DB-level uniqueness constraint guarantees only one active operation per scope
- some history metadata writes are not operation-fenced
- destructive history deletion cascades away its operation row, so successful delete operations are not retained as terminal operation records
- assistant message success/failure and operation terminal state are committed in separate transactions
- `finalizing`, `cancelled`, several checkpoint/provider-state values are defined but effectively unused
- blank-page multi-file behavior is sequential-history based; concurrent blank uploads create separate histories because there is no reusable client-visible or session-visible draft id

## Managed Tables

All current managed tables are listed in `backend/app/db/postgres/migrations.py`.

In scope for this audit:

- `chat_histories`
- `chat_drafts`
- `chat_operations`
- `chat_messages`
- `chat_history_memories`
- `chat_context_checkpoints`
- `stored_files`
- `stored_file_provider_states`
- `chat_history_files`
- `chat_draft_files`
- `chat_message_attachments`
- `operator_events`
- `usage_ledger_events`

Related but not the chat state machine:

- `users`: owner row and account status
- `auth_sessions`: owns `auth_session_id` snapshots and chat capability checks
- `user_usage_caps`: affects send validation before turn persistence

Out of scope for this persistence-state audit:

- `ms_identities`
- `guest_identities`
- `auth_provider_sessions`
- `auth_conflict_tickets`
- `oauth_transactions`

## Table Schemas And State Columns

### `chat_histories`

Purpose: visible conversation owner. It owns messages, logical attachments, checkpoints, and active operation ownership.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owning user id, FK `users.id`.
- `title`: display title.
- `pin_order`: nullable integer; `NULL` means unpinned.
- `lifecycle_state`: project-defined lifecycle state.
- `active_operation_id`: nullable current operation id. Not a DB FK.
- `active_operation_token`: nullable current operation token. Pairs with `active_operation_id`.
- `created_at`, `updated_at`: timestamps.
- `last_message_at`: nullable timestamp used for history ordering.
- `usage_summary`: JSON rollup cache.

Accepted project-defined values:

- `lifecycle_state`: `active`, `deleting`.

Notes:

- `deleting` is set only when a `delete_history` operation starts.
- `active_operation_id` and `active_operation_token` are the real write fence, not `lifecycle_state`.
- `load_user_history()` does not filter `lifecycle_state`, so a history in `deleting` is still loadable until the delete commits.

### `chat_drafts`

Purpose: internal staging owner for blank-page file upload. It is not a user-visible draft conversation.

Columns:

- `id`: string UUID, primary key. On successful promotion, the resulting `chat_histories.id` is the same value.
- `user_id`: owner.
- `lifecycle_state`: project-defined draft cleanup state.
- `active_operation_id`: nullable current operation id. Not a DB FK.
- `active_operation_token`: nullable current operation token.
- `expires_at`: draft cleanup deadline.
- `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `lifecycle_state`: `active`, `expired`.

Notes:

- Successful blank upload promotes the draft into `chat_histories`, copies draft files into `chat_history_files`, then deletes the draft.
- Housekeeping deletes expired drafts when they have no active operation.
- `expired` is a cleanup marker, not a user-visible state.

### `chat_operations`

Purpose: intended master operation record for one in-flight mutation on a history or draft.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `auth_session_id`: nullable auth session snapshot, FK `auth_sessions.id`.
- `scope_type`: project-defined scope discriminator.
- `scope_id`: UUID of the history or draft owner.
- `chat_history_id`: nullable FK to `chat_histories.id`.
- `draft_id`: nullable FK to `chat_drafts.id`.
- `operation_type`: project-defined operation kind.
- `state`: project-defined operation state.
- `owner_token`: random token copied onto the current owner row.
- `deadline_at`: next validation/provider event deadline.
- `provider_started_at`: timestamp when provider phase started.
- `first_provider_event_at`: timestamp of first provider event.
- `last_provider_event_at`: throttled provider heartbeat timestamp.
- `provider_max_deadline_at`: hard provider runtime deadline.
- `result_code`: nullable project/provider result code.
- `error_detail`: nullable safe detail.
- `created_at`, `updated_at`, `completed_at`: timestamps.

Accepted project-defined values:

- `scope_type`: `history`, `draft`.
- `operation_type`: `send`, `attach_file`, `delete_file`, `toggle_file`, `delete_history`.
- `state`: `validating`, `provider_streaming`, `finalizing`, `succeeded`, `failed`, `timed_out`, `cancelled`.

Observed transitions:

```text
create -> validating

send:
  validating -> provider_streaming -> succeeded
  validating -> failed
  validating -> timed_out
  provider_streaming -> failed
  provider_streaming -> timed_out

attach_file existing history:
  validating -> succeeded
  validating -> failed
  validating -> timed_out

attach_file blank-page draft:
  draft validating -> history validating -> succeeded
  draft validating -> failed/timed_out + draft cleanup

delete_file:
  validating -> succeeded
  validating -> failed
  validating -> timed_out
  validating -> history row deleted, operation row cascaded when last file removes empty file-only history

toggle_file:
  validating -> succeeded
  validating -> failed

delete_history:
  validating -> history row deleted, operation row cascaded
  validating -> failed
  validating -> timed_out
```

Unused or weak values:

- `finalizing` is defined but not used by current code.
- `cancelled` is accepted by DB but not used by current code.
- `scope_type`, `scope_id`, `chat_history_id`, and `draft_id` consistency is not DB-enforced. For example, DB constraints do not require exactly one of `chat_history_id` or `draft_id`.
- There is no partial unique index on active operation states per `(scope_type, scope_id)`. Single-active behavior depends on `chat_histories.active_operation_id` or `chat_drafts.active_operation_id` and row locking in service code.

### `chat_messages`

Purpose: persisted transcript. User prompt and assistant placeholder are created only after request context, compression, and attachment preparation are ready for provider dispatch.

Columns:

- `id`: string UUID, primary key.
- `chat_history_id`: FK `chat_histories.id`.
- `sequence`: per-history ordering integer, unique with `chat_history_id`.
- `role`: project-defined message role.
- `content`: message text.
- `status`: project-defined message status.
- `excluded_from_context`: boolean. Failed turns are renderable but excluded from future provider context.
- `model_id`: selected public model snapshot.
- `provider`: provider snapshot.
- `tool_ids`: JSON array snapshot.
- `finish_reason`: provider-native/free-form finish reason.
- `result_code`: project/provider result code, not DB-constrained.
- `result_message`: user-safe result message.
- `error_detail`: user-safe/debug-safe detail.
- `usage`: JSON normalized/provider usage and price snapshot.
- `first_response_at`: nullable first provider event timestamp.
- `deadline_at`: nullable assistant/provider liveness deadline.
- `completed_at`, `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `role`: `user`, `assistant`.
- `status`: `done`, `streaming`, `error`.

Observed transitions:

```text
user message:
  created as done
  if provider/prepared turn fails after persistence: excluded_from_context = true

assistant message:
  created as streaming
  streaming -> done
  streaming -> error + excluded_from_context = true
```

Notes:

- `finish_reason` is intentionally provider-native and should not be treated as an enum.
- `result_code` is not constrained because it mixes proxy codes and provider-specific codes.

### `chat_context_checkpoints`

Purpose: active compression checkpoint table. A ready checkpoint replaces older messages for provider context only; raw chat rendering still comes from `chat_messages`.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `chat_history_id`: FK `chat_histories.id`, unique.
- `status`: project-defined checkpoint state.
- `summary_text`: compressed summary.
- `covered_through_sequence`: last message sequence covered by summary.
- `model_id`, `provider`: compression model/provider snapshot.
- `usage`: compression usage JSON.
- `error_detail`: nullable.
- `requested_at`, `completed_at`, `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `status`: `building`, `ready`, `failed`.

Observed runtime use:

- Current code only loads `ready`.
- Current code persists `ready`.
- `building` and `failed` are accepted but not currently written by the compression pipeline.

### `chat_history_memories`

Purpose: older remembered-summary placeholder. It is model-defined but has no active writer in the current backend search.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `chat_history_id`: FK `chat_histories.id`, unique.
- `status`: project-defined memory state.
- `summary_text`: nullable.
- `source_last_message_sequence`: nullable.
- `model_id`, `provider`: nullable.
- `usage`: nullable JSON.
- `error_detail`: nullable.
- `requested_at`, `completed_at`, `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `status`: `pending`, `ready`, `failed`.

Current status:

- Appears unused in runtime code. Treat as legacy/dead unless an external worker exists outside this repository.

### `stored_files`

Purpose: backend-owned attachment blob storage and physical cleanup lifecycle.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `sha256`: content hash; unique with `user_id`.
- `mime_type`: normalized MIME type.
- `byte_size`: integer.
- `content`: bytea blob.
- `lifecycle_state`: project-defined blob cleanup state.
- `delete_error`: nullable cleanup failure detail.
- `delete_attempt_count`: integer retry count.
- `delete_last_attempt_at`, `delete_next_attempt_at`: nullable retry timestamps.
- `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `lifecycle_state`: `active`, `pending_delete`, `delete_failed`.

Observed transitions:

```text
active -> pending_delete
pending_delete -> delete_failed
pending_delete -> physical row delete
delete_failed -> physical row delete
delete_failed -> active
```

Notes:

- `delete_failed -> active` happens if the file gains a logical reference again.
- Provider remote files are disposable; this table is the source of truth for bytes.

### `stored_file_provider_states`

Purpose: per-provider token count and remote file reference cache for each stored blob.

Columns:

- `id`: string UUID, primary key.
- `stored_file_id`: FK `stored_files.id`.
- `provider`: project-defined provider.
- `token_count`: nullable integer.
- `token_count_status`: project-defined token-count state.
- `token_count_error`: nullable detail.
- `provider_file_id`: nullable provider file id or Vertex `gs://` URI.
- `remote_file_status`: project-defined remote-file state.
- `remote_file_error`: nullable detail.
- `count_model_id`: nullable model used for token count.
- `uploaded_at`, `last_used_at`, `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `provider`: `openai`, `anthropic`, `vertex_ai`.
- `token_count_status`: `ready`, `failed`, `unsupported`.
- `remote_file_status`: `not_uploaded`, `ready`, `failed`, `unsupported`.

Observed runtime use:

- Token count path currently writes `ready` or raises before persisting a failed state.
- Send-time remote file path writes `ready`, `failed`, and `not_uploaded`.
- `unsupported` appears accepted but unused.

### `chat_history_files`

Purpose: logical file attachments for a visible chat history.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `chat_history_id`: FK `chat_histories.id`.
- `stored_file_id`: FK `stored_files.id`.
- `display_name`: safe display filename.
- `mime_type`: normalized MIME type.
- `byte_size`: integer.
- `is_active`: boolean; active files are injected into future sends.
- `created_at`, `updated_at`: timestamps.

State-like values:

- `is_active`: boolean only.

Notes:

- Duplicate content in the same history is blocked by `UNIQUE(chat_history_id, stored_file_id)`.

### `chat_draft_files`

Purpose: logical file attachments while a blank-page upload is staging.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner.
- `draft_id`: FK `chat_drafts.id`.
- `stored_file_id`: FK `stored_files.id`.
- `display_name`: safe display filename.
- `mime_type`: normalized MIME type.
- `byte_size`: integer.
- `is_active`: boolean.
- `created_at`, `updated_at`: timestamps.

State-like values:

- `is_active`: boolean only.

Notes:

- Successful promotion copies rows into `chat_history_files` with the same file row ids, then deletes draft rows.

### `chat_message_attachments`

Purpose: per-turn snapshot of active attachments at provider dispatch time.

Columns:

- `id`: string UUID, primary key.
- `chat_message_id`: FK `chat_messages.id`; this snapshots against the persisted user message.
- `attachment_index`: per-message order.
- `chat_history_file_id`: nullable logical attachment id snapshot.
- `stored_file_id`: nullable blob id snapshot.
- `display_name`, `mime_type`, `byte_size`: file snapshot.
- `provider`: project-defined provider.
- `provider_file_id`: nullable provider id or Vertex URI used for the turn.
- `token_count`: nullable integer.
- `created_at`, `updated_at`: timestamps.

Accepted project-defined values:

- `provider`: `openai`, `anthropic`, `vertex_ai`.

### `operator_events`

Purpose: operator-facing audit stream for rejects, provider turn failures, timeout recovery, and attachment cleanup failures.

Columns:

- `id`: string UUID, primary key.
- `event_type`: project-defined but not DB-constrained.
- `severity`: project-defined severity.
- `user_id`: nullable FK.
- `auth_session_id`: nullable FK.
- `chat_history_id`: nullable string snapshot.
- `chat_message_id`: nullable string snapshot.
- `stored_file_id`: nullable string snapshot.
- `model_id`, `provider`, `operation`, `result_code`: nullable snapshots.
- `http_status`, `retry_after_seconds`: nullable integers.
- `message`, `detail`: nullable text.
- `metadata`: nullable JSON.
- `created_at`, `resolved_at`: timestamps.

Accepted project-defined values:

- `severity`: `debug`, `info`, `warning`, `error`, `critical`.

Common observed event/result/operation values:

- event types: `chat_request_rejected`, `usage_cap_exceeded`, `chat_turn_failed`, `chat_provider_first_response_timeout`, `chat_provider_response_timeout`, `chat_operation_timed_out`, `chat_execution_stale_closed`, `attachment_blob_delete_failed`, `attachment_remote_delete_failed`, `attachment_remote_reconcile_failed`, `attachment_remote_purge_failed`.
- operations: `chat_completion`, `send`, `attach_file`, `delete_file`, `toggle_file`, `delete_history`, `attachment_blob_delete`, `attachment_remote_delete`, `attachment_remote_reconcile`, `attachment_remote_purge`.

Notes:

- This is an audit table, not the state machine.
- Successful history deletes are not retained here by default.

### `usage_ledger_events`

Purpose: append-only spend ledger for successful billable assistant turns.

Columns:

- `id`: string UUID, primary key.
- `user_id`: owner snapshot.
- `auth_session_id`: nullable session snapshot.
- `chat_history_id_snapshot`, `chat_message_id_snapshot`: nullable/string snapshots.
- `provider`, `model_id`, `tool_ids`: route snapshot.
- `operation`: operation label, currently `chat_completion`.
- `source`: project-defined source.
- `status`: project-defined ledger status.
- `result_code`: nullable result code.
- token count columns: nullable integer usage snapshots.
- `price_estimate`, `provider_raw_usage`: nullable JSON.
- `total_cost_usd`: numeric.
- `currency`, `pricing_version`, `price_completeness`: pricing snapshot.
- `created_at`: timestamp.

Accepted project-defined values:

- `source`: `chat_completion`, `backfill`, `operator_adjustment`.
- `status`: `billable`, `adjustment`.

Notes:

- This table intentionally snapshots deleted chat ids rather than FK-ing to deletable chat rows.

## Current Pipeline Graphs

### Text-Only First Send

```text
POST /chat/completions without chat_history_id
  -> create chat_histories row
  -> create chat_operations(send, history, validating)
  -> run validation
  -> build context
  -> optional compression checkpoint
  -> prepare active attachments, if any
  -> transition operation to provider_streaming
  -> create user done + assistant streaming messages
  -> provider stream continues even if SSE disconnects
  -> assistant streaming -> done/error
  -> operation -> succeeded/failed/timed_out
```

Important behavior:

- If validation fails before turn persistence, the empty history is best-effort deleted.
- Local rejects are persisted to `operator_events`, not to `chat_messages`.

### Send With Existing History

```text
POST /chat/completions with chat_history_id
  -> begin_history_operation(send)
  -> reject 409 if active_operation_id exists
  -> run validation/context/compression/attachments
  -> provider_streaming
  -> persist user+assistant rows
  -> terminal assistant + terminal operation
```

Future context includes:

- ready checkpoint summary, if present
- non-error, non-excluded, done messages after checkpoint coverage
- latest request user message

### Blank-Page File Upload

```text
POST /chat/files without chat_history_id
  -> begin_draft_operation(attach_file)
  -> validate file bytes/name/MIME
  -> upload/count provider copies
  -> create stored_files + provider states
  -> create chat_draft_files
  -> promote draft to chat_histories(id = draft.id)
  -> copy draft files into chat_history_files
  -> reassign operation from draft to history
  -> delete draft
  -> operation -> succeeded
```

Failure behavior:

- rollback operation to failed/timed_out
- delete staging draft and draft files
- clean orphan stored file/provider files where possible

Important limitation:

- A blank upload creates and promotes one draft in one request. There is no reusable draft id. Concurrent blank uploads cannot be joined into one backend conversation without the frontend serializing around the returned `chat_history_id`.

### Attach Existing History File

```text
POST /chat/files with chat_history_id
  -> begin_history_operation(attach_file)
  -> validate file
  -> create or reuse stored_files by user+sha256
  -> ensure provider token states
  -> create chat_history_files
  -> operation -> succeeded
```

### Send-Time Attachment Preparation

```text
send validating
  -> load active chat_history_files
  -> require selected provider token_count_status=ready
  -> enforce provider total attachment token limit
  -> verify/reupload provider remote file for selected provider
  -> commit provider_file_id/last_used_at
  -> snapshot attachments into chat_message_attachments when user turn persists
```

### File Delete

```text
DELETE /chat/histories/{history_id}/files/{file_id}
  -> begin_history_operation(delete_file)
  -> delete chat_history_files row
  -> if stored file has no logical refs:
       stored_files active -> pending_delete
       delete provider remote files
       physical delete or delete_failed
  -> if history has no messages and no files:
       delete chat_histories row
       operation row cascades
  -> else operation -> succeeded
```

### History Delete

```text
DELETE /chat/histories/{history_id}
  -> begin_history_operation(delete_history)
  -> chat_histories.lifecycle_state = deleting
  -> delete logical attachments
  -> clean orphan stored files
  -> delete chat_histories row
  -> chat_messages/checkpoints/files/operations cascade
```

Notes:

- There is no retained successful `chat_operations` terminal row for a history delete because the operation row is cascaded with the history.
- If delete times out/fails before the history row is deleted, operation cleanup returns `lifecycle_state` to `active`.

### Timeout And Housekeeping

```text
active operation with expired deadline
  -> operation.state = timed_out
  -> active_operation_id/token cleared
  -> deleting history restored to active
  -> streaming assistant messages in that history become error
  -> user side of failed turn excluded_from_context = true
  -> operator_events row written

expired draft with no active operation
  -> delete draft files
  -> clean orphan stored files
  -> delete draft
```

## Production-Readiness Gaps

### 1. `chat_operations` is not the only write gate

Fenced by operations:

- send
- file attach
- file delete
- file activation toggle
- history delete
- context compression during send
- send-time attachment provider prep

Not fenced by operations:

- history title update
- pin/unpin
- list/get/read file content
- housekeeping cleanup
- attachment remote reconciliation/purge

Read paths not being fenced is reasonable. Metadata writes are a product decision: if "every DB change relies on chat_operation" is the requirement, title/pin/unpin currently violate it.

### 2. DB constraints validate values, not valid transitions

The DB accepts operation states and operation types, but does not enforce legal transitions like:

- `validating -> provider_streaming`
- `provider_streaming -> succeeded`
- no terminal -> nonterminal transition
- draft scope can only use `attach_file`
- history scope cannot point to `draft_id`

Those rules exist only in service code.

### 3. Single-active operation is service-enforced

The current lock is:

- row lock on `chat_histories` or newly created `chat_drafts`
- owner row stores `active_operation_id` and `active_operation_token`
- every critical write calls `assert_operation_current`

That is a good application-level fence, but the DB does not have a unique partial index over nonterminal operations. Stray rows can exist. The owner row decides authority.

### 4. Operation terminal state is not atomically committed with final message state

On provider success:

```text
persist assistant done + usage ledger -> commit
complete operation succeeded -> second commit
```

On provider failure:

```text
persist assistant error/exclusions -> commit
complete operation failed/timed_out -> second commit
```

A crash between these commits can leave:

- assistant message `done` or `error`
- operation still `provider_streaming`
- active operation still blocking new writes until cleanup
- later housekeeping may mark the operation `timed_out`, even though the user-visible assistant row is already terminal

The accepted but unused `finalizing` state looks like the intended place to close this gap.

### 5. Successful destructive operations often delete their own operation record

When deleting a history, the history row cascades `chat_operations`, so no successful terminal operation remains.

When deleting the last file from a file-only history, the empty history is deleted and the operation row also cascades before `complete_operation` can persist success.

This is acceptable if deleted histories are intentionally erased, but it means `chat_operations` is not a durable audit log for all operations.

### 6. Several accepted states are unused or reserved

Observed unused or mostly unused states:

- `chat_operations.state = finalizing`
- `chat_operations.state = cancelled`
- `chat_context_checkpoints.status = building`
- `chat_context_checkpoints.status = failed`
- `chat_history_memories.status` entirely, unless external code exists
- `stored_file_provider_states.token_count_status = failed`
- `stored_file_provider_states.token_count_status = unsupported`
- `stored_file_provider_states.remote_file_status = unsupported`

Unused candidates increase cognitive load and make the state graph look larger than it is.

### 7. `delete_stale_empty_histories` does not check active operation ownership

The stale-empty-history cleanup deletes histories with no messages and no files. It does not explicitly require `active_operation_id IS NULL`.

In normal settings, expired operation cleanup runs before this and the cutoff is larger than validation timeout, so it is probably safe in practice. Still, if the timeouts are reconfigured, this cleanup can become a hidden writer outside the operation fence.

### 8. `lifecycle_state` is not consistently used as an access guard

`chat_histories.lifecycle_state='deleting'` is exposed through API summaries but is not used by `load_user_history()` as a filter. Mutating endpoints are still protected by `active_operation_id`, so this is not currently a data corruption path. It does mean lifecycle is a hint, not a closed-state guard.

## Recommended Refactor Targets

1. Decide whether `chat_operations` is a coordination fence or a durable state ledger.
   - If it is a ledger, deletion flows need operation rows that survive history deletion, or operator-event equivalents for success.
   - If it is only a fence, document that deleted histories intentionally erase operation rows.

2. Add explicit transition helpers.
   - Avoid setting operation `state` directly outside one module.
   - Either use `finalizing` or remove it.
   - Remove `cancelled` unless cancellation exists.

3. Add DB-level integrity where practical.
   - Check exactly one of `chat_history_id`/`draft_id` based on `scope_type`.
   - Consider FK or consistency strategy for `active_operation_id`.
   - Consider a partial unique index for nonterminal operations by scope if PostgreSQL migrations allow it.

4. Make final message + operation terminal update one DB transaction.
   - Persist assistant terminal state, usage ledger, and operation terminal state together.
   - This reduces cleanup false-timeout states after process crashes.

5. Make housekeeping respect active operation ownership explicitly.
   - Add `ChatHistory.active_operation_id.is_(None)` to stale-empty cleanup unless intentionally deleting active empty histories.

6. Either remove dead states/tables or document them as reserved.
   - `chat_history_memories` is especially likely to confuse future state-machine work because checkpoints are the active compression model.

7. Clarify blank-page multi-upload semantics.
   - Current design requires the frontend to use the returned `chat_history_id` after the first blank upload.
   - If the frontend should truly know only `session_id`, the backend needs a session-scoped current draft/history concept or a server-owned pending conversation selector.
