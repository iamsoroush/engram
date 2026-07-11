import React from "react";
import type {
  PatientAssignmentDraft,
  PatientSummary,
} from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, CaptureStatus, StructuredPatientInformation } from "../../domain/types";
import {
  createClientId,
  isLocalAssignmentPatient,
  isLocalSessionId,
  mergeCaptureItemsPreservingPreview,
} from "../../features/capture/captureModel";
import { metadataRecord } from "../../features/capture/metadata";
import {
  applyNameCorrection,
  applyUnassignSuggestion,
  assignSessionPatient,
  confirmCarriedForward,
  createPatient,
  deleteCapture,
  restoreReportVersion as restoreReportVersionRequest,
  dismissAiPatientAction,
  editTreatmentOverlay,
  fetchCapture,
  fetchSession,
  fetchSessionCaptures,
  getPatient,
  isNotFoundError,
  markCaptureRelevant,
  type PatientEditDraft,
  postFeedback,
  rejectSafetyFlag,
  saveSessionForProcessing,
  revertTreatmentOverlay,
  searchPatients,
  setAftercareDismissed,
  updateCaptureCaption,
  updateCaptureNote,
  updateCaptureTitle,
  updateCaptureTranscript,
  updatePatient,
  updateSessionTitle,
  verifyAiPatientCreation,
} from "../../services/api/client";
import {
  loadPendingCaptures,
  removePendingCapture,
  removePendingOperation,
  updatePendingCapture,
} from "../../services/storage/captureStorage";
import {
  markReportStaleForCaptureChange,
  markReportStaleForPatientChange,
  mergeSessionUpdate,
  PROCESSING_REFRESH_DELAYS,
} from "../sessionState";
import {
  applyStaffAssignment,
  setItemStatusInSession,
  setItemStatusInSessions,
  stripPatientFromSession,
  stripStalePatientAcross,
  upsertSessionList,
} from "../sessionStoreReducers";
import type { SessionSink } from "../outbox/types";
import { useApi } from "./ApiProvider";
import { useAuth } from "./AuthProvider";
import { useSync } from "./SyncProvider";
import { useToast } from "./ToastProvider";

// Seam C (frontend-refactor plan §2/§4, increment 5). The capture/session domain store lifted out of
// the App god-component: `sessions[]` / `activeSession` / `selectedSessionId` / `assignmentSessionId` /
// `memoryRefreshSignal`, the async-correctness refs (§6), and the whole *non-navigating* session/patient
// action layer. It sits on Api + Sync (child of SyncProvider so it can drive the outbox), and provides
// the `SessionSink` the outbox engine reads/writes through — App re-points its SyncBridge at
// `store.sessionSink` instead of building the sink from its own refs.
//
// The *navigating* helpers (startNewSession, startVisitForPatient, openMemorySession,
// continueMemorySession, returnToActiveCapture, openPatientHistory) and the capture-screen display
// effects (sessionContext, sessionLineupCard, aftercareTemplates, nextLinedUpPatient) stay in App — they
// are interleaved with navigation and belong to the router seam (increment 7). So App consumes ONE
// `useSessionStore()` omnibus and destructures it back into the same local names, leaving its large
// render body + nav helpers unchanged. See docs/frontend/overview.md#composition-root--seams.
//
// Render-cadence (plan §2 fork): split-context — a STABLE actions object (never changes identity) is kept
// separate from the VOLATILE state slice, so increment-6 consumers that only dispatch don't re-render on
// data churn. No useSyncExternalStore (not needed until a measured re-render problem forces it).

function sessionNeedsProcessingRefresh(session: CaptureSession | null) {
  if (!session) return false;
  if (session.processingStatus?.state === "processing" || session.report?.status === "generating") return true;
  return session.items.some((item) => item.status === "uploaded" || item.status === "processing" || item.status === "uploading");
}

/** The volatile session data slice — changes on every capture/session mutation. */
export type SessionState = {
  sessions: CaptureSession[];
  activeSession: CaptureSession | null;
  selectedSessionId: string;
  assignmentSessionId: string;
  /** Bumped over the processing delay ladder so Clinical Memory re-fetches after captures/assignments. */
  memoryRefreshSignal: number;
};

