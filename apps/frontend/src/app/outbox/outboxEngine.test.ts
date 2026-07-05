import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthSession, CaptureDraft, IdMapping, PendingCapture, PendingOperation } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, CaptureStatus } from "../../domain/types";
import { ApiError } from "../../services/api/client";
import { makeLocalCapture } from "../../features/capture/captureModel";
import { normalizePendingCapture } from "../../services/storage/captureStorage";
import { OK_STORAGE_STATUS } from "../../services/storage/storageStatus";
import { createOutboxEngine, shouldWarnBeforeUnload } from "./outboxEngine";
import type { ApiPort, OutboxEnv, SessionSink, StoragePort, SyncStatusSink } from "./types";

// Offline outbox characterization suite (frontend-refactor plan §4). Pins the current behavior of the
// serial-upload / operation-replay / 404-self-heal / optimistic-save engine against a FAKE in-memory
// storage adapter — the behavioral contract the Sync+Store extraction must preserve. jsdom-free: the
// engine takes injected ports, so no DOM/IndexedDB is needed. `URL.createObjectURL` (used by the
// optimistic preview) is the one browser global saveDraft reaches through captureModel — stub it.
(globalThis as unknown as { URL: { createObjectURL: () => string; revokeObjectURL: () => void } }).URL = {
  createObjectURL: () => "blob:fake",
  revokeObjectURL: () => undefined,
} as never;

// --- Fake in-memory storage adapter (faithful to captureStorage's sort/normalize semantics) ---
function makeFakeStorage() {
  const captures = new Map<string, PendingCapture>();
  const operations = new Map<string, PendingOperation>();
  const idMappings = new Map<string, IdMapping>();
  const exported: PendingCapture[][] = [];
  const port: StoragePort = {
    loadPendingCaptures: async () =>
      [...captures.values()].map(normalizePendingCapture).sort((a, b) => a.createdAt - b.createdAt),
    loadPendingCapture: async (id) => {
      const found = captures.get(id);
      return found ? normalizePendingCapture(found) : undefined;
    },
    savePendingCapture: async (capture) => {
      captures.set(capture.id, capture);
    },
    updatePendingCapture: async (id, update) => {
      const current = captures.get(id);
      if (current) captures.set(id, update(current));
    },
    removePendingCapture: async (id) => {
      captures.delete(id);
    },
    loadPendingOperations: async () => [...operations.values()].sort((a, b) => a.createdAt - b.createdAt),
    savePendingOperation: async (operation) => {
      operations.set(operation.id, operation);
    },
    updatePendingOperation: async (id, update) => {
      const current = operations.get(id);
      if (current) operations.set(id, update(current));
    },
    removePendingOperation: async (id) => {
      operations.delete(id);
    },
    loadIdMapping: async (id) => idMappings.get(id),
    bindPendingSession: async () => undefined,
    saveSyncedCaptureCache: async () => undefined,
    normalizePendingCapture,
    clearLocalCaptureData: async () => {
      captures.clear();
      operations.clear();
      idMappings.clear();
    },
    exportPendingCaptures: async (pending) => {
      exported.push(pending);
      return pending.length;
    },
  };
  return { port, captures, operations, idMappings, exported };
}

function makeSessionSink(sessions: CaptureSession[] = [], active: CaptureSession | null = null) {
  const state = { sessions, active, selected: "" };
  const sink: SessionSink = {
    getSessions: () => state.sessions,
    getActiveSession: () => state.active,
    setSessions: (update) => {
      state.sessions = update(state.sessions);
    },
    setActiveSession: (update) => {
      state.active = update(state.active);
    },
    setSelectedSessionId: (update) => {
      state.selected = update(state.selected);
    },
    upsertSession: (session, removeIds = []) => {
      state.sessions = [session, ...state.sessions.filter((s) => s.id !== session.id && !removeIds.includes(s.id))];
    },
    updateItemStatus: (itemId, status) => {
      const apply = (s: CaptureSession) => ({ ...s, items: s.items.map((i) => (i.id === itemId ? { ...i, status } : i)) });
      state.sessions = state.sessions.map(apply);
      if (state.active) state.active = apply(state.active);
    },
    applySessionUpdate: vi.fn(),
    selfHealStalePatient: vi.fn(async () => undefined),
    scheduleCaptureProcessingRefresh: vi.fn(),
    scheduleSessionProcessingRefresh: vi.fn(),
    scheduleMemoryRefresh: vi.fn(),
  };
  return { sink, state };
}

