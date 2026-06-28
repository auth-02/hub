# Migrate file uploads from local disk to object storage

## Context
User-uploaded files (avatars, attachments, exports) are currently written to the
app server's local disk under `/var/app/uploads` and served by the app process.
This blocks horizontal scaling (each server has its own disk), risks data loss on
instance replacement, and couples file serving to the app's request loop. The goal
is to move uploads to an S3-compatible object store, serve them via presigned URLs,
and keep a backward-compatible read path during the transition. Design-first task:
plan and decisions are agreed before any code lands.

### Decisions
1. **S3-compatible store via the standard SDK** — no provider-specific lock-in;
   endpoint + bucket are configuration — captured 2026-06-01.
2. **Presigned URLs for reads/writes** — the app never proxies file bytes; clients
   upload/download directly against the store — captured 2026-06-01.
3. **Dual-read during migration** — read path checks the object store first, falls
   back to local disk for not-yet-migrated files; new writes go only to the store —
   captured 2026-06-01.
4. **Backfill is a separate, resumable job** — not part of the request path; can run
   in batches and be re-run safely — captured 2026-06-02.
5. **Keys are content-addressed** (`sha256/<hash>`) — dedupes identical uploads and
   avoids guessable paths — captured 2026-06-02.

## Exploration Results
_(populate after grep / read / probe — `file:line` cross-links for every claim)_

### Current write path
- `services/upload.py:88` — `save_upload()` writes to `UPLOAD_DIR` and stores the
  relative path in `files.path`.
- Called from 3 places: avatar update, attachment create, export generation.

### Current read path
- `routes/files.py:42` — streams the file through the app (`send_file`). This is the
  coupling to remove.

### Schema
- `files` table: `id, owner_id, path, content_type, size, created_at`. Add
  `storage` (`local` | `object`) and `key` columns; keep `path` for legacy rows.

### Out of scope
- CDN in front of the bucket (later optimization).
- Re-encoding or virus-scanning uploads.

## Stack
_(layers; implement bottom-up — see the `stacked` skill)_

```
uploads/storage-adapter      ← implement first (put/get/presign behind an interface)
      ↑
uploads/dual-read-path       (read object store, fall back to local disk)
      ↑
uploads/write-to-object      (new writes go to the store; record storage+key)
      ↑
uploads/backfill-job         ← implement last (resumable batch migration of old files)
```

| Layer | What it does | Depends on | Reviewable question | Status |
|-------|-------------|------------|---------------------|--------|
| `uploads/storage-adapter` | `ObjectStore` interface + S3 impl: `put`, `get`, `presign_get/put` | — | Do put/get round-trip a file against a local MinIO bucket? | open |
| `uploads/dual-read-path` | Read checks object store by `key`, falls back to local `path` | storage-adapter | Do legacy local files still serve unchanged? | open |
| `uploads/write-to-object` | New uploads write to the store, set `storage='object'`, return presigned URL | dual-read-path | Are app servers no longer touching local disk on upload? | open |
| `uploads/backfill-job` | Resumable batch job copying local files to the store and flipping their rows | write-to-object | Can the job be killed and re-run without duplicating or skipping? | open |

## Plan
### uploads/storage-adapter
- [ ] **Step 1 — `ObjectStore` interface + S3 implementation** `services/storage.py`
  - `put(key, bytes, content_type)`, `get(key)`, `presign_get(key, ttl)`, `presign_put(key, ttl)`
  - Endpoint/bucket/credentials from config; works against local MinIO in tests

### uploads/dual-read-path
- [ ] **Step 2 — Route reads through the adapter with fallback** `routes/files.py`
  - If `storage='object'`, redirect to a presigned GET; else serve legacy local file

### uploads/write-to-object
- [ ] **Step 3 — New writes go to the store** `services/upload.py`
  - Content-address the key (`sha256/<hash>`), persist `storage='object'` + `key`

### uploads/backfill-job
- [ ] **Step 4 — Resumable backfill** `jobs/backfill_uploads.py`
  - Page over `files WHERE storage='local'`, copy, flip row; checkpoint progress

## Open questions
1. Presigned URL TTL for downloads? → 15 min default; configurable per file type.
2. Keep local files after backfill, or delete? → Keep for one release as a safety net,
   delete in a follow-up once object reads are confirmed in production.

## Confirmed findings
- ⚠️ The export feature writes large files synchronously in the request — moving to
  presigned PUT lets the client upload directly and removes a timeout risk.
- Read path is the only place that streams bytes through the app (`routes/files.py:42`).

## Testing plan
- Adapter round-trip against local MinIO (put → get → presign → fetch).
- Dual-read: a legacy `local` row and a new `object` row both resolve correctly.
- Backfill idempotency: run, kill mid-batch, re-run → no dupes, no skips.
- Regression: avatar upload + attachment download work end to end.

## Rollout plan
- Ship behind `UPLOADS_BACKEND=object` flag (default `local`); enable in staging first.
- Backfill runs after the flag is on in production; monitor object-store error rate.
- Rollback = flip the flag; dual-read keeps legacy files reachable.

## Review
_(fill at end: files changed with one-line summaries, how to cut over, follow-ups)_
