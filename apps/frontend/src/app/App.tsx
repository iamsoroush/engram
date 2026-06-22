import React from "react";
import { flushSync } from "react-dom";
import type {
  ApiFetch,
  AftercareTemplate,
  AuthSession,
  CaptureDraft,
  DevTier,
  LineupCard,
  PatientAssignmentDraft,
  PatientMemoryFilter,
  PatientMemoryListResponse,
  PatientSummary,
  PendingOperation,
  Persona,
  RolePermissions,
  SessionContext,
  SyncHealth,
} from "../domain/appTypes";
import type { CaptureItem, CaptureSession, CaptureStatus, Screen } from "../domain/types";
import { Card, Skeleton, Toast } from "../shared/ui/primitives";
import { currentUserRoles, isSessionReadOnly } from "../shared/lib/multiseat";
import { setAppLanguage } from "../shared/lib/datetime";
import {
  assignSessionPatient,
  confirmCarriedForward,
  unassignSessionPatient,
  checkDuplicatePatient,
  createAftercareTemplate,
  createPatient,
  createPatientShare,
  deleteAftercareTemplate,
  deleteCapture,
  fetchAiModels,
  fetchAssignmentSuggestion,
  cancelWorklistEntry,
  createSession,
  createWorklistEntry,
  fetchClinicMembers,
  fetchLastVisit,
  fetchSessionContext,
  fetchWorklist,
  getPatient,
  listAftercareTemplates,
  markWorklistEntrySeen,
  revokePatientShare,
  searchPatientsSmart,
  updateAftercareTemplate,
  fetchPatientMemory,
  fetchPatientMemoryDetail,
  fetchSession,
  fetchSessionCaptures,
  fetchSessions,
  loginWithPassword,
  loginWithPersona,
  logoutSession,
  markCaptureRelevant,
  refreshAuthToken,
  resolveCaptureFileUrl,
  saveSessionForProcessing,
  searchPatients,
  storeBackendMappings,
  updateCaptureCaption,
  updateCaptureNote,
  updateCaptureTitle,
  updateCaptureTranscript,
  updatePatient,
  type PatientEditDraft,
  updateAiModels,
  updateSessionTitle,
  updateTenantSettings,
  uploadCapture,
  verifyAiPatientCreation,
} from "../services/api/client";
import { standardizeCaptureDraft } from "../features/capture/audio";
import { clearStoredAuthProfile, loadStoredAuthProfile, persistAuthProfile } from "../services/storage/authStorage";
import {
  isLocalSessionId,
  makeLocalCapture,
  mergeCaptureItemsPreservingPreview,
  mergeSessionItems,
  sessionWithLocalPreview,
  sessionsFromPending,
} from "../features/capture/captureModel";
import { ProfileScreen, SettingsScreen } from "../features/account/AccountScreens";
import { SharePatientSheet } from "../features/aesthetics/SharePatientSheet";
import type { GalleryVisit } from "../features/aesthetics/PatientPhotoGallery";
import { LoginGate, PatientPreviewGate } from "../features/auth/AuthGates";
import { TherapyApp } from "../features/therapy/TherapyApp";
import { AddPhotoSheet, AudioDialog, TextCaptureSheet } from "../features/capture/components/CaptureDialogs";
import { CaptureScreen } from "../features/capture/components/CaptureScreen";
import { StorageGuardDialog } from "../features/capture/components/StorageGuardDialog";
import { metadataRecord } from "../features/capture/metadata";
import { CaptureDestinationPanel, PatientsHome, SearchHome, type ClinicalMemoryReturnContext } from "../features/memory/components/MemoryScreens";
import { DoctorQaInbox } from "../features/qa/DoctorQaInbox";
import { fetchQaInbox, openQaChannel } from "../features/qa/qaClient";
import { Shell } from "../features/shell/Shell";
import {
  bindPendingSession,
  clearLocalCaptureData,
  loadIdMapping,
  loadPendingCapture,
  loadPendingCaptures,
  loadPendingOperations,
  normalizePendingCapture,
  removePendingCapture,
  removePendingOperation,
  savePendingCapture,
  savePendingOperation,
  saveSyncedCaptureCache,
  updatePendingCapture,
  updatePendingOperation,
} from "../services/storage/captureStorage";
import { exportPendingCaptures } from "../services/storage/exportCaptures";
import { estimateStorageStatus, OK_STORAGE_STATUS, type StorageStatus } from "../services/storage/storageStatus";
import { clearWorkspaceState, loadWorkspaceState, persistWorkspaceState } from "../services/storage/workspaceStorage";
import { replaceScreenLocation, screenFromLocation } from "./navigation";
import {
  makeEmptyLocalSession,
  markReportStaleForCaptureChange,
  markReportStaleForPatientChange,
  mergeSessionUpdate,
  PROCESSING_REFRESH_DELAYS,
  resolveRestoredSession,
} from "./sessionState";

// E9 — where a freshly signed-in user lands. Doctors capture-first → the Session workspace;
// reception (assistant) and admins coordinate → Clinical Memory (worklist, patients, needs-input).
function defaultScreenForAuth(auth: AuthSession): Screen {
  const roles = auth.memberships.filter((m) => m.tenantId === auth.tenant.id).map((m) => m.role);
  const effective = roles.length ? roles : auth.user.persona ? [String(auth.user.persona)] : [];
  if (effective.includes("doctor")) return "active-session";
  if (effective.includes("assistant") || effective.includes("admin")) return "patients";
  return "active-session";
}

function sessionNeedsProcessingRefresh(session: CaptureSession | null) {
  if (!session) return false;
  if (session.processingStatus?.state === "processing" || session.report?.status === "generating") return true;
  return session.items.some((item) => item.status === "uploaded" || item.status === "processing" || item.status === "uploading");
}