function makeStatusSink() {
  const record = {
    pendingCount: 0,
    pendingOperationCount: 0,
    syncing: [] as boolean[],
    online: [] as boolean[],
    backendReachable: [] as (boolean | null)[],
    syncError: [] as string[],
    toasts: [] as string[],
  };
  const sink: SyncStatusSink = {
    setPendingCount: (c) => {
      record.pendingCount = c;
    },
    setPendingOperationCount: (c) => {
      record.pendingOperationCount = c;
    },
    setSyncing: (s) => record.syncing.push(s),
    setOnline: (o) => record.online.push(o),
    setBackendReachable: (r) => record.backendReachable.push(r),
    setSyncError: (e) => record.syncError.push(e),
    setStorage: () => undefined,
    toast: (m) => record.toasts.push(m),
  };
  return { sink, record };
}

const authFixture: AuthSession = {
  accessToken: "a",
  refreshToken: "r",
  user: { id: "u1", email: "d@e.test", displayName: "Doc", persona: null },
  tenant: { id: "tenant-1", name: "Clinic", tier: "pro" },
  memberships: [{ tenantId: "tenant-1", role: "owner" }],
};

function makeEnv(overrides: Partial<OutboxEnv> = {}): OutboxEnv {
  let clock = 1_000;
  return {
    getAuth: () => authFixture,
    isOnline: () => true,
    now: () => (clock += 1),
    standardizeDraft: async (draft) => draft,
    flushOptimistic: (fn) => fn(),
    navigateActiveSession: vi.fn(),
    t: (key: string) => key,
    estimateStorage: async () => OK_STORAGE_STATUS,
    ...overrides,
  };
}

function makeBackendSession(id: string, itemId: string, status: CaptureStatus = "uploaded"): CaptureSession {
  const item: CaptureItem = { id: itemId, type: "note", title: "Note", detail: "", time: "now", sourceName: "n.txt", status };
  return {
    id,
    label: "Visit",
    time: "now",
    dateLabel: "Today",
    duration: "just now",
    summary: "",
    createdAt: "",
    updatedAt: "",
    status: "processing",
    items: [item],
  };
}

function uploadResult() {
  const session = makeBackendSession("backend-sess-1", "backend-cap-1");
  return { session, item: session.items[0] };
}

function makeApi(overrides: Partial<ApiPort> = {}): ApiPort {
  return {
    fetchSessions: async () => [],
    searchPatients: async () => [],
    uploadCapture: async () => uploadResult(),
    assignSessionPatient: async (sessionId) => makeBackendSession(sessionId, "backend-cap-1"),
    unassignSessionPatient: async (sessionId) => makeBackendSession(sessionId, "backend-cap-1"),
    updateSessionTitle: async (sessionId) => makeBackendSession(sessionId, "backend-cap-1"),
    saveSessionForProcessing: async (sessionId) => makeBackendSession(sessionId, "backend-cap-1"),
    createPatient: async () => ({ id: "patient-1", displayName: "Sara" }),
    storeBackendMappings: async () => undefined,
    ...overrides,
  };
}

