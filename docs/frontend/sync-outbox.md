# Frontend Sync Outbox

## Summary

The frontend saves captures to IndexedDB before any backend request. This doc owns the technical outbox, ID mapping, and cache policy. User-facing copy and state labels are owned by [UX states](../ux/states.md).

## Local Stores

Continue using:

- `pendingCaptures`: unsynced source blobs and metadata. These are safety copies and must not be evicted automatically.
- `cachedCaptures`: synced source blobs for fast preview. These are convenience copies and may be evicted.
- `pendingOperations`: lightweight offline work that depends on backend IDs, such as session title changes, patient assignment/create intent, and structured-report generation requests.

## Authenticated Sync

Outbox processing requires:

- a logged-in user;
- an active tenant;
- a reachable backend;
- a pending capture with a source blob, or a pending operation that can now resolve its backend IDs.

The frontend should pause sync while logged out. Pending captures remain visible as saved on device.

## Backend ID Mapping

Each pending capture should include:

- local capture ID;
- local session ID;
- `client_capture_id` sent to backend for idempotency;
- optional backend session ID once created;
- optional backend capture ID once uploaded;
- active tenant ID used for upload.

After upload succeeds, store backend IDs and remove the pending item. Keep an evictable cache copy if storage budget allows. Dependent pending operations replay after local session IDs are mapped to backend session IDs.

## Upload Flow

1. Save source blob to `pendingCaptures`.
2. Surface local safety using the current UX state language.
3. If authenticated, create or reuse backend session.
4. Upload capture with `client_capture_id`.
5. Backend stores MinIO object and Postgres metadata.
6. Backend returns stable IDs and state.
7. Store local/backend ID mappings.
8. Remove pending safety copy and optionally cache synced blob.
9. Replay dependent pending operations, such as assignment or report generation.

If upload fails, keep the pending source. Do not require the user to operate sync in normal UI; see [UX states](../ux/states.md#offline-and-ai-unavailable-behavior).

## Pending Operations

The app queues small operations when the backend is unavailable or when work depends on a local-only session:

- session title updates;
- patient assignment/create intent;
- structured report generation requests.

Operations are replayed after captures because they often need the backend session ID created by upload. The UI keeps the local draft visible while replay is pending. Duplicate retry risk is reduced with stable operation IDs and idempotency-friendly backend behavior.

## States

Internal outbox state may track pending, uploading, uploaded, replaying operations, or failed attempts. These names are implementation detail.

Important distinction:

- `Organized` means backend/AI processing has created organized output.
- `Verified` means a doctor or assistant reviewed and accepted it.

For visible labels, use [UX states](../ux/states.md).

## Patient Assignment

Capture creation does not require patient selection.

The frontend should support:

- unassigned sessions;
- assigning a session to a patient later;
- assigning or overriding a capture patient later;
- creating a patient during review;
- displaying assignment source when useful, such as staff or AI processing.

## Cache Policy

Keep the existing policy:

- Only synced cached captures may be evicted.
- Unsynced pending captures must never be automatically deleted.
- Oldest/least recently accessed cached captures are evicted first.
- If local cache is missing, preview falls back to backend file access.

Future work can add chunked uploads and compression, but v2 docs do not require them.
