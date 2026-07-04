import React from "react";
import { flushSync } from "react-dom";
import type { CaptureDraft, PendingCapture, PendingOperation, SyncHealth } from "../../domain/appTypes";
import { standardizeCaptureDraft } from "../../features/capture/audio";
import {
  assignSessionPatient,
  createPatient,
  fetchSessions,
  saveSessionForProcessing,
  searchPatients,
  storeBackendMappings,
  unassignSessionPatient,
  updateSessionTitle,
  uploadCapture,
} from "../../services/api/client";
import { estimateStorageStatus, OK_STORAGE_STATUS, type StorageStatus } from "../../services/storage/storageStatus";
import { createOutboxEngine, type OutboxEngine, shouldWarnBeforeUnload } from "../outbox/outboxEngine";
import { indexedDbStoragePort } from "../outbox/storagePort";
import type { ApiPort, SessionSink } from "../outbox/types";
import { useApi } from "./ApiProvider";
import { useAuth } from "./AuthProvider";

// Seam B (frontend-refactor plan §4, increment 4). The offline-first outbox engine lifted out of the
// App god-component into shared infrastructure. SyncProvider owns the sync UI state (online / backend
// reachable / pending counts / syncing / storage) and the recovery effects (retry interval, online
// resume, beforeunload guard, offline-return receipt), and drives the framework-agnostic engine in
// `../outbox`. Consumers read `useSync()`; session state still lives in App (increment 4) and is
// supplied through a **bridge** the app body registers upward — the same inversion ApiProvider uses
// for its auth bridge. In increment 5 the identical bridge is registered by SessionStore instead; the
// engine and this provider do not change. See docs/work/frontend-sync-store-codesign.md.

/** What the app body (or, in increment 5, SessionStore) supplies upward so the engine can read/write
 *  session state, raise toasts, and land on the capture screen. Its methods may close over fresh state
 *  every render; the engine reads them through a ref, so it never captures a stale closure. */
export type SyncBridge = {
  session: SessionSink;
  toast: (message: string) => void;
  navigateActiveSession: () => void;
};

export type SyncContextValue = {
  syncHealth: SyncHealth;
  /** No connection OR the backend is known-unreachable — gates the only sync indicators shown. */
  offline: boolean;
  storage: StorageStatus;
  storageGuardOpen: boolean;
  setStorageGuardOpen: (open: boolean) => void;
  /** Peak captures queued while offline, confirmed once after reconnect drains them (0 = hide). */
  offlineReceipt: number;
  saveDraft: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
  queueOperation: (operation: Omit<PendingOperation, "retryCount" | "status" | "createdAt" | "updatedAt">) => Promise<void>;
  processOutbox: () => Promise<void>;
  refreshPendingCount: () => Promise<PendingCapture[]>;
  refreshStorage: () => Promise<void>;
  exportQueuedCaptures: () => Promise<void>;
  loadBackendSessions: OutboxEngine["loadBackendSessions"];
  rebuildLocalPendingSessions: () => Promise<void>;
  resetProcessing: () => void;
  /** Hydrate sets this directly from whether the backend session load succeeded. */
  setBackendReachable: (reachable: boolean | null) => void;
  registerSyncBridge: (bridge: SyncBridge | null) => void;
};

