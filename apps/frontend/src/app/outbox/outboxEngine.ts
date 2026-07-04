import type { CaptureDraft, PendingCapture, PendingOperation } from "../../domain/appTypes";
import type { CaptureSession } from "../../domain/types";
import { isNotFoundError } from "../../services/api/client";
import {
  isLocalAssignmentPatient,
  isLocalSessionId,
  makeLocalCapture,
  mergeSessionItems,
  sessionWithLocalPreview,
  sessionsFromPending,
} from "../../features/capture/captureModel";
import { mergeSessionUpdate } from "../sessionState";
import type { OutboxDeps } from "./types";

// The framework-agnostic offline outbox engine (frontend-refactor plan §4, increment 4). This is a
// faithful lift of the sync functions that used to live in App.tsx: serial capture upload, dependent
// operation replay (title/assignment/processing), 404 self-heal, and the optimistic local save. All
// side effects go through the injected ports (see ./types.ts) so this can be unit-tested against a
// fake storage adapter — it imports no React and reads no browser globals directly.
//
// The load-bearing async-correctness refs (plan §6) are preserved by construction: latest auth/session
// state is read through `env.getAuth()` / `session.getSessions()` getters at call time (never a stale
// closure), and the overlap guard is the module-local `processing` flag below (was `processingRef`).

export type OutboxEngine = ReturnType<typeof createOutboxEngine>;