/** The stable action/dispatch surface — memoized once, safe to consume without re-rendering on data churn. */
export type SessionActions = {
  setSessions: React.Dispatch<React.SetStateAction<CaptureSession[]>>;
  setActiveSession: React.Dispatch<React.SetStateAction<CaptureSession | null>>;
  setSelectedSessionId: React.Dispatch<React.SetStateAction<string>>;
  setAssignmentSessionId: React.Dispatch<React.SetStateAction<string>>;
  upsertSession: (session: CaptureSession, removeIds?: string[]) => void;
  applySessionUpdate: (sessionId: string, updated: CaptureSession) => void;
  saveSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  renameCapture: (sessionId: string, captureId: string, title: string) => Promise<void>;
  editCaptureSourceText: (
    sessionId: string,
    captureId: string,
    text: string,
    field: "caption" | "transcript",
  ) => Promise<CaptureItem | null>;
  editCaptureNote: (sessionId: string, captureId: string, text: string) => Promise<void>;
  removeCaptureFromSession: (sessionId: string, captureId: string) => Promise<void>;
  /** E14: restore the report to a stored version (revert semantics; owner-only, shares the undo path). */
  restoreReportVersion: (sessionId: string, versionId: string) => Promise<void>;
  markCaptureRelevantInSession: (sessionId: string, captureId: string) => Promise<void>;
  confirmCarriedForwardDose: (sessionId: string, key: string) => Promise<void>;
  rateReport: (sessionId: string, rating: number) => void;
  fetchCaptureById: (captureId: string) => ReturnType<typeof fetchCapture>;
  dismissAftercareTemplate: (sessionId: string, templateId: string, dismissed: boolean) => Promise<void>;
  rejectSafetyFlagFromSession: (sessionId: string, flagKey: string) => Promise<void>;
  /** E1 one-tap: apply a `suggested_name_correction` chip (rename the assigned patient in place). */
  applyPatientNameCorrection: (sessionId: string, spokenName: string, basisCaptureId?: string) => Promise<void>;
  /** E1 one-tap: apply a `suggested_unassign` chip (clear the visit's patient). */
  unassignPatientFromSession: (sessionId: string, basisCaptureId?: string) => Promise<void>;
  /** AES-1102: record a human field edit on a treatment row (user-owned overlay, no re-synthesis). */
  editTreatmentField: (sessionId: string, treatmentKey: string, field: string, value: string) => Promise<void>;
  /** AES-1103: Revert-to-AI / Use-AI — drop the overlay edit for (treatmentKey, field). */
  revertTreatmentField: (sessionId: string, treatmentKey: string, field: string) => Promise<void>;
  selfHealStalePatient: (sessionId: string | undefined, deadPatientId?: string) => Promise<void>;
  assignPatientToSession: (
    sessionId: string,
    draft: PatientAssignmentDraft,
    options?: { successMessage?: string },
  ) => Promise<void>;
  searchPatientsForAssignment: (query: string) => Promise<PatientSummary[]>;
  fetchAssignedPatientDetails: (patientId: string) => Promise<StructuredPatientInformation | null>;
  completeAiCreatedPatient: (
    sessionId: string,
    patientId: string,
    draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
    action: Record<string, unknown>,
  ) => Promise<void>;
  editPatientDetails: (patientId: string, draft: PatientEditDraft) => Promise<void>;
  createNewPatient: (draft: PatientAssignmentDraft) => Promise<PatientSummary | null>;
  confirmSessionSummary: (sessionId: string, summary: string) => Promise<void>;
  loadCapturesForSession: (sessionId: string) => Promise<CaptureItem[]>;
  scheduleCaptureProcessingRefresh: (sessionId: string) => void;
  scheduleSessionProcessingRefresh: (sessionId: string) => void;
  scheduleMemoryRefresh: () => void;
  /** The port the outbox engine reads/writes through (App wires it into its SyncBridge). */
  sessionSink: SessionSink;
};

const SessionStateContext = React.createContext<SessionState | null>(null);
const SessionActionsContext = React.createContext<SessionActions | null>(null);

