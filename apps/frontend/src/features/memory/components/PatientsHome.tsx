// Clinical Memory home screen (Today / Patients / Needs input tabs).
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { AftercareTemplate, AssignmentSuggestionResponse, AttentionItem, AttentionScope, AuthSession, ClinicMember, CreatePatientShareInput, DuplicateCheckResponse, LastVisitInfo, LotLedger, LotRecallResult, PatientAssignmentDraft, PatientMemoryDetailResponse, PatientMemoryFilter, PatientMemoryListResponse, PatientMemoryRow as ApiPatientMemoryRow, PatientShare, PatientSummary, SmartListCounts, SmartListKey, SmartListResponse, SmartPatientMatch, SmartPatientSearchResponse, SyncHealth, WorklistEntry, WorklistResponse } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import type { PatientEditDraft } from "../../../services/api/client";
import { Input } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
import { useBackLevel } from "../../../shared/lib/backStack";
import { WorklistSection } from "./WorklistSection";
import { PatientForm } from "../../patient/PatientForm";
import { RegisterPatientForm } from "../../aesthetics/RegisterPatientForm";
import { type GalleryVisit } from "../../aesthetics/PatientPhotoGallery";
import { SharePatientSheet } from "../../aesthetics/SharePatientSheet";
import type { QaThreadSummary } from "../../qa/qaClient";
import { ClinicalMemoryTab, PatientFilter, ClinicalMemoryReturnContext, PatientRowModel, PatientNeedsInputItem, StorageWarningDecision, buildTodayModel, buildPatientRows, patientRowFromApi, patientRowStub, patientRowFromSmartMatch, smartMatchBadges, todayNeedsInputActionLabel, activeSectionBadge, decisionActionForSession, decisionIdForSession, formatPatientLastVisit, visitCountLabel } from "./memoryModel";
import { SearchIcon, FilterIcon, CalendarIcon, PatientsIcon, NeedsInputIcon, SparkleIcon, ChevronIcon, OfflineIcon, InfoIcon } from "./MemoryIcons";
import { AssistantStatusPill, ClinicalSection, VisitCard, EmptyClinicalState, PatientRow, PatientListLoading } from "./MemoryCards";
import { AttentionSweep } from "./AttentionSweep";
import { PatientDecisionListSheet, SummaryReviewSheet, StorageReviewSheet, PatientRecapSheet, ChoosePatientResolver, AssignPatientResolver } from "./MemorySheets";
import { PatientTimelineDetail } from "./PatientTimeline";
import { SmartListsTab } from "./SmartListsTab";
import { useMemoryApi } from "../useMemoryApi";
import { useAuth } from "../../../app/providers/AuthProvider";
import { useCapabilities } from "../../../app/providers/CapabilitiesProvider";
import { useToast } from "../../../app/providers/ToastProvider";
import { useSync } from "../../../app/providers/SyncProvider";
import { useActiveSession, useMemoryRefreshSignal, useSessionActions, useSessions } from "../../../app/providers/SessionStoreProvider";

