import React from "react";
import type {
  AftercareTemplate,
  AttentionCounts,
  AttentionResponse,
  AuthSession,
  CaptureDraft,
  DevTier,
  LineupCard,
  Persona,
  RolePermissions,
  SessionContext,
} from "../domain/appTypes";
import type { CaptureSession, Screen } from "../domain/types";
import { Card, Skeleton } from "../shared/ui/primitives";
import { currentUserRoles, isSessionReadOnly } from "../shared/lib/multiseat";
import { AppLangProvider, toLang, type Translator } from "../shared/i18n";
import {
  createAftercareTemplate,
  createPatientShare,
  deleteAftercareTemplate,
  createSession,
  fetchAttention,
  fetchLastVisit,
  fetchSessionContext,
  fetchWorklist,
  listAftercareTemplates,
  markWorklistEntrySeen,
  revokePatientShare,
  updateAftercareTemplate,
  fetchPatientMemoryDetail,
  fetchSession,
  fetchSessionCaptures,
  type RegisterClinicInput,
  resolveCaptureFileUrl,
  updateTenantSettings,
} from "../services/api/client";
import {
  isLocalAssignmentPatient,
  isLocalSessionId,
  mergeCaptureItemsPreservingPreview,
  sessionsFromPending,
  suggestedAftercareTemplateIds,
  workspaceTreatments,
  sessionDismissedAftercare,
} from "../features/capture/captureModel";
import { ProfileScreen, SettingsScreen } from "../features/account/AccountScreens";
import { TeamScreen } from "../features/account/TeamScreen";
import { InsightsScreen } from "../features/insights/InsightsScreen";
import { PlanScreen } from "../features/account/PlanScreen";
import { SwitchClinicScreen } from "../features/account/SwitchClinicScreen";
import { SharePatientSheet } from "../features/aesthetics/SharePatientSheet";
import type { GalleryVisit } from "../features/aesthetics/PatientPhotoGallery";
import { PatientPreviewGate } from "../features/auth/AuthGates";
import { UnauthShell } from "../features/auth/UnauthShell";
import { OnboardingOverlay } from "../features/onboarding/OnboardingOverlay";
import { clearOnboardingPending, isOnboardingPending, markOnboardingPending } from "../features/onboarding/onboardingState";
import { TherapyApp } from "../features/therapy/TherapyApp";
import { AddPhotoSheet, AudioDialog, TextCaptureSheet } from "../features/capture/components/CaptureDialogs";
import { CaptureScreen } from "../features/capture/components/CaptureScreen";
import { useAiUsage } from "../features/aiUsage/useAiUsage";
import { AiUsageNotice } from "../features/aiUsage/AiUsageNotice";
import { StorageGuardDialog } from "../features/capture/components/StorageGuardDialog";
import { CaptureDestinationPanel, PatientsHome, type ClinicalMemoryReturnContext } from "../features/memory/components/MemoryScreens";
import { attentionBadgeCount } from "../features/memory/components/attentionModel";
import { useMemoryApi } from "../features/memory/useMemoryApi";
import { FinderOverlay } from "../features/finder";
import { DoctorQaInbox } from "../features/qa/DoctorQaInbox";
import { openQaChannel, fetchQaInboxSummary, type QaInboxSummary } from "../features/qa/qaClient";
import { Shell } from "../features/shell/Shell";
import { clearLocalCaptureData } from "../services/storage/captureStorage";
import { clearWorkspaceState, loadWorkspaceState, persistWorkspaceState } from "../services/storage/workspaceStorage";
import { useBackLevel } from "../shared/lib/backStack";
import { makeEmptyLocalSession, mergeSessionUpdate, resolveRestoredSession } from "./sessionState";
import { ApiProvider, useApi } from "./providers/ApiProvider";
import { AuthProvider, useAuth } from "./providers/AuthProvider";
import { CapabilitiesProvider, useCapabilities } from "./providers/CapabilitiesProvider";
import { SyncProvider, useSync, useRegisterSyncBridge, type SyncBridge } from "./providers/SyncProvider";
import { SessionStoreProvider, useSessionStore } from "./providers/SessionStoreProvider";
import { NavigationProvider, useNavigation } from "./providers/NavigationProvider";
import { ToastProvider, useToast } from "./providers/ToastProvider";

// E9 — where a freshly signed-in user lands. Doctors capture-first → the Session workspace;
// reception (assistant) and admins coordinate → Clinical Memory (worklist, patients, needs-input).
function defaultScreenForAuth(auth: AuthSession): Screen {
  const roles = auth.memberships.filter((m) => m.tenantId === auth.tenant.id).map((m) => m.role);
  const effective = roles.length ? roles : auth.user.persona ? [String(auth.user.persona)] : [];
  if (effective.includes("doctor")) return "active-session";
  if (effective.includes("assistant") || effective.includes("admin")) return "patients";
  return "active-session";
}