export function App() {
  const [auth, setAuth] = React.useState<AuthSession | null>(null);
  // Drive app-wide UI language + date formatting (Jalali when Persian) from the tenant's APP
  // language — distinct from report language, which scopes only report/share content.
  setAppLanguage(auth?.tenant.appLanguage ?? null);
  const [authReady, setAuthReady] = React.useState(false);
  const [authError, setAuthError] = React.useState("");
  const authRef = React.useRef<AuthSession | null>(null);
  const refreshPromiseRef = React.useRef<Promise<string> | null>(null);
  const bootstrappedAuthRef = React.useRef(false);
  const [screen, setScreen] = React.useState<Screen>(() => screenFromLocation());
  const [qaPendingCount, setQaPendingCount] = React.useState(0);
  const [sessions, setSessions] = React.useState<CaptureSession[]>([]);
  const [activeSession, setActiveSession] = React.useState<CaptureSession | null>(null);
  const [selectedSessionId, setSelectedSessionId] = React.useState("");
  const [pendingCount, setPendingCount] = React.useState(0);
  const [pendingOperationCount, setPendingOperationCount] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [online, setOnline] = React.useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [backendReachable, setBackendReachable] = React.useState<boolean | null>(null);
  const [syncError, setSyncError] = React.useState("");
  const [textOpen, setTextOpen] = React.useState(false);
  const [textSeed, setTextSeed] = React.useState("");
  const [photoOpen, setPhotoOpen] = React.useState(false);
  const [audioOpen, setAudioOpen] = React.useState(false);
  // AES-106 — the active patient's prior visit (note + photos), surfaced at capture in Basic.
  const [sessionContext, setSessionContext] = React.useState<SessionContext | null>(null);
  const [aftercareTemplates, setAftercareTemplates] = React.useState<AftercareTemplate[]>([]);
  // Pro only: the active patient's Job-4 curated brief (line-up projection), surfaced in the session
  // context card so Pro reads as a compact pre-visit brief instead of the raw deterministic digest.
  const [sessionLineupCard, setSessionLineupCard] = React.useState<LineupCard | null>(null);
  // Per-visit share, opened from the session screen (FB6) — curates THIS visit's report.
  const [sessionShare, setSessionShare] = React.useState<{ id: string; name: string; visits: GalleryVisit[] } | null>(null);
  const [ghostPhotoUrl, setGhostPhotoUrl] = React.useState("");
  const [storage, setStorage] = React.useState<StorageStatus>(OK_STORAGE_STATUS);
  const [storageGuardOpen, setStorageGuardOpen] = React.useState(false);
  const [pendingCaptureKind, setPendingCaptureKind] = React.useState<CaptureDraft["kind"] | null>(null);
  // E9 — the patient whose file is open in Clinical Memory. While set (and on the patients screen),
  // the footer captures *for that patient* (a new visit). Cleared when the detail closes or the
  // screen changes, so the target naturally reverts to the active session.
  const [viewedPatient, setViewedPatient] = React.useState<{ id: string; name: string } | null>(null);
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const [toast, setToast] = React.useState("");
  const [clinicalMemoryReturnContext, setClinicalMemoryReturnContext] = React.useState<ClinicalMemoryReturnContext | null>(null);
  // Round-trip: the in-progress capture visit stashed when the clinician jumps to the patient
  // timeline from the session, so "← Back to this visit" restores it exactly (no lost place).
  const [captureReturnSession, setCaptureReturnSession] = React.useState<CaptureSession | null>(null);
  const processingRef = React.useRef(false);
  const workspaceHydratedRef = React.useRef(false);
  const activeSessionRef = React.useRef<CaptureSession | null>(null);
  const sessionsRef = React.useRef<CaptureSession[]>([]);
  const accountReturnRef = React.useRef<Screen>("active-session");
  const aiPatientToastIdsRef = React.useRef(new Set<string>());

  React.useEffect(() => {
    activeSessionRef.current = activeSession;
  }, [activeSession]);

  React.useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  const navigateScreen = React.useCallback((nextScreen: Screen) => {
    setScreen(nextScreen);
    replaceScreenLocation(nextScreen);
    if (nextScreen === "active-session") setSelectedSessionId("");
  }, []);

  const clearAuth = React.useCallback(() => {
    authRef.current = null;
    setAuth(null);
    clearStoredAuthProfile();
    clearWorkspaceState();
    processingRef.current = false;
    workspaceHydratedRef.current = false;
  }, []);

  const commitAuth = React.useCallback((nextAuth: AuthSession) => {
    authRef.current = nextAuth;
    setAuth(nextAuth);
    persistAuthProfile(nextAuth);
    setAuthError("");
  }, []);

  const refreshAccessToken = React.useCallback(async () => {
    const currentAuth = authRef.current;
    if (!currentAuth) throw new Error("No auth session");
    if (!refreshPromiseRef.current) {
      refreshPromiseRef.current = refreshAuthToken(currentAuth.refreshToken)
        .then((tokens) => {
          const refreshed = { ...currentAuth, ...tokens };
          commitAuth(refreshed);
          return refreshed.accessToken;
        })
        .catch((error) => {
          clearAuth();
          throw error;
        })
        .finally(() => {
          refreshPromiseRef.current = null;
        });
    }
    return refreshPromiseRef.current;
  }, [clearAuth, commitAuth]);

  /**
   * Adds the current bearer token to API requests and performs a single token
   * refresh/retry when the backend responds with 401.
   */
  const apiFetch = React.useCallback<ApiFetch>(
    async (input, init = {}) => {
      const token = authRef.current?.accessToken;
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);

      const response = await fetch(input, { ...init, headers });
      if (response.status !== 401) return response;

      try {
        const nextToken = await refreshAccessToken();
        const retryHeaders = new Headers(init.headers);
        retryHeaders.set("Authorization", `Bearer ${nextToken}`);
        return await fetch(input, { ...init, headers: retryHeaders });
      } catch {
        return response;
      }
    },
    [refreshAccessToken],
  );

  // Pending-question count for the top-bar Q&A inbox badge (Pro only). Refreshed on login and
  // whenever the inbox loads or the doctor sends/dismisses (the inbox calls onChanged → here).
  const refreshQaPendingCount = React.useCallback(() => {
    if (!auth || auth.tenant.tier === "basic") {
      setQaPendingCount(0);
      return;
    }
    fetchQaInbox(apiFetch, "mine")
      .then((response) => setQaPendingCount(response.total))
      .catch(() => undefined);
  }, [apiFetch, auth]);

  React.useEffect(() => {
    refreshQaPendingCount();
  }, [refreshQaPendingCount]);

  React.useEffect(() => {
    if (bootstrappedAuthRef.current) return;
    bootstrappedAuthRef.current = true;
    const storedAuth = loadStoredAuthProfile();
    if (!storedAuth) {
      setAuthReady(true);
      return;
    }
    refreshAuthToken(storedAuth.refreshToken)
      .then((tokens) => commitAuth({ ...storedAuth, ...tokens }))
      .catch(() => clearAuth())
      .finally(() => setAuthReady(true));
  }, [clearAuth, commitAuth]);

  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview") return;
    void hydrateFromStorage();
    void navigator.storage?.persist?.();
    void refreshStorage();
  }, [auth]);

  React.useEffect(() => {
    if (auth) return;
    void refreshPendingCount();
  }, [auth]);

  React.useEffect(() => {
    if (!auth || !workspaceHydratedRef.current) return;
    persistWorkspaceState({
      tenantId: auth.tenant.id,
      screen,
      activeSession,
      selectedSessionId,
      assignmentSessionId,
      pendingCaptureKind,
    });
  }, [activeSession, assignmentSessionId, auth, pendingCaptureKind, screen, selectedSessionId]);

  React.useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  React.useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine);
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
    };
  }, []);

  React.useEffect(() => {
    const syncScreenFromLocation = () => {
      const nextScreen = screenFromLocation();
      setScreen(nextScreen);
      if (nextScreen === "active-session") setSelectedSessionId("");
    };
    window.addEventListener("hashchange", syncScreenFromLocation);
    return () => window.removeEventListener("hashchange", syncScreenFromLocation);
  }, []);

  React.useEffect(() => {
    const warnIfPending = (event: BeforeUnloadEvent) => {
      if (!pendingCount && !pendingOperationCount) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnIfPending);
    return () => window.removeEventListener("beforeunload", warnIfPending);
  }, [pendingCount, pendingOperationCount]);

  React.useEffect(() => {
    const retryWhenOnline = () => void processOutbox();
    window.addEventListener("online", retryWhenOnline);
    return () => window.removeEventListener("online", retryWhenOnline);
  }, []);

  const refreshStorage = React.useCallback(async () => {
    setStorage(await estimateStorageStatus());
  }, []);

  const refreshPendingCount = async () => {
    const [pending, operations] = await Promise.all([loadPendingCaptures(), loadPendingOperations()]);
    setPendingCount(pending.length);
    setPendingOperationCount(operations.length);
    void refreshStorage();
    return pending;
  };

  // Export queued (unsynced) captures to disk — the durability escape hatch (Epic G).
  const exportQueuedCaptures = React.useCallback(async () => {
    const pending = await loadPendingCaptures();
    if (!pending.length) {
      setToast("No queued captures to export.");
      return;
    }
    try {
      const count = await exportPendingCaptures(pending, new Date().toISOString());
      setToast(`Exported ${count} queued capture${count === 1 ? "" : "s"}.`);
    } catch {
      setToast("Could not export queued captures.");
    }
  }, []);

  const queueOperation = async (operation: Omit<PendingOperation, "retryCount" | "status" | "createdAt" | "updatedAt">) => {
    const now = Date.now();
    await savePendingOperation({
      ...operation,
      retryCount: 0,
      status: "pending",
      createdAt: now,
      updatedAt: now,
    });
    await refreshPendingCount();
  };

  const loadBackendSessions = React.useCallback(async () => {
    const loadedSessions = await fetchSessions(apiFetch);
    try {
      const patients = await searchPatients(apiFetch, "");
      const patientNameById = new Map(patients.map((patient) => [patient.id, patient.displayName]));
      return loadedSessions.map((session) =>
        session.patientId && !session.patientName
          ? { ...session, patientName: patientNameById.get(session.patientId) || `Patient ${session.patientId.slice(0, 8)}` }
          : session,
      );
    } catch {
      return loadedSessions;
    }
  }, [apiFetch]);

  /**
   * Rebuilds the visible session list from durable local captures first, then
   * layers backend sessions on top so offline work is never hidden by a failed load.
   */
  const hydrateFromStorage = async () => {
    const pending = await refreshPendingCount();
    const localSessions = sessionsFromPending(pending);
    const workspace = loadWorkspaceState(authRef.current?.tenant.id);
    try {
      const loadedSessions = await loadBackendSessions();
      setBackendReachable(true);
      const nextSessions = [
        ...loadedSessions.map((session) => {
          const localSession = localSessions.find((local) => local.id === session.id);
          if (!localSession) return session;
          return mergeSessionUpdate(
            localSession,
            session,
            mergeCaptureItemsPreservingPreview(localSession.items, session.items),
          );
        }),
        ...localSessions.filter((local) => !loadedSessions.some((session) => session.id === local.id)),
      ];
      setSessions(nextSessions);
      if (workspace) {
        setActiveSession(resolveRestoredSession(workspace.activeSession, nextSessions));
        setSelectedSessionId(workspace.selectedSessionId);
        setAssignmentSessionId(workspace.assignmentSessionId);
        setPendingCaptureKind(workspace.pendingCaptureKind);
        if (!window.location.hash && ["active-session", "patients", "search"].includes(workspace.screen)) {
          navigateScreen(workspace.screen as Screen);
        }
      }
    } catch {
      setBackendReachable(false);
      setSessions(localSessions);
      if (workspace) {
        setActiveSession(resolveRestoredSession(workspace.activeSession, localSessions));
        setSelectedSessionId(workspace.selectedSessionId);
        setAssignmentSessionId(workspace.assignmentSessionId);
        setPendingCaptureKind(workspace.pendingCaptureKind);
      }
      setToast("Offline · Captures are saved on this device.");
    } finally {
      workspaceHydratedRef.current = true;
    }
    if (pending.length) window.setTimeout(() => void processOutbox(), 0);
  };

  const updateItemStatus = (itemId: string, status: CaptureStatus) => {
    setActiveSession((session) =>
      session
        ? {
            ...session,
            items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
          }
        : session,
    );
    setSessions((current) =>
      current.map((session) => ({
        ...session,
        items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
      })),
    );
  };

  const upsertSession = (session: CaptureSession, removeIds: string[] = []) => {
    setSessions((current) => [
      session,
      ...current.filter((currentSession) => currentSession.id !== session.id && !removeIds.includes(currentSession.id)),
    ]);
  };

  const notifyAiPatientAction = React.useCallback((session: CaptureSession) => {
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
  }, []);

  const rebuildLocalPendingSessions = async () => {
    const pending = await loadPendingCaptures();
    const localSessions = sessionsFromPending(pending);
    setSessions((current) => [
      ...localSessions,
      ...current.filter((session) => !localSessions.some((localSession) => localSession.id === session.id)),
    ]);
  };

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
  const [memoryRefreshSignal, setMemoryRefreshSignal] = React.useState(0);
  const scheduleMemoryRefresh = React.useCallback(() => {
    PROCESSING_REFRESH_DELAYS.forEach((delay) => {
      window.setTimeout(() => setMemoryRefreshSignal((value) => value + 1), delay);
    });
  }, []);

  React.useEffect(() => {
    if (!activeSession?.id || isLocalSessionId(activeSession.id) || !sessionNeedsProcessingRefresh(activeSession)) return;
    const refreshTimer = window.setTimeout(() => {
      void refreshVisibleSession(activeSession.id).catch(() => undefined);
    }, 15000);
    return () => window.clearTimeout(refreshTimer);
  }, [activeSession, refreshVisibleSession]);

  // When a patient is determined for the active session (manual assign OR AI match), fetch the
  // deterministic session context — last-visit digest + cross-visit photo strip + key facts — so the
  // context card can surface it in BOTH tiers (Pro is no longer blank here; the intelligent window
  // layers on top later). Also resolve the prior visit's first photo as a ghost overlay (AES-105) for
  // the next shot, kept Basic-only. Deterministic retrieval — no AI.
  const patientId = activeSession?.patientId;
  const activeSessionId = activeSession?.id;
  const isBasicTier = auth?.tenant.tier === "basic";
  React.useEffect(() => {
    if (!patientId || isLocalAssignmentPatient(patientId)) {
      setSessionContext(null);
      setGhostPhotoUrl("");
      return;
    }
    let cancelled = false;
    void fetchSessionContext(apiFetch, patientId, activeSessionId && !isLocalSessionId(activeSessionId) ? activeSessionId : undefined)
      .then((context) => {
        if (cancelled) return;
        setSessionContext(context);
        const firstPhoto = context.lastVisit.visit?.media?.[0];
        const ghostEndpoint = isBasicTier ? firstPhoto?.contentEndpoint || firstPhoto?.fileEndpoint : null;
        if (ghostEndpoint) {
          void resolveCaptureFileUrl(apiFetch, ghostEndpoint)
            .then((url) => {
              if (!cancelled) setGhostPhotoUrl(url);
            })
            .catch(() => undefined);
        } else {
          setGhostPhotoUrl("");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSessionContext(null);
          setGhostPhotoUrl("");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiFetch, isBasicTier, patientId, activeSessionId]);

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

  const resolveBackendSessionId = async (operation: PendingOperation, tenantId: string) => {
    if (operation.backendSessionId) return operation.backendSessionId;
    if (!operation.localSessionId) return undefined;
    if (!isLocalSessionId(operation.localSessionId)) return operation.localSessionId;
    return (await loadIdMapping(`${tenantId}:session:${operation.localSessionId}`))?.backendId;
  };

  const syncPendingOperation = async (operation: PendingOperation, tenantId: string) => {
    const backendSessionId = await resolveBackendSessionId(operation, tenantId);
    if (!backendSessionId) return false;

    await updatePendingOperation(operation.id, (current) => ({
      ...current,
      status: "syncing",
      updatedAt: Date.now(),
      lastError: undefined,
    }));

    if (operation.type === "sessionTitle") {
      const title = typeof operation.payload.title === "string" ? operation.payload.title : "";
      if (title.trim()) {
        const updated = await updateSessionTitle(apiFetch, backendSessionId, title.trim());
        applySessionUpdate(backendSessionId, updated);
      }
    }

    if (operation.type === "patientAssignment") {
      if (operation.payload.unassign === true) {
        if (backendSessionId) {
          const unassigned = await unassignSessionPatient(apiFetch, backendSessionId, operation.id);
          applySessionUpdate(backendSessionId, unassigned);
        }
      } else {
        const draft = {
          patientId: typeof operation.payload.patientId === "string" ? operation.payload.patientId : undefined,
          displayName: String(operation.payload.displayName || "").trim(),
          nationalId: typeof operation.payload.nationalId === "string" ? operation.payload.nationalId : undefined,
        };
        let patientId = operation.backendPatientId || (draft.patientId && !isLocalAssignmentPatient(draft.patientId) ? draft.patientId : undefined);
        if (!patientId && draft.displayName) {
          const matches = await searchPatients(apiFetch, draft.nationalId || draft.displayName);
          const normalizedName = draft.displayName.toLowerCase();
          const exact = matches.find(
            (patient) =>
              patient.displayName.trim().toLowerCase() === normalizedName ||
              (draft.nationalId && patient.nationalId === draft.nationalId),
          );
          patientId = (exact || (await createPatient(apiFetch, draft, operation.id))).id;
        }
        if (patientId) {
          const basisCaptureId = typeof operation.payload.basisCaptureId === "string" ? operation.payload.basisCaptureId : undefined;
          const assigned = await assignSessionPatient(apiFetch, backendSessionId, patientId, operation.id, basisCaptureId);
          applySessionUpdate(backendSessionId, assigned);
        }
      }
    }

    if (operation.type === "sessionProcessing") {
      const processingSession = await saveSessionForProcessing(apiFetch, backendSessionId);
      applySessionUpdate(backendSessionId, processingSession);
      scheduleSessionProcessingRefresh(backendSessionId);
    }

    await removePendingOperation(operation.id);
    return true;
  };

  const processPendingOperations = async (tenantId: string) => {
    const operations = await loadPendingOperations();
    let failed = false;
    for (const operation of operations) {
      if (operation.tenantId && operation.tenantId !== tenantId) continue;
      try {
        const completed = await syncPendingOperation(operation, tenantId);
        if (!completed) continue;
      } catch (error) {
        await updatePendingOperation(operation.id, (current) => ({
          ...current,
          status: "failed",
          retryCount: current.retryCount + 1,
          updatedAt: Date.now(),
          lastError: error instanceof Error ? error.message : "Sync failed",
        }));
        setSyncError("Some local changes need retry");
        setBackendReachable(false);
        failed = true;
      }
    }
    return !failed;
  };

  /**
   * Serially uploads locally saved captures for the active tenant.
   *
   * The outbox is intentionally processed one item at a time so a failed upload
   * leaves later captures untouched and keeps local session previews consistent.
   */
  const processOutbox = async () => {
    const currentAuth = authRef.current;
    const activeTenantId = currentAuth?.tenant.id;
    if (processingRef.current || !currentAuth || !activeTenantId || currentAuth.user.persona === "patient-preview") return;
    // `navigator.onLine` is unreliable — it returns false-negatives after sleep / Wi-Fi / VPN
    // changes and often never recovers, which used to strand captures in "waiting to upload".
    // Treat it as a UI hint only and STILL attempt the upload: a genuinely-offline fetch fails
    // fast and is caught + retried below, so a wrong `onLine` can no longer block syncing.
    if (!navigator.onLine) setOnline(false);
    processingRef.current = true;
    setSyncing(true);
    setSyncError("");
    try {
      const pending = await loadPendingCaptures();
      let captureFailed = false;
      for (const pendingCapture of pending) {
        if (!authRef.current || authRef.current.tenant.id !== activeTenantId) break;
        const capture = (await loadPendingCapture(pendingCapture.id)) || pendingCapture;
        if (capture.tenantId && capture.tenantId !== activeTenantId) {
          // A capture only uploads for the tenant it was made under. After tier/clinic switching this
          // strands it as "waiting to upload" under the wrong tenant — surface why instead of hiding it.
          console.warn(
            `[outbox] capture ${capture.item.id} is for tenant ${capture.tenantId}, not the active tenant ${activeTenantId} — skipping. Log in under that clinic/tier to upload it.`,
          );
          continue;
        }
        const backendSessionId = capture.backendSessionId || capture.sessionId;
        await updatePendingCapture(capture.id, (current) => ({
          ...normalizePendingCapture(current),
          tenantId: current.tenantId || activeTenantId,
          backendSessionId,
          sessionId: backendSessionId,
        }));
        updateItemStatus(capture.item.id, "syncing");
        try {
          const uploadDraft = await standardizeCaptureDraft(capture.draft);
          const result = await uploadCapture(apiFetch, capture.clientCaptureId, uploadDraft, backendSessionId, capture.intoNew);
          const remainingPending = await loadPendingCaptures();
          const stillPendingForLocalSession = remainingPending.some(
            (pendingCapture) => pendingCapture.id !== capture.id && pendingCapture.localSessionId === capture.localSessionId,
          );
          const currentSession = sessionsRef.current.find((session) => session.id === capture.localSessionId || session.id === result.session.id);
          let mergedSession = mergeSessionItems(currentSession || activeSessionRef.current, result.session, capture.item.id);
          if (mergedSession.patientId && !result.session.patientId && !isLocalSessionId(mergedSession.id)) {
            try {
              const assignedSession = await assignSessionPatient(apiFetch, mergedSession.id, mergedSession.patientId);
              mergedSession = mergeSessionUpdate(mergedSession, assignedSession, mergedSession.items);
            } catch {
              // Keep the local patient context visible; assignment can be retried from the patient control.
            }
          }
          upsertSession(mergedSession, stillPendingForLocalSession ? [] : [capture.localSessionId]);
          setActiveSession((current) =>
            current?.id === capture.localSessionId || current?.id === result.session.id
              ? mergeSessionUpdate(mergeSessionItems(current, result.session, capture.item.id), mergedSession, mergedSession.items)
              : current,
          );
          setSelectedSessionId((current) => (current === capture.localSessionId ? mergedSession.id : current));
          setToast("Capture safely transferred.");
          if (result.item.status === "uploaded" || result.item.status === "processing") scheduleCaptureProcessingRefresh(result.session.id);
          scheduleMemoryRefresh();
          try {
            await updatePendingCapture(capture.id, (current) => ({
              ...normalizePendingCapture(current),
              draft: uploadDraft,
              tenantId: activeTenantId,
              backendSessionId: result.session.id,
              backendCaptureId: result.item.id,
              sessionId: result.session.id,
              intoNew: false,
            }));
            await storeBackendMappings(capture, result, activeTenantId);
            await saveSyncedCaptureCache(result.item, uploadDraft.file);
            await bindPendingSession(capture.localSessionId, result.session.id);
            await removePendingCapture(capture.id);
            await refreshPendingCount();
          } catch {
            setToast("Capture safely transferred.");
          }
        } catch (uploadError) {
          // Was swallowed silently — log the real reason so a perpetually-stuck capture is diagnosable.
          console.warn(`[outbox] upload failed for capture ${capture.item.id} (retry ${capture.retryCount + 1}):`, uploadError);
          await updatePendingCapture(capture.id, (current) => ({ ...current, retryCount: current.retryCount + 1 }));
          updateItemStatus(capture.item.id, "saved");
          await rebuildLocalPendingSessions();
          setBackendReachable(false);
          setSyncError("Capture upload failed");
          captureFailed = true;
          setToast("Saved on this device. I'll organize it when connection returns.");
          continue;
        }
      }
      const operationsHealthy = await processPendingOperations(activeTenantId);
      if (operationsHealthy && !captureFailed) setBackendReachable(true);
    } finally {
      processingRef.current = false;
      setSyncing(false);
      await refreshPendingCount();
    }
  };

  // Robust periodic retry: while there is pending work, re-attempt on a FIXED interval regardless
  // of transient sync/online state. processOutbox() self-guards against overlap (processingRef), so
  // a tick during an in-flight sync is a no-op. Using setInterval (not a setTimeout re-armed only
  // when `syncing` toggles) guarantees stuck "waiting to upload" items are always retried — even
  // after an early-return that never flipped `syncing`.
  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview" || (!pendingCount && !pendingOperationCount)) return;
    const retryTimer = window.setInterval(() => void processOutbox(), 15000);
    return () => window.clearInterval(retryTimer);
  }, [auth, pendingCount, pendingOperationCount]);

  /**
   * Saves a capture to IndexedDB before attempting network transfer.
   *
   * The optimistic UI update happens only after local persistence succeeds,
   * which keeps the visible feed aligned with recoverable browser state.
   */
  const saveDraft = async (draft: CaptureDraft, intoNew = false) => {
    let pending;
    let visibleSession: CaptureSession;
    try {
      const safeDraft = await standardizeCaptureDraft(draft);
      pending = makeLocalCapture(safeDraft, activeSession, intoNew, authRef.current?.tenant.id);
      visibleSession = sessionWithLocalPreview(pending.session, pending.item.id, safeDraft.file);
      await savePendingCapture(pending);
      flushSync(() => {
        setActiveSession(visibleSession);
        upsertSession(visibleSession);
        navigateScreen("active-session");
      });
    } catch {
      setToast(draft.kind === "audio" ? "Audio conversion failed." : "Device storage failed.");
      return;
    }

    void saveSyncedCaptureCache(pending.item, pending.draft.file);
    setToast("Saved on device.");
    void refreshPendingCount();
    if (authRef.current?.tenant.id) void processOutbox();
  };

  const openCaptureDialog = (kind: CaptureDraft["kind"]) => {
    if (kind === "note") setTextOpen(true);
    if (kind === "photo") setPhotoOpen(true);
    if (kind === "audio") setAudioOpen(true);
  };

  // AES-106 "same as last time": seed an editable note from the prior visit's typed note (never
  // auto-saved — the doctor confirms with an edit/save).
  const composeNoteFromText = (text: string) => {
    setTextSeed(text);
    setTextOpen(true);
  };

  const beginCapture = (kind: CaptureDraft["kind"]) => {
    // Durability hard-stop (Epic G): when durable storage is full we can't guarantee a new
    // capture survives, so pause capturing and offer the export escape hatch instead.
    if (storage.level === "full") {
      void refreshStorage();
      setStorageGuardOpen(true);
      return;
    }
    // On a patient's file → capture *for that patient* (start their visit + open the recorder),
    // skipping the destination chooser. The session is created only now (on the capture action),
    // so merely viewing a patient never changes the target.
    if (screen === "patients" && viewedPatient) {
      void startVisitForPatient(viewedPatient.id, undefined, kind);
      return;
    }
    if (screen !== "active-session") {
      setPendingCaptureKind(kind);
      return;
    }
    openCaptureDialog(kind);
  };

  const chooseCaptureDestination = (kind: CaptureDraft["kind"], sessionId?: string) => {
    setPendingCaptureKind(null);
    if (!sessionId) {
      setActiveSession(null);
      navigateScreen("active-session");
      openCaptureDialog(kind);
      return;
    }
    continueMemorySession(sessionId);
    openCaptureDialog(kind);
  };

  const startNewSession = () => {
    if (activeSession && isLocalSessionId(activeSession.id) && !activeSession.items.length) {
      setSessions((current) => current.filter((session) => session.id !== activeSession.id));
    }
    setActiveSession(null);
    setSelectedSessionId("");
    setAssignmentSessionId("");
    navigateScreen("active-session");
    setToast("New session ready.");
  };

  // AES-903 — worklist "Start visit": open a fresh session already assigned to the patient, mark the
  // worklist entry seen (linking the session), and drop into the capture screen. Capture-first is
  // untouched — this is just a shortcut past the patient card for a queued patient.
  const startVisitForPatient = React.useCallback(
    async (patientId: string, worklistEntryId?: string, openCaptureKind?: CaptureDraft["kind"]) => {
      try {
        const session = await createSession(apiFetch, patientId);
        if (worklistEntryId) {
          try {
            await markWorklistEntrySeen(apiFetch, worklistEntryId, session.id);
          } catch {
            /* a stale/seen entry shouldn't block the visit */
          }
        }
        upsertSession(session);
        setActiveSession(session);
        setSelectedSessionId(session.id);
        setAssignmentSessionId("");
        navigateScreen("active-session");
        // Capture-for-patient: drop straight into the recorder/photo/note for the new visit.
        if (openCaptureKind) openCaptureDialog(openCaptureKind);
      } catch {
        setToast("Could not start the visit.");
      }
    },
    [apiFetch],
  );

  // AES-903/AES-301 — the doctor's next lined-up patient, surfaced on the capture screen so an
  // unassigned visit can be filed to them (or a fresh one started) without leaving capture.
  const [nextLinedUpPatient, setNextLinedUpPatient] = React.useState<{ patientId: string; patientName: string; entryId: string } | null>(null);
  const [worklistRefresh, setWorklistRefresh] = React.useState(0);
  React.useEffect(() => {
    const current = authRef.current;
    if (!current || !currentUserRoles(current).includes("doctor")) {
      setNextLinedUpPatient(null);
      return;
    }
    let cancelled = false;
    void fetchWorklist(apiFetch, { scope: "mine", status: "waiting" })
      .then((result) => {
        if (cancelled) return;
        const top = result.items[0];
        setNextLinedUpPatient(top ? { patientId: top.patientId, patientName: top.patientName || "Patient", entryId: top.id } : null);
      })
      .catch(() => {
        if (!cancelled) setNextLinedUpPatient(null);
      });
    return () => {
      cancelled = true;
    };
  }, [apiFetch, auth, memoryRefreshSignal, worklistRefresh]);

  const startNextLinedUpVisit = React.useCallback(() => {
    if (!nextLinedUpPatient) return;
    void startVisitForPatient(nextLinedUpPatient.patientId, nextLinedUpPatient.entryId).then(() => setWorklistRefresh((v) => v + 1));
  }, [nextLinedUpPatient, startVisitForPatient]);

  const clearLocalPendingCaptures = async () => {
    if (!window.confirm("Clear captures saved only on this device? This cannot be undone.")) return;
    processingRef.current = false;
    setSyncing(false);
    await clearLocalCaptureData();
    clearWorkspaceState();
    setActiveSession(null);
    setSessions([]);
    setSelectedSessionId("");
    setAssignmentSessionId("");
    setPendingCaptureKind(null);
    setPendingCount(0);
    setPendingOperationCount(0);
    setToast("Local pending captures cleared.");
    void hydrateFromStorage();
  };

  const saveSession = async (sessionId: string) => {
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
        label: "Generating structured report",
        detail: "Background AI is organizing the latest captures.",
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
        setToast("Saved on this device. I'll organize it when connection returns.");
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
      setToast("Structured report is generating.");
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
        setToast("Saved. I'll organize it when available.");
        void processOutbox();
        return;
      }
      setToast("Saved on this device. I'll organize it when connection returns.");
    }
  };

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
        setToast("Session title updated.");
        return;
      }
      try {
        const updated = await updateSessionTitle(apiFetch, sessionId, title);
        setSessions((current) =>
          current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
        );
        setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
        setToast("Session title updated.");
      } catch {
        if (authRef.current?.tenant.id) {
          await queueOperation({
            id: `${authRef.current.tenant.id}:sessionTitle:${sessionId}`,
            type: "sessionTitle",
            backendSessionId: sessionId,
            tenantId: authRef.current.tenant.id,
            payload: { title },
          });
          setToast("Title saved on this device.");
          void processOutbox();
          return;
        }
        setToast("Could not update title.");
      }
    },
    [apiFetch],
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
        setToast("Capture renamed.");
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
      setToast("Capture renamed.");
    },
    [apiFetch],
  );

  const editCaptureSourceText = React.useCallback(
    async (sessionId: string, captureId: string, text: string, field: "caption" | "transcript") => {
      const editedAt = new Date().toISOString();
      const editorName = auth?.user.displayName || auth?.user.email || "You";
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
            edited_by_email: auth?.user.email,
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
        setToast(field === "caption" ? "Caption updated." : "Transcript updated.");
        const currentItem = activeSession?.id === sessionId ? activeSession.items.find((item) => item.id === captureId) : null;
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
      setToast(field === "caption" ? "Caption updated." : "Transcript updated.");
      return updated;
    },
    [activeSession?.id, activeSession?.items, apiFetch, auth?.user.displayName, auth?.user.email],
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
        setToast("Capture deleted.");
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
      setToast("Capture deleted. The live report is updating.");
    },
    [apiFetch, scheduleCaptureProcessingRefresh],
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
      setToast("Marked relevant. The live report is updating.");
    },
    [apiFetch, scheduleCaptureProcessingRefresh],
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
        setToast("Dose confirmed.");
      } catch {
        setToast("Could not confirm the dose. Try again.");
      }
    },
    [apiFetch, applySessionUpdate],
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

  const assignPatientToSession = React.useCallback(
    async (sessionId: string, draft: PatientAssignmentDraft, options?: { successMessage?: string }) => {
      if (draft.unassign) {
        const clearPatient = (session: CaptureSession) =>
          markReportStaleForPatientChange(session, { ...session, patientId: undefined, patientName: undefined, assignmentSource: undefined });
        setSessions((current) => current.map((session) => (session.id === sessionId ? clearPatient(session) : session)));
        setActiveSession((current) => (current?.id === sessionId ? clearPatient(current) : current));
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
        setToast("Visit unassigned.");
        void processOutbox();
        return;
      }
      const localPatient: PatientSummary = draft.patientId && !isLocalAssignmentPatient(draft.patientId)
        ? { id: draft.patientId, displayName: draft.displayName, nationalId: draft.nationalId || null }
        : {
            id: draft.patientId || `local-patient-${createClientSideId()}`,
            displayName: draft.displayName,
            nationalId: draft.nationalId || null,
          };
      const successMessage = options?.successMessage || `Visit assigned to ${draft.displayName}.`;
      const applyLocalAssignment = (patient: PatientSummary) => {
        const enriched = {
          patientId: patient.id,
          patientName: patient.displayName,
          assignmentSource: "staff",
        };
        setSessions((current) =>
          current.map((session) =>
            session.id === sessionId ? markReportStaleForPatientChange(session, { ...session, ...enriched }) : session,
          ),
        );
        setActiveSession((current) =>
          current?.id === sessionId ? markReportStaleForPatientChange(current, { ...current, ...enriched }) : current,
        );
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
      } catch {
        applyLocalAssignment(localPatient);
        await enqueueAssignment(localPatient);
        setToast(successMessage);
        void processOutbox();
      }
    },
    [apiFetch, ensurePatient],
  );

  // AES-301/903 — file the current unassigned visit onto the doctor's next lined-up patient.
  const assignActiveVisitToNext = React.useCallback(async () => {
    if (!activeSession || !nextLinedUpPatient) return;
    await assignPatientToSession(
      activeSession.id,
      { patientId: nextLinedUpPatient.patientId, displayName: nextLinedUpPatient.patientName },
      { successMessage: `Visit assigned to ${nextLinedUpPatient.patientName}.` },
    );
    try {
      await markWorklistEntrySeen(apiFetch, nextLinedUpPatient.entryId, activeSession.id);
    } catch {
      /* non-fatal */
    }
    setWorklistRefresh((v) => v + 1);
  }, [activeSession, nextLinedUpPatient, assignPatientToSession, apiFetch]);

  const searchPatientsForAssignment = React.useCallback((query: string) => searchPatients(apiFetch, query), [apiFetch]);
  const fetchAssignedPatientDetails = React.useCallback(
    (patientId: string) => (isLocalAssignmentPatient(patientId) ? Promise.resolve(null) : getPatient(apiFetch, patientId).catch(() => null)),
    [apiFetch],
  );
  const completeAiCreatedPatient = React.useCallback(
    async (
      sessionId: string,
      patientId: string,
      draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
      action: Record<string, unknown>,
    ) => {
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
      setToast("AI-created patient verified.");
    },
    [apiFetch],
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
      setToast("Patient details updated.");
    },
    [apiFetch],
  );
  const createNewPatient = React.useCallback(
    async (draft: PatientAssignmentDraft): Promise<PatientSummary | null> => {
      try {
        const patient = await createPatient(apiFetch, draft);
        setToast("Patient created.");
        return patient;
      } catch {
        setToast("Could not create patient.");
        return null;
      }
    },
    [apiFetch],
  );
  const listPatientMemory = React.useCallback(
    (params: { query?: string; filter: PatientMemoryFilter; limit?: number; offset?: number; clinicianId?: string }): Promise<PatientMemoryListResponse> =>
      fetchPatientMemory(apiFetch, params),
    [apiFetch],
  );

  // E9 multi-seat (AES-903): the soft worklist + clinic directory.
  const listWorklist = React.useCallback(
    (options?: { scope?: "mine" | "clinic"; status?: "waiting" | "seen" | "cancelled" | "all"; clinicianId?: string }) =>
      fetchWorklist(apiFetch, options),
    [apiFetch],
  );
  const lineUpPatient = React.useCallback(
    (input: { patientId: string; clinicianUserId: string; note?: string }) => createWorklistEntry(apiFetch, input),
    [apiFetch],
  );
  const markWorklistSeen = React.useCallback(
    (entryId: string, sessionId?: string) => markWorklistEntrySeen(apiFetch, entryId, sessionId),
    [apiFetch],
  );
  const cancelWorklist = React.useCallback((entryId: string) => cancelWorklistEntry(apiFetch, entryId), [apiFetch]);
  const listClinicMembers = React.useCallback(() => fetchClinicMembers(apiFetch), [apiFetch]);

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
      setToast("Summary added to patient memory");
    },
    [],
  );

  const loadCapturesForSession = React.useCallback(
    async (sessionId: string) => {
      const captures = await fetchSessionCaptures(apiFetch, sessionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? { ...session, items: captures } : session)));
      return captures;
    },
    [apiFetch],
  );

  const resolveSourceFile = React.useCallback((endpoint: string) => resolveCaptureFileUrl(apiFetch, endpoint), [apiFetch]);

  // Stable callbacks for the aesthetics-Basic surfaces. These feed child effects (smart search,
  // gallery, share sheet, resolvers), so they MUST be memoized — an inline `() => fn(apiFetch, …)`
  // is a new reference every render and would re-fire those effects (the "refreshing every few
  // seconds" symptom). apiFetch is itself stable.
  const getPatientMemoryDetail = React.useCallback((patientId: string) => fetchPatientMemoryDetail(apiFetch, patientId), [apiFetch]);

  // Pro: fetch the active patient's curated brief for the session context card, polling while it is
  // still "organizing" (read-triggered cold generation), capped so it never spins forever.
  React.useEffect(() => {
    if (isBasicTier || !patientId || isLocalAssignmentPatient(patientId)) {
      setSessionLineupCard(null);
      return;
    }
    let cancelled = false;
    let attempts = 0;
    const load = () => {
      void getPatientMemoryDetail(patientId)
        .then((detail) => {
          if (cancelled) return;
          const card = detail.lineupCard || null;
          setSessionLineupCard(card);
          if (card?.status === "updating" && attempts < 10) {
            attempts += 1;
            window.setTimeout(load, 3000);
          }
        })
        .catch(() => undefined);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [getPatientMemoryDetail, isBasicTier, patientId]);
  const smartSearchPatients = React.useCallback((query: string) => searchPatientsSmart(apiFetch, query), [apiFetch]);
  const duplicateCheckPatient = React.useCallback((body: { displayName?: string; nationalId?: string; phone?: string }) => checkDuplicatePatient(apiFetch, body), [apiFetch]);
  const loadSessionCaptures = React.useCallback((sessionId: string) => fetchSessionCaptures(apiFetch, sessionId), [apiFetch]);
  const loadSession = React.useCallback((sessionId: string) => fetchSession(apiFetch, sessionId), [apiFetch]);
  const loadLastVisitForPatient = React.useCallback((patientId: string) => fetchLastVisit(apiFetch, patientId), [apiFetch]);
  const listAftercare = React.useCallback(() => listAftercareTemplates(apiFetch), [apiFetch]);
  // Clinic aftercare templates, loaded once per auth, so the session can offer one-tap follow-up
  // instructions (deterministic — the clinic's own text, never AI-authored advice).
  React.useEffect(() => {
    if (!auth) {
      setAftercareTemplates([]);
      return;
    }
    let cancelled = false;
    void listAftercareTemplates(apiFetch)
      .then((templates) => {
        if (!cancelled) setAftercareTemplates(templates.filter((template) => template.isActive));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [apiFetch, auth]);
  const createShare = React.useCallback((input: Parameters<typeof createPatientShare>[1]) => createPatientShare(apiFetch, input), [apiFetch]);
  const revokeShare = React.useCallback((id: string) => revokePatientShare(apiFetch, id), [apiFetch]);
  const loadAssignmentSuggestion = React.useCallback((sessionId: string) => fetchAssignmentSuggestion(apiFetch, sessionId), [apiFetch]);
  const createAftercare = React.useCallback((draft: Parameters<typeof createAftercareTemplate>[1]) => createAftercareTemplate(apiFetch, draft), [apiFetch]);
  const updateAftercare = React.useCallback((id: string, draft: Parameters<typeof updateAftercareTemplate>[2]) => updateAftercareTemplate(apiFetch, id, draft), [apiFetch]);
  const deleteAftercare = React.useCallback((id: string) => deleteAftercareTemplate(apiFetch, id), [apiFetch]);

  // AES-101 — edit a (Basic) note's text inline. Persisted as a staff-edited note metadata field so
  // it survives reloads; local (unsynced) notes update their pending capture in place.
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
        setToast("Note updated.");
        return;
      }
      const updated = await updateCaptureNote(apiFetch, captureId, text);
      const merge = (item: CaptureItem): CaptureItem => (item.id === captureId ? { ...item, ...updated, detail: text } : item);
      const mergeSession = (session: CaptureSession): CaptureSession =>
        session.id === sessionId ? { ...session, items: session.items.map(merge) } : session;
      setSessions((current) => current.map(mergeSession));
      setActiveSession((current) => (current?.id === sessionId ? mergeSession(current) : current));
      setToast("Note updated.");
    },
    [apiFetch],
  );

  const handlePersonaLogin = async (persona: Persona, tier: DevTier = "pro") => {
    setAuthError("");
    try {
      const next = await loginWithPersona(persona, tier);
      commitAuth(next);
      navigateScreen(defaultScreenForAuth(next));
    } catch {
      setAuthError("Could not sign in with that persona.");
    }
  };

  const handlePasswordLogin = async (email: string, password: string) => {
    setAuthError("");
    try {
      const next = await loginWithPassword(email, password);
      commitAuth(next);
      navigateScreen(defaultScreenForAuth(next));
    } catch {
      setAuthError("Invalid email or password.");
    }
  };

  const handleUpdateTenantSettings = React.useCallback(
    async (settings: {
      transcriptionLanguage?: string;
      reportLanguage?: string | null;
      matchStrictness?: string;
      rolePermissions?: RolePermissions;
    }) => {
      const currentAuth = authRef.current;
      if (!currentAuth) return;
      const changingStrictness = "matchStrictness" in settings;
      const changingPermissions = "rolePermissions" in settings;
      try {
        const updated = await updateTenantSettings(apiFetch, settings);
        commitAuth({
          ...currentAuth,
          tenant: {
            ...currentAuth.tenant,
            transcriptionLanguage: updated.transcriptionLanguage ?? currentAuth.tenant.transcriptionLanguage,
            reportLanguage: updated.reportLanguage ?? null,
            matchStrictness: updated.matchStrictness ?? currentAuth.tenant.matchStrictness,
            // AES-905: the response carries the full effective preset map (defaults + overrides).
            rolePermissions: updated.rolePermissions ?? currentAuth.tenant.rolePermissions,
          },
        });
        setToast(
          changingPermissions
            ? "Role permissions updated."
            : changingStrictness
              ? "Patient-matching preference updated."
              : "Language preferences updated.",
        );
      } catch {
        setToast(
          changingPermissions
            ? "Could not update role permissions."
            : changingStrictness
              ? "Could not update matching preference."
              : "Could not update language preferences.",
        );
      }
    },
    [apiFetch, commitAuth],
  );

  const handleLogout = async () => {
    const currentAuth = authRef.current;
    clearAuth();
    setSessions([]);
    setActiveSession(null);
    setSelectedSessionId("");
    setSyncing(false);
    navigateScreen("active-session");
    void refreshPendingCount();
    if (currentAuth) {
      try {
        await logoutSession(currentAuth.accessToken, currentAuth.refreshToken);
      } catch {
        // Local logout still wins when the backend cannot be reached.
      }
    }
  };

  const selectedSession = sessions.find((session) => session.id === selectedSessionId);
  const syncHealth: SyncHealth = {
    online,
    backendReachable,
    pendingCaptures: pendingCount,
    pendingOperations: pendingOperationCount,
    syncing,
    lastError: syncError || undefined,
  };
  // Offline = no connection OR the backend is known-unreachable. Used to gate the only sync
  // indicators we show (header + per-capture "Trying to sync"); everything else stays badge-free.
  const offline = !online || backendReachable === false;
  const activeSessionOrdinal = computeSessionOrdinal(activeSession, sessions);

  const openMemorySession = (sessionId: string, returnContext?: ClinicalMemoryReturnContext) => {
    setClinicalMemoryReturnContext(returnContext || null);
    const session = sessions.find((candidate) => candidate.id === sessionId);
    navigateScreen("active-session");
    if (session) {
      setSelectedSessionId("");
      setActiveSession(session);
      if (!session.items.length && !isLocalSessionId(session.id)) {
        void loadCapturesForSession(session.id)
          .then((captures) => {
            setActiveSession((current) => (current?.id === session.id ? { ...session, items: captures } : current));
          })
          .catch(() => setToast("Could not load captures for this session."));
      }
      return;
    }
    setSelectedSessionId(sessionId);
  };

  const returnToClinicalMemory = () => {
    setSelectedSessionId("");
    navigateScreen("patients");
  };

  // Round-trip from the session: open the assigned patient's full timeline, remembering the
  // in-progress visit so we can come straight back to it (the live session stays in state the whole
  // time — we just change which screen is shown).
  const openPatientHistory = (patientId: string) => {
    // Stash the in-progress visit once — keep the original if we're already mid-round-trip (e.g. the
    // user jumped to a prior visit and tapped History again), so "back" still lands on the live one.
    setCaptureReturnSession((current) => current || activeSession);
    setClinicalMemoryReturnContext({ tab: "patients", patientId });
    setSelectedSessionId("");
    navigateScreen("patients");
  };

  const openSessionShare = () => {
    const session = activeSession;
    if (!session?.patientId) return;
    setSessionShare({
      id: session.patientId,
      name: session.patientName || "Patient",
      visits: [{ sessionId: session.id, title: "Visit", dateLabel: "" }],
    });
  };

  const returnToActiveCapture = () => {
    const stashed = captureReturnSession;
    setCaptureReturnSession(null);
    setClinicalMemoryReturnContext(null);
    if (stashed) {
      setSelectedSessionId("");
      setActiveSession(stashed);
      navigateScreen("active-session");
    }
  };

  const clinicalMemoryBackLabel = clinicalMemoryReturnContext?.patientId
    ? "Patient history"
    : clinicalMemoryReturnContext?.tab === "today"
      ? "Today"
      : clinicalMemoryReturnContext?.tab === "needs-input"
        ? "Needs input"
        : clinicalMemoryReturnContext?.tab === "patients"
          ? "Patients"
          : "Clinical Memory";

  const handleShellNavigate = (nextScreen: Screen) => {
    // Settings/Profile are utility pages reached from the account menu; remember where we came
    // from so Back returns there (don't record an account page as its own return target).
    if ((nextScreen === "settings" || nextScreen === "profile") && screen !== "settings" && screen !== "profile") {
      accountReturnRef.current = screen;
    }
    setClinicalMemoryReturnContext(null);
    setCaptureReturnSession(null); // deliberate nav abandons the back-to-visit round-trip
    navigateScreen(nextScreen);
  };

  const continueMemorySession = (sessionId: string) => {
    const session = sessions.find((candidate) => candidate.id === sessionId);
    if (!session) return;
    const nextSession: CaptureSession = {
      ...session,
      reviewReason: session.reviewReason || "Current capture destination",
    };
    setSelectedSessionId("");
    setActiveSession(nextSession);
    navigateScreen("active-session");
    if (!session.items.length && !isLocalSessionId(session.id)) {
      void loadCapturesForSession(session.id)
        .then((captures) => {
          setActiveSession((current) => (current?.id === session.id ? { ...nextSession, items: captures } : current));
        })
        .catch(() => setToast("Could not load captures for this session."));
    }
    setToast("Add the next capture to this session.");
  };

  const renderCurrentScreen = () => {
    if (screen === "settings" && auth) {
      return (
        <SettingsScreen
          auth={auth}
          onBack={() => navigateScreen(accountReturnRef.current)}
          onUpdateSettings={handleUpdateTenantSettings}
          onListAiModels={() => fetchAiModels(apiFetch)}
          onUpdateAiModels={(models) => updateAiModels(apiFetch, models)}
          onListAftercareTemplates={listAftercare}
          onCreateAftercareTemplate={createAftercare}
          onUpdateAftercareTemplate={updateAftercare}
          onDeleteAftercareTemplate={deleteAftercare}
        />
      );
    }
    if (screen === "profile" && auth) {
      return (
        <ProfileScreen
          auth={auth}
          onBack={() => navigateScreen(accountReturnRef.current)}
          onClearLocal={() => void clearLocalPendingCaptures()}
          onLogout={handleLogout}
        />
      );
    }
    if (screen !== "active-session" && selectedSession) {
      return (
        <CaptureScreen
          activeSession={selectedSession}
          mode="historical"
          onBack={() => setSelectedSessionId("")}
          onResumeCapture={() => {
            setActiveSession({
              ...selectedSession,
              reviewReason: "Current capture destination",
            });
            setSelectedSessionId("");
            navigateScreen("active-session");
            setToast("Add the next capture to this session.");
          }}
          assignmentOpen={assignmentSessionId === selectedSession.id}
          onAssignPatient={assignPatientToSession}
          onSearchPatients={searchPatientsForAssignment}
          onCompleteAiCreatedPatient={completeAiCreatedPatient}
          onFetchPatient={fetchAssignedPatientDetails}
          onCloseAssignment={() => setAssignmentSessionId((current) => (current === selectedSession.id ? "" : selectedSession.id))}
          onOpenResolver={() => setAssignmentSessionId(selectedSession.id)}
          onSaveSession={saveSession}
          onResolveFile={resolveSourceFile}
          onUpdateTitle={renameSession}
          onRenameCapture={renameCapture}
          onUpdateCaptureCaption={(sessionId, captureId, caption) => editCaptureSourceText(sessionId, captureId, caption, "caption")}
          onUpdateCaptureTranscript={(sessionId, captureId, transcript) => editCaptureSourceText(sessionId, captureId, transcript, "transcript")}
          onUpdateNote={editCaptureNote}
          onDeleteCapture={removeCaptureFromSession}
          onMarkRelevant={markCaptureRelevantInSession}
          onConfirmCarriedForward={confirmCarriedForwardDose}
          tier={auth?.tenant.tier}
          offline={offline}
        />
      );
    }
    if (screen === "active-session") {
      return (
        <CaptureScreen
          activeSession={activeSession}
          assignmentOpen={Boolean(activeSession && assignmentSessionId === activeSession.id)}
          onBack={clinicalMemoryReturnContext ? returnToClinicalMemory : undefined}
          backLabel={clinicalMemoryBackLabel}
          onAssignPatient={assignPatientToSession}
          onSearchPatients={searchPatientsForAssignment}
          onCompleteAiCreatedPatient={completeAiCreatedPatient}
          onFetchPatient={fetchAssignedPatientDetails}
          onCloseAssignment={() => {
            if (activeSession) {
              setAssignmentSessionId((current) => (current === activeSession.id ? "" : activeSession.id));
              return;
            }
            const session = makeEmptyLocalSession();
            setActiveSession(session);
            upsertSession(session);
            setAssignmentSessionId(session.id);
          }}
          onOpenResolver={() => {
            if (activeSession) setAssignmentSessionId(activeSession.id);
          }}
          onSaveSession={saveSession}
          onResolveFile={resolveSourceFile}
          onStartNewSession={startNewSession}
          onUpdateTitle={renameSession}
          onRenameCapture={renameCapture}
          onUpdateCaptureCaption={(sessionId, captureId, caption) => editCaptureSourceText(sessionId, captureId, caption, "caption")}
          onUpdateCaptureTranscript={(sessionId, captureId, transcript) => editCaptureSourceText(sessionId, captureId, transcript, "transcript")}
          onUpdateNote={editCaptureNote}
          onDeleteCapture={removeCaptureFromSession}
          onMarkRelevant={markCaptureRelevantInSession}
          onConfirmCarriedForward={confirmCarriedForwardDose}
          tier={auth?.tenant.tier}
          sessionContext={sessionContext}
          lineupCard={sessionLineupCard}
          onOpenVisit={(sessionId) => openMemorySession(sessionId)}
          onViewPatientHistory={openPatientHistory}
          onShareVisit={openSessionShare}
          onUseAsNote={composeNoteFromText}
          aftercareTemplates={aftercareTemplates}
          offline={offline}
          sessionOrdinal={activeSessionOrdinal}
          currentUserId={auth?.user.id ?? null}
          readOnly={activeSession ? isSessionReadOnly(activeSession, auth) : false}
          nextLinedUpPatient={nextLinedUpPatient ? { patientName: nextLinedUpPatient.patientName } : null}
          onAssignActiveToNext={assignActiveVisitToNext}
          onStartNextVisit={startNextLinedUpVisit}
        />
      );
    }
    if (screen === "qa-inbox" && auth && auth.tenant.tier !== "basic") {
      // Pro-only post-session patient Q&A inbox (AES-402); the nav entry is hidden for Basic.
      return <DoctorQaInbox apiFetch={apiFetch} onToast={setToast} onChanged={refreshQaPendingCount} />;
    }
    if (screen === "search") {
      return <SearchHome onOpenSession={openMemorySession} sessions={sessions} syncHealth={syncHealth} />;
    }
    return (
      <PatientsHome
        activeSession={activeSession}
        auth={auth}
        initialPatientId={clinicalMemoryReturnContext?.patientId}
        onBackToVisit={captureReturnSession ? returnToActiveCapture : undefined}
        initialTab={clinicalMemoryReturnContext?.tab}
        onAssignPatient={assignPatientToSession}
        onContinueSession={continueMemorySession}
        onConfirmSummary={confirmSessionSummary}
        onOpenSession={openMemorySession}
        onListPatientMemory={listPatientMemory}
        onListWorklist={listWorklist}
        onLineUpPatient={lineUpPatient}
        onMarkWorklistSeen={markWorklistSeen}
        onCancelWorklistEntry={cancelWorklist}
        onListClinicMembers={listClinicMembers}
        onStartVisit={startVisitForPatient}
        onViewingPatientChange={setViewedPatient}
        onGetPatientMemory={getPatientMemoryDetail}
        onUpdatePatient={editPatientDetails}
        onFetchPatient={fetchAssignedPatientDetails}
        onCreatePatient={createNewPatient}
        onExportCaptures={exportQueuedCaptures}
        onSearchPatients={searchPatientsForAssignment}
        onSmartSearch={smartSearchPatients}
        onDuplicateCheck={duplicateCheckPatient}
        onLoadSessionCaptures={loadSessionCaptures}
        onLoadSession={loadSession}
        shareIncludeBrands={Boolean(auth?.tenant.shareIncludeBrands)}
        shareLanguage={auth?.tenant.reportLanguage || null}
        onResolveFile={resolveSourceFile}
        onLoadLastVisit={loadLastVisitForPatient}
        onListAftercareTemplates={listAftercare}
        onCreateShare={createShare}
        onRevokeShare={revokeShare}
        onOpenQaChannel={auth && auth.tenant.tier !== "basic" ? (patientId) => openQaChannel(apiFetch, patientId) : undefined}
        onToast={setToast}
        onLoadAssignmentSuggestion={loadAssignmentSuggestion}
        sessions={sessions}
        syncHealth={syncHealth}
        tier={auth?.tenant.tier}
        memoryRefreshSignal={memoryRefreshSignal}
      />
    );
  };

  if (!authReady) {
    return (
      <main className="login-shell">
        <Card className="login-card">
          <Skeleton className="h-16" />
          <Skeleton className="h-12" />
        </Card>
      </main>
    );
  }

  if (!auth) {
    return (
      <LoginGate
        error={authError}
        pendingCount={pendingCount}
        onLogin={handlePasswordLogin}
        onPersonaLogin={handlePersonaLogin}
      />
    );
  }

  if (auth.user.persona === "patient-preview") {
    return <PatientPreviewGate auth={auth} onLogout={handleLogout} />;
  }

  // Therapy vertical is a greenfield surface (note-first capture, two-plane synthesis, federated
  // caseloads) — render its own self-contained app rather than the aesthetics capture shell.
  if (auth.tenant.vertical === "therapy") {
    return <TherapyApp auth={auth} apiFetch={apiFetch} onLogout={handleLogout} />;
  }

  return (
    <>
      <Shell
        auth={auth}
        captureContextLabel={captureContextLabel(activeSession, screen, viewedPatient)}
        onCapture={beginCapture}
        onLogout={handleLogout}
        screen={screen}
        syncHealth={syncHealth}
        onNavigate={handleShellNavigate}
        qaPendingCount={qaPendingCount}
      >
        {pendingCaptureKind ? (
          <CaptureDestinationPanel
            activeSession={activeSession}
            kind={pendingCaptureKind}
            selectedSession={selectedSession}
            sessions={sessions}
            onCancel={() => setPendingCaptureKind(null)}
            onNewSession={() => chooseCaptureDestination(pendingCaptureKind)}
            onUseSession={(sessionId) => chooseCaptureDestination(pendingCaptureKind, sessionId)}
          />
        ) : null}
        {renderCurrentScreen()}
      </Shell>
      {sessionShare && auth ? (
        <SharePatientSheet
          patientId={sessionShare.id}
          patientName={sessionShare.name}
          visits={sessionShare.visits}
          sessionId={sessionShare.visits[0]?.sessionId}
          onLoadLastVisit={loadLastVisitForPatient}
          onLoadSessionCaptures={loadSessionCaptures}
          onLoadSession={loadSession}
          shareIncludeBrands={Boolean(auth.tenant.shareIncludeBrands)}
          shareLanguage={auth.tenant.reportLanguage || null}
          onListAftercareTemplates={listAftercare}
          onResolveFile={resolveSourceFile}
          onCreateShare={createShare}
          onRevokeShare={revokeShare}
          onClose={() => setSessionShare(null)}
        />
      ) : null}
      <TextCaptureSheet
        initialValue={textSeed}
        onClose={() => {
          setTextOpen(false);
          setTextSeed("");
        }}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setTextOpen(false);
          setTextSeed("");
        }}
        open={textOpen}
      />
      <AddPhotoSheet
        ghostPhotoUrl={ghostPhotoUrl}
        onClose={() => {
          setPhotoOpen(false);
        }}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setPhotoOpen(false);
        }}
        open={photoOpen}
      />
      <AudioDialog
        onClose={() => setAudioOpen(false)}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setAudioOpen(false);
        }}
        open={audioOpen}
        storageWarning={storage.level === "warn" ? storage : null}
      />
      {storageGuardOpen ? (
        <StorageGuardDialog
          onClose={() => setStorageGuardOpen(false)}
          onExport={exportQueuedCaptures}
          pendingCount={pendingCount}
          storage={storage}
        />
      ) : null}
      <Toast message={toast} />
    </>
  );
}

