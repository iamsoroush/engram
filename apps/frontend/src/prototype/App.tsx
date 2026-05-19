import React from "react";
import { flushSync } from "react-dom";
import type { ApiFetch, AuthSession, CaptureDraft, Persona, PatientAssignmentTarget } from "./appTypes";
import type { CaptureSession, CaptureStatus, Screen } from "./types";
import { Button, Card, Dialog, Skeleton, Toast } from "./ui";
import {
  assignCapturePatient,
  assignSessionPatient,
  createPatient,
  fetchSessionCaptures,
  fetchSessions,
  loginWithPassword,
  loginWithPersona,
  logoutSession,
  refreshAuthToken,
  resolveCaptureFileUrl,
  retrySessionProcessing,
  saveSessionForProcessing,
  searchPatients,
  storeBackendMappings,
  updateSessionMetadata,
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
import { OrganizeHome, SessionDetail } from "./components/OrganizeWorkflow";
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

function screenFromLocation(): Screen {
  if (typeof window !== "undefined" && window.location.hash === "#organize") return "organize";
  return "capture";
}

function replaceScreenLocation(screen: Screen) {
  if (typeof window === "undefined" || (screen !== "capture" && screen !== "organize")) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${screen}`);
}

function shouldOpenCameraDirectly() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: none) and (pointer: coarse)").matches;
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
  const [toast, setToast] = React.useState("");
  const mobilePhotoInputRef = React.useRef<HTMLInputElement | null>(null);
  const processingRef = React.useRef(false);

  const navigateScreen = React.useCallback((nextScreen: Screen) => {
    setScreen(nextScreen);
    replaceScreenLocation(nextScreen);
    if (nextScreen === "capture") setSelectedSessionId("");
  }, []);

  const clearAuth = React.useCallback(() => {
    authRef.current = null;
    setAuth(null);
    clearStoredAuthProfile();
    processingRef.current = false;
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
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  React.useEffect(() => {
    const syncScreenFromLocation = () => {
      setScreen(screenFromLocation());
      if (screenFromLocation() === "capture") setSelectedSessionId("");
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

  /**
   * Rebuilds the visible session list from durable local captures first, then
   * layers backend sessions on top so offline work is never hidden by a failed load.
   */
  const hydrateFromStorage = async () => {
    const pending = await refreshPendingCount();
    const localSessions = sessionsFromPending(pending);
    try {
      const loadedSessions = await fetchSessions(apiFetch);
      setSessions([...localSessions, ...loadedSessions.filter((session) => !localSessions.some((local) => local.id === session.id))]);
    } catch {
      setSessions(localSessions);
      setToast("Backend is not reachable. Captures stay on this device.");
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
      }, 5500);
    },
    [apiFetch],
  );

  const scheduleSessionProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      window.setTimeout(() => {
        void fetchSessions(apiFetch)
          .then((loadedSessions) => {
            const updated = loadedSessions.find((session) => session.id === sessionId);
            if (!updated) return;
            setSessions((current) =>
              current.map((session) => (session.id === sessionId ? { ...updated, items: session.items } : session)),
            );
            setActiveSession((current) => (current?.id === sessionId ? { ...updated, items: current.items } : current));
          })
          .catch(() => undefined);
      }, 5500);
    },
    [apiFetch],
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
          const stillPendingForLocalSession = pending.some(
            (pendingCapture) => pendingCapture.id !== capture.id && pendingCapture.localSessionId === capture.localSessionId,
          );
          const currentSession = sessions.find((session) => session.id === capture.localSessionId || session.id === result.session.id);
          const mergedSession = mergeSessionItems(currentSession || activeSession, result.session, capture.item.id);
          upsertSession(mergedSession, stillPendingForLocalSession ? [] : [capture.localSessionId]);
          setActiveSession((current) =>
            current?.id === capture.localSessionId || current?.id === result.session.id
              ? mergeSessionItems(current, result.session, capture.item.id)
              : current,
          );
          setSelectedSessionId((current) => (current === capture.localSessionId ? mergedSession.id : current));
          setToast("Capture safely transferred.");
          if (result.item.status === "processing") scheduleCaptureProcessingRefresh(result.session.id);
          void (async () => {
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
          })();
        } catch {
          await updatePendingCapture(capture.id, (current) => ({ ...current, retryCount: current.retryCount + 1 }));
          updateItemStatus(capture.item.id, "failed");
          await rebuildLocalPendingSessions();
          setToast("Failed/Retry");
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
        navigateScreen("capture");
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

  const beginCapture = (kind: CaptureDraft["kind"]) => {
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

  const startNewSession = () => {
    setActiveSession(null);
    setToast("New session ready.");
  };

  const clearLocalPendingCaptures = async () => {
    if (!window.confirm("Clear captures saved only on this device? This cannot be undone.")) return;
    processingRef.current = false;
    setSyncing(false);
    await clearLocalCaptureData();
    setActiveSession(null);
    setSessions([]);
    setSelectedSessionId("");
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
      setToast("Session processing started.");
      scheduleSessionProcessingRefresh(sessionId);
    } catch {
      setToast("Failed/Retry");
    }
  };

  const retrySession = async (sessionId: string) => {
    try {
      const processing = await retrySessionProcessing(apiFetch, sessionId);
      setSessions((current) =>
        current.map((session) => (session.id === sessionId ? { ...processing, items: session.items } : session)),
      );
      setActiveSession((current) => (current?.id === sessionId ? { ...processing, items: current.items } : current));
      setToast("Retry started.");
      scheduleSessionProcessingRefresh(sessionId);
    } catch {
      setToast("Failed/Retry");
    }
  };

  const verifySelectedSession = React.useCallback(
    async (sessionId: string) => {
      try {
        const verified = await verifySession(apiFetch, sessionId);
        setSessions((current) =>
          current.map((session) => (session.id === sessionId ? { ...session, ...verified, items: session.items } : session)),
        );
        setActiveSession((current) => (current?.id === sessionId ? { ...current, ...verified, items: current.items } : current));
        setToast("Session verified.");
      } catch {
        setToast("Could not verify session.");
      }
    },
    [apiFetch],
  );

  const saveSessionMetadata = React.useCallback(
    async (sessionId: string, extractedMetadata: Record<string, unknown>) => {
      const updated = await updateSessionMetadata(apiFetch, sessionId, extractedMetadata);
      setSessions((current) =>
        current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
      );
      setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
      setToast("Metadata updated.");
    },
    [apiFetch],
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

  const loadCapturesForSession = React.useCallback(
    async (sessionId: string) => {
      const captures = await fetchSessionCaptures(apiFetch, sessionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? { ...session, items: captures } : session)));
      return captures;
    },
    [apiFetch],
  );

  const searchPatientOptions = React.useCallback((query: string) => searchPatients(apiFetch, query), [apiFetch]);

  const createPatientOption = React.useCallback(
    (displayName: string, nationalId?: string) => createPatient(apiFetch, displayName, nationalId),
    [apiFetch],
  );

  const assignPatientToSession = React.useCallback(
    async (sessionId: string, target: PatientAssignmentTarget) => {
      const assigned = await assignSessionPatient(apiFetch, sessionId, target);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                ...assigned,
                items: session.items.map((item) =>
                  item.patientId
                    ? item
                    : {
                        ...item,
                        patientId: target.patientId,
                        patientName: target.patientName,
                        assignmentSource: target.source || "staff",
                      },
                ),
              }
            : session,
        ),
      );
      setToast(target.patientId ? "Session assigned." : "Session patient cleared.");
    },
    [apiFetch],
  );

  const assignPatientToCapture = React.useCallback(
    async (sessionId: string, captureId: string, target: PatientAssignmentTarget) => {
      const assigned = await assignCapturePatient(apiFetch, captureId, target);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                items: session.items.map((item) => (item.id === captureId ? { ...item, ...assigned } : item)),
              }
            : session,
        ),
      );
      setToast(target.patientId ? "Capture assigned." : "Capture patient cleared.");
    },
    [apiFetch],
  );

  const resolveSourceFile = React.useCallback((endpoint: string) => resolveCaptureFileUrl(apiFetch, endpoint), [apiFetch]);

  const handlePersonaLogin = async (persona: Persona) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPersona(persona));
      navigateScreen("capture");
    } catch {
      setAuthError("Could not sign in with that persona.");
    }
  };

  const handlePasswordLogin = async (email: string, password: string) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPassword(email, password));
      navigateScreen("capture");
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
    navigateScreen("capture");
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

  const openOrganizeSession = (sessionId: string) => {
    const session = sessions.find((candidate) => candidate.id === sessionId);
    if (session?.status === "draft") {
      setSelectedSessionId("");
      navigateScreen("capture");
      if (session.items.length || isLocalSessionId(session.id)) {
        setActiveSession(session);
        return;
      }
      setActiveSession(session);
      void loadCapturesForSession(session.id)
        .then((captures) => {
          setActiveSession((current) => (current?.id === session.id ? { ...session, items: captures } : current));
        })
        .catch(() => setToast("Could not load captures for this draft."));
      return;
    }
    setSelectedSessionId(sessionId);
    navigateScreen("organize");
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
        topAction={
          screen === "capture" && activeSession?.items.length ? (
            <Button className="top-new-session-button" onClick={startNewSession} size="sm" type="button" variant="secondary">
              + New session
            </Button>
          ) : null
        }
      >
        <SyncSafetyBanner
          pendingCount={pendingCount}
          syncing={syncing}
          onClearLocal={() => void clearLocalPendingCaptures()}
          onRetry={() => void processOutbox()}
        />
        {screen === "capture" ? (
          <CaptureScreen
            activeSession={activeSession}
            onCapture={beginCapture}
            onSaveSession={saveSession}
            onResolveFile={resolveSourceFile}
            onUpdateTitle={renameSession}
          />
        ) : (
          <OrganizeHome
            onOpenSession={openOrganizeSession}
            sessions={sessions}
          />
        )}
      </Shell>
      <Dialog
        className="session-dialog"
        onClose={() => setSelectedSessionId("")}
        open={screen !== "capture" && Boolean(selectedSession)}
        title={selectedSession?.label || "Session review"}
      >
        <SessionDetail
          onAssignCapturePatient={assignPatientToCapture}
          onAssignSessionPatient={assignPatientToSession}
          onCreatePatient={createPatientOption}
          onLoadCaptures={loadCapturesForSession}
          onRetrySession={retrySession}
          onSaveSession={saveSession}
          onSaveMetadata={saveSessionMetadata}
          onAddCapture={() => {
            if (!selectedSession) return;
            setActiveSession({
              ...selectedSession,
              status: "draft",
              reviewReason: "Draft changed after generated output",
              extractedMetadata: {
                ...(selectedSession.extractedMetadata || {}),
                generated_output_stale: true,
              },
            });
            setSelectedSessionId("");
            navigateScreen("capture");
            setToast("Add the next capture to this draft.");
          }}
          onResolveFile={resolveSourceFile}
          onSearchPatients={searchPatientOptions}
          onUpdateTitle={renameSession}
          onVerifySession={verifySelectedSession}
          session={selectedSession}
        />
      </Dialog>
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
