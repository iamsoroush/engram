import type {
  IdMapping,
  PatientAssignmentDraft,
  PatientSummary,
  PendingCapture,
  PendingOperation,
  AuthSession,
  CaptureDraft,
} from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, CaptureStatus } from "../../domain/types";
import type { Translator } from "../../shared/i18n";
import type { StorageStatus } from "../../services/storage/storageStatus";

// Ports for the framework-agnostic outbox engine (frontend-refactor plan §4, increment 4). The engine
// touches no React and no browser globals directly: it receives storage, api, session, status, and env
// ports so it can be unit-tested against a fake in-memory storage adapter (vitest runs in Node — there
// is no DOM/IndexedDB). See docs/frontend/sync-outbox.md for the seam contract.

/** Durable local outbox persistence (IndexedDB in production; in-memory fake in tests). */
export type StoragePort = {
  loadPendingCaptures: () => Promise<PendingCapture[]>;
  loadPendingCapture: (id: string) => Promise<PendingCapture | undefined>;
  savePendingCapture: (capture: PendingCapture) => Promise<unknown>;
  updatePendingCapture: (id: string, update: (capture: PendingCapture) => PendingCapture) => Promise<void>;
  removePendingCapture: (id: string) => Promise<unknown>;
  loadPendingOperations: () => Promise<PendingOperation[]>;
  savePendingOperation: (operation: PendingOperation) => Promise<unknown>;
  updatePendingOperation: (id: string, update: (operation: PendingOperation) => PendingOperation) => Promise<void>;
  removePendingOperation: (id: string) => Promise<unknown>;
  loadIdMapping: (id: string) => Promise<IdMapping | undefined>;
  bindPendingSession: (localSessionId: string, sessionId: string) => Promise<void>;
  saveSyncedCaptureCache: (item: CaptureItem, blob: Blob) => Promise<void>;
  normalizePendingCapture: (capture: PendingCapture) => PendingCapture;
  clearLocalCaptureData: () => Promise<void>;
  exportPendingCaptures: (pending: PendingCapture[], dateStamp: string) => Promise<number>;
};

/** Backend client calls, pre-bound to the auth-aware `apiFetch` (real fetch in production; fakes in tests). */
export type ApiPort = {
  fetchSessions: (options?: { clinicianId?: string }) => Promise<CaptureSession[]>;
  searchPatients: (query: string) => Promise<PatientSummary[]>;
  uploadCapture: (
    clientCaptureId: string,
    draft: CaptureDraft,
    sessionId?: string,
    intoNew?: boolean,
  ) => Promise<{ session: CaptureSession; item: CaptureItem }>;
  assignSessionPatient: (
    sessionId: string,
    patientId: string,
    idempotencyKey?: string,
    basisCaptureId?: string,
  ) => Promise<CaptureSession>;
  unassignSessionPatient: (sessionId: string, idempotencyKey?: string) => Promise<CaptureSession>;
  updateSessionTitle: (sessionId: string, title: string) => Promise<CaptureSession>;
  saveSessionForProcessing: (sessionId: string) => Promise<CaptureSession>;
  createPatient: (draft: PatientAssignmentDraft, idempotencyKey?: string) => Promise<PatientSummary>;
  storeBackendMappings: (
    capture: PendingCapture,
    result: { session: CaptureSession; item: CaptureItem },
    tenantId: string,
  ) => Promise<void>;
};

/**
 * Session read/write the engine performs. THIS IS THE INCREMENT-4→5 SEAM: in increment 4 `AppInner`
 * implements it from its own `useState`+refs; in increment 5 `SessionStore` implements the identical
 * shape — the engine and SyncProvider never change, only who provides this port moves.
 */
export type SessionSink = {
  /** Latest session list (was `sessionsRef.current` — read at call time, never a stale closure). */
  getSessions: () => CaptureSession[];
  /** Latest active session (was `activeSessionRef.current`). */
  getActiveSession: () => CaptureSession | null;
  setSessions: (update: (current: CaptureSession[]) => CaptureSession[]) => void;
  setActiveSession: (update: (current: CaptureSession | null) => CaptureSession | null) => void;
  setSelectedSessionId: (update: (current: string) => string) => void;
  upsertSession: (session: CaptureSession, removeIds?: string[]) => void;
  updateItemStatus: (itemId: string, status: CaptureStatus) => void;
  applySessionUpdate: (sessionId: string, updated: CaptureSession) => void;
  /** Drop a queued assignment to a vanished patient and clear its stale reference (404 self-heal). */
  selfHealStalePatient: (sessionId: string | undefined, deadPatientId?: string) => Promise<void>;
  scheduleCaptureProcessingRefresh: (sessionId: string) => void;
  scheduleSessionProcessingRefresh: (sessionId: string) => void;
  scheduleMemoryRefresh: () => void;
};

/** Sync UI state the engine drives (owned by SyncProvider in production; spies in tests). */
export type SyncStatusSink = {
  setPendingCount: (count: number) => void;
  setPendingOperationCount: (count: number) => void;
  setSyncing: (syncing: boolean) => void;
  setOnline: (online: boolean) => void;
  setBackendReachable: (reachable: boolean | null) => void;
  setSyncError: (message: string) => void;
  setStorage: (status: StorageStatus) => void;
  toast: (message: string) => void;
};

/** Environment/effect ports (browser globals + navigation + optimistic paint), injectable for tests. */
export type OutboxEnv = {
  /** Always-current auth (was `authRef.current`). */
  getAuth: () => AuthSession | null;
  /** `navigator.onLine` — a UI hint only; processOutbox still attempts the upload regardless. */
  isOnline: () => boolean;
  now: () => number;
  /** Audio transcode / draft standardization (a no-op passthrough in Node tests). */
  standardizeDraft: (draft: CaptureDraft) => Promise<CaptureDraft>;
  /** `react-dom` flushSync wrapper so saveDraft's optimistic write paints before the async upload (§6). */
  flushOptimistic: (fn: () => void) => void;
  /** Land on the capture screen (replaced by the router seam in increment 7). */
  navigateActiveSession: () => void;
  /** Translator bound to the live app language, for chrome toasts. */
  t: Translator;
  /** Current durable-storage status (defaults to OK in Node). */
  estimateStorage: () => Promise<StorageStatus>;
};

export type OutboxDeps = {
  storage: StoragePort;
  api: ApiPort;
  session: SessionSink;
  status: SyncStatusSink;
  env: OutboxEnv;
};
