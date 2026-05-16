# Frontend v1 Current Prototype

## Stack

- Vite
- React
- TypeScript
- Plain CSS with shadcn/Tailwind-inspired component conventions

The active prototype entrypoint is:

```text
apps/frontend/src/main.tsx
apps/frontend/src/prototype/App.tsx
```

## UX Principles

- The default destination is `Capture`.
- Empty capture shows only three large actions: `Record audio`, `Take photo`, `Write note`.
- The first successful capture creates an active session automatically.
- New captures go into the current session by default.
- The doctor can start a `New session` quickly.
- Each capture flow includes a secondary action to save into a new session.
- Capture must remain available while syncing, processing, matching, or organizing happens in the background.

## Local-First Capture

The frontend uses IndexedDB before any backend request. This is intentional.

Stores:

- `pendingCaptures`: unsynced source blobs and metadata.
- `cachedCaptures`: synced source blobs for fast local preview.

State meanings:

- `Saved on device`: the source blob has been written to IndexedDB.
- `Syncing`: the outbox is uploading to backend.
- `Failed/Retry`: upload failed, but the source blob remains in IndexedDB.
- `Needs review`: backend has received the capture and it is ready for organization.
- `Organized`: in the current prototype, the session has been marked reviewed/organized.

Backend v2 separates generated organization from human verification. See [sync outbox](sync-outbox.md) and [backend v2 design](../backend/v2-design.md) for the new `organized` versus `verified` semantics.

## Outbox and Retry

The outbox retries when:

- the user taps `Retry now`;
- the browser fires the `online` event;
- the app hydrates with pending captures.

While unsynced captures exist, the UI shows a warning banner and registers a `beforeunload` warning. This warning matters because closing the browser, clearing site data, or browser storage eviction could endanger unsynced clinical material.

## Cache Policy

Synced captures are kept in `cachedCaptures` for faster previews. This cache is capped at `50 MB`.

Eviction policy:

- Only synced cached captures may be evicted.
- Unsynced pending captures must never be automatically deleted.
- Oldest/least recently accessed cached captures are evicted first.
- If local cache is missing, preview falls back to the backend source URL.

Future work should add:

- visible storage meter;
- warning when pending unsynced data grows too large;
- per-file limits for audio/photo;
- client-side image compression/resizing;
- chunked upload for long audio or large media.

## Mobile/LAN Testing

Run Vite on all interfaces:

```sh
cd apps/frontend
npm run dev -- --host 0.0.0.0
```

Use the `Network` URL printed by Vite on a phone connected to the same Wi-Fi.

Important: if `VITE_API_URL` points to `localhost`, the frontend falls back to `/api/v1` when opened by LAN IP. This prevents the phone from trying to call its own `localhost`.

## Browser Media Notes

Photo capture uses:

```text
<input type="file" accept="image/*" capture="environment">
```

Audio capture uses `MediaRecorder` when available and an audio file input fallback. Phone browsers commonly require HTTPS for microphone access, so local LAN HTTP testing may need the fallback.

## Development Commands

```sh
cd apps/frontend
npm install
npm run dev
npm run build
```
