# Sync + Store extraction — co-design (frontend-refactor increments 4–5)

**Status (process doc):** the design record for the *deferred pair* of the frontend-refactor plan
(`frontend-refactor-plan.md` §4, increments 4–5). Increments 1–3 (Api/Auth/Capabilities seams) are
merged. This doc is deleted when increments 4–8 land and their durable essence is folded into
`docs/frontend/overview.md` + `docs/architecture.md`. It may describe unbuilt state; system-state
docs must not link into it.

## Why 4 and 5 are one design, two commits

The plan flagged increment 4 (`SyncProvider`) as the riskiest single extraction and noted it is **not
safely separable** from increment 5 (`SessionStore`): `processOutbox` and `syncPendingOperation`
*write* session state (`upsertSession`, `setActiveSession`, `updateItemStatus`, `applySessionUpdate`,
`selfHealStalePatient`) and *read* the latest session list (was `sessionsRef`/`activeSessionRef`);
conversely the session actions (`saveSession`, `assignPatientToSession`, `renameSession`) call
`queueOperation` + `processOutbox`. The coupling is genuinely bidirectional.

So we **design both together** and **land in two reviewable commits** joined by a stable **port seam**:

- The outbox engine is a framework-agnostic module (`app/outbox/outboxEngine.ts`) that takes injected
  ports and touches no React. This is what makes it **unit-testable against a fake storage adapter**
  (vitest runs in a Node environment — there is no DOM/IndexedDB, so the engine cannot import the
  concrete IndexedDB storage layer directly; it receives a `StoragePort`).
- `SyncProvider` is the thin React shell that constructs the engine with the real storage/api/session
  ports + React state setters, owns the retry interval / online / beforeunload / storage-guard, and
  exposes `useSync()`.

The **SessionSink** port (below) is the seam. In increment 4 `AppInner` implements it from its own
`useState`+refs and hands it to `SyncProvider`. In increment 5 the identical port is implemented by
`SessionStore` instead — **`SyncProvider` and the engine do not change**; only who provides the port
moves. That is the "co-design, separate landing" contract.

## Ports

```
StoragePort   (app/outbox/*, wraps services/storage/captureStorage + exportCaptures)
  loadPendingCaptures / loadPendingCapture / savePendingCapture / updatePendingCapture /
  removePendingCapture / loadPendingOperations / savePendingOperation / updatePendingOperation /
  removePendingOperation / loadIdMapping / bindPendingSession / saveSyncedCaptureCache /
  normalizePendingCapture / clearLocalCaptureData / exportPendingCaptures

ApiPort       (services/api/client fns pre-bound to apiFetch)
  fetchSessions / searchPatients / uploadCapture / assignSessionPatient / unassignSessionPatient /
  updateSessionTitle / saveSessionForProcessing / createPatient / storeBackendMappings

SessionSink   (the increment-4→5 seam — session read/write the engine performs)
  getSessions() / getActiveSession()
  setSessions(updater) / setActiveSession(updater) / setSelectedSessionId(updater)
  upsertSession(session, removeIds?) / updateItemStatus(id, status) / applySessionUpdate(id, updated)
  rebuildLocalPendingSessions() / selfHealStalePatient(sessionId?, patientId?)
  notifyAiPatientAction(session)
  scheduleCaptureProcessingRefresh(id) / scheduleSessionProcessingRefresh(id) / scheduleMemoryRefresh()

SyncStatusSink (sync UI state the engine drives — owned by SyncProvider)
  setPendingCount / setPendingOperationCount / setSyncing / setOnline / setBackendReachable /
  setSyncError / setStorage / toast(msg)

Env
  getAuth() -> AuthSession | null   (was authRef.current — never a stale closure)
  isOnline() -> boolean             (navigator.onLine, a UI hint only; see processOutbox comment)
  now() -> number
  navigateActiveSession()           (saveDraft/hydrate land on the capture screen; a nav effect,
                                     replaced by the router seam in increment 7)
  flushOptimistic(fn)               (react-dom flushSync wrapper for saveDraft's §6 sync paint)
```

The load-bearing async-correctness refs (§6 of the plan) are preserved by construction: the engine
reads current auth/session state through `getAuth()` / `SessionSink.getSessions()` getters at call
time (never a captured closure), and keeps its own `processing` overlap guard + `refreshPromise`
single-flight internally. `flushSync` in `saveDraft` is preserved via `Env.flushOptimistic`.

## Engine surface (what SyncProvider exposes as `useSync()`)

`syncHealth`, `storage`, `storageGuardOpen`/`setStorageGuardOpen`, `saveDraft(draft, intoNew)`,
`queueOperation(op)`, `processOutbox()`, `hydrateFromStorage()`, `refreshPendingCount()`,
`exportQueuedCaptures()`, `clearLocal()`, and the offline-return-receipt count. Session actions stay
out of Sync — they live in `SessionStore` (increment 5) and call `useSync().queueOperation` /
`processOutbox`.

## Commit split

- **Increment 4 (Sync):** add `app/outbox/` (types + `outboxEngine.ts` + `storagePort.ts`) and
  `app/providers/SyncProvider.tsx`; move all outbox/online/storage-guard state + effects out of
  `AppInner` behind `useSync()`. `AppInner` still owns `sessions`/`activeSession` `useState` and
  implements `SessionSink` from them. Add `outboxEngine.test.ts` (fake adapter). Full gate.
- **Increment 5 (Store):** add `app/providers/SessionStoreProvider.tsx` exposing
  `useSessions()`/`useActiveSession()`/`useSessionActions()`; move `sessions`/`activeSession`/
  `selectedSessionId` + the session/patient actions out of `AppInner`. Re-point the `SessionSink`
  Sync consumes at the store. Add reducer unit tests. Full gate.

Render-cadence (plan §2 fork): keep `useState` + relocated refs (behavior-preserving). Apply the
split-context pattern (stable actions context separate from volatile state) in increment 5 where it
is free; do **not** introduce `useSyncExternalStore` unless a measured re-render problem forces it.
