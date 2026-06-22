# Attachment Provider Files

This file is for operators inspecting and cleaning attachment storage across:

- PostgreSQL `stored_files`
- PostgreSQL `stored_file_provider_states`
- OpenAI Files API
- Anthropic Files API
- Vertex GCS attachment objects

The current maintenance script is:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files --help
```

## Assumptions

- PostgreSQL `stored_files` is the source of truth for attachment bytes.
- Remote attachment files are disposable execution copies.
- For this product, remote OpenAI files, remote Anthropic files, and Vertex objects in the configured bucket/prefix are assumed to belong to this product.
- Default Vertex scope comes from:
  - `VERTEX_AI_ATTACHMENT_GCS_BUCKET`
  - `VERTEX_AI_ATTACHMENT_GCS_PREFIX`
- If you need to force the current known Vertex scope explicitly, use:
  - bucket: `nextin-aipx-gemini-files-20260601-test`
  - prefix: `chat_attachments`

## Lifecycle

- Browser upload stores file bytes in PostgreSQL `stored_files`.
- Attach-time uploads a remote copy for each supported provider and stores per-provider token metadata in `stored_file_provider_states`.
- OpenAI and Anthropic store provider file ids.
- Vertex stores private `gs://bucket/object` URIs.
- Send-time reuses the remote copy for the selected provider when available.
- If a selected provider copy was deleted out of band, send-time checks the current remote id, notices the miss, and recreates it from PostgreSQL before continuing.
- Housekeeping clears dead remote refs and deletes stale remote copies after the configured TTL.
- PostgreSQL blobs stay in place even after remote copies are deleted.
- When the last logical history reference is deleted, `stored_files.lifecycle_state` moves from `active` to `pending_delete` while provider remote refs are deleted.
- If any provider delete fails, the blob remains in PostgreSQL as `delete_failed` with `delete_error`, `delete_attempt_count`, `delete_last_attempt_at`, and `delete_next_attempt_at`.
- Housekeeping retries due `pending_delete` and `delete_failed` blobs with backoff. It logs `attachment_blob_delete_failed` only on the transition into failed state, so repeated retry failures do not flood `operator_events`.

## Quick Checks

Inspect local PostgreSQL blobs and metadata:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db-blobs
```

Inspect one local blob by `stored_file_id`:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db-blobs --stored-file-id PUT_STORED_FILE_ID_HERE
```

Inspect one user's local blobs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db-blobs --user-id PUT_USER_ID_HERE
```

Inspect blobs waiting for delete retry directly in PostgreSQL:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, user_id, lifecycle_state, delete_attempt_count, delete_error, delete_last_attempt_at, delete_next_attempt_at FROM stored_files WHERE lifecycle_state IN ('pending_delete', 'delete_failed') ORDER BY delete_next_attempt_at NULLS FIRST, updated_at;"
```

Inspect DB-tracked remote refs only:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db
```

Inspect DB-tracked remote refs for one provider:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider openai
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider anthropic
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider vertex_ai
```

List remote OpenAI files:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-openai --limit 100
```

List remote Anthropic files:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-anthropic --limit 100
```

List remote Vertex objects using current env scope:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-vertex --limit 100
```

List remote Vertex objects using the current known bucket/prefix explicitly:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-vertex --bucket nextin-aipx-gemini-files-20260601-test --prefix chat_attachments --limit 100
```

## Consistency Inspection

Inspect full local-vs-remote consistency across all providers:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency
```

Inspect only one provider:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency --provider openai
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency --provider anthropic
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency --provider vertex_ai
```

Inspect consistency with the current known Vertex bucket/prefix explicitly:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency --bucket nextin-aipx-gemini-files-20260601-test --prefix chat_attachments
```

Inspect consistency with larger sample lists in the output:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files inspect-consistency --sample-limit 300
```

The consistency report checks:

- local PostgreSQL blob count, orphan local blobs, and blob lifecycle state
- DB provider refs missing from remote storage
- remote files missing any DB ref
- duplicate DB provider file ids
- invalid DB states such as `remote_file_status = ready` with no `provider_file_id`
- provider-by-provider counts and bytes
- cross-provider count mismatch warnings

Important: a cross-provider remote count mismatch is a warning, not automatic corruption. The current runtime refreshes `last_used_at` only for the provider actually used on send, so one provider can stay warm while another provider copy ages out after 24 hours.

## Consistency Cleanup

Dry-run a full reconciliation plan:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency
```

Apply full reconciliation:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency --apply
```

Apply reconciliation only for one provider:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency --provider openai --apply
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency --provider anthropic --apply
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency --provider vertex_ai --apply
```

Apply reconciliation with the current known Vertex bucket/prefix explicitly:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files reconcile-consistency --bucket nextin-aipx-gemini-files-20260601-test --prefix chat_attachments --apply
```

`reconcile-consistency --apply` does two things:

- clears DB refs whose remote file is already gone
- deletes remote files that have no DB ref

It does not delete local PostgreSQL orphan blobs. Runtime housekeeping deletes unreferenced blobs through the `pending_delete` / `delete_failed` lifecycle after provider remote refs are cleared.

With the current runtime, reconciliation is no longer required for basic recovery after an out-of-band remote delete. The next send now verifies the stored remote id and reuploads if the file is gone. Reconciliation is still useful for cleaning stale metadata and remote orphan files.

## Exact File Id Cleanup

Delete one exact OpenAI file id and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider openai --file-id PUT_OPENAI_FILE_ID_HERE
```

Delete one exact Anthropic file id and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider anthropic --file-id PUT_ANTHROPIC_FILE_ID_HERE
```

Delete one exact Vertex object URI and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider vertex_ai --file-id gs://PUT_BUCKET/PATH/TO/OBJECT
```

Delete one exact remote file id without changing DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider openai --file-id PUT_OPENAI_FILE_ID_HERE --skip-db-clear
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider anthropic --file-id PUT_ANTHROPIC_FILE_ID_HERE --skip-db-clear
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider vertex_ai --file-id gs://PUT_BUCKET/PATH/TO/OBJECT --skip-db-clear
```

## Filename Cleanup

`filename` is only a human label. It is not a unique identity key. Browsers often reuse names such as `image.png`.

Delete matching OpenAI filenames and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider openai --filename test.pdf
```

Delete matching Anthropic filenames and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider anthropic --filename test.pdf
```

Delete matching Vertex basenames and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider vertex_ai --filename test.pdf
```

Delete matching filenames from all providers:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --filename test.pdf
```

Delete matching Vertex basenames using the current known bucket/prefix explicitly:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider vertex_ai --filename test.pdf --bucket nextin-aipx-gemini-files-20260601-test --prefix chat_attachments
```

Remote-only filename cleanup without DB changes:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --filename test.pdf --skip-db-clear
```

Use filename cleanup only when the filename is specific enough to target exactly what you intend to delete.
