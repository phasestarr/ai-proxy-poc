# TO-DO

Current follow-up list for issues that are either intentional policy gaps or
future cleanup work. Keep this file short and remove items when the code or
product policy settles.

## Operation Atomicity

Attachment mutations currently commit the product change before the endpoint
marks the `chat_operations` row terminal.

Normal example:

1. `POST /api/v1/chat/files` starts `chat_operations(attach_file, running)`.
2. Backend validates the upload, prepares all provider file/token metadata, and
   commits `stored_files` plus `chat_history_files`.
3. Endpoint marks the operation `succeeded`.

Crash-only gap:

- If the process crashes after step 2 and before step 3, the file is attached
  but the operation can remain live until housekeeping times it out.
- Housekeeping can clear the active token and write `chat_operation_timed_out`
  when the operation row still exists.
- Housekeeping does not roll back the already-committed attachment.
- Whole-history deletes and last-file deletes of empty file-only histories can
  cascade the operation row away, leaving no stale operation row to close.

Possible fix:

- Move mutation and terminal operation update into one transaction where
  practical.
- For destructive history deletes, decide whether a separate tombstone/audit
  event is needed before deleting the parent row.

## Provider Streaming Pre-Turn Gap

Chat send transitions an operation to `provider_streaming` before the
user/assistant rows are persisted.

Normal example:

1. Backend validates request, rebuilds context, compacts if needed, and prepares
   attachments.
2. Backend transitions operation to `provider_streaming`.
3. Backend persists user message and streaming assistant placeholder.
4. Provider stream starts.

Crash-only gap:

- If the process crashes between steps 2 and 3, the history can show an active
  provider-streaming operation with no new turn rows.
- Housekeeping can time out the operation and clear the active token, but there
  is no assistant row to mark as error.

Possible fix:

- Persist the turn first and transition to `provider_streaming` in the same
  transaction, or add explicit pre-turn recovery/audit for operations without
  matching message rows.

## Empty-History Cleanup Guard

`delete_stale_empty_histories` deletes old histories with no messages or files.
With the current defaults this is safe because `HOUSEKEEPING_INTERVAL_MINUTES=60`
and `CHAT_VALIDATING_OPERATION_TIMEOUT_SECONDS=900`.

Risk:

- If housekeeping is tuned below the operation timeout, it can delete an empty
  new text-send history while its operation is still active.

Possible fix:

- Add `ChatHistory.active_operation_id IS NULL` to the stale-empty-history
  deletion query, or keep the current timeout invariant documented and enforced.

## Hard Per-User Attachment Quota

`CHAT_ATTACHMENT_MAX_FILES_PER_USER` is currently enforced by counting existing
history/draft files before inserting the new row.

Risk:

- Concurrent uploads to different histories can each pass the count check and
  exceed the per-user file count by a small amount.

Possible fix:

- Use a per-user quota row with `SELECT ... FOR UPDATE`.
- Alternatively use PostgreSQL advisory locks keyed by user id around the
  count-and-insert section.
- Keep the existing per-history duplicate constraints; those are already hard DB
  guarantees.

## Provider Error Formatting

Provider errors are mostly mapped to product result codes/messages, but raw or
provider-specific detail can still flow through `error_detail`, SSE `detail`,
and history responses.

Possible fix:

- Split user-facing error text from operator diagnostic detail across API,
  persisted message fields, and frontend rendering.
- Keep provider raw detail available only through operator/audit surfaces.

## Migration Squash

The current migration history includes several schema evolution steps that are
already resolved in code. After production data strategy is settled, consider
squashing to a clean baseline migration for fresh deployments.
