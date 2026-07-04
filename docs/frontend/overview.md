# Frontend v1 Current App

## Stack

- Vite
- React
- TypeScript
- Plain CSS with shadcn/Tailwind-inspired component conventions

The active app entrypoint is:

```text
apps/frontend/src/main.tsx
apps/frontend/src/app/App.tsx
```

## Source Layout

- `src/app`: root orchestration, hash navigation, and session state helpers. `App.tsx` is a thin
  composition root that mounts the shared-infrastructure provider seams before the app body:
  `src/app/providers` holds `ApiProvider` (memoized auth-aware `apiFetch` via `useApi()`),
  `AuthProvider` (the auth session + lifecycle via `useAuth()`), `CapabilitiesProvider`
  (tier/role affordances via `useCapabilities()`), `ToastProvider` (the transient toast via
  `useToast()`), and `SyncProvider` (the offline-first outbox engine via `useSync()`). Cross-cutting
  deps are consumed through these hooks rather than threaded as props.
- `src/app/outbox`: the framework-agnostic outbox engine (`createOutboxEngine`) that `SyncProvider`
  drives — serial capture upload, dependent-operation replay, retry, and the optimistic `saveDraft`.
  It touches no React/IndexedDB directly (injected ports), so it is unit-tested against a fake storage
  adapter (`outboxEngine.test.ts`). The durable stores + upload flow are unchanged; see
  [sync outbox](sync-outbox.md).
- `src/domain`: frontend session/capture/auth types and UX status mapping.
- `src/features/auth`: login and patient-preview gates.
- `src/features/capture`: capture dialogs, active session workspace, capture metadata, audio helpers, and local capture modeling.
- `src/features/memory`: Clinical Memory and Search screens.
- `src/features/shell`: authenticated app shell and sync safety banner.
- `src/services/api`: backend client and response normalizers.
- `src/services/storage`: IndexedDB/localStorage persistence boundaries.
- `src/shared`: small UI primitives and environment config.

## UX Principles

- The default destination is `Capture`.
- Empty capture shows only three large actions: `Record audio`, `Take photo`, `Write note`.
- The first successful capture creates an active session automatically.
- New captures go into the current session by default.
- The doctor can start a `New session` quickly.
- Each capture flow includes a secondary action to save into a new session.
- Capture must remain available while syncing, processing, matching, or organizing happens in the background.
- Clinical Memory follows the UX docs: Today is session-first, Patients is patient-memory-first, and Needs input is decision-first with focused resolver actions.

## Local-First Capture

The frontend uses IndexedDB before any backend request. This is intentional.

Stores:

- `pendingCaptures`: unsynced source blobs and metadata.
- `cachedCaptures`: synced source blobs for fast local preview.

Visible state labels are owned by [UX states](../ux/states.md). Technical outbox semantics live in [sync outbox](sync-outbox.md).

## Outbox Recovery

The outbox should resume when:

- the browser fires the `online` event;
- the app hydrates with pending captures.

While unsynced captures exist, the UI reassures the user that captures are saved on this device. A `beforeunload` warning is acceptable when leaving could endanger device-only clinical material.

## Cache Policy

Synced captures are kept in `cachedCaptures` for faster previews. This cache is capped at `50 MB`.

Eviction policy:

- Only synced cached captures may be evicted.
- Unsynced pending captures must never be automatically deleted.
- Oldest/least recently accessed cached captures are evicted first.
- If local cache is missing, preview falls back to the backend source URL.

Known gaps:

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