export function createOutboxEngine({ storage, api, session, status, env }: OutboxDeps) {
  // Overlap guard (was `processingRef`): a retry tick during an in-flight sync is a no-op.
  let processing = false;

  const refreshStorage = async () => {
    status.setStorage(await env.estimateStorage());
  };

  const refreshPendingCount = async (): Promise<PendingCapture[]> => {
    const [pending, operations] = await Promise.all([storage.loadPendingCaptures(), storage.loadPendingOperations()]);
    status.setPendingCount(pending.length);
    status.setPendingOperationCount(operations.length);
    void refreshStorage();
    return pending;
  };

  // Export queued (unsynced) captures to disk — the durability escape hatch (Epic G).
  const exportQueuedCaptures = async () => {
    const pending = await storage.loadPendingCaptures();
    if (!pending.length) {
      status.toast(env.t("capture.toastNoQueuedExport"));
      return;
    }
    try {
      const count = await storage.exportPendingCaptures(pending, new Date(env.now()).toISOString());
      status.toast(env.t("capture.toastExportedQueued", { count }));
    } catch {
      status.toast(env.t("capture.toastCouldNotExportQueued"));
    }
  };

  const queueOperation = async (operation: Omit<PendingOperation, "retryCount" | "status" | "createdAt" | "updatedAt">) => {
    const now = env.now();
    await storage.savePendingOperation({
      ...operation,
      retryCount: 0,
      status: "pending",
      createdAt: now,
      updatedAt: now,
    });
    await refreshPendingCount();
  };

  const loadBackendSessions = async (): Promise<CaptureSession[]> => {
    const loadedSessions = await api.fetchSessions();
    try {
      const patients = await api.searchPatients("");
      const patientNameById = new Map(patients.map((patient) => [patient.id, patient.displayName]));
      return loadedSessions.map((loaded) =>
        loaded.patientId && !loaded.patientName
          ? { ...loaded, patientName: patientNameById.get(loaded.patientId) || `Patient ${loaded.patientId.slice(0, 8)}` }
          : loaded,
      );
    } catch {
      return loadedSessions;
    }
  };

  const rebuildLocalPendingSessions = async () => {
    const pending = await storage.loadPendingCaptures();
    const localSessions = sessionsFromPending(pending);
    session.setSessions((current) => [
      ...localSessions,
      ...current.filter((existing) => !localSessions.some((localSession) => localSession.id === existing.id)),
    ]);
  };

  const resolveBackendSessionId = async (operation: PendingOperation, tenantId: string) => {
    if (operation.backendSessionId) return operation.backendSessionId;
    if (!operation.localSessionId) return undefined;
    if (!isLocalSessionId(operation.localSessionId)) return operation.localSessionId;
    return (await storage.loadIdMapping(`${tenantId}:session:${operation.localSessionId}`))?.backendId;
  };

  const syncPendingOperation = async (operation: PendingOperation, tenantId: string) => {
    const backendSessionId = await resolveBackendSessionId(operation, tenantId);
    if (!backendSessionId) return false;

    await storage.updatePendingOperation(operation.id, (current) => ({
      ...current,
      status: "syncing",
      updatedAt: env.now(),
      lastError: undefined,
    }));

    if (operation.type === "sessionTitle") {
      const title = typeof operation.payload.title === "string" ? operation.payload.title : "";
      if (title.trim()) {
        const updated = await api.updateSessionTitle(backendSessionId, title.trim());
        session.applySessionUpdate(backendSessionId, updated);
      }
    }

    if (operation.type === "patientAssignment") {
      if (operation.payload.unassign === true) {
        if (backendSessionId) {
          const unassigned = await api.unassignSessionPatient(backendSessionId, operation.id);
          session.applySessionUpdate(backendSessionId, unassigned);
        }
      } else {
        const draft = {
          patientId: typeof operation.payload.patientId === "string" ? operation.payload.patientId : undefined,
          displayName: String(operation.payload.displayName || "").trim(),
          nationalId: typeof operation.payload.nationalId === "string" ? operation.payload.nationalId : undefined,
        };
        let patientId = operation.backendPatientId || (draft.patientId && !isLocalAssignmentPatient(draft.patientId) ? draft.patientId : undefined);
        if (!patientId && draft.displayName) {
          const matches = await api.searchPatients(draft.nationalId || draft.displayName);
          const normalizedName = draft.displayName.toLowerCase();
          const exact = matches.find(
            (patient) =>
              patient.displayName.trim().toLowerCase() === normalizedName ||
              (draft.nationalId && patient.nationalId === draft.nationalId),
          );
          patientId = (exact || (await api.createPatient(draft, operation.id))).id;
        }
        if (patientId) {
          const basisCaptureId = typeof operation.payload.basisCaptureId === "string" ? operation.payload.basisCaptureId : undefined;
          const assigned = await api.assignSessionPatient(backendSessionId, patientId, operation.id, basisCaptureId);
          session.applySessionUpdate(backendSessionId, assigned);
        }
      }
    }

    if (operation.type === "sessionProcessing") {
      const processingSession = await api.saveSessionForProcessing(backendSessionId);
      session.applySessionUpdate(backendSessionId, processingSession);
      session.scheduleSessionProcessingRefresh(backendSessionId);
    }

    await storage.removePendingOperation(operation.id);
    return true;
  };

  const processPendingOperations = async (tenantId: string) => {
    const operations = await storage.loadPendingOperations();
    let failed = false;
    for (const operation of operations) {
      if (operation.tenantId && operation.tenantId !== tenantId) continue;
      try {
        const completed = await syncPendingOperation(operation, tenantId);
        if (!completed) continue;
      } catch (error) {
        if (isNotFoundError(error)) {
          // The op targets a patient/session that no longer exists (deleted/merged). Retrying would
          // 404 forever — drop it and self-heal the stale reference instead of stranding the outbox.
          await storage.removePendingOperation(operation.id);
          const opSessionId = operation.backendSessionId || operation.localSessionId;
          const opPatientId =
            operation.backendPatientId ||
            (typeof operation.payload.patientId === "string" ? operation.payload.patientId : undefined);
          await session.selfHealStalePatient(opSessionId, opPatientId);
          continue;
        }
        await storage.updatePendingOperation(operation.id, (current) => ({
          ...current,
          status: "failed",
          retryCount: current.retryCount + 1,
          updatedAt: env.now(),
          lastError: error instanceof Error ? error.message : env.t("capture.syncFailed"),
        }));
        status.setSyncError(env.t("capture.syncNeedsRetry"));
        status.setBackendReachable(false);
        failed = true;
      }
    }
    return !failed;
  };

  /**
   * Serially uploads locally saved captures for the active tenant.
   *
   * The outbox is intentionally processed one item at a time so a failed upload leaves later captures
   * untouched and keeps local session previews consistent.
   */
  const processOutbox = async () => {
    const currentAuth = env.getAuth();
    const activeTenantId = currentAuth?.tenant.id;
    if (processing || !currentAuth || !activeTenantId || currentAuth.user.persona === "patient-preview") return;
    // `navigator.onLine` is unreliable — it returns false-negatives after sleep / Wi-Fi / VPN changes
    // and often never recovers, which used to strand captures in "waiting to upload". Treat it as a UI
    // hint only and STILL attempt the upload: a genuinely-offline fetch fails fast and is caught +
    // retried below, so a wrong `onLine` can no longer block syncing.
    if (!env.isOnline()) status.setOnline(false);
    processing = true;
    status.setSyncing(true);
    status.setSyncError("");
    try {
      const pending = await storage.loadPendingCaptures();
      let captureFailed = false;
      for (const pendingCapture of pending) {
        const auth = env.getAuth();
        if (!auth || auth.tenant.id !== activeTenantId) break;
        const capture = (await storage.loadPendingCapture(pendingCapture.id)) || pendingCapture;
        if (capture.tenantId && capture.tenantId !== activeTenantId) {
          // A capture only uploads for the tenant it was made under. After tier/clinic switching this
          // strands it as "waiting to upload" under the wrong tenant — surface why instead of hiding it.
          console.warn(
            `[outbox] capture ${capture.item.id} is for tenant ${capture.tenantId}, not the active tenant ${activeTenantId} — skipping. Log in under that clinic/tier to upload it.`,
          );
          continue;
        }
        const backendSessionId = capture.backendSessionId || capture.sessionId;
        await storage.updatePendingCapture(capture.id, (current) => ({
          ...storage.normalizePendingCapture(current),
          tenantId: current.tenantId || activeTenantId,
          backendSessionId,
          sessionId: backendSessionId,
        }));
        session.updateItemStatus(capture.item.id, "syncing");
        try {
          const uploadDraft = await env.standardizeDraft(capture.draft);
          const result = await api.uploadCapture(capture.clientCaptureId, uploadDraft, backendSessionId, capture.intoNew);
          const remainingPending = await storage.loadPendingCaptures();
          const stillPendingForLocalSession = remainingPending.some(
            (other) => other.id !== capture.id && other.localSessionId === capture.localSessionId,
          );
          const currentSession = session.getSessions().find((existing) => existing.id === capture.localSessionId || existing.id === result.session.id);
          let mergedSession = mergeSessionItems(currentSession || session.getActiveSession(), result.session, capture.item.id);
          if (mergedSession.patientId && !result.session.patientId && !isLocalSessionId(mergedSession.id)) {
            try {
              const assignedSession = await api.assignSessionPatient(mergedSession.id, mergedSession.patientId);
              mergedSession = mergeSessionUpdate(mergedSession, assignedSession, mergedSession.items);
            } catch {
              // Keep the local patient context visible; assignment can be retried from the patient control.
            }
          }
          session.upsertSession(mergedSession, stillPendingForLocalSession ? [] : [capture.localSessionId]);
          session.setActiveSession((current) =>
            current?.id === capture.localSessionId || current?.id === result.session.id
              ? mergeSessionUpdate(mergeSessionItems(current, result.session, capture.item.id), mergedSession, mergedSession.items)
              : current,
          );
          session.setSelectedSessionId((current) => (current === capture.localSessionId ? mergedSession.id : current));
          status.toast(env.t("capture.toastCaptureTransferred"));
          if (result.item.status === "uploaded" || result.item.status === "processing") session.scheduleCaptureProcessingRefresh(result.session.id);
          session.scheduleMemoryRefresh();
          try {
            await storage.updatePendingCapture(capture.id, (current) => ({
              ...storage.normalizePendingCapture(current),
              draft: uploadDraft,
              tenantId: activeTenantId,
              backendSessionId: result.session.id,
              backendCaptureId: result.item.id,
              sessionId: result.session.id,
              intoNew: false,
            }));
            await api.storeBackendMappings(capture, result, activeTenantId);
            await storage.saveSyncedCaptureCache(result.item, uploadDraft.file);
            await storage.bindPendingSession(capture.localSessionId, result.session.id);
            await storage.removePendingCapture(capture.id);
            await refreshPendingCount();
          } catch {
            status.toast(env.t("capture.toastCaptureTransferred"));
          }
        } catch (uploadError) {
          // Was swallowed silently — log the real reason so a perpetually-stuck capture is diagnosable.
          console.warn(`[outbox] upload failed for capture ${capture.item.id} (retry ${capture.retryCount + 1}):`, uploadError);
          await storage.updatePendingCapture(capture.id, (current) => ({ ...current, retryCount: current.retryCount + 1 }));
          session.updateItemStatus(capture.item.id, "saved");
          await rebuildLocalPendingSessions();
          status.setBackendReachable(false);
          status.setSyncError(env.t("capture.syncUploadFailed"));
          captureFailed = true;
          status.toast(env.t("capture.toastSavedDeviceWillOrganize"));
          continue;
        }
      }
      const operationsHealthy = await processPendingOperations(activeTenantId);
      if (operationsHealthy && !captureFailed) status.setBackendReachable(true);
    } finally {
      processing = false;
      status.setSyncing(false);
      await refreshPendingCount();
    }
  };

  /**
   * Saves a capture to IndexedDB before attempting network transfer.
   *
   * The optimistic UI update happens only after local persistence succeeds, which keeps the visible
   * feed aligned with recoverable browser state.
   */
  const saveDraft = async (draft: CaptureDraft, intoNew = false) => {
    let pending: PendingCapture;
    let visibleSession: CaptureSession;
    try {
      const safeDraft = await env.standardizeDraft(draft);
      pending = makeLocalCapture(safeDraft, session.getActiveSession(), intoNew, env.getAuth()?.tenant.id);
      visibleSession = sessionWithLocalPreview(pending.session, pending.item.id, safeDraft.file);
      await storage.savePendingCapture(pending);
      env.flushOptimistic(() => {
        session.setActiveSession(() => visibleSession);
        session.upsertSession(visibleSession);
        env.navigateActiveSession();
      });
    } catch {
      status.toast(draft.kind === "audio" ? env.t("capture.toastAudioConversionFailed") : env.t("capture.toastDeviceStorageFailed"));
      return;
    }

    void storage.saveSyncedCaptureCache(pending.item, pending.draft.file);
    status.toast(env.t("capture.toastSavedDevice"));
    void refreshPendingCount();
    if (env.getAuth()?.tenant.id) void processOutbox();
  };

  /** Reset the overlap guard (called when clearing local data / on logout). */
  const resetProcessing = () => {
    processing = false;
  };

  return {
    refreshStorage,
    refreshPendingCount,
    exportQueuedCaptures,
    queueOperation,
    loadBackendSessions,
    rebuildLocalPendingSessions,
    processOutbox,
    saveDraft,
    resetProcessing,
  };
}

/** Warn on unload iff there is device-only clinical material not yet synced (was App's beforeunload). */
export function shouldWarnBeforeUnload(pendingCaptures: number, pendingOperations: number): boolean {
  return pendingCaptures > 0 || pendingOperations > 0;
}