/** Clinic-management pages reachable only by owner/admin (route-guarded; see the redirect effect). */
const OWNER_ADMIN_SCREENS: Screen[] = ["insights", "team", "plan"];


function AppInner() {
  const apiFetch = useApi();
  // App-wide UI language, date/Jalali formatting, and document direction are all driven from the
  // tenant's APP language (distinct from report language, which scopes only report/share content) by
  // <AppLangProvider>, which wraps every authed render branch below. Auth state + lifecycle live in
  // AuthProvider (seam A2); `authRef` and `appT` are exposed for the still-in-App async sync/session
  // code that must read the latest tenant/app-language without a reactive dependency.
  const {
    auth,
    authReady,
    authError,
    authRef,
    appT,
    commitAuth,
    signInWithPersona,
    signInWithPassword,
    register,
    switchClinic,
    applyTierChange,
    logout,
    onboardingDismissed,
    setOnboardingDismissed,
  } = useAuth();
  // Capability seam (A3): tier/role affordances have one home. Replaces the scattered
  // `auth.tenant.tier !== "basic"` checks + `onFetchX = isPro ? cb : undefined` prop-gating below.
  const { isBasic, canUseQa, canUseSmartLists, canManageTeam } = useCapabilities();
  // The Clinical-Memory API surface, bound once (patient search, recent memory, Pro lot ledger/recall,
  // Q&A) — consumed by the unified finder overlay below.
  const memoryApi = useMemoryApi();
  // Seam B (increment 4): the offline outbox engine + its sync UI state (online/reachable/pending
  // counts/syncing/storage) live in SyncProvider. App drives it via `sync.*` and registers the
  // session bridge below so the engine can read/write session state that still lives here.
  const sync = useSync();
  // Seam C (frontend-refactor plan §4, increment 5): the capture/session domain store. App destructures
  // the omnibus back into the local names its render body + navigation helpers already use; feature
  // screens consume the narrower useSessions()/useActiveSession()/useSessionActions() seams instead.
  const {
    sessions,
    setSessions,
    activeSession,
    setActiveSession,
    selectedSessionId,
    setSelectedSessionId,
    assignmentSessionId,
    setAssignmentSessionId,
    memoryRefreshSignal,
    sessionSink,
    upsertSession,
    assignPatientToSession,
    loadCapturesForSession,
  } = useSessionStore();
  // Seam D (frontend-refactor plan §2, increment 7): navigation + history + return-context. App
  // destructures the omnibus back into the local names its render body + navigation helpers use.
  const {
    screen,
    navigateScreen,
    shouldRestoreLastScreen,
    clinicalMemoryReturnContext,
    setClinicalMemoryReturnContext,
    captureReturnSession,
    setCaptureReturnSession,
    accountReturnRef,
  } = useNavigation();
  // Unified attention roll-up for the top-bar indicator (AES-1003): one count that merges the S2
  // "to confirm" items with pending Q&A messages (safety keeps top salience but is never a to-do).
  const [attention, setAttention] = React.useState<{ counts: AttentionCounts; highestTier: AttentionResponse["highestTier"] } | null>(null);
  // Pending Q&A count for the glanceable top-bar badge (AES-1901) — messages earn their own badge again
  // (a deliberate partial-revert of the E16 merge; the bell keeps its merged count). Polled with the
  // attention roll-up; a newly-arrived URGENT thread also fires a toast (see below).
  const [qaSummary, setQaSummary] = React.useState<QaInboxSummary | null>(null);
  const seenUrgentThreadsRef = React.useRef<Set<string> | null>(null);
  // The unified finder overlay (AES-1201..1205): app-wide, floats over the current screen.
  const [finderOpen, setFinderOpen] = React.useState(false);
  // AES-1610 — the session whose capture screen should arm the guided attention-review state (opened
  // from a grouped Close-the-day card). Cleared once the active session moves off it (effect below).
  const [reviewSessionId, setReviewSessionId] = React.useState<string | null>(null);
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
  const [sessionShare, setSessionShare] = React.useState<{ id: string; name: string; visits: GalleryVisit[]; preferredAftercareId?: string } | null>(null);
  const [ghostPhotoUrl, setGhostPhotoUrl] = React.useState("");
  const [pendingCaptureKind, setPendingCaptureKind] = React.useState<CaptureDraft["kind"] | null>(null);
  // E9 — the patient whose file is open in Clinical Memory. While set (and on the patients screen),
  // the footer captures *for that patient* (a new visit). Cleared when the detail closes or the
  // screen changes, so the target naturally reverts to the active session.
  const [viewedPatient, setViewedPatient] = React.useState<{ id: string; name: string } | null>(null);
  // Toast is owned by ToastProvider (seam A4) — App raises them via setToast; the provider renders it.
  const { setToast } = useToast();
  const workspaceHydratedRef = React.useRef(false);

  // Sync/workspace refs are App-local (they belong to the outbox + workspace-persistence machinery,
  // extracted in later increments), so reset them here whenever auth clears — covering logout and a
  // failed token refresh, which AuthProvider's clearAuth can no longer reach.
  React.useEffect(() => {
    if (!auth) {
      sync.resetProcessing();
      workspaceHydratedRef.current = false;
    }
  }, [auth, sync]);

  // The indicator scope follows the sweep's role default (AES-1005): a doctor/owner clears their own
  // doses/safety/messages (`mine`); reception (assistant/admin) coordinates intake (`clinic`).
  const attentionScope = React.useMemo<"mine" | "clinic">(() => {
    const role = auth?.memberships.find((m) => m.tenantId === auth.tenant.id)?.role || auth?.user.persona;
    return role === "assistant" || role === "admin" ? "clinic" : "mine";
  }, [auth]);

  // Refreshed on login, on any memory-refresh signal (a capture/assignment lands), and on a gentle
  // interval — a new patient question arrives out-of-band, so the indicator can't wait for a screen
  // open. The doctor sending/dismissing a Q&A reply also refreshes it (the inbox calls onChanged).
  const refreshAttention = React.useCallback(() => {
    if (!auth || auth.user.persona === "patient-preview") {
      setAttention(null);
      return;
    }
    fetchAttention(apiFetch, { scope: attentionScope })
      .then((response) => setAttention({ counts: response.counts, highestTier: response.highestTier }))
      .catch(() => undefined);
  }, [apiFetch, auth, attentionScope]);

  // The Q&A badge follows the same scope the bell uses (a doctor sees their routed threads; reception
  // the clinic) — "scoped like the inbox's Mine/Clinic". A newly-arrived urgent thread fires an in-app
  // toast «سؤال فوری بیمار — تاری دید»; the first fetch seeds the seen-set so we alert on ARRIVAL, not
  // on every pre-existing urgent thread each time the app opens.
  const inboxScope = attentionScope === "clinic" ? "all" : "mine";
  const refreshQaSummary = React.useCallback(() => {
    if (!auth || auth.user.persona === "patient-preview" || !canUseQa) {
      setQaSummary(null);
      return;
    }
    fetchQaInboxSummary(apiFetch, inboxScope)
      .then((summary) => {
        setQaSummary(summary);
        const nowUrgent = new Set(summary.urgentThreads.map((thread) => thread.threadId));
        const seen = seenUrgentThreadsRef.current;
        if (seen === null) {
          seenUrgentThreadsRef.current = nowUrgent; // first load — seed without alerting.
          return;
        }
        for (const thread of summary.urgentThreads) {
          if (!seen.has(thread.threadId)) {
            const flag = thread.flags[0];
            const label = flag ? appT(`qa.redflag.${flag}`) : appT("qa.redflag.generic");
            // Loud + held longer than a routine toast — an urgent patient question must not slip by.
            setToast(appT("qa.urgentToast", { flag: label }), { tone: "danger", durationMs: 7000 });
          }
        }
        seenUrgentThreadsRef.current = nowUrgent;
      })
      .catch(() => undefined);
  }, [apiFetch, auth, canUseQa, inboxScope, appT, setToast]);

  // Freshness (AES-1901): both counts poll while the app is VISIBLE (~60s) and refetch on window focus
  // / on becoming visible; the interval pauses when hidden (a backgrounded tab shouldn't poll). A new
  // patient question arrives out-of-band, so the badge/bell can't wait for a screen open.
  const refreshFreshness = React.useCallback(() => {
    refreshAttention();
    refreshQaSummary();
  }, [refreshAttention, refreshQaSummary]);

  React.useEffect(() => {
    refreshFreshness();
    if (!auth || auth.user.persona === "patient-preview") return;
    const handle = window.setInterval(() => {
      if (!document.hidden) refreshFreshness();
    }, 60_000);
    const onVisible = () => {
      if (!document.hidden) refreshFreshness();
    };
    window.addEventListener("focus", refreshFreshness);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(handle);
      window.removeEventListener("focus", refreshFreshness);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshFreshness, memoryRefreshSignal, auth]);

  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview") return;
    void hydrateFromStorage();
    void navigator.storage?.persist?.();
    void sync.refreshStorage();
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


  const loadBackendSessions = sync.loadBackendSessions;

  /**
   * Rebuilds the visible session list from durable local captures first, then
   * layers backend sessions on top so offline work is never hidden by a failed load.
   */
  const hydrateFromStorage = async () => {
    const pending = await sync.refreshPendingCount();
    const localSessions = sessionsFromPending(pending);
    const workspace = loadWorkspaceState(authRef.current?.tenant.id);
    try {
      const loadedSessions = await loadBackendSessions();
      sync.setBackendReachable(true);
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
        // Navigation-race rule (seam D): an explicit initial hash always wins over restore-last-screen;
        // only restore the persisted screen when the load carried no hash.
        if (shouldRestoreLastScreen && ["active-session", "patients", "search"].includes(workspace.screen)) {
          navigateScreen(workspace.screen as Screen);
        }
      }
    } catch {
      sync.setBackendReachable(false);
      setSessions(localSessions);
      if (workspace) {
        setActiveSession(resolveRestoredSession(workspace.activeSession, localSessions));
        setSelectedSessionId(workspace.selectedSessionId);
        setAssignmentSessionId(workspace.assignmentSessionId);
        setPendingCaptureKind(workspace.pendingCaptureKind);
      }
      setToast(appT("capture.toastOfflineSavedDevice"));
    } finally {
      workspaceHydratedRef.current = true;
    }
    if (pending.length) window.setTimeout(() => void sync.processOutbox(), 0);
  };


  // Fair-use monthly AI usage/limit. Fetched on login and re-fetched over the same signal that fires
  // after captures/processing, so the calm usage surfaces (Settings card + capture notice) stay current.
  const { state: aiUsage, refresh: refreshAiUsage } = useAiUsage(apiFetch, `${auth?.tenant.id ?? ""}:${memoryRefreshSignal}`);


  // When a patient is determined for the active session (manual assign OR AI match), fetch the
  // deterministic session context — last-visit digest + cross-visit photo strip + key facts — so the
  // context card can surface it in BOTH tiers (Pro is no longer blank here; the intelligent window
  // layers on top later). Also resolve the prior visit's first photo as a ghost overlay (AES-105) for
  // the next shot, kept Basic-only. Deterministic retrieval — no AI.
  const patientId = activeSession?.patientId;
  const activeSessionId = activeSession?.id;
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
        const ghostEndpoint = isBasic ? firstPhoto?.contentEndpoint || firstPhoto?.fileEndpoint : null;
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
  }, [apiFetch, isBasic, patientId, activeSessionId]);


  // The outbox engine (upload / operation replay / retry interval / optimistic saveDraft) lives in
  // SyncProvider (seam B); App calls it via `sync.*`. The engine reads/writes session state through
  // the bridge registered below.
  const saveDraft = sync.saveDraft;

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
    if (sync.storage.level === "full") {
      void sync.refreshStorage();
      sync.setStorageGuardOpen(true);
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
    setToast(appT("capture.toastNewSessionReady"));
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
        setToast(appT("capture.toastCouldNotStartVisit"));
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
    if (!window.confirm(appT("capture.confirmClearLocal"))) return;
    sync.resetProcessing();
    await clearLocalCaptureData();
    clearWorkspaceState();
    setActiveSession(null);
    setSessions([]);
    setSelectedSessionId("");
    setAssignmentSessionId("");
    setPendingCaptureKind(null);
    setToast(appT("capture.toastPendingCleared"));
    // hydrate refreshes the pending counts (owned by SyncProvider) once the caches are re-read.
    void hydrateFromStorage();
  };


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

  const resolveSourceFile = React.useCallback((endpoint: string) => resolveCaptureFileUrl(apiFetch, endpoint), [apiFetch]);

  // Stable callbacks for the aesthetics-Basic surfaces. These feed child effects (smart search,
  // gallery, share sheet, resolvers), so they MUST be memoized — an inline `() => fn(apiFetch, …)`
  // is a new reference every render and would re-fire those effects (the "refreshing every few
  // seconds" symptom). apiFetch is itself stable.
  const getPatientMemoryDetail = React.useCallback((patientId: string) => fetchPatientMemoryDetail(apiFetch, patientId), [apiFetch]);

  // Pro: fetch the active patient's curated brief for the session context card, polling while it is
  // still "organizing" (read-triggered cold generation), capped so it never spins forever.
  React.useEffect(() => {
    if (isBasic || !patientId || isLocalAssignmentPatient(patientId)) {
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
  }, [getPatientMemoryDetail, isBasic, patientId]);
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
  const createAftercare = React.useCallback((draft: Parameters<typeof createAftercareTemplate>[1]) => createAftercareTemplate(apiFetch, draft), [apiFetch]);
  const updateAftercare = React.useCallback((id: string, draft: Parameters<typeof updateAftercareTemplate>[2]) => updateAftercareTemplate(apiFetch, id, draft), [apiFetch]);
  const deleteAftercare = React.useCallback((id: string) => deleteAftercareTemplate(apiFetch, id), [apiFetch]);


  // Auth sign-in/register/switch are owned by AuthProvider; App wraps them only to land on the
  // role-appropriate default screen (or, for register, to also navigate while letting the form map
  // 409/422 from the propagated error).
  const handlePersonaLogin = async (persona: Persona, tier: DevTier = "pro") => {
    const next = await signInWithPersona(persona, tier);
    if (next) navigateScreen(defaultScreenForAuth(next));
  };

  const handlePasswordLogin = async (email: string, password: string) => {
    const next = await signInWithPassword(email, password);
    if (next) navigateScreen(defaultScreenForAuth(next));
  };

  const handleRegister = async (input: RegisterClinicInput) => {
    const next = await register(input);
    navigateScreen(defaultScreenForAuth(next));
  };

  // Plan switch (Plan screen): reflect the new tier in the in-app tenant so capabilities + UI follow.
  const handleTierChanged = (tier: string) => {
    applyTierChange(tier);
    setToast(appT("capture.toastSwitchedTier", { tier: tier === "pro" ? "Pro" : "Basic" }));
  };

  const handleSwitchClinic = async (tenantId: string) => {
    const next = await switchClinic(tenantId);
    navigateScreen(defaultScreenForAuth(next));
  };

  // Re-arm the first-run guide so a user who skipped it can replay it (from the account menu).
  const handleReplayGuide = () => {
    const current = authRef.current;
    if (!current) return;
    markOnboardingPending(current.user.id);
    setOnboardingDismissed(false);
    navigateScreen("active-session");
  };

  const handleUpdateTenantSettings = React.useCallback(
    async (settings: {
      appLanguage?: string;
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
            // Propagate the app language so changing it LIVE re-renders <AppLangProvider> (no reload).
            appLanguage: updated.appLanguage ?? settings.appLanguage ?? currentAuth.tenant.appLanguage,
            transcriptionLanguage: updated.transcriptionLanguage ?? currentAuth.tenant.transcriptionLanguage,
            reportLanguage: updated.reportLanguage ?? null,
            matchStrictness: updated.matchStrictness ?? currentAuth.tenant.matchStrictness,
            // AES-905: the response carries the full effective preset map (defaults + overrides).
            rolePermissions: updated.rolePermissions ?? currentAuth.tenant.rolePermissions,
          },
        });
        setToast(
          changingPermissions
            ? appT("settings.toastRolePermsUpdated")
            : changingStrictness
              ? appT("settings.toastMatchingUpdated")
              : appT("settings.toastLanguageUpdated"),
        );
      } catch {
        setToast(
          changingPermissions
            ? appT("settings.toastCouldNotUpdateRolePerms")
            : changingStrictness
              ? appT("settings.toastCouldNotUpdateMatching")
              : appT("settings.toastCouldNotUpdateLanguage"),
        );
      }
    },
    [apiFetch, commitAuth],
  );

  const handleLogout = async () => {
    // AuthProvider.logout() clears auth locally then best-effort revokes the backend session; App
    // clears the session workspace and returns to capture (SyncProvider owns the sync state).
    setSessions([]);
    setActiveSession(null);
    setSelectedSessionId("");
    navigateScreen("active-session");
    void sync.refreshPendingCount();
    await logout();
  };

  const selectedSession = sessions.find((session) => session.id === selectedSessionId);
  // Sync health + offline flag + offline-return receipt are owned by SyncProvider (seam B).
  const { syncHealth, offline } = sync;
  const activeSessionOrdinal = computeSessionOrdinal(activeSession, sessions);

  // Disarm the guided review once the active session moves off the one it was armed for (navigating
  // away, starting a new visit, or opening another session) — so it never re-arms on a later plain open.
  React.useEffect(() => {
    if (reviewSessionId && activeSession?.id !== reviewSessionId) setReviewSessionId(null);
  }, [activeSession?.id, reviewSessionId]);

  // A historical visit review (opened over Clinical Memory) gets its own history entry so Back
  // returns to the memory list instead of exiting the area (item: in-screen history levels).
  useBackLevel(screen !== "active-session" && Boolean(selectedSession), () => setSelectedSessionId(""));

  // The finder overlay is an in-screen level: hardware Back closes it before exiting the area (AES-1201).
  useBackLevel(finderOpen, () => setFinderOpen(false));

  // Desktop launcher: ⌘K / Ctrl-K opens the finder from anywhere — a nicety layered on the mobile-first
  // top-bar entry (harmless on mobile, which has no hardware keyboard). Not load-bearing (AES-1205).
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        setFinderOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // `/#search` is a deep-link into the finder: open the overlay over the Clinical-Memory workspace and
  // normalize the hash. The old local-substring search screen is retired — its behavior survives only as
  // the finder's offline fallback (AES-1204).
  React.useEffect(() => {
    if (screen === "search") {
      navigateScreen("patients");
      setFinderOpen(true);
    }
  }, [screen, navigateScreen]);

  // Route guard (AES-1501): the clinic-management pages (Insights / Team / Plan) are owner/admin only.
  // The account menu already hides them, but a direct `#insights`/`#team`/`#plan` hash (deep link,
  // bookmark, restored screen) by a plain doctor would otherwise render the page and 403 the API.
  // Redirect to `#patients`; the render below also falls through for these screens so no owner-only
  // content flashes and no API call fires before the hash normalizes.
  React.useEffect(() => {
    if (auth && OWNER_ADMIN_SCREENS.includes(screen) && !canManageTeam) {
      navigateScreen("patients");
    }
  }, [auth, screen, canManageTeam, navigateScreen]);

  // Register the outbox engine's session bridge (seam B). Session state + the SessionSink now live in
  // SessionStore (seam C, increment 5); App wires the store's sink into the bridge and keeps ownership
  // of navigation (the router seam, increment 7). Placed before any early return so hook order is stable.
  const syncBridge: SyncBridge = {
    session: sessionSink,
    navigateActiveSession: () => navigateScreen("active-session"),
  };
  // useRegisterSyncBridge re-points a stable ref at this object every render, so the engine always
  // sees the latest navigation callback (a fresh object here is correct — freshness is the point).
  useRegisterSyncBridge(syncBridge);

  const openMemorySession = (sessionId: string, returnContext?: ClinicalMemoryReturnContext, opts?: { review?: boolean }) => {
    setClinicalMemoryReturnContext(returnContext || null);
    // Arm (or clear) the guided attention-review state for this open (a grouped sweep card sets it).
    setReviewSessionId(opts?.review ? sessionId : null);
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
          .catch(() => setToast(appT("capture.toastCouldNotLoadCaptures")));
      }
      return;
    }
    setSelectedSessionId(sessionId);
  };

  const returnToClinicalMemory = () => {
    setSelectedSessionId("");
    navigateScreen("patients");
  };

  // Open a patient's timeline from the finder — no capture round-trip stash (the finder is not a
  // mid-visit jump), just land on the patient's file in Clinical Memory.
  const openPatientFromFinder = (patientId: string) => {
    setClinicalMemoryReturnContext({ tab: "patients", patientId });
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
    // Keep the share consistent with the report's auto-included aftercare: default the share's
    // aftercare to the matched clinic template the doctor hasn't removed for this visit.
    const matchedIds = aftercareTemplates.length
      ? suggestedAftercareTemplateIds(aftercareTemplates, workspaceTreatments(session))
      : new Set<string>();
    const dismissed = new Set(sessionDismissedAftercare(session));
    const preferredAftercareId = aftercareTemplates.find(
      (template) => template.isActive && matchedIds.has(template.id) && !dismissed.has(template.id),
    )?.id;
    setSessionShare({
      id: session.patientId,
      name: session.patientName || "Patient",
      visits: [{ sessionId: session.id, title: "Visit", dateLabel: "" }],
      preferredAftercareId,
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
    ? appT("capture.backToPatientHistory")
    : clinicalMemoryReturnContext?.tab === "recent"
      ? appT("patients.tab.recent")
      : clinicalMemoryReturnContext?.tab === "attention"
        ? appT("patients.tab.attention")
        : clinicalMemoryReturnContext?.tab === "patients"
          ? appT("patients.tab.patients")
          : appT("capture.backToMemory");

  // The top-bar Attention indicator opens the Close-the-day sweep — the Attention tab of Clinical
  // Memory. Setting the return context to that tab makes PatientsHome land on (and switch to) it.
  const openAttention = () => {
    setCaptureReturnSession(null);
    setClinicalMemoryReturnContext({ tab: "attention" });
    navigateScreen("patients");
  };

  const handleShellNavigate = (nextScreen: Screen) => {
    // Settings/Profile are utility pages reached from the account menu; remember where we came
    // from so Back returns there (don't record an account page as its own return target).
    const accountScreens: Screen[] = ["settings", "profile", "team", "insights", "plan", "switch-clinic"];
    if (accountScreens.includes(nextScreen) && !accountScreens.includes(screen)) {
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
      reviewReason: session.reviewReason || appT("capture.currentCaptureDestination"),
    };
    setSelectedSessionId("");
    setActiveSession(nextSession);
    navigateScreen("active-session");
    if (!session.items.length && !isLocalSessionId(session.id)) {
      void loadCapturesForSession(session.id)
        .then((captures) => {
          setActiveSession((current) => (current?.id === session.id ? { ...nextSession, items: captures } : current));
        })
        .catch(() => setToast(appT("capture.toastCouldNotLoadCaptures")));
    }
    setToast(appT("capture.toastAddNext"));
  };

  const renderCurrentScreen = () => {
    if (screen === "settings" && auth) {
      return (
        <SettingsScreen
          auth={auth}
          onBack={() => navigateScreen(accountReturnRef.current)}
          onUpdateSettings={handleUpdateTenantSettings}
          onListAftercareTemplates={listAftercare}
          onCreateAftercareTemplate={createAftercare}
          onUpdateAftercareTemplate={updateAftercare}
          onDeleteAftercareTemplate={deleteAftercare}
          apiFetch={apiFetch}
          aiUsage={aiUsage}
          onRefreshAiUsage={refreshAiUsage}
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
    if (screen === "team" && auth && canManageTeam) {
      return <TeamScreen auth={auth} apiFetch={apiFetch} onBack={() => navigateScreen(accountReturnRef.current)} />;
    }
    if (screen === "insights" && auth && canManageTeam) {
      return <InsightsScreen auth={auth} apiFetch={apiFetch} onBack={() => navigateScreen(accountReturnRef.current)} />;
    }
    if (screen === "plan" && auth && canManageTeam) {
      return (
        <PlanScreen
          auth={auth}
          apiFetch={apiFetch}
          onBack={() => navigateScreen(accountReturnRef.current)}
          onTierChanged={handleTierChanged}
        />
      );
    }
    if (screen === "switch-clinic" && auth) {
      return (
        <SwitchClinicScreen auth={auth} onBack={() => navigateScreen(accountReturnRef.current)} onSwitch={handleSwitchClinic} />
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
              reviewReason: appT("capture.currentCaptureDestination"),
            });
            setSelectedSessionId("");
            navigateScreen("active-session");
            setToast(appT("capture.toastAddNext"));
          }}
          assignmentOpen={assignmentSessionId === selectedSession.id}
          onCloseAssignment={() => setAssignmentSessionId((current) => (current === selectedSession.id ? "" : selectedSession.id))}
          onOpenResolver={() => setAssignmentSessionId(selectedSession.id)}
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
          onStartNewSession={startNewSession}
          sessionContext={sessionContext}
          lineupCard={sessionLineupCard}
          onOpenVisit={(sessionId) => openMemorySession(sessionId)}
          onViewPatientHistory={openPatientHistory}
          onShareVisit={openSessionShare}
          onUseAsNote={composeNoteFromText}
          aftercareTemplates={aftercareTemplates}
          sessionOrdinal={activeSessionOrdinal}
          currentUserId={auth?.user.id ?? null}
          readOnly={activeSession ? isSessionReadOnly(activeSession, auth) : false}
          nextLinedUpPatient={nextLinedUpPatient ? { patientName: nextLinedUpPatient.patientName } : null}
          onAssignActiveToNext={assignActiveVisitToNext}
          onStartNextVisit={startNextLinedUpVisit}
          usageNotice={<AiUsageNotice state={aiUsage} />}
          reviewMode={Boolean(activeSession && reviewSessionId === activeSession.id)}
        />
      );
    }
    if (screen === "qa-inbox" && canUseQa) {
      // Pro-only post-session patient Q&A inbox (AES-402); the nav entry is hidden for Basic.
      return (
        <DoctorQaInbox
          apiFetch={apiFetch}
          onToast={setToast}
          onChanged={refreshFreshness}
          onShareQaLink={() => setFinderOpen(true)}
        />
      );
    }
    return (
      <PatientsHome
        // `initialPatientId` seeds the open patient file on MOUNT only. When the finder targets a
        // patient while Clinical Memory is already the screen beneath it, PatientsHome is already
        // mounted, so keying on the target id remounts it and the file opens (AES-1201). Undefined
        // target → stable key, no churn on ordinary Patients-tab use.
        key={`patients-${clinicalMemoryReturnContext?.patientId ?? ""}`}
        initialPatientId={clinicalMemoryReturnContext?.patientId}
        onBackToVisit={captureReturnSession ? returnToActiveCapture : undefined}
        initialTab={clinicalMemoryReturnContext?.tab}
        onContinueSession={continueMemorySession}
        onOpenSession={openMemorySession}
        onStartVisit={startVisitForPatient}
        onViewingPatientChange={setViewedPatient}
        onOpenQaInbox={canUseQa ? () => navigateScreen("qa-inbox") : undefined}
        // The unified attention count (same source as the top-bar bell) feeds the Today chip, so the
        // two "needs me" numbers can never disagree; surface-by-exception when zero (#1, AES-1007).
        attentionCount={attention ? attentionBadgeCount(attention.counts) : 0}
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
      <UnauthShell
        error={authError}
        onLogin={handlePasswordLogin}
        onPersonaLogin={handlePersonaLogin}
        onRegister={handleRegister}
        pendingCount={syncHealth.pendingCaptures}
      />
    );
  }

  if (auth.user.persona === "patient-preview") {
    return (
      <AppLangProvider lang={toLang(auth.tenant.appLanguage)}>
        <PatientPreviewGate auth={auth} onLogout={handleLogout} />
      </AppLangProvider>
    );
  }

  // Therapy vertical is a greenfield surface (note-first capture, two-plane synthesis, federated
  // caseloads) — render its own self-contained app rather than the aesthetics capture shell.
  if (auth.tenant.vertical === "therapy") {
    return (
      <AppLangProvider lang={toLang(auth.tenant.appLanguage)}>
        <TherapyApp auth={auth} apiFetch={apiFetch} onLogout={handleLogout} aiUsage={aiUsage} onRefreshAiUsage={refreshAiUsage} />
      </AppLangProvider>
    );
  }

  return (
    <AppLangProvider lang={toLang(auth.tenant.appLanguage)}>
      <>
      {!onboardingDismissed && isOnboardingPending(auth.user.id) ? (
        <OnboardingOverlay
          canInviteTeam={auth.memberships.some(
            (m) => m.tenantId === auth.tenant.id && (m.role === "owner" || m.role === "admin"),
          )}
          captureCount={activeSession?.items.length ?? 0}
          captureDialogOpen={textOpen || photoOpen || audioOpen}
          displayName={auth.user.displayName || auth.user.email || ""}
          lang={auth.tenant.appLanguage === "fa" ? "fa" : "en"}
          onFinish={() => {
            clearOnboardingPending();
            setOnboardingDismissed(true);
          }}
          onInviteTeam={() => {
            clearOnboardingPending();
            setOnboardingDismissed(true);
            navigateScreen("team");
          }}
          onSeePlan={() => {
            clearOnboardingPending();
            setOnboardingDismissed(true);
            navigateScreen("plan");
          }}
          tier={auth.tenant.tier ?? "basic"}
        />
      ) : null}
      <Shell
        auth={auth}
        captureContextLabel={captureContextLabel(activeSession, screen, viewedPatient, appT)}
        onCapture={beginCapture}
        onLogout={handleLogout}
        onReplayGuide={handleReplayGuide}
        screen={screen}
        syncHealth={syncHealth}
        onNavigate={handleShellNavigate}
        attentionCounts={attention?.counts ?? null}
        attentionHighestTier={attention?.highestTier ?? null}
        onOpenAttention={openAttention}
        qaPendingCount={qaSummary?.pending ?? 0}
        qaUrgent={(qaSummary?.urgent ?? 0) > 0}
        onOpenFinder={() => setFinderOpen(true)}
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
      {finderOpen ? (
        <FinderOverlay
          onClose={() => setFinderOpen(false)}
          memoryApi={memoryApi}
          sessions={sessions}
          syncHealth={syncHealth}
          onOpenPatient={openPatientFromFinder}
          onOpenSession={openMemorySession}
          onCreatePatient={() => navigateScreen("patients")}
          onToast={setToast}
        />
      ) : null}
      {sessionShare && auth ? (
        <SharePatientSheet
          patientId={sessionShare.id}
          patientName={sessionShare.name}
          visits={sessionShare.visits}
          sessionId={sessionShare.visits[0]?.sessionId}
          preferredAftercareId={sessionShare.preferredAftercareId}
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
        storageWarning={sync.storage.level === "warn" ? sync.storage : null}
      />
      {sync.storageGuardOpen ? (
        <StorageGuardDialog
          onClose={() => sync.setStorageGuardOpen(false)}
          onExport={sync.exportQueuedCaptures}
          pendingCount={syncHealth.pendingCaptures}
          storage={sync.storage}
        />
      ) : null}
      {sync.offlineReceipt > 0 ? (
        <div className="offline-return-receipt" role="status" aria-live="polite">
          <span className="offline-return-receipt-icon" aria-hidden="true">✓</span>
          <span>{appT("sync.returnReceipt", { count: sync.offlineReceipt })}</span>
        </div>
      ) : null}
      </>
    </AppLangProvider>
  );
}

// Composition root (frontend-refactor plan §2). Assembles the shared-infrastructure provider seams
// around the app body. Increments 1–3 mounted Api/Auth/Capabilities; increment 4 adds SyncProvider
// (seam B — the offline outbox engine) and ToastProvider (seam A4). Increment 5 adds the session store.
export function App() {
  return (
    <ToastProvider>
      <ApiProvider>
        <AuthProvider>
          <CapabilitiesProvider>
            <SyncProvider>
              <SessionStoreProvider>
                <NavigationProvider>
                  <AppInner />
                </NavigationProvider>
              </SessionStoreProvider>
            </SyncProvider>
          </CapabilitiesProvider>
        </AuthProvider>
      </ApiProvider>
    </ToastProvider>
  );
}


function captureContextLabel(session: CaptureSession | null, screen: Screen, viewedPatient: { id: string; name: string } | null, t: Translator) {
  // On a patient's file the footer captures for *them* (a new visit) — make that explicit. The patient
  // NAME stays as data; only the surrounding chrome is translated.
  if (screen === "patients" && viewedPatient) {
    return t("capture.capturingForNewVisit", { name: viewedPatient.name });
  }
  const patient = session?.patientName || t("capture.unassignedVisit");
  return t("capture.capturingForToday", { name: patient });
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