function isLocalAssignmentPatient(patientId: string) {
  return patientId.startsWith("mock-") || patientId.startsWith("local-patient-") || patientId === "current-session-patient";
}

function captureContextLabel(session: CaptureSession | null, screen: Screen, viewedPatient: { id: string; name: string } | null) {
  // On a patient's file the footer captures for *them* (a new visit) — make that explicit.
  if (screen === "patients" && viewedPatient) {
    return `Capturing for: ${viewedPatient.name} · new visit`;
  }
  const patient = session?.patientName || "Unassigned visit";
  return `Capturing for: ${patient} · Today's visit`;
}

function createClientSideId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * This session's 1-based chronological rank among its patient's sessions (so the capture header can
 * read "Sara's third session"). Best-effort from the loaded sessions; null when unassigned.
 */
function computeSessionOrdinal(session: CaptureSession | null, sessions: CaptureSession[]): number | null {
  if (!session || (!session.patientId && !session.patientName)) return null;
  const matches = sessions.filter((candidate) =>
    session.patientId ? candidate.patientId === session.patientId : Boolean(session.patientName) && candidate.patientName === session.patientName,
  );
  const pool = matches.some((candidate) => candidate.id === session.id) ? matches : [...matches, session];
  const timeOf = (candidate: CaptureSession) => {
    const value = candidate.capturedAt || candidate.createdAt || candidate.updatedAt;
    const ms = value ? new Date(value).getTime() : NaN;
    return Number.isNaN(ms) ? 0 : ms;
  };
  const sorted = [...pool].sort((left, right) => timeOf(left) - timeOf(right));
  const index = sorted.findIndex((candidate) => candidate.id === session.id);
  return index >= 0 ? index + 1 : sorted.length;
}