export const PATIENT_PAGE_SIZE = 25;
// Backed-off memory-refresh poll ceiling. With 3s→30s exponential backoff this spans a few minutes
// before ceding to the signal-driven refresh — long enough for a slow/parked rebuild, never infinite.
const MEMORY_POLL_MAX_ATTEMPTS = 18;
export function PatientsHome({
  initialPatientId,
  initialTab,
  onBackToVisit,
  onOpenSession,
  onContinueSession,
  onViewingPatientChange,
  onStartVisit,
  onOpenQaInbox,
  attentionCount = 0,
}: {
  initialPatientId?: string;
  initialTab?: ClinicalMemoryTab;
  /** When set, the clinician arrived from an in-progress visit; the timeline's back returns there. */
  onBackToVisit?: () => void;
  onOpenSession: (sessionId: string, context?: ClinicalMemoryReturnContext) => void;
  onContinueSession: (sessionId: string) => void;
  /** Reports which patient's file is open (or null), so the footer can capture for them. */
  onViewingPatientChange?: (patient: { id: string; name: string } | null) => void;
  /** AES-903 — start a fresh visit assigned to the patient (worklist quick action); marks the
   *  entry seen + navigates to the capture screen. */
  onStartVisit?: (patientId: string, worklistEntryId?: string) => Promise<void>;
  /** Deep-link a sweep "Messages" item to the Q&A inbox thread (the sweep never reimplements reply). */
  onOpenQaInbox?: () => void;
  /** The unified attention roll-up count (confirm + messages) — the SAME number the top-bar bell
   *  shows. Feeds the Today chip so the two "needs me" signals never disagree; the chip is hidden
   *  entirely when this is 0 (surface-by-exception). #1 / AES-1007. */
  attentionCount?: number;
}) {
  const t = useT();
  // Seam consumption (frontend-refactor plan §3, increment 6): the ~38 apiFetch-bound / session /
  // capability / toast callback props this screen used to receive collapse into the feature hook
  // (useMemoryApi) + the store/capability/sync/toast context, aliased back to the local names the body
  // already uses so the render body is unchanged. Navigation + route params stay as props above
  // (they move to the router seam in increment 7). The Pro-only binders are `undefined` for Basic
  // (capability gating now lives inside useMemoryApi, seam A3).
  const memoryApi = useMemoryApi();
  const { auth } = useAuth();
  const { tier } = useCapabilities();
  const { setToast: onToast } = useToast();
  const sessions = useSessions();
  const activeSession = useActiveSession();
  const memoryRefreshSignal = useMemoryRefreshSignal();
  const { syncHealth, exportQueuedCaptures: onExportCaptures } = useSync();
  const {
    assignPatientToSession: onAssignPatient,
    confirmSessionSummary: onConfirmSummary,
    fetchAssignedPatientDetails: onFetchPatient,
    editPatientDetails: onUpdatePatient,
    createNewPatient: onCreatePatient,
    searchPatientsForAssignment: onSearchPatients,
  } = useSessionActions();
  const onGetPatientMemory = memoryApi.getPatientMemoryDetail;
  const onListPatientMemory = memoryApi.listPatientMemory;
  const onSmartSearch = memoryApi.smartSearchPatients;
  const onDuplicateCheck = memoryApi.duplicateCheckPatient;
  const onLoadSessionCaptures = memoryApi.loadSessionCaptures;
  const onLoadSession = memoryApi.loadSession;
  const onResolveFile = memoryApi.resolveSourceFile;
  const onLoadLastVisit = memoryApi.loadLastVisit;
  const onListAftercareTemplates = memoryApi.listAftercareTemplates;
  const onCreateShare = memoryApi.createShare;
  const onRevokeShare = memoryApi.revokeShare;
  const onLoadAssignmentSuggestion = memoryApi.loadAssignmentSuggestion;
  const onListWorklist = memoryApi.listWorklist;
  const onLineUpPatient = memoryApi.lineUpPatient;
  const onMarkWorklistSeen = memoryApi.markWorklistSeen;
  const onCancelWorklistEntry = memoryApi.cancelWorklistEntry;
  const onListClinicMembers = memoryApi.listClinicMembers;
  const onOpenQaChannel = memoryApi.openQaChannel;
  const onFetchSmartListCounts = memoryApi.fetchSmartListCounts;
  const onFetchSmartList = memoryApi.fetchSmartList;
  const onFetchLotLedger = memoryApi.fetchLotLedger;
  const onFetchLotRecall = memoryApi.fetchLotRecall;
  const shareIncludeBrands = Boolean(auth?.tenant.shareIncludeBrands);
  const shareLanguage = auth?.tenant.reportLanguage || null;
  const [activeTab, setActiveTab] = React.useState<ClinicalMemoryTab>(initialTab || "today");
  // Follow an externally-driven tab change (e.g. the top-bar Attention indicator opening the sweep
  // while already on this screen, where the mount initializer above wouldn't re-run).
  React.useEffect(() => {
    if (initialTab) setActiveTab(initialTab);
  }, [initialTab]);
  const [query, setQuery] = React.useState("");
  const [patientFilter, setPatientFilter] = React.useState<PatientFilter>("recent");
  // AES-904 "Mine vs Clinic" on the patients list. Default Clinic (the whole shared base); Mine
  // filters to the patients the signed-in clinician has worked with (their owned sessions).
  const [ownershipScope, setOwnershipScope] = React.useState<"mine" | "clinic">("clinic");
  const myUserId = auth?.user.id;
  const patientClinicianId = ownershipScope === "mine" && myUserId ? myUserId : undefined;
  // The Close-the-day sweep defaults its scope by role: a doctor/owner clears their own doses/safety/
  // messages (`mine`); reception (assistant/admin) coordinates the room, so intake/assignment (`clinic`).
  const myRole = auth?.memberships.find((membership) => membership.tenantId === auth.tenant.id)?.role || auth?.user.persona || "doctor";
  const attentionDefaultScope: AttentionScope = myRole === "assistant" || myRole === "admin" ? "clinic" : "mine";
  const [backendPatientRows, setBackendPatientRows] = React.useState<ApiPatientMemoryRow[]>([]);
  const [patientRowsLoading, setPatientRowsLoading] = React.useState(false);
  const [patientRowsError, setPatientRowsError] = React.useState(false);
  const [patientTotal, setPatientTotal] = React.useState(0);
  const [patientLoadingMore, setPatientLoadingMore] = React.useState(false);
  const [patientListVersion, setPatientListVersion] = React.useState(0);
  const [creatingPatient, setCreatingPatient] = React.useState(false);
  // AES-204 — deterministic, Persian-aware smart search (shown while there is a query).
  const [smartResults, setSmartResults] = React.useState<SmartPatientMatch[] | null>(null);
  const [smartSearching, setSmartSearching] = React.useState(false);
  // AES-303 — the patient whose curated share sheet is open (carrying their recent visits so the
  // sheet can build a real before/after photo pool to curate from).
  const [sharePatient, setSharePatient] = React.useState<{ id: string; name: string; visits: GalleryVisit[] } | null>(null);
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const [summaryReviewSessionId, setSummaryReviewSessionId] = React.useState("");
  const [decisionListPatientId, setDecisionListPatientId] = React.useState("");
  const [selectedPatientId, setSelectedPatientId] = React.useState(initialPatientId || "");
  // A {id,name} hint when a patient is opened by id from outside the loaded list (the worklist), so
  // the timeline detail renders immediately while its memory loads. Cleared on back.
  const [pendingPatientStub, setPendingPatientStub] = React.useState<{ id: string; name: string } | null>(null);
  // AES-903 — the queued patient whose recap popup is open (history + before/after + Start visit).
  const [recapPatient, setRecapPatient] = React.useState<{ id: string; name: string; entryId: string; canStart: boolean } | null>(null);
  const [patientDetailCache, setPatientDetailCache] = React.useState<Record<string, PatientMemoryDetailResponse>>({});
  const [patientDetailLoading, setPatientDetailLoading] = React.useState(false);
  const [patientDetailError, setPatientDetailError] = React.useState(false);
  const [storageReviewOpen, setStorageReviewOpen] = React.useState(false);
  const [storageWarning, setStorageWarning] = React.useState<StorageWarningDecision | null>(null);
  const [resolvedDecisionIds, setResolvedDecisionIds] = React.useState<Set<string>>(() => new Set());
  // Pro tenants get AI-maintained memory artifacts (the ✨ surfaces); Basic gets deterministic text.
  const isPro = tier !== "basic";
  // The Lists tab is Pro-only; the count drives the tab-bar grid (3 → 1 row, 4 → a tidy 2×2).
  const visibleTabs = React.useMemo(() => (isPro ? clinicalTabs : clinicalTabs.filter((tab) => tab.value !== "lists")), [isPro]);
  const today = React.useMemo(
    () => buildTodayModel({ activeSession, sessions, syncHealth, resolvedDecisionIds, t }),
    [activeSession, resolvedDecisionIds, sessions, syncHealth, t],
  );
  const localPatientRows = React.useMemo(
    () => buildPatientRows({ activeSession, sessions, resolvedDecisionIds, t }),
    [activeSession, resolvedDecisionIds, sessions, t],
  );
  // The device storage warning is a client-only data-safety signal the backend roll-up can't see, so
  // it's injected into the sweep as an S2 item (keeping the epic's "storage in the Basic ladder"),
  // routed to the same StorageReviewSheet at its source.
  const attentionClientItems = React.useMemo<AttentionItem[]>(
    () =>
      storageWarning
        ? [
            {
              id: "client:storage-warning",
              kind: "storage-warning",
              tier: "S2",
              dayGroup: "today",
              sessionId: null,
              patientId: null,
              patientName: null,
              clinicianId: null,
              threadId: null,
              reason: t("attention.reason.storage"),
              key: null,
              sortTime: null,
            },
          ]
        : [],
    [storageWarning, t],
  );
  // First page: re-fetched from offset 0 whenever the tab, search query, filter, or a create
  // (patientListVersion) changes — keeping the list in sync with the shared search box.
  React.useEffect(() => {
    if (activeTab !== "patients" || !onListPatientMemory) return;
    let cancelled = false;
    setPatientRowsLoading(true);
    setPatientRowsError(false);
    void onListPatientMemory({ query, filter: patientFilter, limit: PATIENT_PAGE_SIZE, offset: 0, clinicianId: patientClinicianId })
      .then((result) => {
        if (cancelled) return;
        setBackendPatientRows(result.items);
        setPatientTotal(result.total);
      })
      .catch(() => {
        if (cancelled) return;
        setPatientRowsError(true);
      })
      .finally(() => {
        if (!cancelled) setPatientRowsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, onListPatientMemory, patientFilter, query, patientListVersion, patientClinicianId]);

  // AES-204 — run the deterministic smart search whenever the Patients tab has a query.
  React.useEffect(() => {
    if (activeTab !== "patients" || !onSmartSearch || !query.trim()) {
      setSmartResults(null);
      setSmartSearching(false);
      return;
    }
    let cancelled = false;
    setSmartSearching(true);
    const timer = window.setTimeout(() => {
      void onSmartSearch(query.trim())
        .then((response) => {
          if (!cancelled) setSmartResults(response.items);
        })
        .catch(() => {
          if (!cancelled) setSmartResults(null);
        })
        .finally(() => {
          if (!cancelled) setSmartSearching(false);
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeTab, onSmartSearch, query]);

  const loadMorePatients = () => {
    if (!onListPatientMemory || patientLoadingMore) return;
    setPatientLoadingMore(true);
    void onListPatientMemory({ query, filter: patientFilter, limit: PATIENT_PAGE_SIZE, offset: backendPatientRows.length, clinicianId: patientClinicianId })
      .then((result) => {
        setBackendPatientRows((current) => [...current, ...result.items]);
        setPatientTotal(result.total);
      })
      .catch(() => setPatientRowsError(true))
      .finally(() => setPatientLoadingMore(false));
  };

  const submitNewPatient = (draft: PatientAssignmentDraft) => {
    if (!onCreatePatient) return;
    void onCreatePatient(draft).then((patient) => {
      setCreatingPatient(false);
      setPatientListVersion((version) => version + 1); // refresh the list
      if (patient?.id) setSelectedPatientId(patient.id); // open the new patient's detail
    });
  };
  React.useEffect(() => {
    let cancelled = false;
    if (!navigator.storage?.estimate) return;
    void navigator.storage.estimate().then((estimate) => {
      if (cancelled) return;
      const quota = estimate.quota || 0;
      const usage = estimate.usage || 0;
      const remaining = quota > usage ? quota - usage : 0;
      const usageRatio = quota ? usage / quota : 0;
      setStorageWarning(usageRatio >= 0.85 || (quota > 0 && remaining < 100 * 1024 * 1024) ? { remainingBytes: remaining, usageRatio } : null);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  const patientRows = React.useMemo(
    () =>
      backendPatientRows.length && !patientRowsError
        ? backendPatientRows.map((row) => patientRowFromApi(row, t))
        : localPatientRows.filter((patient) => {
            if (patientFilter === "active") return patient.isActive;
            return true;
          }),
    [backendPatientRows, localPatientRows, patientFilter, patientRowsError, t],
  );
  const needsInputSessions = today.needsInputSessions;
  // How many needs-input visits are beyond the (max 3) previewed on Today — surfaced as the overflow pill.
  const needsInputOverflowCount = needsInputSessions.length - today.needsInputPreviews.length;
  const normalizedQuery = query.trim().toLowerCase();
  const backendRowsActive = backendPatientRows.length > 0 && !patientRowsError;
  const filteredPatients = backendRowsActive
    ? patientRows
    : patientRows.filter((patient) =>
        normalizedQuery ? [patient.name, patient.summary, patient.badges.map((badge) => badge.label).join(" ")].join(" ").toLowerCase().includes(normalizedQuery) : true,
      );
  const assignmentSession = assignmentSessionId
    ? sessions.find((session) => session.id === assignmentSessionId) || (activeSession?.id === assignmentSessionId ? activeSession : null)
    : null;
  const summaryReviewSession = summaryReviewSessionId
    ? sessions.find((session) => session.id === summaryReviewSessionId) || (activeSession?.id === summaryReviewSessionId ? activeSession : null)
    : null;
  const decisionListPatient = decisionListPatientId ? patientRows.find((patient) => patient.id === decisionListPatientId) : null;
  // Resolve a selected patient from the loaded rows, or synthesize one from a smart-search match
  // (so opening a result that is not on the current page still loads the detail by id).
  const selectedPatientDetail = selectedPatientId ? patientDetailCache[selectedPatientId] : undefined;
  const selectedPatient = selectedPatientId
    ? patientRows.find((patient) => patient.id === selectedPatientId) ||
      (() => {
        const match = smartResults?.find((result) => result.id === selectedPatientId);
        return match ? patientRowFromSmartMatch(match, t) : undefined;
      })() ||
      // Opened by id from a surface that isn't the loaded list (e.g. the worklist): resolve from the
      // fetched detail, or a lightweight stub (its name) so the detail renders without a tab flash.
      (selectedPatientDetail ? patientRowFromApi(selectedPatientDetail.patient, t) : undefined) ||
      (pendingPatientStub && pendingPatientStub.id === selectedPatientId
        ? patientRowStub(pendingPatientStub.id, pendingPatientStub.name, t)
        : undefined)
    : null;
  const viewedPatientId = selectedPatient?.id;
  const viewedPatientName = selectedPatient?.name;

  // Report the open patient's file up to App so the global footer can capture *for them* (E9). On
  // unmount (leaving Clinical Memory) clear it, so the capture target reverts to the active session.
  React.useEffect(() => {
    onViewingPatientChange?.(viewedPatientId ? { id: viewedPatientId, name: viewedPatientName || t("patients.fallbackName") } : null);
  }, [viewedPatientId, viewedPatientName, onViewingPatientChange]);
  React.useEffect(() => () => onViewingPatientChange?.(null), [onViewingPatientChange]);

  // Give the open patient file its own history entry so hardware/browser Back returns to the list
  // instead of exiting Clinical Memory (item: in-screen history levels).
  useBackLevel(Boolean(selectedPatientId), () => {
    setSelectedPatientId("");
    setPendingPatientStub(null);
  });

  // Fetch on open and re-fetch whenever a refresh signal fires (post-capture, so memory flips
  // updating→ready). Cached content keeps showing during a background re-fetch (no skeleton flash);
  // the skeleton only appears on the very first load when there is nothing cached yet.
  React.useEffect(() => {
    if (!selectedPatientId || !onGetPatientMemory) return;
    let cancelled = false;
    setPatientDetailLoading(true);
    setPatientDetailError(false);
    void onGetPatientMemory(selectedPatientId)
      .then((detail) => {
        if (cancelled) return;
        setPatientDetailCache((current) => ({ ...current, [selectedPatientId]: detail }));
      })
      .catch(() => {
        if (!cancelled) setPatientDetailError(true);
      })
      .finally(() => {
        if (!cancelled) setPatientDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onGetPatientMemory, selectedPatientId, memoryRefreshSignal]);

  // A capture/assignment refresh also re-fetches the patient list (fresh memoryStatus + summary).
  React.useEffect(() => {
    if (!memoryRefreshSignal) return;
    setPatientListVersion((version) => version + 1);
  }, [memoryRefreshSignal]);

  // Opening a patient whose memory is cold triggers a server-side (re)generation that finishes in a
  // few seconds — but a passive open gets no post-capture refresh ladder, so poll while it is
  // "organizing" and stop the moment it flips to ready. Track A: exponential BACKOFF (3s → ~30s)
  // rather than a hard 12-attempt cap, so a slow rebuild — or a fair-use-PARKED one that only resumes
  // next cycle / on upgrade — keeps refreshing calmly instead of either spinning fast forever or
  // giving up at a fixed count. The pill shows the usage-limit state while parked (see MemoryUpdatingPill).
  React.useEffect(() => {
    if (!selectedPatientId || !onGetPatientMemory) return;
    if (selectedPatientDetail?.patient?.memoryStatus !== "updating") return;
    let cancelled = false;
    let attempts = 0;
    let timer = 0;
    const poll = () => {
      attempts += 1;
      void onGetPatientMemory(selectedPatientId)
        .then((detail) => {
          if (!cancelled) setPatientDetailCache((current) => ({ ...current, [selectedPatientId]: detail }));
        })
        .catch(() => undefined)
        .finally(() => {
          if (cancelled || attempts >= MEMORY_POLL_MAX_ATTEMPTS) return;
          const delay = Math.min(3000 * Math.pow(1.6, attempts - 1), 30000);
          timer = window.setTimeout(poll, delay);
        });
    };
    timer = window.setTimeout(poll, 3000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [onGetPatientMemory, selectedPatientId, selectedPatientDetail?.patient?.memoryStatus]);

  const localSessionById = (sessionId?: string | null) =>
    sessionId ? sessions.find((session) => session.id === sessionId) || (activeSession?.id === sessionId ? activeSession : null) : null;

  // Route a needs-input decision to its focused resolver. `verify` lives in Active Session (the
  // AiCreatedPatientPanel), and any decision whose session is not in the local cache also falls
  // back to opening the visit, since the inline resolvers need the local session.
  const openNeedsInputDecision = (
    action: PatientNeedsInputItem["action"],
    sessionId?: string | null,
    returnTab?: ClinicalMemoryTab,
  ) => {
    if (!sessionId) return;
    if (action === "verify" || !localSessionById(sessionId)) {
      onOpenSession(sessionId, returnTab ? { tab: returnTab } : undefined);
      return;
    }
    if (action === "assign-patient" || action === "choose-patient" || action === "resolve-conflict") {
      setAssignmentSessionId(sessionId);
      return;
    }
    setSummaryReviewSessionId(sessionId);
  };

  const handlePatientAction = (patient: PatientRowModel) => {
    if (patient.action === "continue" && patient.activeSessionId) {
      onContinueSession(patient.activeSessionId);
      return;
    }
    if (patient.action === "review-items") {
      setDecisionListPatientId(patient.id);
      return;
    }
    const targetItem = patient.needsInputItems[0];
    if (targetItem) {
      openNeedsInputDecision(targetItem.action, targetItem.sessionId || patient.latestSessionId);
      return;
    }
    setSelectedPatientId(patient.id);
  };

  const handleDecisionAction = (item: PatientNeedsInputItem, patient?: PatientRowModel) => {
    openNeedsInputDecision(item.action, item.sessionId || patient?.latestSessionId);
  };

  // Route a sweep item to the SAME resolver it uses at its source. Assignment decisions open the
  // in-place assign/choose resolver; a dose/verify/safety/suggestion opens the visit in Active
  // Session (where its inline resolver lives); a message deep-links to the Q&A inbox thread.
  const ATTENTION_RESOLVER_KINDS = new Set(["assign-patient", "choose-patient", "resolve-conflict", "verify"]);
  const handleAttentionItem = (item: AttentionItem) => {
    if (item.kind === "storage-warning") {
      setStorageReviewOpen(true);
      return;
    }
    if (item.kind === "qa-pending") {
      onOpenQaInbox?.();
      return;
    }
    if (!item.sessionId) return;
    if (ATTENTION_RESOLVER_KINDS.has(item.kind)) {
      openNeedsInputDecision(item.kind as PatientNeedsInputItem["action"], item.sessionId, "attention");
      return;
    }
    onOpenSession(item.sessionId, { tab: "attention" });
  };
  const handleAttentionSelect = (item: AttentionItem) => {
    if (item.kind === "qa-pending") {
      onOpenQaInbox?.();
      return;
    }
    if (item.sessionId) onOpenSession(item.sessionId, { tab: "attention" });
  };

  return (
    <section className="clinical-memory" aria-label={t("patients.clinicalMemory")}>
      {decisionListPatient ? (
        <PatientDecisionListSheet
          patient={decisionListPatient}
          onClose={() => setDecisionListPatientId("")}
          onOpenMemory={() => {
            setSelectedPatientId(decisionListPatient.id);
            setDecisionListPatientId("");
          }}
          onItemAction={(item) => {
            setDecisionListPatientId("");
            handleDecisionAction(item, decisionListPatient);
          }}
        />
      ) : null}
      {summaryReviewSession ? (
        <SummaryReviewSheet
          session={summaryReviewSession}
          onClose={() => setSummaryReviewSessionId("")}
          onOpenVisit={() => {
            onOpenSession(summaryReviewSession.id);
            setSummaryReviewSessionId("");
          }}
          onConfirm={async (summary) => {
            await onConfirmSummary?.(summaryReviewSession.id, summary);
            setResolvedDecisionIds((current) => new Set(current).add(decisionIdForSession(summaryReviewSession)));
            setSummaryReviewSessionId("");
          }}
        />
      ) : null}
      {storageReviewOpen ? <StorageReviewSheet onClose={() => setStorageReviewOpen(false)} onExport={onExportCaptures} storageWarning={storageWarning} /> : null}
      {recapPatient ? (
        <PatientRecapSheet
          patientId={recapPatient.id}
          patientName={recapPatient.name}
          worklistEntryId={recapPatient.entryId}
          canStartVisit={recapPatient.canStart}
          isPro={isPro}
          onGetPatientMemory={onGetPatientMemory}
          onLoadLastVisit={onLoadLastVisit}
          onResolveFile={onResolveFile}
          onStartVisit={onStartVisit ? (patientId, entryId) => { setRecapPatient(null); void onStartVisit(patientId, entryId); } : undefined}
          onOpenFullTimeline={() => {
            setPendingPatientStub({ id: recapPatient.id, name: recapPatient.name });
            setSelectedPatientId(recapPatient.id);
            setRecapPatient(null);
          }}
          onClose={() => setRecapPatient(null)}
        />
      ) : null}
      {sharePatient ? (
        <SharePatientSheet
          patientId={sharePatient.id}
          patientName={sharePatient.name}
          visits={sharePatient.visits}
          onLoadLastVisit={onLoadLastVisit}
          onLoadSessionCaptures={onLoadSessionCaptures}
          onLoadSession={onLoadSession}
          shareIncludeBrands={shareIncludeBrands}
          shareLanguage={shareLanguage}
          onListAftercareTemplates={onListAftercareTemplates}
          onResolveFile={onResolveFile}
          onCreateShare={onCreateShare}
          onRevokeShare={onRevokeShare}
          onClose={() => setSharePatient(null)}
        />
      ) : null}
      {assignmentSession && onAssignPatient ? (
        decisionActionForSession(assignmentSession) === "choose-patient" || decisionActionForSession(assignmentSession) === "resolve-conflict" ? (
          <ChoosePatientResolver
            session={assignmentSession}
            onAssign={async (draft) => {
              await onAssignPatient(assignmentSession.id, draft, { successMessage: t("patients.toast.patientConfirmed") });
              setResolvedDecisionIds((current) => new Set(current).add(decisionIdForSession(assignmentSession)));
              setAssignmentSessionId("");
            }}
            onClose={() => setAssignmentSessionId("")}
            onKeepUnassigned={() => {
              setResolvedDecisionIds((current) => new Set(current).add(decisionIdForSession(assignmentSession)));
              setAssignmentSessionId("");
            }}
            onSearchPatients={onSearchPatients}
          />
        ) : (
          <AssignPatientResolver
            session={assignmentSession}
            onAssign={async (draft) => {
              await onAssignPatient(assignmentSession.id, draft);
              setResolvedDecisionIds((current) => new Set(current).add(decisionIdForSession(assignmentSession)));
              setAssignmentSessionId("");
            }}
            onClose={() => setAssignmentSessionId("")}
            onKeepUnassigned={() => setAssignmentSessionId("")}
            onOpenVisit={() => {
              onOpenSession(assignmentSession.id);
              setAssignmentSessionId("");
            }}
            onSearchPatients={onSearchPatients}
            onLoadSuggestion={onLoadAssignmentSuggestion}
          />
        )
      ) : null}
      {selectedPatient ? (
        <PatientTimelineDetail
          detail={selectedPatientDetail}
          loading={patientDetailLoading}
          loadError={patientDetailError}
          patient={selectedPatient}
          isPro={isPro}
          sessions={sessions}
          activeSession={activeSession}
          onBack={() => setSelectedPatientId("")}
          onBackToVisit={onBackToVisit}
          onContinueSession={onContinueSession}
          onOpenSession={onOpenSession}
          onUpdatePatient={onUpdatePatient}
          onFetchPatient={onFetchPatient}
          onAssignPatient={(sessionId) => setAssignmentSessionId(sessionId)}
          onReviewSummary={(sessionId) => setSummaryReviewSessionId(sessionId)}
          onLoadSessionCaptures={onLoadSessionCaptures}
          onResolveFile={onResolveFile}
          onShare={(visits) => setSharePatient({ id: selectedPatient.id, name: selectedPatient.name, visits })}
          currentUserId={myUserId}
          onOpenQaChannel={onOpenQaChannel}
          onToast={onToast}
        />
      ) : (
        <>
      <div className="clinical-memory-hero">
        <div>
          <h1>{t("patients.clinicalMemory")}</h1>
        </div>
        {/* One "needs me" number, shared with the top-bar bell (attentionCount = confirm + messages).
            Surface-by-exception: the chip renders only when something is open — when it's zero there is
            no "All caught up" pill, so the chip can never contradict the sections below it (#1). */}
        {attentionCount > 0 ? (
          <button className="needs-input-pill" onClick={() => setActiveTab("attention")} type="button">
            <SparkleIcon />
            {t("patients.needYourInputCount", { n: attentionCount })}
            <ChevronIcon />
          </button>
        ) : null}
      </div>

      {today.isOffline ? (
        <AssistantStatusPill icon={<OfflineIcon />}>
          {t("patients.offlineCapturesSaved")}
        </AssistantStatusPill>
      ) : null}

      <label className="clinical-search">
        <SearchIcon />
        <Input
          aria-label={t("patients.searchAriaLabel")}
          onChange={(event) => {
            // The search drives patient results, so typing jumps to the Patients tab where it acts
            // (rather than sitting inert on Today / Needs input).
            setQuery(event.target.value);
            if (event.target.value.trim() && activeTab !== "patients") setActiveTab("patients");
          }}
          placeholder={t("patients.searchPlaceholder")}
          value={query}
        />
        <span aria-hidden="true" className="clinical-search-filter">
          <FilterIcon />
        </span>
      </label>

      <div className={`clinical-tabs tabs-count-${visibleTabs.length}`} role="tablist" aria-label={t("patients.sectionsAriaLabel")}>
        {visibleTabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.value}
            className={activeTab === tab.value ? "active" : ""}
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            role="tab"
            type="button"
          >
            <span aria-hidden="true">{tab.icon}</span>
            {t(`patients.tab.${tab.value}`)}
          </button>
        ))}
      </div>

      {activeTab === "today" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <WorklistSection
            auth={auth ?? null}
            onListWorklist={onListWorklist}
            onLineUpPatient={onLineUpPatient}
            onMarkWorklistSeen={onMarkWorklistSeen}
            onCancelWorklistEntry={onCancelWorklistEntry}
            onListClinicMembers={onListClinicMembers}
            onSearchPatients={onSearchPatients}
            onStartVisit={onStartVisit}
            onPeekPatient={(patientId, patientName, worklistEntryId, canStartVisit) =>
              setRecapPatient({ id: patientId, name: patientName || t("patients.fallbackName"), entryId: worklistEntryId, canStart: canStartVisit })
            }
            refreshSignal={memoryRefreshSignal}
          />
          <ClinicalSection
            title={t("patients.section.activeSession")}
            badge={today.currentVisit ? activeSectionBadge(today.currentVisit.session, t) : undefined}
            badgeTone={today.currentVisit?.tone === "amber" ? "amber" : "green"}
          >
            {today.currentVisit ? (
              <VisitCard
                primaryActionLabel={today.currentVisit.session.patientName || today.currentVisit.session.patientId ? t("patients.action.continueVisit") : t("patients.action.assignPatient")}
                summary={today.currentVisit.summary}
                session={today.currentVisit.session}
                statusLabel={today.currentVisit.statusLabel}
                tone={today.currentVisit.tone}
                title={today.currentVisit.title}
                onSelect={() => onOpenSession(today.currentVisit!.session.id, { tab: "today" })}
                onPrimaryAction={() => {
                  const currentVisit = today.currentVisit;
                  if (!currentVisit) return;
                  if (currentVisit.session.patientName || currentVisit.session.patientId) {
                    onContinueSession(currentVisit.session.id);
                    return;
                  }
                  setAssignmentSessionId(currentVisit.session.id);
                }}
              />
            ) : (
              <EmptyClinicalState title={t("patients.empty.noActiveVisit.title")} copy={t("patients.empty.noActiveVisit.copy")} />
            )}
          </ClinicalSection>
          {!today.isOffline ? (
            <ClinicalSection title={t("patients.section.needsYourInput")} badge={needsInputSessions.length ? visitCountLabel(needsInputSessions.length, t) : undefined} badgeTone="amber">
              {today.needsInputPreviews.length ? (
                <div className="clinical-list">
                  {today.needsInputPreviews.map((preview) => (
                    <VisitCard
                      key={preview.session.id}
                      primaryActionLabel={todayNeedsInputActionLabel(preview.session, t)}
                      summary={preview.summary}
                      session={preview.session}
                      statusLabel={preview.statusLabel}
                      title={preview.title}
                      tone="amber"
                      onSelect={() => onOpenSession(preview.session.id, { tab: "today" })}
                      onPrimaryAction={() => {
                        const action = decisionActionForSession(preview.session);
                        if (action === "assign-patient" || action === "choose-patient") {
                          setAssignmentSessionId(preview.session.id);
                          return;
                        }
                        setSummaryReviewSessionId(preview.session.id);
                      }}
                    />
                  ))}
                  {needsInputOverflowCount > 0 ? (
                    <button className="needs-input-overflow" type="button" onClick={() => setActiveTab("attention")}>
                      {t("patients.needsInputSeeAll", { n: needsInputOverflowCount })}
                      <ChevronIcon />
                    </button>
                  ) : null}
                </div>
              ) : attentionCount > 0 ? (
                <button className="needs-input-overflow" type="button" onClick={() => setActiveTab("attention")}>
                  {t("patients.needsInputSweepAll", { n: attentionCount })}
                  <ChevronIcon />
                </button>
              ) : (
                <EmptyClinicalState title={t("patients.empty.allCaughtUp.title")} copy={t("patients.empty.allCaughtUp.copyToday")} />
              )}
            </ClinicalSection>
          ) : (
            <p className="clinical-offline-note"><InfoIcon /> {t("patients.offlineSearchLimited")}</p>
          )}
          <ClinicalSection title={t("patients.section.updatedToday")} badge={today.recentMemory.length ? today.recentMemoryBadge : undefined}>
            {today.recentMemory.length ? (
              <div className="clinical-list">
                {today.recentMemory.map((memory) => (
                  <VisitCard
                    key={memory.session.id}
                    session={memory.session}
                    statusLabel={memory.statusLabel}
                    summary={memory.summary}
                    title={memory.title}
                    tone={memory.tone}
                    onSelect={() => onOpenSession(memory.session.id, { tab: "today" })}
                  />
                ))}
              </div>
            ) : (
              <EmptyClinicalState title={t("patients.empty.noVisitsToday.title")} copy={t("patients.empty.noVisitsToday.copy")} />
            )}
          </ClinicalSection>
        </div>
      ) : null}

      {activeTab === "patients" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <div className="patients-toolbar">
            <div className="clinical-filter-row" aria-label={t("patients.filtersAriaLabel")}>
              {patientFilters.map((filter) => (
                <button
                  aria-pressed={patientFilter === filter.value}
                  className={patientFilter === filter.value ? "active" : ""}
                  key={filter.value}
                  onClick={() => setPatientFilter(filter.value)}
                  type="button"
                >
                  {t(`patients.filter.${filter.value}`)}
                </button>
              ))}
            </div>
            {myUserId ? (
              <div className="mine-clinic-toggle" role="group" aria-label={t("patients.scopeAriaLabel")}>
                {(["mine", "clinic"] as const).map((value) => (
                  <button
                    key={value}
                    aria-pressed={ownershipScope === value}
                    className={ownershipScope === value ? "active" : ""}
                    onClick={() => setOwnershipScope(value)}
                    type="button"
                  >
                    {value === "mine" ? t("patients.scope.mine") : t("patients.scope.clinic")}
                  </button>
                ))}
              </div>
            ) : null}
            <button className="patients-create-button" onClick={() => setCreatingPatient((value) => !value)} type="button">
              <span aria-hidden="true">+</span> {t("patients.newPatient")}
            </button>
          </div>
          {creatingPatient ? (
            <section className="patient-edit-card" aria-label={t("patients.createPatientAriaLabel")}>
              {onDuplicateCheck ? (
                <RegisterPatientForm
                  initialName={query.trim()}
                  onDuplicateCheck={onDuplicateCheck}
                  onCancel={() => setCreatingPatient(false)}
                  onSubmit={submitNewPatient}
                  onUseExisting={(candidate) => {
                    setCreatingPatient(false);
                    setSelectedPatientId(candidate.patientId);
                  }}
                />
              ) : (
                <PatientForm onCancel={() => setCreatingPatient(false)} onSubmit={submitNewPatient} submitLabel={t("patients.createPatient")} />
              )}
            </section>
          ) : null}
          {smartResults ? (
            <div className="clinical-list">
              <p className="smart-search-note">
                <SearchIcon /> {t("patients.smartMatch")} · {smartSearching ? t("patients.searching") : t("patients.resultCount", { n: smartResults.length })}
              </p>
              {smartResults.length ? (
                smartResults.map((match) => (
                  <PatientRow
                    actionLabel={t("patients.viewHistory")}
                    badges={smartMatchBadges(match, t)}
                    latestVisitLabel={match.lastVisit ? t("patients.lastVisit", { date: formatPatientLastVisit(match.lastVisit, t) }) : null}
                    key={match.id}
                    patientName={match.displayName}
                    summary={match.reason || t("patients.matchedRecord")}
                    isPro={isPro}
                    tone="green"
                    onAction={() => setSelectedPatientId(match.id)}
                    onSelect={() => setSelectedPatientId(match.id)}
                  />
                ))
              ) : (
                <EmptyClinicalState
                  title={t("patients.empty.noMatches.title")}
                  copy={/^\d{1,3}$/.test(query.trim()) ? t("patients.empty.noMatches.copyDigits") : t("patients.empty.noMatches.copy")}
                />
              )}
            </div>
          ) : (
          <div className="clinical-list">
            {patientRowsError ? (
              <p className="clinical-offline-note"><InfoIcon /> {t("patients.savedFromDevice")}</p>
            ) : null}
            {patientRowsLoading && !filteredPatients.length ? (
              <PatientListLoading />
            ) : filteredPatients.length ? (
              filteredPatients.map((patient) => (
                <PatientRow
                  actionLabel={patient.action === "open-memory" ? undefined : patient.actionLabel}
                  badges={patient.badges}
                  latestVisitLabel={patient.latestVisitLabel}
                  key={patient.id}
                  patientName={patient.name}
                  summary={patient.summary}
                  summaryStatus={patient.memoryStatus}
                  summaryStatusReason={patient.memoryStatusReason}
                  isPro={isPro}
                  tone={patient.needsInput ? "amber" : "green"}
                  onAction={() => handlePatientAction(patient)}
                  onSelect={() => setSelectedPatientId(patient.id)}
                />
              ))
            ) : (
              <EmptyClinicalState
                title={patientRows.length ? t("patients.empty.noMatches.title") : t("patients.empty.noPatients.title")}
                copy={patientRows.length ? t("patients.empty.noMatches.copyFilter") : t("patients.empty.noPatients.copy")}
              />
            )}
          </div>
          )}
          {!smartResults && backendRowsActive && filteredPatients.length ? (
            <div className="patients-pagination">
              <span className="patients-count">{t("patients.showingOf", { shown: filteredPatients.length, total: patientTotal })}</span>
              {filteredPatients.length < patientTotal ? (
                <button className="patients-load-more" disabled={patientLoadingMore} onClick={loadMorePatients} type="button">
                  {patientLoadingMore ? t("patients.loading") : t("patients.loadMore")}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {activeTab === "lists" && isPro && onFetchSmartListCounts && onFetchSmartList && onFetchLotLedger && onFetchLotRecall ? (
        <SmartListsTab
          onFetchCounts={onFetchSmartListCounts}
          onFetchList={onFetchSmartList}
          onFetchLedger={onFetchLotLedger}
          onFetchRecall={onFetchLotRecall}
          onOpenPatient={(patientId, name) => {
            if (name) setPendingPatientStub({ id: patientId, name });
            setSelectedPatientId(patientId);
          }}
          onOpenSession={(sessionId) => onOpenSession(sessionId, { tab: "lists" })}
          onOpenQaChannel={onOpenQaChannel}
          onToast={onToast}
          refreshSignal={memoryRefreshSignal}
        />
      ) : null}

      {activeTab === "attention" ? (
        <AttentionSweep
          fetchAttention={memoryApi.fetchAttention}
          defaultScope={attentionDefaultScope}
          refreshSignal={memoryRefreshSignal}
          clientItems={attentionClientItems}
          nudgeEnabled
          onItemPrimary={handleAttentionItem}
          onItemSelect={handleAttentionSelect}
        />
      ) : null}
        </>
      )}
    </section>
  );
}

export const clinicalTabs: Array<{ value: ClinicalMemoryTab; label: string; icon: React.ReactNode }> = [
  { value: "today", label: "Today", icon: <CalendarIcon /> },
  { value: "patients", label: "Patients", icon: <PatientsIcon /> },
  // Lists is Pro-only (AES-501/502); PatientsHome filters it out for Basic.
  { value: "lists", label: "Lists", icon: <ListsTabIcon /> },
  { value: "attention", label: "Attention", icon: <NeedsInputIcon /> },
];

function ListsTabIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M9 6.5h10M9 12h10M9 17.5h10" />
      <path d="M5 6.5h.01M5 12h.01M5 17.5h.01" />
    </svg>
  );
}

export const patientFilters: Array<{ value: PatientFilter; label: string }> = [
  { value: "recent", label: "Recent" },
  { value: "active", label: "Active" },
  { value: "all", label: "All" },
];