const noteDraft = (): CaptureDraft => ({ kind: "note", detail: "hi", file: new Blob(["x"]), filename: "n.txt" });

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("outbox engine — capture upload", () => {
  it("saveDraft persists locally, paints the optimistic session, then uploads and clears the queue", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const navigate = vi.fn();
    const uploadCapture = vi.fn(makeApi().uploadCapture);
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ uploadCapture }),
      session: session.sink,
      status: status.sink,
      env: makeEnv({ navigateActiveSession: navigate }),
    });

    await engine.saveDraft(noteDraft());
    // wait a microtask for the fire-and-forget processOutbox() saveDraft kicks off
    await new Promise((r) => setTimeout(r, 0));

    // Optimistic paint happened synchronously (flushOptimistic): a session became active + visible + nav.
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(session.state.sessions.length).toBeGreaterThan(0);
    // Upload ran and the pending queue drained to zero.
    expect(uploadCapture).toHaveBeenCalledTimes(1);
    expect(storage.captures.size).toBe(0);
    expect(status.record.toasts).toContain("capture.toastCaptureTransferred");
    expect(status.record.backendReachable[status.record.backendReachable.length - 1]).toBe(true);
  });

  it("keeps the capture queued and marks it unreachable when the upload fails, then drains on the next run", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    let failNext = true;
    const uploadCapture = vi.fn(async () => {
      if (failNext) throw new Error("network down");
      return { session: makeBackendSession("backend-sess-1", "backend-cap-1"), item: makeBackendSession("backend-sess-1", "backend-cap-1").items[0] };
    });
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ uploadCapture }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });

    // First save fails to upload → capture stays queued, retryCount bumps, backend marked unreachable.
    await engine.saveDraft(noteDraft());
    await new Promise((r) => setTimeout(r, 0));
    expect(storage.captures.size).toBe(1);
    expect([...storage.captures.values()][0].retryCount).toBe(1);
    expect(status.record.backendReachable).toContain(false);
    expect(status.record.syncError).toContain("capture.syncUploadFailed");

    // Reconnect: a later processOutbox uploads the still-queued capture and clears it (offline→online resume).
    failNext = false;
    await engine.processOutbox();
    expect(uploadCapture).toHaveBeenCalledTimes(2);
    expect(storage.captures.size).toBe(0);
    expect(status.record.backendReachable[status.record.backendReachable.length - 1]).toBe(true);
  });

  it("presents a 403 upload as an auth problem, not connectivity — and still heals after re-login", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    let failNext = true;
    const forbidden = new ApiError("Capture upload failed", 403);
    const uploadCapture = vi.fn(async () => {
      if (failNext) throw forbidden;
      return { session: makeBackendSession("backend-sess-1", "backend-cap-1"), item: makeBackendSession("backend-sess-1", "backend-cap-1").items[0] };
    });
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ uploadCapture }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });

    // 403: capture stays queued locally, but the user sees the auth message and the backend is
    // NOT declared unreachable (it answered — it refused).
    await engine.saveDraft(noteDraft());
    await new Promise((r) => setTimeout(r, 0));
    expect(storage.captures.size).toBe(1);
    expect(status.record.syncError).toContain("capture.syncAuthNeeded");
    expect(status.record.backendReachable).not.toContain(false);

    // After a fresh sign-in the same queued capture syncs untouched.
    failNext = false;
    await engine.processOutbox();
    expect(storage.captures.size).toBe(0);
  });

  it("skips a capture made under a different tenant instead of stranding the run", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const uploadCapture = vi.fn(makeApi().uploadCapture);
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ uploadCapture }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });
    // A pre-existing pending capture belonging to another tenant.
    const foreign = { ...(await seedPending(storage)), tenantId: "other-tenant" };
    storage.captures.set(foreign.id, foreign);

    await engine.processOutbox();
    expect(uploadCapture).not.toHaveBeenCalled();
    expect(storage.captures.has(foreign.id)).toBe(true); // still queued, not lost
  });

  it("does not run concurrently — the overlap guard makes a re-entrant call a no-op", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const gate: { resolve: (() => void) | null } = { resolve: null };
    const uploadCapture = vi.fn(
      () =>
        new Promise<{ session: CaptureSession; item: CaptureItem }>((resolve) => {
          gate.resolve = () =>
            resolve({ session: makeBackendSession("s", "c"), item: makeBackendSession("s", "c").items[0] });
        }),
    );
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ uploadCapture }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });
    await seedPending(storage);

    const first = engine.processOutbox();
    const second = engine.processOutbox(); // re-entrant while first is mid-upload → guarded no-op
    await second; // resolves immediately (guard returned early)
    await new Promise((r) => setTimeout(r, 0)); // let `first` advance to the hanging upload
    expect(uploadCapture).toHaveBeenCalledTimes(1); // only `first` reached the upload; `second` was a no-op
    gate.resolve?.();
    await first;
  });
});