const SyncContext = React.createContext<SyncContextValue | null>(null);

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const apiFetch = useApi();
  const { auth, authRef, appT } = useAuth();

  const [pendingCount, setPendingCount] = React.useState(0);
  const [pendingOperationCount, setPendingOperationCount] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [online, setOnline] = React.useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [backendReachable, setBackendReachable] = React.useState<boolean | null>(null);
  const [syncError, setSyncError] = React.useState("");
  const [storage, setStorage] = React.useState<StorageStatus>(OK_STORAGE_STATUS);
  const [storageGuardOpen, setStorageGuardOpen] = React.useState(false);
  const [offlineReceipt, setOfflineReceipt] = React.useState(0);
  const offlineBacklogRef = React.useRef(0);
  const hadOfflineBacklogRef = React.useRef(false);

  // The app body registers its session sink / toast / navigate here every render; the engine reads
  // through this ref so it always sees the latest callbacks without being reconstructed.
  const bridgeRef = React.useRef<SyncBridge | null>(null);
  const registerSyncBridge = React.useCallback((bridge: SyncBridge | null) => {
    bridgeRef.current = bridge;
  }, []);

  const api = React.useMemo<ApiPort>(
    () => ({
      fetchSessions: (options) => fetchSessions(apiFetch, options),
      searchPatients: (query) => searchPatients(apiFetch, query),
      uploadCapture: (clientCaptureId, draft, sessionId, intoNew) => uploadCapture(apiFetch, clientCaptureId, draft, sessionId, intoNew),
      assignSessionPatient: (sessionId, patientId, idempotencyKey, basisCaptureId) =>
        assignSessionPatient(apiFetch, sessionId, patientId, idempotencyKey, basisCaptureId),
      unassignSessionPatient: (sessionId, idempotencyKey) => unassignSessionPatient(apiFetch, sessionId, idempotencyKey),
      updateSessionTitle: (sessionId, title) => updateSessionTitle(apiFetch, sessionId, title),
      saveSessionForProcessing: (sessionId) => saveSessionForProcessing(apiFetch, sessionId),
      createPatient: (draft, idempotencyKey) => createPatient(apiFetch, draft, idempotencyKey),
      storeBackendMappings: (capture, result, tenantId) => storeBackendMappings(capture, result, tenantId),
    }),
    [apiFetch],
  );

  // A STABLE session sink that delegates through the bridge ref (so `createOutboxEngine` runs once).
  const sessionSink = React.useMemo<SessionSink>(
    () => ({
      getSessions: () => bridgeRef.current?.session.getSessions() ?? [],
      getActiveSession: () => bridgeRef.current?.session.getActiveSession() ?? null,
      setSessions: (update) => bridgeRef.current?.session.setSessions(update),
      setActiveSession: (update) => bridgeRef.current?.session.setActiveSession(update),
      setSelectedSessionId: (update) => bridgeRef.current?.session.setSelectedSessionId(update),
      upsertSession: (session, removeIds) => bridgeRef.current?.session.upsertSession(session, removeIds),
      updateItemStatus: (itemId, status) => bridgeRef.current?.session.updateItemStatus(itemId, status),
      applySessionUpdate: (sessionId, updated) => bridgeRef.current?.session.applySessionUpdate(sessionId, updated),
      selfHealStalePatient: async (sessionId, deadPatientId) =>
        bridgeRef.current?.session.selfHealStalePatient(sessionId, deadPatientId),
      scheduleCaptureProcessingRefresh: (sessionId) => bridgeRef.current?.session.scheduleCaptureProcessingRefresh(sessionId),
      scheduleSessionProcessingRefresh: (sessionId) => bridgeRef.current?.session.scheduleSessionProcessingRefresh(sessionId),
      scheduleMemoryRefresh: () => bridgeRef.current?.session.scheduleMemoryRefresh(),
    }),
    [],
  );

  const engine = React.useMemo<OutboxEngine>(
    () =>
      createOutboxEngine({
        storage: indexedDbStoragePort,
        api,
        session: sessionSink,
        status: {
          setPendingCount,
          setPendingOperationCount,
          setSyncing,
          setOnline,
          setBackendReachable,
          setSyncError,
          setStorage,
          toast: (message) => bridgeRef.current?.toast(message),
        },
        env: {
          getAuth: () => authRef.current,
          isOnline: () => (typeof navigator === "undefined" ? true : navigator.onLine),
          now: () => Date.now(),
          standardizeDraft: standardizeCaptureDraft,
          flushOptimistic: (fn) => flushSync(fn),
          navigateActiveSession: () => bridgeRef.current?.navigateActiveSession(),
          t: appT,
          estimateStorage: estimateStorageStatus,
        },
      }),
    // `api` changes only if `apiFetch` changes (effectively never); the sink/env read through refs.
    [api, sessionSink, authRef, appT],
  );

  // Keep sync state consistent with the browser's online/offline events (a UI hint only — see the
  // processOutbox comment) and resume the outbox when connectivity returns.
  React.useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine);
    const retryWhenOnline = () => void engine.processOutbox();
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    window.addEventListener("online", retryWhenOnline);
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
      window.removeEventListener("online", retryWhenOnline);
    };
  }, [engine]);

  // A beforeunload warning while device-only clinical material is unsynced (leaving could lose it).
  React.useEffect(() => {
    const warnIfPending = (event: BeforeUnloadEvent) => {
      if (!shouldWarnBeforeUnload(pendingCount, pendingOperationCount)) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnIfPending);
    return () => window.removeEventListener("beforeunload", warnIfPending);
  }, [pendingCount, pendingOperationCount]);

  // Robust periodic retry: while there is pending work, re-attempt on a FIXED interval regardless of
  // transient sync/online state. processOutbox() self-guards against overlap, so a tick during an
  // in-flight sync is a no-op. setInterval (not a re-armed setTimeout) guarantees stuck items retry.
  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview" || (!pendingCount && !pendingOperationCount)) return;
    const retryTimer = window.setInterval(() => void engine.processOutbox(), 15000);
    return () => window.clearInterval(retryTimer);
  }, [auth, pendingCount, pendingOperationCount, engine]);

  // Logged-out: still surface how many device-only captures are waiting (badge on the unauth shell).
  React.useEffect(() => {
    if (auth) return;
    void engine.refreshPendingCount();
  }, [auth, engine]);

  const offline = !online || backendReachable === false;

  // Offline return receipt: remember the PEAK captures queued while offline, then confirm them once —
  // after reconnect drains the backlog to zero — with a single transient banner, so sync isn't silent.
  React.useEffect(() => {
    if (offline && pendingCount > 0) {
      offlineBacklogRef.current = Math.max(offlineBacklogRef.current, pendingCount);
      hadOfflineBacklogRef.current = true;
    }
  }, [offline, pendingCount]);
  React.useEffect(() => {
    if (!offline && hadOfflineBacklogRef.current && !syncing && pendingCount === 0) {
      setOfflineReceipt(offlineBacklogRef.current);
      offlineBacklogRef.current = 0;
      hadOfflineBacklogRef.current = false;
    }
  }, [offline, syncing, pendingCount]);
  React.useEffect(() => {
    if (!offlineReceipt) return;
    const timer = window.setTimeout(() => setOfflineReceipt(0), 5200);
    return () => window.clearTimeout(timer);
  }, [offlineReceipt]);

  const syncHealth: SyncHealth = {
    online,
    backendReachable,
    pendingCaptures: pendingCount,
    pendingOperations: pendingOperationCount,
    syncing,
    lastError: syncError || undefined,
  };

  const value = React.useMemo<SyncContextValue>(
    () => ({
      syncHealth,
      offline,
      storage,
      storageGuardOpen,
      setStorageGuardOpen,
      offlineReceipt,
      saveDraft: engine.saveDraft,
      queueOperation: engine.queueOperation,
      processOutbox: engine.processOutbox,
      refreshPendingCount: engine.refreshPendingCount,
      refreshStorage: engine.refreshStorage,
      exportQueuedCaptures: engine.exportQueuedCaptures,
      loadBackendSessions: engine.loadBackendSessions,
      rebuildLocalPendingSessions: engine.rebuildLocalPendingSessions,
      resetProcessing: engine.resetProcessing,
      setBackendReachable,
      registerSyncBridge,
    }),
    [syncHealth, offline, storage, storageGuardOpen, offlineReceipt, engine, registerSyncBridge],
  );

  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>;
}