export function SessionStoreProvider({ children }: { children: React.ReactNode }) {
  const apiFetch = useApi();
  const { authRef, appT } = useAuth();
  const { setToast } = useToast();
  const { queueOperation, processOutbox, loadBackendSessions } = useSync();

  const [sessions, setSessions] = React.useState<CaptureSession[]>([]);
  const [activeSession, setActiveSession] = React.useState<CaptureSession | null>(null);
  const [selectedSessionId, setSelectedSessionId] = React.useState("");
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const [memoryRefreshSignal, setMemoryRefreshSignal] = React.useState(0);

  // Async-correctness refs (§6): the outbox loop and session actions must read the LATEST session state
  // without a stale closure — so keep refs mirroring state and read them at call time.
  const activeSessionRef = React.useRef<CaptureSession | null>(null);
  const sessionsRef = React.useRef<CaptureSession[]>([]);
  const aiPatientToastIdsRef = React.useRef(new Set<string>());

  React.useEffect(() => {
    activeSessionRef.current = activeSession;
  }, [activeSession]);

  React.useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  const updateItemStatus = React.useCallback((itemId: string, status: CaptureStatus) => {
    setActiveSession((session) => setItemStatusInSession(session, itemId, status));
    setSessions((current) => setItemStatusInSessions(current, itemId, status));
  }, []);

  const upsertSession = React.useCallback((session: CaptureSession, removeIds: string[] = []) => {
    setSessions((current) => upsertSessionList(current, session, removeIds));
  }, []);

  const notifyAiPatientAction = React.useCallback(
    (session: CaptureSession) => {
      const action = metadataRecord(session.extractedMetadata?.ai_patient_action);
      const patientId = typeof action.patientId === "string" ? action.patientId : session.patientId;
      const basisCaptureId = typeof action.basisCaptureId === "string" ? action.basisCaptureId : "";
      const actionName = typeof action.action === "string" ? action.action : "";
      if (!patientId || !actionName) return;
      const toastId = `${session.id}:${actionName}:${patientId}:${basisCaptureId}`;
      if (aiPatientToastIdsRef.current.has(toastId)) return;
      aiPatientToastIdsRef.current.add(toastId);
      const displayName = typeof action.displayName === "string" ? action.displayName : session.patientName || "patient";
      setToast(
        actionName === "created_and_assigned"
          ? `AI created and assigned ${displayName}.`
          : `AI matched this visit to ${displayName}.`,
      );
    },
    [setToast],
  );

  const refreshVisibleSession = React.useCallback(
    async (sessionId: string) => {
      const [captures, updatedSession] = await Promise.all([fetchSessionCaptures(apiFetch, sessionId), fetchSession(apiFetch, sessionId)]);
      setSessions((current) =>
        current.map((session) => {
          if (session.id !== sessionId) return session;
          const items = mergeCaptureItemsPreservingPreview(session.items, captures);
          const merged = mergeSessionUpdate(session, updatedSession, items);
          notifyAiPatientAction(merged);
          return merged;
        }),
      );
      setActiveSession((current) =>
        current?.id === sessionId
          ? (() => {
              const items = mergeCaptureItemsPreservingPreview(current.items, captures);
              const merged = mergeSessionUpdate(current, updatedSession, items);
              notifyAiPatientAction(merged);
              return merged;
            })()
          : current,
      );
    },
    [apiFetch, notifyAiPatientAction],
  );

  const scheduleCaptureProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      PROCESSING_REFRESH_DELAYS.forEach((delay) => {
        window.setTimeout(() => {
          void refreshVisibleSession(sessionId).catch(() => undefined);
        }, delay);
      });
    },
    [refreshVisibleSession],
  );

  // Patient summary/history regenerate (mock AI job) after a capture/assignment; bump a signal over
  // the same delay ladder so Clinical Memory re-fetches and animates the updating→ready transition.
  const scheduleMemoryRefresh = React.useCallback(() => {
    PROCESSING_REFRESH_DELAYS.forEach((delay) => {
      window.setTimeout(() => setMemoryRefreshSignal((value) => value + 1), delay);
    });
  }, []);

  // While the active backend session is still processing, poll it once after a short delay so the live
  // report/status settles without waiting for the next capture. (Only session state — belongs here.)
  React.useEffect(() => {
    if (!activeSession?.id || isLocalSessionId(activeSession.id) || !sessionNeedsProcessingRefresh(activeSession)) return;
    const refreshTimer = window.setTimeout(() => {
      void refreshVisibleSession(activeSession.id).catch(() => undefined);
    }, 15000);
    return () => window.clearTimeout(refreshTimer);
  }, [activeSession, refreshVisibleSession]);

  const scheduleSessionProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      PROCESSING_REFRESH_DELAYS.forEach((delay) => {
        window.setTimeout(() => {
          void loadBackendSessions()
            .then((loadedSessions) => {
              const updated = loadedSessions.find((session) => session.id === sessionId);
              if (!updated) return;
              setSessions((current) =>
                current.map((session) => (session.id === sessionId ? mergeSessionUpdate(session, updated) : session)),
              );
              setActiveSession((current) => (current?.id === sessionId ? mergeSessionUpdate(current, updated) : current));
            })
            .catch(() => undefined);
        }, delay);
      });
    },
    [loadBackendSessions],
  );

  const saveSession = React.useCallback(
    async (sessionId: string) => {
      const markProcessing = (session: CaptureSession): CaptureSession => ({
        ...session,
        status: "processing",
        report: {
          schemaVersion: session.report?.schemaVersion,
          status: "generating",
          format: session.report?.format || "markdown",
          title: session.report?.title || session.label,
          body: "",
          sections: [{ id: "body", title: "Body", body: "" }],
          structuredModel: session.report?.structuredModel || session.reportModel || null,
          patientInformation: session.report?.patientInformation || null,
          patientInformationSource: session.report?.patientInformationSource || null,
          template: session.report?.template || null,
          source: session.report?.source || null,
          generatedAt: session.report?.generatedAt || null,
          updatedAt: new Date().toISOString(),
          isStale: false,
        },
        processingStatus: {
          schemaVersion: session.processingStatus?.schemaVersion,
          state: "processing",
          label: appT("capture.generatingReport"),
          detail: appT("capture.generatingReportDetail"),
          stage: "report",
          progress: session.processingStatus?.progress ?? null,
          canEdit: false,
          canReview: false,
          source: session.processingStatus?.source || null,
          updatedAt: new Date().toISOString(),
        },
      });
      setSessions((current) => current.map((session) => (session.id === sessionId ? markProcessing(session) : session)));
      setActiveSession((current) => (current?.id === sessionId ? markProcessing(current) : current));
      if (isLocalSessionId(sessionId)) {
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:sessionProcessing:${sessionId}`,
            type: "sessionProcessing",
            localSessionId: sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { reportTemplateKey: "default" },
          });
          setToast(appT("capture.toastSavedDeviceWillOrganize"));
        }
        void processOutbox();
        return;
      }
      try {
        const processingSession = await saveSessionForProcessing(apiFetch, sessionId);
        setSessions((current) =>
          current.map((session) => (session.id === sessionId ? mergeSessionUpdate(session, processingSession) : session)),
        );
        setActiveSession((current) => (current?.id === sessionId ? mergeSessionUpdate(current, processingSession) : current));
        setToast(appT("capture.toastReportGenerating"));
        scheduleSessionProcessingRefresh(sessionId);
      } catch {
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:sessionProcessing:${sessionId}`,
            type: "sessionProcessing",
            backendSessionId: sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { reportTemplateKey: "default" },
          });
          setToast(appT("capture.toastSavedWillOrganize"));
          void processOutbox();
          return;
        }
        setToast(appT("capture.toastSavedDeviceWillOrganize"));
      }
    },
    [apiFetch, appT, authRef, processOutbox, queueOperation, scheduleSessionProcessingRefresh, setToast],
  );

  const renameSession = React.useCallback(
    async (sessionId: string, title: string) => {
      if (isLocalSessionId(sessionId)) {
        const updateSession = (session: CaptureSession) => ({ ...session, label: title });
        setSessions((current) => current.map((session) => (session.id === sessionId ? updateSession(session) : session)));
        setActiveSession((current) => (current?.id === sessionId ? updateSession(current) : current));
        const pending = await loadPendingCaptures();
        await Promise.all(
          pending
            .filter((capture) => capture.localSessionId === sessionId)
            .map((capture) =>
              updatePendingCapture(capture.id, (current) => ({
                ...current,
                session: updateSession(current.session),
              })),
            ),
        );
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:sessionTitle:${sessionId}`,
            type: "sessionTitle",
            localSessionId: sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { title },
          });
        }
        setToast(appT("capture.toastTitleUpdated"));
        return;
      }
      try {
        const updated = await updateSessionTitle(apiFetch, sessionId, title);
        setSessions((current) =>
          current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
        );
        setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
        setToast(appT("capture.toastTitleUpdated"));
      } catch {
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:sessionTitle:${sessionId}`,
            type: "sessionTitle",
            backendSessionId: sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { title },
          });
          setToast(appT("capture.toastTitleSavedDevice"));
          void processOutbox();
          return;
        }
        setToast(appT("capture.toastCouldNotUpdateTitle"));
      }
    },
    [apiFetch, appT, authRef, processOutbox, queueOperation, setToast],
  );

  const renameCapture = React.useCallback(
    async (sessionId: string, captureId: string, title: string) => {
      const updateLocalItem = (session: CaptureSession): CaptureSession =>
        session.id === sessionId
          ? { ...session, items: session.items.map((item) => (item.id === captureId ? { ...item, title } : item)) }
          : session;
      if (captureId.startsWith("local-capture-")) {
        setSessions((current) => current.map(updateLocalItem));
        setActiveSession((current) => (current?.id === sessionId ? updateLocalItem(current) : current));
        await updatePendingCapture(captureId, (current) => ({
          ...current,
          item: { ...current.item, title },
          session: updateLocalItem(current.session),
        }));
        setToast(appT("capture.toastCaptureRenamed"));
        return;
      }
      const updated = await updateCaptureTitle(apiFetch, captureId, title);
      const mergeCaptureTitleUpdate = (item: typeof updated) => ({
        ...item,
        ...updated,
        sourceUrl: item.sourceUrl || updated.sourceUrl,
        contentType: item.contentType || updated.contentType,
      });
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? { ...session, items: session.items.map((item) => (item.id === captureId ? mergeCaptureTitleUpdate(item) : item)) }
            : session,
        ),
      );
      setActiveSession((current) =>
        current?.id === sessionId
          ? { ...current, items: current.items.map((item) => (item.id === captureId ? mergeCaptureTitleUpdate(item) : item)) }
          : current,
      );
      setToast(appT("capture.toastCaptureRenamed"));
    },
    [apiFetch, appT, setToast],
  );

  const editCaptureSourceText = React.useCallback(
    async (sessionId: string, captureId: string, text: string, field: "caption" | "transcript"): Promise<CaptureItem | null> => {
      const editedAt = new Date().toISOString();
      const editorName = authRef.current?.user.displayName || authRef.current?.user.email || "You";
      const updateItem = (item: CaptureItem): CaptureItem => {
        if (item.id !== captureId) return item;
        const currentText = item.metadata?.[field] && typeof item.metadata[field] === "object"
          ? (item.metadata[field] as Record<string, unknown>)
          : {};
        const aiField = field === "caption" ? "ai_caption" : "ai_transcript";
        const shouldPreserveAiText = item.metadata?.[field] && currentText.source !== "staff_edit" && !item.metadata?.[aiField];
        const nextMetadata = {
          ...(item.metadata || {}),
          ...(shouldPreserveAiText ? { [aiField]: item.metadata?.[field] } : {}),
          [field]: {
            ...currentText,
            text,
            source: "staff_edit",
            edited_at: editedAt,
            edited_by_name: editorName,
            edited_by_email: authRef.current?.user.email,
          },
        };
        return {
          ...item,
          caption: field === "caption" ? text : item.caption,
          transcript: field === "transcript" ? text : item.transcript,
          metadata: nextMetadata,
        };
      };
      const updateSession = (session: CaptureSession): CaptureSession =>
        session.id === sessionId ? markReportStaleForCaptureChange({ ...session, items: session.items.map(updateItem) }) : session;

      if (captureId.startsWith("local-capture-")) {
        setSessions((current) => current.map(updateSession));
        setActiveSession((current) => (current?.id === sessionId ? updateSession(current) : current));
        await updatePendingCapture(captureId, (current) => ({
          ...current,
          item: updateItem(current.item),
          session: updateSession(current.session),
        }));
        setToast(field === "caption" ? appT("capture.toastCaptionUpdated") : appT("capture.toastTranscriptUpdated"));
        const active = activeSessionRef.current;
        const currentItem = active?.id === sessionId ? active.items.find((item) => item.id === captureId) : null;
        return currentItem ? updateItem(currentItem) : null;
      }

      const updated = field === "caption"
        ? await updateCaptureCaption(apiFetch, captureId, text)
        : await updateCaptureTranscript(apiFetch, captureId, text);
      const mergeCaptionUpdate = (item: CaptureItem): CaptureItem =>
        item.id === captureId
          ? {
              ...item,
              ...updated,
              sourceUrl: item.sourceUrl || updated.sourceUrl,
              contentType: item.contentType || updated.contentType,
            }
          : item;
      const updateBackendSession = (session: CaptureSession): CaptureSession =>
        session.id === sessionId ? markReportStaleForCaptureChange({ ...session, items: session.items.map(mergeCaptionUpdate) }) : session;
      setSessions((current) => current.map(updateBackendSession));
      setActiveSession((current) => (current?.id === sessionId ? updateBackendSession(current) : current));
      setToast(field === "caption" ? appT("capture.toastCaptionUpdated") : appT("capture.toastTranscriptUpdated"));
      return updated;
    },
    [apiFetch, appT, authRef, setToast],
  );

  const removeCaptureFromSession = React.useCallback(
    async (sessionId: string, captureId: string) => {
      const removeLocalItem = (session: CaptureSession): CaptureSession =>
        session.id === sessionId
          ? markReportStaleForCaptureChange({ ...session, items: session.items.filter((item) => item.id !== captureId) })
          : session;
      if (captureId.startsWith("local-capture-")) {
        setSessions((current) => current.map(removeLocalItem));
        setActiveSession((current) => (current?.id === sessionId ? removeLocalItem(current) : current));
        await removePendingCapture(captureId);
        setToast(appT("capture.toastCaptureDeleted"));
        return;
      }
      const updated = await deleteCapture(apiFetch, captureId);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? mergeSessionUpdate(session, updated, session.items.filter((item) => item.id !== captureId))
            : session,
        ),
      );
      setActiveSession((current) =>
        current?.id === sessionId
          ? mergeSessionUpdate(current, updated, current.items.filter((item) => item.id !== captureId))
          : current,
      );
      // Deleting a capture regenerates the Pro live report; poll for the refreshed result.
      scheduleCaptureProcessingRefresh(sessionId);
      setToast(appT("capture.toastCaptureDeletedUpdating"));
    },
    [apiFetch, appT, scheduleCaptureProcessingRefresh, setToast],
  );

  const restoreReportVersion = React.useCallback(
    async (sessionId: string, versionId: string) => {
      // Reverting to an older version soft-deletes the captures added after it (server-side de-effect,
      // shared with undo). Apply the returned report fields optimistically, then reconcile the authoritative
      // capture list + report via refreshVisibleSession (session_payload omits the items array).
      const updated = await restoreReportVersionRequest(apiFetch, sessionId, versionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? mergeSessionUpdate(session, updated) : session)));
      setActiveSession((current) => (current?.id === sessionId ? mergeSessionUpdate(current, updated) : current));
      await refreshVisibleSession(sessionId).catch(() => undefined);
      scheduleCaptureProcessingRefresh(sessionId);
      setToast(appT("capture.history.toastRestored"));
    },
    [apiFetch, appT, refreshVisibleSession, scheduleCaptureProcessingRefresh, setToast],
  );

  const markCaptureRelevantInSession = React.useCallback(
    async (sessionId: string, captureId: string) => {
      if (captureId.startsWith("local-capture-")) return;
      const updated = await markCaptureRelevant(apiFetch, captureId);
      const applyItem = (session: CaptureSession): CaptureSession =>
        session.id === sessionId
          ? { ...session, items: session.items.map((item) => (item.id === captureId ? { ...item, ...updated } : item)) }
          : session;
      setSessions((current) => current.map(applyItem));
      setActiveSession((current) => (current?.id === sessionId ? applyItem(current) : current));
      // Marking relevant re-folds the capture into the Pro live report; poll for the refresh.
      scheduleCaptureProcessingRefresh(sessionId);
      setToast(appT("capture.toastMarkedRelevant"));
    },
    [apiFetch, appT, scheduleCaptureProcessingRefresh, setToast],
  );

  const applySessionUpdate = React.useCallback((sessionId: string, updated: CaptureSession) => {
    setSessions((current) =>
      current.map((session) => (session.id === sessionId ? mergeSessionUpdate(session, updated) : session)),
    );
    setActiveSession((current) => (current?.id === sessionId ? mergeSessionUpdate(current, updated) : current));
  }, []);

  // Q3: clinician confirms a carried-forward dose; the report can then read Complete.
  const confirmCarriedForwardDose = React.useCallback(
    async (sessionId: string, key: string) => {
      try {
        const updated = await confirmCarriedForward(apiFetch, sessionId, key);
        applySessionUpdate(sessionId, updated);
        setToast(appT("capture.toastDoseConfirmed"));
      } catch {
        setToast(appT("capture.toastCouldNotConfirmDose"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  // Report thumbs rating → the AI-quality feedback harvester (eval golden-set; eval-epic §1b).
  // Fire-and-forget: a quiet "noted" toast, never blocks; failures are swallowed in postFeedback.
  const rateReport = React.useCallback(
    (sessionId: string, rating: number) => {
      void postFeedback(apiFetch, { kind: "rating", aiOutputType: "report", rating, sessionId });
    },
    [apiFetch],
  );

  // Resolve a citation's source capture by id when it isn't in the open session (a carried-forward
  // claim cites a prior visit) — for "tap a claim → its source capture".
  const fetchCaptureById = React.useCallback((captureId: string) => fetchCapture(apiFetch, captureId), [apiFetch]);

  // Aftercare opt-out: remove an auto-included clinic template from this visit (or re-add it).
  const dismissAftercareTemplate = React.useCallback(
    async (sessionId: string, templateId: string, dismissed: boolean) => {
      try {
        const updated = await setAftercareDismissed(apiFetch, sessionId, templateId, dismissed);
        applySessionUpdate(sessionId, updated);
      } catch {
        setToast(appT("capture.toastCouldNotUpdateAftercare"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  // Safety-flag opt-out: reject (×) an auto-kept safety flag this visit. Persisted, survives
  // re-synthesis, and removes the flag from the patient's cross-visit store (backend re-syncs).
  const rejectSafetyFlagFromSession = React.useCallback(
    async (sessionId: string, flagKey: string) => {
      try {
        const updated = await rejectSafetyFlag(apiFetch, sessionId, flagKey);
        applySessionUpdate(sessionId, updated);
      } catch {
        setToast(appT("capture.toastCouldNotUpdateSafetyFlag"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  // E1 one-tap: apply a `suggested_name_correction` chip — rename the assigned patient in place
  // (deterministic, no re-synthesis). Backend derives the rename from the spoken name + aliases.
  const applyPatientNameCorrection = React.useCallback(
    async (sessionId: string, spokenName: string, basisCaptureId?: string) => {
      try {
        const updated = await applyNameCorrection(apiFetch, sessionId, spokenName, basisCaptureId);
        applySessionUpdate(sessionId, updated);
        setToast(appT("capture.toastNameCorrected"));
      } catch {
        setToast(appT("capture.toastCouldNotCorrectName"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  // E1 one-tap: apply a `suggested_unassign` chip — clear the visit's patient via the assignment
  // choke point (drops the wrong patient's flags/carry-forward/reconcile server-side).
  const unassignPatientFromSession = React.useCallback(
    async (sessionId: string, basisCaptureId?: string) => {
      try {
        const updated = await applyUnassignSuggestion(apiFetch, sessionId, basisCaptureId);
        applySessionUpdate(sessionId, updated);
        setToast(appT("memory.toastVisitUnassigned"));
      } catch {
        setToast(appT("capture.toastCouldNotUnassign"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  // AES-1102/1103: a human field edit on a treatment row — deterministic + instant (no re-synthesis,
  // no AI budget). Authoritative on render; a later re-synthesis surfaces any disagreement, never
  // overwrites. Revert drops the overlay so the AI value returns.
  const editTreatmentField = React.useCallback(
    async (sessionId: string, treatmentKey: string, field: string, value: string) => {
      try {
        const updated = await editTreatmentOverlay(apiFetch, sessionId, treatmentKey, field, value);
        applySessionUpdate(sessionId, updated);
        setToast(appT("capture.toastTreatmentUpdated"));
      } catch {
        setToast(appT("capture.toastCouldNotUpdateTreatment"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  const revertTreatmentField = React.useCallback(
    async (sessionId: string, treatmentKey: string, field: string) => {
      try {
        const updated = await revertTreatmentOverlay(apiFetch, sessionId, treatmentKey, field);
        applySessionUpdate(sessionId, updated);
        setToast(appT("capture.toastTreatmentReverted"));
      } catch {
        setToast(appT("capture.toastCouldNotUpdateTreatment"));
      }
    },
    [apiFetch, appT, applySessionUpdate, setToast],
  );

  const ensurePatient = React.useCallback(
    async (draft: PatientAssignmentDraft): Promise<PatientSummary> => {
      if (draft.patientId) {
        return {
          id: draft.patientId,
          displayName: draft.displayName,
          nationalId: draft.nationalId || null,
        };
      }
      const matches = await searchPatients(apiFetch, draft.nationalId || draft.displayName);
      const normalizedName = draft.displayName.trim().toLowerCase();
      const normalizedNationalId = draft.nationalId?.trim();
      const exact = matches.find(
        (patient) =>
          patient.displayName.trim().toLowerCase() === normalizedName ||
          (normalizedNationalId && patient.nationalId === normalizedNationalId),
      );
      return exact || createPatient(apiFetch, draft);
    },
    [apiFetch],
  );

  // Stale-client self-heal: a patient a session/panel still references was deleted or merged away, so
  // a patient-scoped call 404s. Rather than freeze (the known incident: deleting a merged patient left
  // the AI-created "verify" panel PATCHing a dead id → 404 forever), clear the stale reference across
  // the caches, dismiss the verify panel for good, drop any queued assignment to that dead id so the
  // outbox stops looping, and tell the user calmly. Safe to call from any 404 catch.
  const selfHealStalePatient = React.useCallback(
    async (sessionId: string | undefined, deadPatientId?: string) => {
      // Drop a queued assignment to the vanished patient so the outbox stops retrying the 404.
      if (sessionId && authRef.current?.tenant.id) {
        await removePendingOperation(`${authRef.current.tenant.id}:patientAssignment:${sessionId}`).catch(() => {});
      }
      // Neutralize the AI-created-patient action server-side so the verify panel dismisses permanently.
      if (sessionId && !isLocalSessionId(sessionId)) {
        try {
          const cleared = await dismissAiPatientAction(apiFetch, sessionId);
          applySessionUpdate(sessionId, cleared);
        } catch (error) {
          // The session itself is gone too — evict it from the caches entirely.
          if (isNotFoundError(error)) {
            setSessions((current) => current.filter((session) => session.id !== sessionId));
            setActiveSession((current) => (current?.id === sessionId ? null : current));
            setSelectedSessionId((current) => (current === sessionId ? "" : current));
          }
        }
      }
      // Clear the stale patient reference from cached session(s) — the server already SET NULL the FK.
      setSessions((current) => stripStalePatientAcross(current, sessionId, deadPatientId));
      setActiveSession((current) =>
        current && (current.id === sessionId || (deadPatientId && current.patientId === deadPatientId)) ? stripPatientFromSession(current) : current,
      );
      setAssignmentSessionId((current) => (current === sessionId ? "" : current));
      setToast(appT("memory.toastPatientRecordGone"));
    },
    [apiFetch, appT, applySessionUpdate, authRef, setToast],
  );

  const assignPatientToSession = React.useCallback(
    async (sessionId: string, draft: PatientAssignmentDraft, options?: { successMessage?: string }) => {
      if (draft.unassign) {
        setSessions((current) => current.map((session) => (session.id === sessionId ? stripPatientFromSession(session) : session)));
        setActiveSession((current) => (current?.id === sessionId ? stripPatientFromSession(current) : current));
        setAssignmentSessionId("");
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:patientAssignment:${sessionId}`,
            type: "patientAssignment",
            localSessionId: sessionId,
            backendSessionId: isLocalSessionId(sessionId) ? undefined : sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { unassign: true },
          });
        }
        setToast(appT("memory.toastVisitUnassigned"));
        void processOutbox();
        return;
      }
      const localPatient: PatientSummary = draft.patientId && !isLocalAssignmentPatient(draft.patientId)
        ? { id: draft.patientId, displayName: draft.displayName, nationalId: draft.nationalId || null }
        : {
            id: draft.patientId || `local-patient-${createClientId()}`,
            displayName: draft.displayName,
            nationalId: draft.nationalId || null,
          };
      const successMessage = options?.successMessage || `Visit assigned to ${draft.displayName}.`;
      const applyLocalAssignment = (patient: PatientSummary) => {
        setSessions((current) =>
          current.map((session) => (session.id === sessionId ? applyStaffAssignment(session, patient) : session)),
        );
        setActiveSession((current) => (current?.id === sessionId ? applyStaffAssignment(current, patient) : current));
        setAssignmentSessionId("");
      };
      const enqueueAssignment = async (patient: PatientSummary) => {
        if (!authRef.current?.tenant.id) return;
        await queueOperation({
          id: `${authRef.current.tenant.id}:patientAssignment:${sessionId}`,
          type: "patientAssignment",
          localSessionId: sessionId,
          backendSessionId: isLocalSessionId(sessionId) ? undefined : sessionId,
          localPatientId: patient.id.startsWith("local-patient-") ? patient.id : undefined,
          backendPatientId: patient.id.startsWith("local-patient-") || isLocalAssignmentPatient(patient.id) ? undefined : patient.id,
          tenantId: authRef.current.tenant.id,
          payload: {
            patientId: patient.id,
            displayName: patient.displayName,
            nationalId: patient.nationalId || undefined,
            basisCaptureId: draft.basisCaptureId,
          },
        });
      };

      if (isLocalSessionId(sessionId) || !navigator.onLine) {
        applyLocalAssignment(localPatient);
        await enqueueAssignment(localPatient);
        setToast(successMessage);
        void processOutbox();
        return;
      }

      try {
        const patient = await ensurePatient(draft);
        if (isLocalSessionId(sessionId) || isLocalAssignmentPatient(patient.id)) {
          applyLocalAssignment(patient);
          await enqueueAssignment(patient);
          setToast(options?.successMessage || `Visit assigned to ${patient.displayName}.`);
          return;
        }
        const assigned = await assignSessionPatient(apiFetch, sessionId, patient.id, undefined, draft.basisCaptureId);
        const enriched = {
          ...assigned,
          patientId: patient.id,
          patientName: patient.displayName,
          assignmentSource: "staff",
        };
        setSessions((current) =>
          current.map((session) =>
            session.id === sessionId ? markReportStaleForPatientChange(session, mergeSessionUpdate(session, enriched)) : session,
          ),
        );
        setActiveSession((current) =>
          current?.id === sessionId ? markReportStaleForPatientChange(current, mergeSessionUpdate(current, enriched)) : current,
        );
        setAssignmentSessionId("");
        setToast(options?.successMessage || `Visit assigned to ${patient.displayName}.`);
      } catch (error) {
        // The chosen patient was deleted/merged: queuing the assignment would 404 forever in the
        // outbox — self-heal the stale reference and let the user pick again instead.
        if (isNotFoundError(error)) {
          await selfHealStalePatient(sessionId, localPatient.id);
          return;
        }
        // Otherwise treat as a transient/offline failure: keep the local assignment and queue it.
        applyLocalAssignment(localPatient);
        await enqueueAssignment(localPatient);
        setToast(successMessage);
        void processOutbox();
      }
    },
    [apiFetch, appT, authRef, ensurePatient, processOutbox, queueOperation, selfHealStalePatient, setToast],
  );

  const searchPatientsForAssignment = React.useCallback((query: string) => searchPatients(apiFetch, query), [apiFetch]);

  const fetchAssignedPatientDetails = React.useCallback(
    (patientId: string): Promise<StructuredPatientInformation | null> =>
      isLocalAssignmentPatient(patientId) ? Promise.resolve(null) : getPatient(apiFetch, patientId).catch(() => null),
    [apiFetch],
  );

  const completeAiCreatedPatient = React.useCallback(
    async (
      sessionId: string,
      patientId: string,
      draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
      action: Record<string, unknown>,
    ) => {
      try {
        const patient = await updatePatient(apiFetch, patientId, {
          displayName: draft.displayName,
          nationalId: draft.nationalId || null,
          phone: draft.phone || null,
          dateOfBirth: draft.dateOfBirth || null,
          sex: draft.sex || null,
          notes: draft.notes || null,
        });
        const verifiedSession = await verifyAiPatientCreation(apiFetch, sessionId, {
          ...action,
          displayName: patient.displayName,
          patientId: patient.id,
        });
        const enriched = { ...verifiedSession, patientId: patient.id, patientName: patient.displayName };
        setSessions((current) => current.map((session) => (session.id === sessionId ? mergeSessionUpdate(session, enriched) : session)));
        setActiveSession((current) => (current?.id === sessionId ? mergeSessionUpdate(current, enriched) : current));
        setToast(appT("memory.toastAiPatientVerified"));
      } catch (error) {
        // The AI-created patient was deleted/merged out from under the panel: self-heal instead of
        // leaving the verify panel frozen on a dead id (the known incident).
        if (isNotFoundError(error)) {
          await selfHealStalePatient(sessionId, patientId);
          return;
        }
        throw error;
      }
    },
    [apiFetch, appT, selfHealStalePatient, setToast],
  );

  const editPatientDetails = React.useCallback(
    async (patientId: string, draft: PatientEditDraft) => {
      const patient = await updatePatient(apiFetch, patientId, draft);
      if (draft.displayName) {
        setSessions((current) =>
          current.map((session) => (session.patientId === patientId ? { ...session, patientName: patient.displayName } : session)),
        );
        setActiveSession((current) => (current?.patientId === patientId ? { ...current, patientName: patient.displayName } : current));
      }
      setToast(appT("memory.toastPatientDetailsUpdated"));
    },
    [apiFetch, appT, setToast],
  );

  const createNewPatient = React.useCallback(
    async (draft: PatientAssignmentDraft): Promise<PatientSummary | null> => {
      try {
        const patient = await createPatient(apiFetch, draft);
        setToast(appT("memory.toastPatientCreated"));
        return patient;
      } catch {
        setToast(appT("memory.toastCouldNotCreatePatient"));
        return null;
      }
    },
    [apiFetch, appT, setToast],
  );

  const confirmSessionSummary = React.useCallback(
    async (sessionId: string, summary: string) => {
      // Completion is now auto-derived (captures processed + patient assigned + report current),
      // so confirming a summary just records the edited summary locally — there is no manual verify.
      const applyConfirmedSummary = (session: CaptureSession): CaptureSession => {
        const now = new Date().toISOString();
        return {
          ...session,
          summary,
          reviewReason: "",
          updatedAt: now,
          summaries: {
            schemaVersion: session.summaries?.schemaVersion,
            status: session.summaries?.status || "processed",
            short: summary,
            clinical: session.summaries?.clinical || null,
            patientHistory: session.summaries?.patientHistory || summary,
            source: session.summaries?.source || "staff",
            generatedAt: session.summaries?.generatedAt || now,
            updatedAt: now,
          },
        };
      };
      setSessions((current) => current.map((session) => (session.id === sessionId ? applyConfirmedSummary(session) : session)));
      setActiveSession((current) => (current?.id === sessionId ? applyConfirmedSummary(current) : current));
      setToast(appT("memory.toastSummaryAdded"));
    },
    [appT, setToast],
  );

  const loadCapturesForSession = React.useCallback(
    async (sessionId: string) => {
      const captures = await fetchSessionCaptures(apiFetch, sessionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? { ...session, items: captures } : session)));
      return captures;
    },
    [apiFetch],
  );

  const editCaptureNote = React.useCallback(
    async (sessionId: string, captureId: string, text: string) => {
      const editedAt = new Date().toISOString();
      const editorName = authRef.current?.user.displayName || authRef.current?.user.email || "You";
      const applyItem = (item: CaptureItem): CaptureItem =>
        item.id === captureId
          ? {
              ...item,
              detail: text,
              metadata: { ...(item.metadata || {}), note: { text, source: "staff_edit", edited_at: editedAt, edited_by_name: editorName } },
            }
          : item;
      const applySession = (session: CaptureSession): CaptureSession =>
        session.id === sessionId ? { ...session, items: session.items.map(applyItem) } : session;
      if (captureId.startsWith("local-capture-")) {
        setSessions((current) => current.map(applySession));
        setActiveSession((current) => (current?.id === sessionId ? applySession(current) : current));
        await updatePendingCapture(captureId, (current) => ({ ...current, item: applyItem(current.item), session: applySession(current.session) }));
        setToast(appT("memory.toastNoteUpdated"));
        return;
      }
      const updated = await updateCaptureNote(apiFetch, captureId, text);
      const merge = (item: CaptureItem): CaptureItem => (item.id === captureId ? { ...item, ...updated, detail: text } : item);
      const mergeSession = (session: CaptureSession): CaptureSession =>
        session.id === sessionId ? { ...session, items: session.items.map(merge) } : session;
      setSessions((current) => current.map(mergeSession));
      setActiveSession((current) => (current?.id === sessionId ? mergeSession(current) : current));
      setToast(appT("memory.toastNoteUpdated"));
    },
    [apiFetch, appT, authRef, setToast],
  );

  // The port the outbox engine reads/writes through. STABLE (delegates to stable actions + refs), so
  // App's SyncBridge can point at it without churning the engine. `notifyAiPatientAction` runs inside
  // refreshVisibleSession — the sink only needs the fields the engine calls.
  const sessionSink = React.useMemo<SessionSink>(
    () => ({
      getSessions: () => sessionsRef.current,
      getActiveSession: () => activeSessionRef.current,
      setSessions: (update) => setSessions(update),
      setActiveSession: (update) => setActiveSession(update),
      setSelectedSessionId: (update) => setSelectedSessionId(update),
      upsertSession: (session, removeIds) => upsertSession(session, removeIds),
      updateItemStatus: (itemId, status) => updateItemStatus(itemId, status),
      applySessionUpdate: (sessionId, updated) => applySessionUpdate(sessionId, updated),
      selfHealStalePatient: (sessionId, deadPatientId) => selfHealStalePatient(sessionId, deadPatientId),
      scheduleCaptureProcessingRefresh: (sessionId) => scheduleCaptureProcessingRefresh(sessionId),
      scheduleSessionProcessingRefresh: (sessionId) => scheduleSessionProcessingRefresh(sessionId),
      scheduleMemoryRefresh: () => scheduleMemoryRefresh(),
    }),
    [
      applySessionUpdate,
      scheduleCaptureProcessingRefresh,
      scheduleMemoryRefresh,
      scheduleSessionProcessingRefresh,
      selfHealStalePatient,
      updateItemStatus,
      upsertSession,
    ],
  );

  const actions = React.useMemo<SessionActions>(
    () => ({
      setSessions,
      setActiveSession,
      setSelectedSessionId,
      setAssignmentSessionId,
      upsertSession,
      applySessionUpdate,
      saveSession,
      renameSession,
      renameCapture,
      editCaptureSourceText,
      editCaptureNote,
      removeCaptureFromSession,
      restoreReportVersion,
      markCaptureRelevantInSession,
      confirmCarriedForwardDose,
      rateReport,
      fetchCaptureById,
      dismissAftercareTemplate,
      rejectSafetyFlagFromSession,
      applyPatientNameCorrection,
      unassignPatientFromSession,
      editTreatmentField,
      revertTreatmentField,
      selfHealStalePatient,
      assignPatientToSession,
      searchPatientsForAssignment,
      fetchAssignedPatientDetails,
      completeAiCreatedPatient,
      editPatientDetails,
      createNewPatient,
      confirmSessionSummary,
      loadCapturesForSession,
      scheduleCaptureProcessingRefresh,
      scheduleSessionProcessingRefresh,
      scheduleMemoryRefresh,
      sessionSink,
    }),
    [
      upsertSession,
      applySessionUpdate,
      saveSession,
      renameSession,
      renameCapture,
      editCaptureSourceText,
      editCaptureNote,
      removeCaptureFromSession,
      restoreReportVersion,
      markCaptureRelevantInSession,
      confirmCarriedForwardDose,
      rateReport,
      fetchCaptureById,
      dismissAftercareTemplate,
      rejectSafetyFlagFromSession,
      applyPatientNameCorrection,
      unassignPatientFromSession,
      editTreatmentField,
      revertTreatmentField,
      selfHealStalePatient,
      assignPatientToSession,
      searchPatientsForAssignment,
      fetchAssignedPatientDetails,
      completeAiCreatedPatient,
      editPatientDetails,
      createNewPatient,
      confirmSessionSummary,
      loadCapturesForSession,
      scheduleCaptureProcessingRefresh,
      scheduleSessionProcessingRefresh,
      scheduleMemoryRefresh,
      sessionSink,
    ],
  );

  const state = React.useMemo<SessionState>(
    () => ({ sessions, activeSession, selectedSessionId, assignmentSessionId, memoryRefreshSignal }),
    [sessions, activeSession, selectedSessionId, assignmentSessionId, memoryRefreshSignal],
  );

  return (
    <SessionActionsContext.Provider value={actions}>
      <SessionStateContext.Provider value={state}>{children}</SessionStateContext.Provider>
    </SessionActionsContext.Provider>
  );
}

function useSessionStateContext(): SessionState {
  const ctx = React.useContext(SessionStateContext);
  if (!ctx) throw new Error("useSessionState must be used within SessionStoreProvider");
  return ctx;
}

/** The stable session action surface (setters + mutations + the outbox sink). Never re-renders on data churn. */
export function useSessionActions(): SessionActions {
  const ctx = React.useContext(SessionActionsContext);
  if (!ctx) throw new Error("useSessionActions must be used within SessionStoreProvider");
  return ctx;
}

/** The full session list (volatile — re-renders on any session change). */
export function useSessions(): CaptureSession[] {
  return useSessionStateContext().sessions;
}

/** The active capture session (volatile). */
export function useActiveSession(): CaptureSession | null {
  return useSessionStateContext().activeSession;
}

/** The post-capture memory-refresh signal (bumped over the processing delay ladder). */
export function useMemoryRefreshSignal(): number {
  return useSessionStateContext().memoryRefreshSignal;
}

/**
 * The whole store as one object (state + actions) — for App's composition root, which destructures it
 * back into the local names its render body + navigation helpers already use. Feature screens should
 * prefer the narrower `useSessions()` / `useActiveSession()` / `useSessionActions()` seams.
 */
export function useSessionStore(): SessionState & SessionActions {
  return { ...useSessionStateContext(), ...useSessionActions() };
}
