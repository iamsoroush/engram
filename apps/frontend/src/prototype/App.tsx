import React from "react";
import { flushSync } from "react-dom";
import type { ApiFetch, AuthSession, CaptureDraft, PatientAssignmentDraft, PatientSummary, Persona } from "./appTypes";
import type { CaptureSession, CaptureStatus, Screen } from "./types";
import { Button, Card, Skeleton, Toast } from "./ui";
import {
  assignSessionPatient,
  createPatient,
  fetchSessionCaptures,
  fetchSessions,
  loginWithPassword,
  loginWithPersona,
  logoutSession,
  refreshAuthToken,
  resolveCaptureFileUrl,
  saveSessionForProcessing,
  searchPatients,
  storeBackendMappings,
  updateSessionTitle,
  uploadCapture,
  verifySession,
} from "./api";
import { standardizeCaptureDraft } from "./audio";
import { clearStoredAuthProfile, loadStoredAuthProfile, persistAuthProfile } from "./authStorage";
import {
  isLocalSessionId,
  makeLocalCapture,
  mergeCaptureItemsPreservingPreview,
  mergeSessionItems,
  sessionWithLocalPreview,
  sessionsFromPending,
} from "./captureModel";
import { LoginGate, PatientPreviewGate } from "./components/AuthGates";
import { AudioDialog, CaptureScreen, PhotoPreviewDialog, TextCaptureSheet } from "./components/CaptureWorkflow";
import { CaptureDestinationPanel, PatientsHome, SearchHome } from "./components/MemoryScreens";
import { Shell, SyncSafetyBanner } from "./components/Shell";
import {
  bindPendingSession,
  clearLocalCaptureData,
  loadPendingCapture,
  loadPendingCaptures,
  normalizePendingCapture,
  removePendingCapture,
  savePendingCapture,
  saveSyncedCaptureCache,
  updatePendingCapture,
} from "./storage";
import { clearWorkspaceState, loadWorkspaceState, persistWorkspaceState } from "./workspaceStorage";

const MOCK_PROCESSING_REFRESH_DELAYS = [1200, 3000, 5200, 7600];