export function useSync(): SyncContextValue {
  const ctx = React.useContext(SyncContext);
  if (!ctx) throw new Error("useSync must be used within SyncProvider");
  return ctx;
}

/**
 * Register how the outbox engine reads/writes session state, raises toasts, and navigates. The supplied
 * bridge may close over fresh state each render — this re-points a stable ref at the latest one, so the
 * engine never captures stale session callbacks (mirrors ApiProvider's auth bridge).
 */
export function useRegisterSyncBridge(bridge: SyncBridge): void {
  const { registerSyncBridge } = useSync();
  const bridgeRef = React.useRef(bridge);
  bridgeRef.current = bridge;
  React.useEffect(() => {
    registerSyncBridge({
      session: {
        getSessions: () => bridgeRef.current.session.getSessions(),
        getActiveSession: () => bridgeRef.current.session.getActiveSession(),
        setSessions: (update) => bridgeRef.current.session.setSessions(update),
        setActiveSession: (update) => bridgeRef.current.session.setActiveSession(update),
        setSelectedSessionId: (update) => bridgeRef.current.session.setSelectedSessionId(update),
        upsertSession: (session, removeIds) => bridgeRef.current.session.upsertSession(session, removeIds),
        updateItemStatus: (itemId, status) => bridgeRef.current.session.updateItemStatus(itemId, status),
        applySessionUpdate: (sessionId, updated) => bridgeRef.current.session.applySessionUpdate(sessionId, updated),
        selfHealStalePatient: (sessionId, deadPatientId) => bridgeRef.current.session.selfHealStalePatient(sessionId, deadPatientId),
        scheduleCaptureProcessingRefresh: (sessionId) => bridgeRef.current.session.scheduleCaptureProcessingRefresh(sessionId),
        scheduleSessionProcessingRefresh: (sessionId) => bridgeRef.current.session.scheduleSessionProcessingRefresh(sessionId),
        scheduleMemoryRefresh: () => bridgeRef.current.session.scheduleMemoryRefresh(),
      },
      toast: (message) => bridgeRef.current.toast(message),
      navigateActiveSession: () => bridgeRef.current.navigateActiveSession(),
    });
    return () => registerSyncBridge(null);
  }, [registerSyncBridge]);
}
