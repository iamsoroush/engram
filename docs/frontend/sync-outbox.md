# Frontend Sync Outbox

## Summary

The frontend saves captures to IndexedDB before any backend request. Backend v2 keeps this behavior and adds authenticated sync, backend ID mapping, patient-aware session/capture metadata, and richer states.

## Local Stores

Continue using:

- `pendingCaptures`: unsynced source blobs and metadata. These are safety copies and must not be evicted automatically.
- `cachedCaptures`: synced source blobs for fast preview. These are convenience copies and may be evicted.

## Authenticated Sync

Outbox processing requires:

- a logged-in user;
- an active tenant;
- a reachable backend;
- a pending capture with a source blob.

The frontend should pause sync while logged out. Pending captures remain visible as saved on device.

## Backend ID Mapping

Each pending capture should include:

- local capture ID;
- local session ID;
- `client_capture_id` sent to backend for idempotency;
- optional backend session ID once created;
- optional backend capture ID once uploaded;
- active tenant ID used for upload.

After upload succeeds, store backend IDs and remove the pending item. Keep an evictable cache copy if storage budget allows.

## Upload Flow

1. Save source blob to `pendingCaptures`.
2. Show `Saved on device`.
3. If authenticated, create or reuse backend session.
4. Upload capture with `client_capture_id`.
5. Show `Syncing`.
6. Backend stores MinIO object and Postgres metadata.
7. Backend returns stable IDs and state.
8. Remove pending safety copy and optionally cache synced blob.

If upload fails, keep the pending source and show `Failed/Retry`.

## States

Frontend-facing states:

- `Saved on device`
- `Syncing`
- `Failed/Retry`
- `Processing`
- `Unassigned`
- `Needs review`
- `Organized`
- `Verified` or `Reviewed`

Important distinction:

- `Organized` means backend/fake processing has created organized output.
- `Verified` means a doctor or assistant reviewed and accepted it.

## Patient Assignment

Capture creation does not require patient selection.

The frontend should support:

- unassigned sessions;
- assigning a session to a patient later;
- assigning or overriding a capture patient later;
- creating a patient during review;
- displaying assignment source when useful, such as staff or fake processing.

## Cache Policy

Keep the existing policy:

- Only synced cached captures may be evicted.
- Unsynced pending captures must never be automatically deleted.
- Oldest/least recently accessed cached captures are evicted first.
- If local cache is missing, preview falls back to backend file access.

Future work can add chunked uploads and compression, but v2 docs do not require them.