function screenFromLocation(): Screen {
  if (typeof window === "undefined") return "active-session";
  const hash = window.location.hash.replace(/^#/, "");
  // Migration compatibility: old shared links to #organize now land on Patients.
  if (hash === "patients" || hash === "organize") return "patients";
  if (hash === "search") return "search";
  return "active-session";
}

function replaceScreenLocation(screen: Screen) {
  if (typeof window === "undefined" || !["active-session", "patients", "search"].includes(screen)) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${screen}`);
}

function shouldOpenCameraDirectly() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}

function resolveRestoredSession(storedSession: CaptureSession | null, sessions: CaptureSession[]) {
  if (!storedSession) return null;
  const current = sessions.find((session) => session.id === storedSession.id);
  if (!current) return storedSession;
  return {
    ...storedSession,
    ...current,
    items: current.items.length ? current.items : storedSession.items,
  };
}

export function App() {
  const [auth, setAuth] = React.useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = React.useState(false);
  const [authError, setAuthError] = React.useState("");
  const authRef = React.useRef<AuthSession | null>(null);
  const refreshPromiseRef = React.useRef<Promise<string> | null>(null);
  const bootstrappedAuthRef = React.useRef(false);
  const [screen, setScreen] = React.useState<Screen>(() => screenFromLocation());
  const [sessions, setSessions] = React.useState<CaptureSession[]>([]);
  const [activeSession, setActiveSession] = React.useState<CaptureSession | null>(null);
  const [selectedSessionId, setSelectedSessionId] = React.useState("");
  const [pendingCount, setPendingCount] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [textOpen, setTextOpen] = React.useState(false);
  const [photoOpen, setPhotoOpen] = React.useState(false);
  const [initialPhotoFile, setInitialPhotoFile] = React.useState<File | null>(null);
  const [audioOpen, setAudioOpen] = React.useState(false);
  const [pendingCaptureKind, setPendingCaptureKind] = React.useState<CaptureDraft["kind"] | null>(null);
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const [toast, setToast] = React.useState("");
  const mobilePhotoInputRef = React.useRef<HTMLInputElement | null>(null);
  const processingRef = React.useRef(false);
  const workspaceHydratedRef = React.useRef(false);
  const activeSessionRef = React.useRef<CaptureSession | null>(null);
  const sessionsRef = React.useRef<CaptureSession[]>([]);

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
  }, [auth]);

  React.useEffect(() => {
    if (auth) return;
    void refreshPendingCount();
  }, [auth]);

  React.useEffect(() => {
    if (!auth || !workspaceHydratedRef.current) return;
    // TODO(offline-sync): Move workspace continuity into a tenant-scoped durable sync/cache layer when background sync lands.
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
      if (!pendingCount) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnIfPending);
    return () => window.removeEventListener("beforeunload", warnIfPending);
  }, [pendingCount]);

  React.useEffect(() => {
    const retryWhenOnline = () => void processOutbox();
    window.addEventListener("online", retryWhenOnline);
    return () => window.removeEventListener("online", retryWhenOnline);
  }, []);

  const refreshPendingCount = async () => {
    const pending = await loadPendingCaptures();
    setPendingCount(pending.length);
    return pending;
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
      const nextSessions = [...localSessions, ...loadedSessions.filter((session) => !localSessions.some((local) => local.id === session.id))];
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
      setSessions(localSessions);
      if (workspace) {
        setActiveSession(resolveRestoredSession(workspace.activeSession, localSessions));
        setSelectedSessionId(workspace.selectedSessionId);
        setAssignmentSessionId(workspace.assignmentSessionId);
        setPendingCaptureKind(workspace.pendingCaptureKind);
      }
      setToast("Backend is not reachable. Captures stay on this device.");
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

  const rebuildLocalPendingSessions = async () => {
    const pending = await loadPendingCaptures();
    const localSessions = sessionsFromPending(pending);
    setSessions((current) => [
      ...localSessions,
      ...current.filter((session) => !localSessions.some((localSession) => localSession.id === session.id)),
    ]);
  };

  const scheduleCaptureProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      MOCK_PROCESSING_REFRESH_DELAYS.forEach((delay) => {
        window.setTimeout(() => {
        void fetchSessionCaptures(apiFetch, sessionId)
          .then((captures) => {
            setSessions((current) =>
              current.map((session) =>
                session.id === sessionId ? { ...session, items: mergeCaptureItemsPreservingPreview(session.items, captures) } : session,
              ),
            );
            setActiveSession((current) =>
              current?.id === sessionId ? { ...current, items: mergeCaptureItemsPreservingPreview(current.items, captures) } : current,
            );
          })
          .catch(() => undefined);
        }, delay);
      });
    },
    [apiFetch],
  );

  const scheduleSessionProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      MOCK_PROCESSING_REFRESH_DELAYS.forEach((delay) => {
        window.setTimeout(() => {
        void loadBackendSessions()
          .then((loadedSessions) => {
            const updated = loadedSessions.find((session) => session.id === sessionId);
            if (!updated) return;
            setSessions((current) =>
              current.map((session) => (session.id === sessionId ? { ...updated, items: session.items } : session)),
            );
            setActiveSession((current) => (current?.id === sessionId ? { ...updated, items: current.items } : current));
          })
          .catch(() => undefined);
        }, delay);
      });
    },
    [loadBackendSessions],
  );

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
    processingRef.current = true;
    setSyncing(true);
    try {
      const pending = await loadPendingCaptures();
      for (const pendingCapture of pending) {
        if (!authRef.current || authRef.current.tenant.id !== activeTenantId) break;
        const capture = (await loadPendingCapture(pendingCapture.id)) || pendingCapture;
        if (capture.tenantId && capture.tenantId !== activeTenantId) continue;
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
          const mergedSession = mergeSessionItems(currentSession || activeSessionRef.current, result.session, capture.item.id);
          upsertSession(mergedSession, stillPendingForLocalSession ? [] : [capture.localSessionId]);
          setActiveSession((current) =>
            current?.id === capture.localSessionId || current?.id === result.session.id
              ? mergeSessionItems(current, result.session, capture.item.id)
              : current,
          );
          setSelectedSessionId((current) => (current === capture.localSessionId ? mergedSession.id : current));
          setToast("Capture safely transferred.");
          if (result.item.status === "processing") scheduleCaptureProcessingRefresh(result.session.id);
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
            setToast("Capture transferred. Local cleanup will retry.");
          }
        } catch {
          await updatePendingCapture(capture.id, (current) => ({ ...current, retryCount: current.retryCount + 1 }));
          updateItemStatus(capture.item.id, "failed");
          await rebuildLocalPendingSessions();
          setToast("Failed.");
          continue;
        }
      }
    } finally {
      processingRef.current = false;
      setSyncing(false);
      await refreshPendingCount();
    }
  };

  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview" || !pendingCount || syncing) return;
    const retryTimer = window.setTimeout(() => void processOutbox(), 15000);
    return () => window.clearTimeout(retryTimer);
  }, [auth, pendingCount, syncing]);

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
    if (kind === "photo") {
      setInitialPhotoFile(null);
      if (shouldOpenCameraDirectly() && mobilePhotoInputRef.current) {
        setPhotoOpen(true);
        mobilePhotoInputRef.current.click();
        return;
      }
      setPhotoOpen(true);
    }
    if (kind === "audio") setAudioOpen(true);
  };

  const beginCapture = (kind: CaptureDraft["kind"]) => {
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
    setActiveSession(null);
    setSelectedSessionId("");
    navigateScreen("active-session");
    setToast("New session ready.");
  };

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
    setToast("Local pending captures cleared.");
    void hydrateFromStorage();
  };

  const saveSession = async (sessionId: string) => {
    try {
      const processingSession = await saveSessionForProcessing(apiFetch, sessionId);
      setSessions((current) =>
        current.map((session) => (session.id === sessionId ? { ...processingSession, items: session.items } : session)),
      );
      setActiveSession((current) => (current?.id === sessionId ? { ...processingSession, items: current.items } : current));
      setToast("Structured report is generating.");
      scheduleSessionProcessingRefresh(sessionId);
    } catch {
      setToast("Failed.");
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
        setToast("Session title updated.");
        return;
      }
      const updated = await updateSessionTitle(apiFetch, sessionId, title);
      setSessions((current) =>
        current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
      );
      setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
      setToast("Session title updated.");
    },
    [apiFetch],
  );

  const applySessionUpdate = React.useCallback((sessionId: string, updated: CaptureSession) => {
    setSessions((current) =>
      current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
    );
    setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
  }, []);

  const ensurePatient = React.useCallback(
    async (draft: PatientAssignmentDraft): Promise<PatientSummary> => {
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
    async (sessionId: string, draft: PatientAssignmentDraft) => {
      if (isLocalSessionId(sessionId)) {
        setToast("Sync before assigning.");
        return;
      }
      try {
        const patient = await ensurePatient(draft);
        const assigned = await assignSessionPatient(apiFetch, sessionId, patient.id);
        const enriched = {
          ...assigned,
          patientId: patient.id,
          patientName: patient.displayName,
          assignmentSource: "staff",
        };
        applySessionUpdate(sessionId, enriched);
        setAssignmentSessionId("");
        setToast("Patient assigned.");
      } catch {
        setToast("Could not assign patient.");
      }
    },
    [apiFetch, applySessionUpdate, ensurePatient],
  );

  const searchPatientsForAssignment = React.useCallback((query: string) => searchPatients(apiFetch, query), [apiFetch]);

  const verifySelectedSession = React.useCallback(
    async (sessionId: string) => {
      if (isLocalSessionId(sessionId)) {
        setToast("Sync before verifying.");
        return;
      }
      try {
        const verified = await verifySession(apiFetch, sessionId);
        applySessionUpdate(sessionId, verified);
        setToast("Session verified.");
      } catch {
        setToast("Could not verify session.");
      }
    },
    [apiFetch, applySessionUpdate],
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

  const handlePersonaLogin = async (persona: Persona) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPersona(persona));
      navigateScreen("active-session");
    } catch {
      setAuthError("Could not sign in with that persona.");
    }
  };

  const handlePasswordLogin = async (email: string, password: string) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPassword(email, password));
      navigateScreen("active-session");
    } catch {
      setAuthError("Invalid email or password.");
    }
  };

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

  const openMemorySession = (sessionId: string) => {
    const session = sessions.find((candidate) => candidate.id === sessionId);
    if (session?.status === "draft") {
      setSelectedSessionId("");
      navigateScreen("active-session");
      if (session.items.length || isLocalSessionId(session.id)) {
        setActiveSession(session);
        return;
      }
      setActiveSession(session);
      void loadCapturesForSession(session.id)
        .then((captures) => {
          setActiveSession((current) => (current?.id === session.id ? { ...session, items: captures } : current));
        })
        .catch(() => setToast("Could not load captures for this session."));
      return;
    }
    setSelectedSessionId(sessionId);
    if (session && !session.items.length && !isLocalSessionId(session.id)) {
      void loadCapturesForSession(session.id).catch(() => setToast("Could not load captures for this session."));
    }
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
          onCloseAssignment={() => setAssignmentSessionId((current) => (current === selectedSession.id ? "" : selectedSession.id))}
          onSaveSession={saveSession}
          onResolveFile={resolveSourceFile}
          onStartNewSession={activeSession?.items.length ? startNewSession : undefined}
          onUpdateTitle={renameSession}
          onVerifySession={verifySelectedSession}
        />
      );
    }
    if (screen === "active-session") {
      return (
        <CaptureScreen
          activeSession={activeSession}
          assignmentOpen={Boolean(activeSession && assignmentSessionId === activeSession.id)}
          onAssignPatient={assignPatientToSession}
          onSearchPatients={searchPatientsForAssignment}
          onCloseAssignment={() => {
            if (!activeSession) return;
            setAssignmentSessionId((current) => (current === activeSession.id ? "" : activeSession.id));
          }}
          onSaveSession={saveSession}
          onResolveFile={resolveSourceFile}
          onUpdateTitle={renameSession}
          onVerifySession={verifySelectedSession}
        />
      );
    }
    if (screen === "search") {
      return <SearchHome onOpenSession={openMemorySession} sessions={sessions} />;
    }
    return (
      <PatientsHome
        onAssignPatient={assignPatientToSession}
        onContinueSession={continueMemorySession}
        onOpenSession={openMemorySession}
        onVerifySession={(sessionId) => void verifySelectedSession(sessionId)}
        sessions={sessions}
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

  return (
    <>
      <Shell
        auth={auth}
        onCapture={beginCapture}
        onLogout={handleLogout}
        screen={screen}
        onNavigate={navigateScreen}
      >
        <SyncSafetyBanner
          pendingCount={pendingCount}
          syncing={syncing}
          onClearLocal={() => void clearLocalPendingCaptures()}
          onRetry={() => void processOutbox()}
        />
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
      <TextCaptureSheet
        onClose={() => setTextOpen(false)}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setTextOpen(false);
        }}
        open={textOpen}
      />
      <input
        accept="image/*"
        capture="environment"
        onChange={(event) => {
          const selectedFile = event.target.files?.[0] ?? null;
          event.target.value = "";
          if (!selectedFile) {
            setInitialPhotoFile(null);
            setPhotoOpen(true);
            return;
          }
          if (selectedFile.size === 0) {
            setInitialPhotoFile(selectedFile);
            setPhotoOpen(true);
            return;
          }
          setInitialPhotoFile(selectedFile);
          setPhotoOpen(true);
        }}
        ref={mobilePhotoInputRef}
        style={{ display: "none" }}
        type="file"
      />
      <PhotoPreviewDialog
        initialFile={initialPhotoFile}
        onClose={() => {
          setInitialPhotoFile(null);
          setPhotoOpen(false);
        }}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setInitialPhotoFile(null);
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
      />
      <Toast message={toast} />
    </>
  );
}
