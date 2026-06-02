# Attachment Provider Files

This file is for inspecting and manually cleaning provider-managed attachment files in OpenAI, Anthropic, and Vertex GCS.

Use exact provider file ids or Vertex `gs://...` URIs for cleanup. Do not bulk-delete every provider file that is missing from this database, because provider projects or buckets may be shared by another service.

## Lifecycle

- Browser upload stores file bytes in PostgreSQL `stored_files`.
- Attaching a file uploads remote provider copies, runs provider token counting, and stores metadata in `stored_file_provider_states`.
- OpenAI and Anthropic use provider Files API ids.
- Vertex uses private GCS `gs://...` object URIs.
- Send-time reuses the provider remote copy when `provider_file_id` exists and `remote_file_status = 'ready'`.
- If housekeeping removed or reconciled away the remote copy, send-time upload recreates it from PostgreSQL `stored_files.content`.
- Deleting one chat's logical attachment does not delete the provider file if another chat still references the same `stored_file_id`.
- Deleting the final logical reference first deletes provider remote files and then deletes the PostgreSQL `stored_files` row. If provider delete fails, the DB row is kept for a future retry path.
- The housekeeping job runs at startup and every `HOUSEKEEPING_INTERVAL_MINUTES`; it reconciles missing provider refs and deletes provider remote copies after `CHAT_ATTACHMENT_REMOTE_TTL_HOURS` without use while leaving DB-owned blobs in place.

## List DB Refs

List all DB-tracked provider refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db
```

List DB refs for one provider:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider openai
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider anthropic
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-db --provider vertex_ai
```

Check one exact DB ref before deleting:

```powershell
docker exec ai-proxy-postgres psql -U postgres -d ai_proxy -c "SELECT id, provider, stored_file_id, provider_file_id, remote_file_status, uploaded_at, last_used_at FROM stored_file_provider_states WHERE provider_file_id = 'PUT_PROVIDER_FILE_ID_HERE';"
```

## List Remote Files

List OpenAI files:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-openai --limit 100
```

List Anthropic files:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-anthropic --limit 100
```

Filter remote lists by exact filename:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-openai --filename test.pdf
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files list-anthropic --filename test.pdf
```

## Exact File Id Cleanup

Delete one exact OpenAI file id and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider openai --file-id PUT_OPENAI_FILE_ID_HERE
```

Delete one exact Anthropic file id and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider anthropic --file-id PUT_ANTHROPIC_FILE_ID_HERE
```

Delete one exact Vertex GCS URI and clear matching DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider vertex_ai --file-id gs://PUT_BUCKET/PATH/TO/OBJECT
```

Delete one exact provider file id without changing DB refs:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider openai --file-id PUT_OPENAI_FILE_ID_HERE --skip-db-clear
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider anthropic --file-id PUT_ANTHROPIC_FILE_ID_HERE --skip-db-clear
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-file-id --provider vertex_ai --file-id gs://PUT_BUCKET/PATH/TO/OBJECT --skip-db-clear
```

Only use `--skip-db-clear` if you will fix `stored_file_provider_states` right after.

## Filename Cleanup

`filename` is only a human label. It is not a unique provider identity key. Browsers often hand pasted screenshots a generic name such as `image.png`.

Use filename cleanup only for unique test filenames:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider openai --filename test.pdf
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --provider anthropic --filename test.pdf
```

Delete matching filenames from both providers:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --filename test.pdf
```

Remote-only filename cleanup without DB changes:

```powershell
docker exec ai-proxy-api python -m app.maintenance.attachment_provider_files cleanup-filename --filename test.pdf --skip-db-clear
```

Do not aim filename cleanup at generic names such as `image.png` unless you really intend to wipe all matching provider files for that provider set.