describe("outbox engine — dependent operations", () => {
  it("queues then replays a session-title operation and removes it once applied", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const updateSessionTitle = vi.fn(makeApi().updateSessionTitle);
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({ updateSessionTitle }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });

    await engine.queueOperation({
      id: "tenant-1:sessionTitle:backend-sess-1",
      type: "sessionTitle",
      backendSessionId: "backend-sess-1",
      tenantId: "tenant-1",
      payload: { title: "Renamed" },
    });
    expect(storage.operations.size).toBe(1);

    await engine.processOutbox();
    expect(updateSessionTitle).toHaveBeenCalledWith("backend-sess-1", "Renamed");
    expect(session.sink.applySessionUpdate).toHaveBeenCalled();
    expect(storage.operations.size).toBe(0);
  });

  it("drops a 404 operation and self-heals the stale patient instead of looping forever", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const notFound = new ApiError("gone", 404);
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({
        assignSessionPatient: async () => {
          throw notFound;
        },
      }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });

    await engine.queueOperation({
      id: "tenant-1:patientAssignment:backend-sess-1",
      type: "patientAssignment",
      backendSessionId: "backend-sess-1",
      backendPatientId: "patient-dead",
      tenantId: "tenant-1",
      payload: { patientId: "patient-dead", displayName: "Ghost" },
    });

    await engine.processOutbox();
    expect(session.sink.selfHealStalePatient).toHaveBeenCalledWith("backend-sess-1", "patient-dead");
    expect(storage.operations.size).toBe(0);
  });

  it("marks an operation failed (not dropped) on a transient error so it retries", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const engine = createOutboxEngine({
      storage: storage.port,
      api: makeApi({
        updateSessionTitle: async () => {
          throw new Error("500 transient");
        },
      }),
      session: session.sink,
      status: status.sink,
      env: makeEnv(),
    });
    await engine.queueOperation({
      id: "tenant-1:sessionTitle:backend-sess-1",
      type: "sessionTitle",
      backendSessionId: "backend-sess-1",
      tenantId: "tenant-1",
      payload: { title: "Renamed" },
    });

    await engine.processOutbox();
    expect(storage.operations.size).toBe(1); // still queued for retry
    expect([...storage.operations.values()][0].status).toBe("failed");
    expect([...storage.operations.values()][0].retryCount).toBe(1);
    expect(status.record.backendReachable).toContain(false);
  });
});

describe("outbox engine — export + unload semantics", () => {
  it("exports queued captures and toasts the count", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const engine = createOutboxEngine({ storage: storage.port, api: makeApi(), session: session.sink, status: status.sink, env: makeEnv() });
    await seedPending(storage);

    await engine.exportQueuedCaptures();
    expect(storage.exported).toHaveLength(1);
    expect(status.record.toasts.some((m) => m.includes("Exported") || m === "capture.toastExportedQueued")).toBe(true);
  });

  it("toasts nothing-to-export when the queue is empty", async () => {
    const storage = makeFakeStorage();
    const session = makeSessionSink();
    const status = makeStatusSink();
    const engine = createOutboxEngine({ storage: storage.port, api: makeApi(), session: session.sink, status: status.sink, env: makeEnv() });
    await engine.exportQueuedCaptures();
    expect(storage.exported).toHaveLength(0);
    expect(status.record.toasts).toContain("capture.toastNoQueuedExport");
  });

  it("shouldWarnBeforeUnload is true iff device-only clinical material is unsynced", () => {
    expect(shouldWarnBeforeUnload(0, 0)).toBe(false);
    expect(shouldWarnBeforeUnload(1, 0)).toBe(true);
    expect(shouldWarnBeforeUnload(0, 1)).toBe(true);
  });
});

// Seed one queued capture directly (bypassing saveDraft's auto-processOutbox), returning the record.
async function seedPending(storage: ReturnType<typeof makeFakeStorage>) {
  const pending = makeLocalCapture(noteDraft(), null, false, "tenant-1");
  await storage.port.savePendingCapture(pending);
  return pending;
}
