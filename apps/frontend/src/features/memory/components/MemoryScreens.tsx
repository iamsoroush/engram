import React from "react";
import type {
  AftercareTemplate,
  AssignmentSuggestionResponse,
  AuthSession,
  ClinicMember,
  CaptureDraft,
  CreatePatientShareInput,
  DuplicateCandidate,
  DuplicateCheckResponse,
  LastVisitInfo,
  PatientAssignmentDraft,
  PatientMemoryDetailResponse,
  PatientMemoryFilter,
  PatientMemoryHistory,
  PatientMemoryListResponse,
  PatientMemoryTimelineSession,
  PatientMemoryRow as ApiPatientMemoryRow,
  PatientShare,
  PatientSummary,
  SmartPatientMatch,
  SmartPatientSearchResponse,
  SyncHealth,
  WorklistEntry,
  WorklistResponse,
} from "../../../domain/appTypes";
import type { CaptureItem, CaptureItemType, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import type { PatientEditDraft } from "../../../services/api/client";
import { Badge, Button, Card, Input } from "../../../shared/ui/primitives";
import { attributionName } from "../../../shared/lib/multiseat";
import { WorklistSection } from "./WorklistSection";
import { PatientForm } from "../../patient/PatientForm";
import { RegisterPatientForm } from "../../aesthetics/RegisterPatientForm";
import { PatientPhotoGallery, type GalleryVisit } from "../../aesthetics/PatientPhotoGallery";
import { LastVisitStrip } from "../../aesthetics/LastVisitStrip";
import { SharePatientSheet } from "../../aesthetics/SharePatientSheet";
import { QaChannelButton } from "../../qa/QaChannelButton";
import type { QaThreadSummary } from "../../qa/qaClient";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { SessionStatusBadge } from "../../capture/components/StatusBadges";

const PATIENT_PAGE_SIZE = 25;

export function PatientsHome({
  activeSession,
  auth,
  initialPatientId,
  initialTab,
  sessions,
  syncHealth,
  onOpenSession,
  onContinueSession,
  onGetPatientMemory,
  onUpdatePatient,
  onFetchPatient,
  onCreatePatient,
  onListPatientMemory,
  onSearchPatients,
  onConfirmSummary,
  onAssignPatient,
  onExportCaptures,
  onSmartSearch,
  onDuplicateCheck,
  onLoadSessionCaptures,
  onResolveFile,
  onLoadLastVisit,
  onListAftercareTemplates,
  onCreateShare,
  onRevokeShare,
  onOpenQaChannel,
  onToast,
  onLoadAssignmentSuggestion,
  onListWorklist,
  onLineUpPatient,
  onMarkWorklistSeen,
  onCancelWorklistEntry,
  onListClinicMembers,
  onStartVisit,
  onViewingPatientChange,
  tier,
  memoryRefreshSignal = 0,
}: {
  activeSession: CaptureSession | null;
  auth?: AuthSession | null;
  initialPatientId?: string;
  initialTab?: ClinicalMemoryTab;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  tier?: string | null;
  // Bumped by App on the post-capture refresh ladder so patient memory re-fetches (updating→ready).
  memoryRefreshSignal?: number;
  onOpenSession: (sessionId: string, context?: ClinicalMemoryReturnContext) => void;
  onContinueSession: (sessionId: string) => void;
  onGetPatientMemory?: (patientId: string) => Promise<PatientMemoryDetailResponse>;
  onUpdatePatient?: (patientId: string, draft: PatientEditDraft) => Promise<void>;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  onCreatePatient?: (draft: PatientAssignmentDraft) => Promise<PatientSummary | null>;
  onListPatientMemory?: (params: { query?: string; filter: PatientMemoryFilter; limit?: number; offset?: number; clinicianId?: string }) => Promise<PatientMemoryListResponse>;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  // E9 multi-seat worklist (AES-903).
  onListWorklist?: (options?: { scope?: "mine" | "clinic"; status?: "waiting" | "seen" | "cancelled" | "all"; clinicianId?: string }) => Promise<WorklistResponse>;
  onLineUpPatient?: (input: { patientId: string; clinicianUserId: string; note?: string }) => Promise<WorklistEntry>;
  onMarkWorklistSeen?: (entryId: string, sessionId?: string) => Promise<WorklistEntry>;
  onCancelWorklistEntry?: (entryId: string) => Promise<WorklistEntry>;
  onListClinicMembers?: () => Promise<ClinicMember[]>;
  /** AES-903 — start a fresh visit assigned to the patient (worklist quick action); marks the
   *  entry seen + navigates to the capture screen. */
  onStartVisit?: (patientId: string, worklistEntryId?: string) => Promise<void>;
  /** Reports which patient's file is open (or null), so the footer can capture for them. */
  onViewingPatientChange?: (patient: { id: string; name: string } | null) => void;
  onConfirmSummary?: (sessionId: string, summary: string) => Promise<void>;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft, options?: { successMessage?: string }) => Promise<void>;
  onExportCaptures?: () => Promise<void> | void;
  // Aesthetics-Basic deterministic services
  onSmartSearch?: (query: string) => Promise<SmartPatientSearchResponse>;
  onDuplicateCheck?: (body: { displayName?: string; nationalId?: string; phone?: string }) => Promise<DuplicateCheckResponse>;
  onLoadSessionCaptures?: (sessionId: string) => Promise<CaptureItem[]>;
  onResolveFile?: (endpoint: string) => Promise<string>;
  onLoadLastVisit?: (patientId: string) => Promise<LastVisitInfo>;
  onListAftercareTemplates?: () => Promise<AftercareTemplate[]>;
  onCreateShare?: (input: CreatePatientShareInput) => Promise<PatientShare>;
  onRevokeShare?: (id: string) => Promise<PatientShare>;
  // Pro: open (or reuse) the patient's Q&A channel and return its tokenized public link (AES-402).
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
  onLoadAssignmentSuggestion?: (sessionId: string) => Promise<AssignmentSuggestionResponse>;
}) {
  const [activeTab, setActiveTab] = React.useState<ClinicalMemoryTab>(initialTab || "today");
  const [query, setQuery] = React.useState("");
  const [patientFilter, setPatientFilter] = React.useState<PatientFilter>("recent");
  // AES-904 "Mine vs Clinic" on the patients list. Default Clinic (the whole shared base); Mine
  // filters to the patients the signed-in clinician has worked with (their owned sessions).
  const [ownershipScope, setOwnershipScope] = React.useState<"mine" | "clinic">("clinic");
  const myUserId = auth?.user.id;
  const patientClinicianId = ownershipScope === "mine" && myUserId ? myUserId : undefined;
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
  // Backend-computed needs-input rows (the single source of truth shared with the patient-card
  // badge). Fetched for the Needs input tab; the local derivation below is the offline fallback.
  const [needsInputRows, setNeedsInputRows] = React.useState<ApiPatientMemoryRow[]>([]);
  const [needsInputRowsLoaded, setNeedsInputRowsLoaded] = React.useState(false);
  // Pro tenants get AI-maintained memory artifacts (the ✨ surfaces); Basic gets deterministic text.
  const isPro = tier !== "basic";
  const today = React.useMemo(
    () => buildTodayModel({ activeSession, sessions, syncHealth, resolvedDecisionIds }),
    [activeSession, resolvedDecisionIds, sessions, syncHealth],
  );
  const localPatientRows = React.useMemo(
    () => buildPatientRows({ activeSession, sessions, resolvedDecisionIds }),
    [activeSession, resolvedDecisionIds, sessions],
  );
  const localNeedsInputItems = React.useMemo(
    () => buildNeedsInputItems({ activeSession, sessions, storageWarning, resolvedDecisionIds }),
    [activeSession, resolvedDecisionIds, sessions, storageWarning],
  );
  // Prefer the backend-computed decisions (so the tab matches the patient-card badges exactly);
  // keep the client-only storage warning plus any local-only sessions the backend has not seen.
  const needsInputItems = React.useMemo(() => {
    if (!needsInputRowsLoaded) return localNeedsInputItems;
    const backendCards = needsInputRows.flatMap((row) =>
      patientNeedsInputItemsFromApi(row).map((item) => needsInputCardFromApi(row, item)),
    );
    const backendSessionIds = new Set(backendCards.map((card) => card.sessionId).filter(Boolean));
    const localExtras = localNeedsInputItems.filter(
      (card) => card.kind === "review-storage" || (card.sessionId && !backendSessionIds.has(card.sessionId)),
    );
    return [...localExtras, ...backendCards].sort((a, b) => b.sortTime - a.sortTime);
  }, [needsInputRowsLoaded, needsInputRows, localNeedsInputItems]);
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

  // Needs input tab: fetch every patient with a critical decision (a high limit — this inbox is
  // small and not paginated). On failure we keep `needsInputRowsLoaded` false so the tab falls
  // back to the local (offline) derivation.
  React.useEffect(() => {
    if (activeTab !== "needs-input" || !onListPatientMemory) return;
    let cancelled = false;
    void onListPatientMemory({ filter: "needs-input", limit: 100, offset: 0 })
      .then((result) => {
        if (cancelled) return;
        setNeedsInputRows(result.items);
        setNeedsInputRowsLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setNeedsInputRowsLoaded(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, onListPatientMemory, patientListVersion, memoryRefreshSignal]);

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
        ? backendPatientRows.map(patientRowFromApi)
        : localPatientRows.filter((patient) => {
            if (patientFilter === "active") return patient.isActive;
            return true;
          }),
    [backendPatientRows, localPatientRows, patientFilter, patientRowsError],
  );
  const needsInputSessions = today.needsInputSessions;
  const needsInputCount = needsInputItems.length;
  const normalizedQuery = query.trim().toLowerCase();
  const backendRowsActive = backendPatientRows.length > 0 && !patientRowsError;
  const filteredPatients = backendRowsActive
    ? patientRows
    : patientRows.filter((patient) =>
        normalizedQuery ? [patient.name, patient.summary, patient.badges.join(" ")].join(" ").toLowerCase().includes(normalizedQuery) : true,
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
        return match ? patientRowFromSmartMatch(match) : undefined;
      })() ||
      // Opened by id from a surface that isn't the loaded list (e.g. the worklist): resolve from the
      // fetched detail, or a lightweight stub (its name) so the detail renders without a tab flash.
      (selectedPatientDetail ? patientRowFromApi(selectedPatientDetail.patient) : undefined) ||
      (pendingPatientStub && pendingPatientStub.id === selectedPatientId
        ? patientRowStub(pendingPatientStub.id, pendingPatientStub.name)
        : undefined)
    : null;
  const viewedPatientId = selectedPatient?.id;
  const viewedPatientName = selectedPatient?.name;

  // Report the open patient's file up to App so the global footer can capture *for them* (E9). On
  // unmount (leaving Clinical Memory) clear it, so the capture target reverts to the active session.
  React.useEffect(() => {
    onViewingPatientChange?.(viewedPatientId ? { id: viewedPatientId, name: viewedPatientName || "Patient" } : null);
  }, [viewedPatientId, viewedPatientName, onViewingPatientChange]);
  React.useEffect(() => () => onViewingPatientChange?.(null), [onViewingPatientChange]);

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

  const handleNeedsInputAction = (item: NeedsInputCardItem) => {
    if (item.action === "review-storage") {
      setStorageReviewOpen(true);
      return;
    }
    openNeedsInputDecision(item.action, item.sessionId, "needs-input");
  };

  return (
    <section className="clinical-memory" aria-label="Clinical Memory">
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
      {sharePatient && onCreateShare && onLoadLastVisit && onListAftercareTemplates && onResolveFile && onLoadSessionCaptures ? (
        <SharePatientSheet
          patientId={sharePatient.id}
          patientName={sharePatient.name}
          visits={sharePatient.visits}
          onLoadLastVisit={onLoadLastVisit}
          onLoadSessionCaptures={onLoadSessionCaptures}
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
              await onAssignPatient(assignmentSession.id, draft, { successMessage: "Patient confirmed" });
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
          onContinueSession={onContinueSession}
          onOpenSession={onOpenSession}
          onUpdatePatient={onUpdatePatient}
          onFetchPatient={onFetchPatient}
          onAssignPatient={(sessionId) => setAssignmentSessionId(sessionId)}
          onReviewSummary={(sessionId) => setSummaryReviewSessionId(sessionId)}
          onLoadSessionCaptures={onLoadSessionCaptures}
          onResolveFile={onResolveFile}
          onShare={onCreateShare && onLoadLastVisit ? (visits) => setSharePatient({ id: selectedPatient.id, name: selectedPatient.name, visits }) : undefined}
          currentUserId={myUserId}
          onOpenQaChannel={onOpenQaChannel}
          onToast={onToast}
        />
      ) : (
        <>
      <div className="clinical-memory-hero">
        <div>
          <h1>Clinical Memory</h1>
          <p>Your calm, intelligent assistant for capturing and organizing what matters most.</p>
        </div>
        <button className="needs-input-pill" onClick={() => setActiveTab("needs-input")} type="button">
          <SparkleIcon />
          {needsInputCount ? `${needsInputCount} need your input` : "All caught up"}
          <ChevronIcon />
        </button>
      </div>

      {today.isOffline ? (
        <AssistantStatusPill icon={<OfflineIcon />}>
          Offline · Captures are saved on this device
        </AssistantStatusPill>
      ) : null}

      <label className="clinical-search">
        <SearchIcon />
        <Input
          aria-label="Search patients"
          onChange={(event) => {
            // The search drives patient results, so typing jumps to the Patients tab where it acts
            // (rather than sitting inert on Today / Needs input).
            setQuery(event.target.value);
            if (event.target.value.trim() && activeTab !== "patients") setActiveTab("patients");
          }}
          placeholder="Search patients by name, phone, or ID..."
          value={query}
        />
        <span aria-hidden="true" className="clinical-search-filter">
          <FilterIcon />
        </span>
      </label>

      <div className="clinical-tabs" role="tablist" aria-label="Clinical Memory sections">
        {clinicalTabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.value}
            className={activeTab === tab.value ? "active" : ""}
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            role="tab"
            type="button"
          >
            <span aria-hidden="true">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "today" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          {onListWorklist && onLineUpPatient && onMarkWorklistSeen && onCancelWorklistEntry && onListClinicMembers ? (
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
                setRecapPatient({ id: patientId, name: patientName || "Patient", entryId: worklistEntryId, canStart: canStartVisit })
              }
              refreshSignal={memoryRefreshSignal}
            />
          ) : null}
          <ClinicalSection
            title="Active session"
            badge={today.currentVisit ? activeSectionBadge(today.currentVisit.session) : undefined}
            badgeTone={today.currentVisit?.tone === "amber" ? "amber" : "green"}
          >
            {today.currentVisit ? (
              <VisitCard
                primaryActionLabel={today.currentVisit.session.patientName || today.currentVisit.session.patientId ? "Continue visit" : "Assign patient"}
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
              <EmptyClinicalState title="No active visit." copy="Start with audio, photo, or note." />
            )}
          </ClinicalSection>
          {!today.isOffline ? (
            <ClinicalSection title="Needs your input" badge={needsInputSessions.length ? visitCountLabel(needsInputSessions.length) : undefined} badgeTone="amber">
              {today.needsInputPreview ? (
                <VisitCard
                  primaryActionLabel={todayNeedsInputActionLabel(today.needsInputPreview.session)}
                  summary={today.needsInputPreview.summary}
                  session={today.needsInputPreview.session}
                  statusLabel={today.needsInputPreview.statusLabel}
                  title={today.needsInputPreview.title}
                  tone="amber"
                  onSelect={() => {
                    const preview = today.needsInputPreview;
                    if (preview) onOpenSession(preview.session.id, { tab: "today" });
                  }}
                  onPrimaryAction={() => {
                    const preview = today.needsInputPreview;
                    if (!preview) return;
                    const action = decisionActionForSession(preview.session);
                    if (action === "assign-patient" || action === "choose-patient") {
                      setAssignmentSessionId(preview.session.id);
                      return;
                    }
                    setSummaryReviewSessionId(preview.session.id);
                  }}
                />
              ) : (
                <EmptyClinicalState title="All caught up." copy="Nothing needs your input right now." />
              )}
            </ClinicalSection>
          ) : (
            <p className="clinical-offline-note"><InfoIcon /> You're offline. Patient search may be limited.</p>
          )}
          <ClinicalSection title="Updated today" badge={today.recentMemory.length ? today.recentMemoryBadge : undefined}>
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
              <EmptyClinicalState title="No visits updated today." copy="Visits appear here when captures or patient details change today." />
            )}
          </ClinicalSection>
        </div>
      ) : null}

      {activeTab === "patients" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <div className="patients-toolbar">
            <div className="clinical-filter-row" aria-label="Patient filters">
              {patientFilters.map((filter) => (
                <button
                  aria-pressed={patientFilter === filter.value}
                  className={patientFilter === filter.value ? "active" : ""}
                  key={filter.value}
                  onClick={() => setPatientFilter(filter.value)}
                  type="button"
                >
                  {filter.label}
                </button>
              ))}
            </div>
            {myUserId ? (
              <div className="mine-clinic-toggle" role="group" aria-label="Mine vs Clinic">
                {(["mine", "clinic"] as const).map((value) => (
                  <button
                    key={value}
                    aria-pressed={ownershipScope === value}
                    className={ownershipScope === value ? "active" : ""}
                    onClick={() => setOwnershipScope(value)}
                    type="button"
                  >
                    {value === "mine" ? "Mine" : "Clinic"}
                  </button>
                ))}
              </div>
            ) : null}
            {onCreatePatient ? (
              <button className="patients-create-button" onClick={() => setCreatingPatient((value) => !value)} type="button">
                <span aria-hidden="true">+</span> New patient
              </button>
            ) : null}
          </div>
          {creatingPatient && onCreatePatient ? (
            <section className="patient-edit-card" aria-label="Create a new patient">
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
                <PatientForm onCancel={() => setCreatingPatient(false)} onSubmit={submitNewPatient} submitLabel="Create patient" />
              )}
            </section>
          ) : null}
          {smartResults ? (
            <div className="clinical-list">
              <p className="smart-search-note">
                <SearchIcon /> Deterministic, Persian-aware match · {smartSearching ? "searching…" : `${smartResults.length} result${smartResults.length === 1 ? "" : "s"}`}
              </p>
              {smartResults.length ? (
                smartResults.map((match) => (
                  <PatientRow
                    actionLabel="View history"
                    badges={smartMatchBadges(match)}
                    latestVisitLabel={match.lastVisit ? `Last visit ${formatPatientLastVisit(match.lastVisit)}` : null}
                    key={match.id}
                    patientName={match.displayName}
                    summary={match.reason || "Matched patient record."}
                    isPro={isPro}
                    tone="green"
                    onAction={() => setSelectedPatientId(match.id)}
                    onSelect={() => setSelectedPatientId(match.id)}
                  />
                ))
              ) : (
                <EmptyClinicalState
                  title="No matching patients found."
                  copy={/^\d{1,3}$/.test(query.trim()) ? "Enter at least 4 digits of a phone or national ID — or search by name." : "Try another name, phone, or national ID."}
                />
              )}
            </div>
          ) : (
          <div className="clinical-list">
            {patientRowsError ? (
              <p className="clinical-offline-note"><InfoIcon /> Patient memory is showing saved items from this device.</p>
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
                  isPro={isPro}
                  tone={patient.needsInput ? "amber" : "green"}
                  onAction={() => handlePatientAction(patient)}
                  onSelect={() => setSelectedPatientId(patient.id)}
                />
              ))
            ) : (
              <EmptyClinicalState
                title={patientRows.length ? "No matching patients found." : "No patients yet."}
                copy={patientRows.length ? "Try another search or filter." : "Start by capturing audio, photo, or a note."}
              />
            )}
          </div>
          )}
          {!smartResults && backendRowsActive && filteredPatients.length ? (
            <div className="patients-pagination">
              <span className="patients-count">Showing {filteredPatients.length} of {patientTotal}</span>
              {filteredPatients.length < patientTotal ? (
                <button className="patients-load-more" disabled={patientLoadingMore} onClick={loadMorePatients} type="button">
                  {patientLoadingMore ? "Loading…" : "Load more"}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {activeTab === "needs-input" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <p className="clinical-helper">A few things need your judgment to keep memory accurate and useful.</p>
          <div className="needs-input-list">
            {needsInputItems.length ? (
              needsInputItems.map((item) => (
                <NeedsInputDecisionCard
                  item={item}
                  key={item.id}
                  onSelect={item.sessionId ? () => onOpenSession(item.sessionId!, { tab: "needs-input" }) : undefined}
                  onPrimaryAction={() => handleNeedsInputAction(item)}
                />
              ))
            ) : (
              <EmptyClinicalState title="All caught up." copy="Nothing needs your input." />
            )}
          </div>
        </div>
      ) : null}
        </>
      )}
    </section>
  );
}

type ClinicalMemoryTab = "today" | "patients" | "needs-input";
type PatientFilter = "recent" | "active" | "all";
type ClinicalTone = "blue" | "green" | "amber";

export type ClinicalMemoryReturnContext = {
  tab: ClinicalMemoryTab;
  patientId?: string;
};

type TodayCardModel = {
  session: CaptureSession;
  statusLabel: string;
  title: string;
  summary: string;
  tone: ClinicalTone;
};

type TodayModel = {
  currentVisit?: TodayCardModel;
  isOffline: boolean;
  needsInputPreview?: TodayCardModel;
  needsInputSessions: CaptureSession[];
  recentMemory: TodayCardModel[];
  recentMemoryBadge: string;
};

const clinicalTabs: Array<{ value: ClinicalMemoryTab; label: string; icon: React.ReactNode }> = [
  { value: "today", label: "Today", icon: <CalendarIcon /> },
  { value: "patients", label: "Patients", icon: <PatientsIcon /> },
  { value: "needs-input", label: "Needs input", icon: <NeedsInputIcon /> },
];

const patientFilters: Array<{ value: PatientFilter; label: string }> = [
  { value: "recent", label: "Recent" },
  { value: "active", label: "Active" },
  { value: "all", label: "All" },
];

type PatientRowModel = {
  id: string;
  name: string;
  summary: string;
  memoryStatus: "ready" | "updating" | string;
  badges: string[];
  action: PatientPrimaryAction;
  actionLabel: "Continue" | "View history" | "Review summary" | "Assign patient" | "Choose patient" | "Resolve conflict" | "Verify patient" | "Review items";
  isActive: boolean;
  needsInput: boolean;
  needsInputItems: PatientNeedsInputItem[];
  latestVisitLabel: string | null;
  latestSessionId: string | null;
  activeSessionId: string | null;
  sessionCount: number;
};

type PatientPrimaryAction = "continue" | "open-memory" | "review-summary" | "assign-patient" | "choose-patient" | "resolve-conflict" | "verify" | "review-items";

type PatientNeedsInputItem = {
  id: string;
  sessionId: string | null;
  label: "Needs input: review summary" | "Needs input: assign patient" | "Needs input: choose patient" | "Needs input: resolve conflict" | "Needs input: verify patient";
  action: Exclude<PatientPrimaryAction, "continue" | "open-memory" | "review-items">;
  title: string;
  detail: string;
  sessionLabel: string;
  reason: string;
  sortTime: number;
};

type NeedsInputAction = PatientNeedsInputItem["action"] | "review-storage";
type NeedsInputKind = "assign-patient" | "choose-patient" | "verify" | "review-summary" | "review-storage" | "resolve-conflict" | "missing-field";

type NeedsInputCardItem = {
  id: string;
  kind: NeedsInputKind;
  title: string;
  contextLabel?: string;
  session?: CaptureSession;
  sessionId?: string | null;
  sessionLabel?: string;
  needsInputSinceLabel?: string;
  explanation: string;
  action: NeedsInputAction;
  actionLabel: string;
  possiblePatients?: string[];
  tone: "amber" | "blue" | "purple";
  icon: "assign" | "match" | "summary" | "storage" | "conflict";
  sortTime: number;
};

type StorageWarningDecision = {
  remainingBytes: number;
  usageRatio: number;
};

function buildNeedsInputItems({
  activeSession,
  resolvedDecisionIds,
  sessions,
  storageWarning,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  storageWarning: StorageWarningDecision | null;
}): NeedsInputCardItem[] {
  const sessionItems = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session)))
    .map(needsInputCardFromSession)
    .filter((item): item is NeedsInputCardItem => Boolean(item));
  const storageItem = storageWarning
    ? [
        {
          id: "storage-warning",
          kind: "review-storage" as const,
          title: "Storage getting full",
          contextLabel: "Offline safety warning",
          explanation: "Storage is getting full. New offline captures may not be safely saved soon.",
          action: "review-storage" as const,
          actionLabel: "Review storage",
          tone: "amber" as const,
          icon: "storage" as const,
          sortTime: Date.now(),
        },
      ]
    : [];
  return [...storageItem, ...sessionItems].sort((a, b) => b.sortTime - a.sortTime);
}

function needsInputCardFromSession(session: CaptureSession): NeedsInputCardItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const sortTime = latestSessionTime(session);
  const patientLabel = session.patientName || session.patientId;
  const base = {
    id: `${session.id}-${action}`,
    session,
    sessionId: session.id,
    sessionLabel: `Session: ${sessionTimeLabel(session)}`,
    needsInputSinceLabel: `Needs input since: ${formatSessionTime(sortTime)}`,
    sortTime,
  };
  if (action === "verify") {
    return {
      ...base,
      kind: "verify",
      title: "Verify AI-created patient",
      contextLabel: patientLabel ? `Patient: ${patientLabel}` : undefined,
      explanation: "I created this patient from the visit. Confirm the details before it enters memory.",
      action,
      actionLabel: "Verify patient",
      tone: "blue",
      icon: "match",
    };
  }
  if (action === "assign-patient") {
    return {
      ...base,
      kind: "assign-patient",
      title: "Unassigned visit",
      explanation: needsInputSummary(session),
      action,
      actionLabel: "Assign patient",
      tone: "amber",
      icon: "assign",
    };
  }
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return {
      ...base,
      kind: "choose-patient",
      title: "Patient match uncertain",
      explanation: possiblePatients.length >= 2
        ? `This visit may belong to ${formatNameList(possiblePatients)}. Please choose the correct patient.`
        : "I found a possible patient match before updating memory. Please choose the correct patient.",
      action,
      actionLabel: "Choose patient",
      possiblePatients,
      tone: "purple",
      icon: "match",
    };
  }
  if (action === "resolve-conflict") {
    return {
      ...base,
      kind: "resolve-conflict",
      title: "Conflicting patient information",
      contextLabel: patientLabel ? `Patient: ${patientLabel}` : undefined,
      explanation: "I found patient details that conflict with existing memory. Please review before I update it.",
      action,
      actionLabel: "Resolve conflict",
      tone: "amber",
      icon: "conflict",
    };
  }
  return null;
}

function needsInputCardPresentation(action: PatientNeedsInputItem["action"]): {
  kind: NeedsInputKind;
  title: string;
  tone: NeedsInputCardItem["tone"];
  icon: NeedsInputCardItem["icon"];
  actionLabel: string;
} {
  if (action === "assign-patient") return { kind: "assign-patient", title: "Unassigned visit", tone: "amber", icon: "assign", actionLabel: "Assign patient" };
  if (action === "choose-patient") return { kind: "choose-patient", title: "Patient match uncertain", tone: "purple", icon: "match", actionLabel: "Choose patient" };
  if (action === "resolve-conflict") return { kind: "resolve-conflict", title: "Conflicting patient information", tone: "amber", icon: "conflict", actionLabel: "Resolve conflict" };
  if (action === "verify") return { kind: "verify", title: "Verify AI-created patient", tone: "blue", icon: "match", actionLabel: "Verify patient" };
  return { kind: "review-summary", title: "Summary ready for confirmation", tone: "blue", icon: "summary", actionLabel: "Review summary" };
}

function needsInputCardFromApi(row: ApiPatientMemoryRow, item: PatientNeedsInputItem): NeedsInputCardItem {
  const presentation = needsInputCardPresentation(item.action);
  return {
    id: item.id,
    kind: presentation.kind,
    title: presentation.title,
    contextLabel: row.displayName ? `Patient: ${row.displayName}` : undefined,
    sessionId: item.sessionId,
    sessionLabel: item.sessionLabel,
    needsInputSinceLabel: item.sortTime ? `Needs input since: ${formatSessionTime(item.sortTime)}` : undefined,
    explanation: item.reason,
    action: item.action,
    actionLabel: presentation.actionLabel,
    tone: presentation.tone,
    icon: presentation.icon,
    sortTime: item.sortTime,
  };
}

function buildTodayModel({
  activeSession,
  resolvedDecisionIds,
  sessions,
  syncHealth,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
}): TodayModel {
  const isOffline = !syncHealth.online;
  const todaySessions = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session))).filter(
    sessionTouchedToday,
  );
  const currentSession =
    (activeSession && sessionTouchedToday(activeSession) ? activeSession : null) ||
    todaySessions.find((session) => session.status === "current" || session.status === "draft" || session.status === "reopened");
  const needsInputSessions = todaySessions.filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session))).filter(needsHumanInput);
  const needsInputPreview = needsInputSessions.find((session) => session.id !== currentSession?.id) || needsInputSessions[0];
  const recentMemory = todaySessions
    .filter((session) => session.id !== currentSession?.id)
    .filter((session) => session.id !== needsInputPreview?.id)
    .filter((session) => session.patientName || session.patientId)
    .slice(0, 3)
    .map((session) => ({
      session,
      statusLabel: updatedTodayStatus(session, isOffline),
      title: sessionVisitTitle(session),
      summary: updatedTodaySummary(session),
      tone: "blue" as const,
    }));

  return {
    currentVisit: currentSession
      ? {
          session: currentSession,
          statusLabel: isOffline ? "Saved on this device" : "In progress",
          title: sessionVisitTitle(currentSession),
          summary: currentVisitSummary(currentSession, isOffline),
          tone: currentSession.patientName || currentSession.patientId ? "green" : "amber",
        }
      : undefined,
    isOffline,
    needsInputPreview: needsInputPreview
      ? {
          session: needsInputPreview,
          statusLabel: "Needs your input",
          title: needsInputTitle(needsInputPreview),
          summary: needsInputSummary(needsInputPreview),
          tone: "amber",
        }
      : undefined,
    needsInputSessions,
    recentMemory,
    recentMemoryBadge: isOffline ? `${recentMemory.length} saved on this device` : `${recentMemory.length} updated today`,
  };
}

function buildPatientRows({
  activeSession,
  resolvedDecisionIds,
  sessions,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
}): PatientRowModel[] {
  const groups = new Map<string, CaptureSession[]>();
  uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => session.patientName || session.patientId)
    .forEach((session) => {
      const key = session.patientId || session.patientName || "Patient";
      groups.set(key, [...(groups.get(key) || []), session]);
    });

  return [...groups.entries()]
    .map(([id, patientSessions]) => {
      const sortedSessions = [...patientSessions].sort((a, b) => latestSessionTime(b) - latestSessionTime(a));
      const primarySession = sortedSessions[0];
      const name = primarySession.patientName || sortedSessions.find((session) => session.patientName)?.patientName || id;
      const activeSessions = sortedSessions.filter(isActiveVisit);
      const activeCount = activeSessions.length;
      const needsInputItems = sortedSessions
        .filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session)))
        .map(patientNeedsInputItem)
        .filter((item): item is PatientNeedsInputItem => Boolean(item));
      const needsInput = needsInputItems.length > 0;
      const complete = sortedSessions.some((session) => Boolean(session.complete));
      const primary = patientPrimaryAction({ activeCount, needsInputItems });
      return {
        id,
        name,
        summary: patientCardSummary(sortedSessions),
        memoryStatus: "ready" as const, // local fallback rows are deterministic, never "updating"
        badges: [
          // "Active session" is intentionally not shown on patient cards — live work lives in Today.
          visitCountLabel(sortedSessions.length),
          complete && !needsInput ? "Complete" : undefined,
          needsInputBadgeLabel(needsInputItems),
        ].filter((badge): badge is string => Boolean(badge)),
        action: primary.action,
        actionLabel: primary.label,
        isActive: Boolean(activeCount),
        needsInput,
        needsInputItems,
        latestVisitLabel: latestVisitLabelFromTimestamp(sessionVisitTimestamp(primarySession)),
        latestSessionId: primarySession.id,
        activeSessionId: activeSessions[0]?.id || null,
        sessionCount: sortedSessions.length,
      };
    })
    .sort((a, b) => latestSessionTimeById(b.latestSessionId, sessions, activeSession) - latestSessionTimeById(a.latestSessionId, sessions, activeSession));
}

function patientRowFromApi(row: ApiPatientMemoryRow): PatientRowModel {
  const isActive = row.activeSessionCount > 0;
  const needsInputItems = patientNeedsInputItemsFromApi(row);
  const primary = patientPrimaryAction({ activeCount: row.activeSessionCount, needsInputItems });
  return {
    id: row.patientId,
    name: row.displayName,
    summary: row.summary || "No memory summary yet.",
    memoryStatus: row.memoryStatus === "updating" ? "updating" : "ready",
    badges: [
      // "Active session" is intentionally not shown on patient cards — live work lives in Today.
      visitCountLabel(row.sessionCount),
      row.complete && needsInputItems.length === 0 ? "Complete" : undefined,
      needsInputBadgeLabel(needsInputItems),
    ].filter((badge): badge is string => Boolean(badge)),
    action: primary.action,
    actionLabel: primary.label,
    isActive,
    needsInput: needsInputItems.length > 0,
    needsInputItems,
    latestVisitLabel: latestVisitLabelFromApi(row),
    latestSessionId: row.latestSessionId || null,
    activeSessionId: row.activeSessionId || null,
    sessionCount: row.sessionCount,
  };
}

// AES-204 — a smart-search match rendered as a minimal patient row (so it can open the detail by id).
/** Minimal placeholder row used while a patient opened by id (e.g. from the worklist) loads. */
function patientRowStub(id: string, name: string): PatientRowModel {
  return {
    id,
    name,
    summary: "Loading patient…",
    memoryStatus: "ready",
    badges: [],
    action: "open-memory",
    actionLabel: "View history",
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

function patientRowFromSmartMatch(match: SmartPatientMatch): PatientRowModel {
  return {
    id: match.id,
    name: match.displayName,
    summary: match.reason || "Matched patient record.",
    memoryStatus: "ready",
    badges: smartMatchBadges(match),
    action: "open-memory",
    actionLabel: "View history",
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: match.lastVisit ? `Last visit ${formatPatientLastVisit(match.lastVisit)}` : null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

function smartMatchBadges(match: SmartPatientMatch): string[] {
  const labels: Record<string, string> = {
    national_id: "✓ national ID",
    phone: "✓ phone",
    email: "✓ email",
    name: "✓ name",
    name_prefix: "name prefix",
    name_fuzzy: "fuzzy name",
    contact_partial: "partial contact",
  };
  return match.matchedOn.map((key) => labels[key] || key).slice(0, 3);
}

function patientPrimaryAction({
  activeCount,
  needsInputItems,
}: {
  activeCount: number;
  needsInputItems: PatientNeedsInputItem[];
}): { action: PatientPrimaryAction; label: PatientRowModel["actionLabel"] } {
  if (needsInputItems.length > 1) return { action: "review-items", label: "Review items" };
  const item = needsInputItems[0];
  if (item) return { action: item.action, label: labelForDecisionAction(item.action) };
  if (activeCount > 0) return { action: "continue", label: "Continue" };
  return { action: "open-memory", label: "View history" };
}

function labelForDecisionAction(action: PatientNeedsInputItem["action"]): PatientRowModel["actionLabel"] {
  if (action === "review-summary") return "Review summary";
  if (action === "assign-patient") return "Assign patient";
  if (action === "choose-patient") return "Choose patient";
  if (action === "verify") return "Verify patient";
  return "Resolve conflict";
}

function todayNeedsInputActionLabel(session: CaptureSession) {
  const action = decisionActionForSession(session);
  return action ? labelForDecisionAction(action) : "Open visit";
}

function activeSectionBadge(session: CaptureSession) {
  const action = decisionActionForSession(session);
  return action ? needsInputLabelForAction(action) : "In progress";
}

function needsInputBadgeLabel(items: PatientNeedsInputItem[]) {
  if (items.length > 1) return `${items.length} decisions need input`;
  return items[0]?.label;
}

function patientNeedsInputItemsFromApi(row: ApiPatientMemoryRow): PatientNeedsInputItem[] {
  // The backend is the single source of truth for typed needs-input items. No synthesized
  // fallback: if there are no items, the patient needs nothing.
  return (row.needsInputItems || []).map((item, index) => {
    const action = decisionActionFromKind(item.kind || item.label || "");
    if (!action) return null;
    return {
      id: item.id || `${row.patientId}-needs-input-${index}`,
      sessionId: item.sessionId || row.latestSessionId || row.activeSessionId || null,
      label: needsInputLabelForAction(action),
      action,
      title: titleForDecisionAction(action),
      detail: item.reason || reasonForDecisionAction(action),
      sessionLabel: apiNeedsInputSessionLabel(row, item.createdAt),
      reason: item.reason || reasonForDecisionAction(action),
      sortTime: item.createdAt ? new Date(item.createdAt).getTime() || 0 : 0,
    };
  }).filter((item): item is PatientNeedsInputItem => Boolean(item)).sort((a, b) => b.sortTime - a.sortTime);
}

function patientNeedsInputItem(session: CaptureSession): PatientNeedsInputItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const label = needsInputLabelForAction(action);
  return {
    id: `${session.id}-${action}`,
    sessionId: session.id,
    label,
    action,
    title: titleForSessionDecision(session, action),
    detail: needsInputSummary(session),
    sessionLabel: `Session: ${sessionTimeLabel(session)}`,
    reason: reasonForSessionDecision(session, action),
    sortTime: latestSessionTime(session),
  };
}

function titleForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"]) {
  if (action === "review-summary") return hasMissingClinicalField(session) ? "Clinically important field missing" : "Summary ready for confirmation";
  return titleForDecisionAction(action);
}

function titleForDecisionAction(action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "Unassigned visit";
  if (action === "choose-patient") return "Patient match uncertain";
  if (action === "resolve-conflict") return "Conflicting patient information";
  if (action === "verify") return "Verify AI-created patient";
  return "Summary ready for confirmation";
}

function reasonForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "This visit is saved, but I do not know which patient it belongs to.";
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return possiblePatients.length >= 2
      ? `This visit may belong to ${formatNameList(possiblePatients)}. Please choose the correct patient.`
      : "I found a possible patient match before updating memory. Please choose the correct patient.";
  }
  if (action === "resolve-conflict") return "I found patient details that conflict with existing memory. Please review before I update it.";
  if (hasMissingClinicalField(session)) return "This visit is missing a clinically important detail before it becomes patient memory.";
  return "Review before it becomes part of patient memory.";
}

function reasonForDecisionAction(action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "This visit is saved, but I do not know which patient it belongs to.";
  if (action === "choose-patient") return "I found more than one possible patient match before updating memory.";
  if (action === "resolve-conflict") return "I found patient details that conflict with existing memory.";
  if (action === "verify") return "I created this patient from the visit. Confirm the details before it enters memory.";
  return "Review before it becomes part of patient memory.";
}

function decisionActionForSession(session: CaptureSession): PatientNeedsInputItem["action"] | null {
  // Local (offline) fallback mirroring the backend's three critical needs-input categories:
  // verify (AI-created patient awaiting confirmation), choose-patient / resolve-conflict
  // (ambiguous auto-match on an unassigned visit), and assign-patient (unassigned, no candidate).
  const metadata = session.extractedMetadata as Record<string, unknown> | undefined;
  const aiAction = metadata?.ai_patient_action;
  if (aiAction && typeof aiAction === "object" && (aiAction as Record<string, unknown>).needsVerification === true) {
    return "verify";
  }
  if (session.patientId || session.patientName) return null; // assigned + confirmed → no input
  const patientMatch = metadata?.patient_match;
  const matchStatus =
    patientMatch && typeof patientMatch === "object" && "status" in patientMatch ? String((patientMatch as Record<string, unknown>).status) : "";
  if (matchStatus === "possible_match") {
    const risks = patientMatch && typeof patientMatch === "object" ? (patientMatch as Record<string, unknown>).risks : undefined;
    const hasConflict = Array.isArray(risks) && risks.some((risk) => `${risk}`.toLowerCase().includes("conflict") || `${risk}`.toLowerCase().includes("national id"));
    return hasConflict ? "resolve-conflict" : "choose-patient";
  }
  if (session.status === "unassigned") return "assign-patient";
  return null;
}

function decisionIdForSession(session: CaptureSession) {
  return `${session.id}-${decisionActionForSession(session) || "none"}`;
}

function decisionActionFromKind(value: string): PatientNeedsInputItem["action"] | null {
  const normalized = value.toLowerCase();
  if (isTechnicalNeedsInputText(normalized)) return null;
  if (normalized.includes("verify") || normalized.includes("verification")) return "verify";
  if (normalized.includes("conflict")) return "resolve-conflict";
  if (normalized.includes("assign") || normalized.includes("unassigned")) return "assign-patient";
  if (normalized.includes("choose") || normalized.includes("uncertain") || normalized.includes("match")) return "choose-patient";
  // Routine summary confirmation / missing-field are no longer needs-input categories.
  return null;
}

function needsInputLabelForAction(action: PatientNeedsInputItem["action"]): PatientNeedsInputItem["label"] {
  if (action === "assign-patient") return "Needs input: assign patient";
  if (action === "choose-patient") return "Needs input: choose patient";
  if (action === "resolve-conflict") return "Needs input: resolve conflict";
  if (action === "verify") return "Needs input: verify patient";
  return "Needs input: review summary";
}

function uniqueSessions(sessions: CaptureSession[]) {
  const seen = new Set<string>();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

function sessionTouchedToday(session: CaptureSession) {
  return sessionTouchTimestamps(session).some(isToday);
}

function sessionTouchTimestamps(session: CaptureSession) {
  return [
    session.updatedAt,
    session.createdAt,
    session.capturedAt,
    session.report?.updatedAt,
    session.processingStatus?.updatedAt,
    session.summaries?.updatedAt,
    session.summaries?.generatedAt,
    ...session.items.map((item) => item.capturedAt),
  ].filter((value): value is string => Boolean(value));
}

function isToday(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function AssistantStatusPill({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="assistant-status-pill" role="status">
      {icon}
      <span>{children}</span>
    </div>
  );
}

function ClinicalSection({
  badge,
  badgeTone = "blue",
  children,
  title,
}: {
  badge?: string;
  badgeTone?: "blue" | "green" | "amber";
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="clinical-section">
      <div className="clinical-section-heading">
        <h2>{title}</h2>
        {badge ? <Badge tone={badgeTone}>{badge}</Badge> : null}
      </div>
      {children}
    </section>
  );
}

function ClinicalMemoryCard({
  actionLabel,
  children,
  className,
  tone = "blue",
  onSelect,
  onAction,
}: {
  actionLabel?: string;
  children: React.ReactNode;
  className?: string;
  tone?: ClinicalTone;
  onSelect?: () => void;
  onAction?: () => void;
}) {
  return (
    <Card
      className={["clinical-row", onSelect ? "clinical-row-selectable" : "", `clinical-row-${tone}`, className].filter(Boolean).join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      {children}
      {actionLabel && onAction ? (
        <Button
          onClick={(event) => {
            event.stopPropagation();
            onAction();
          }}
          size="sm"
          type="button"
          variant={tone === "amber" ? "secondary" : "default"}
        >
          {actionLabel}
          <ChevronIcon />
        </Button>
      ) : (
        <span className="patient-row-chevron" aria-hidden="true">
          <ChevronIcon />
        </span>
      )}
    </Card>
  );
}

function VisitCard({
  primaryActionLabel,
  session,
  statusLabel,
  summary,
  title,
  tone,
  onSelect,
  onPrimaryAction,
}: {
  primaryActionLabel?: string;
  session: CaptureSession;
  statusLabel: string;
  summary: string;
  title: string;
  tone: ClinicalTone;
  onSelect?: () => void;
  onPrimaryAction?: () => void;
}) {
  return (
    <Card
      className={["clinical-row", "visit-card", onSelect ? "clinical-row-selectable" : "", `clinical-row-${tone}`].join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      <Avatar label={session.patientName || title} tone={tone} />
      <div className="clinical-row-copy">
        <div className="visit-card-title-row">
          <h3>{title}</h3>
          <Badge tone={tone}>{statusLabel}</Badge>
        </div>
        <VisitMetadata session={session} tone={tone} />
        <p>{summary}</p>
        <CaptureChips session={session} tone={tone} />
      </div>
      <div className="visit-card-actions">
        {primaryActionLabel && onPrimaryAction ? (
          <Button
            onClick={(event) => {
              event.stopPropagation();
              onPrimaryAction();
            }}
            size="sm"
            type="button"
            variant={tone === "amber" ? "secondary" : "default"}
          >
            {primaryActionLabel}
            <ChevronIcon />
          </Button>
        ) : (
          <span className="patient-row-chevron" aria-hidden="true">
            <ChevronIcon />
          </span>
        )}
      </div>
    </Card>
  );
}

function NeedsInputDecisionCard({
  item,
  onSelect,
  onPrimaryAction,
}: {
  item: NeedsInputCardItem;
  onSelect?: () => void;
  onPrimaryAction: () => void;
}) {
  return (
    <Card
      className={["needs-input-card", onSelect ? "clinical-row-selectable" : "", `needs-input-card-${item.tone}`].join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      <Avatar label={item.title} tone={item.tone === "purple" ? "blue" : item.tone} />
      <div className="needs-input-card-icon" aria-hidden="true">
        <NeedsInputDecisionIcon icon={item.icon} />
      </div>
      <div className="needs-input-card-copy">
        <div className="needs-input-title-row">
          <h3>{item.title}</h3>
        </div>
        <div className="visit-metadata" aria-label="Decision context">
          {item.contextLabel ? (
            <div>
              <span>{item.contextLabel.split(":")[0]}:</span>
              <strong>{item.contextLabel.split(":").slice(1).join(":").trim() || item.contextLabel}</strong>
            </div>
          ) : null}
          {item.sessionLabel ? (
            <div>
              <span>Session:</span>
              <strong>{item.sessionLabel.replace(/^Session:\s*/, "")}</strong>
            </div>
          ) : null}
          {item.needsInputSinceLabel ? (
            <div className="visit-metadata-attention">
              <span>Needs input since:</span>
              <strong>{item.needsInputSinceLabel.replace(/^Needs input since:\s*/, "")}</strong>
            </div>
          ) : null}
        </div>
        <p>{item.explanation}</p>
        {item.session && item.kind !== "choose-patient" ? <CaptureChips session={item.session} tone={item.tone === "purple" ? "blue" : item.tone} /> : null}
      </div>
      {item.possiblePatients?.length ? <PossiblePatientOptions patients={item.possiblePatients} /> : null}
      <div className="needs-input-card-actions">
        <Button
          onClick={(event) => {
            event.stopPropagation();
            onPrimaryAction();
          }}
          size="sm"
          type="button"
        >
          {item.actionLabel}
        </Button>
      </div>
    </Card>
  );
}

function PossiblePatientOptions({ patients }: { patients: string[] }) {
  return (
    <div className="possible-patients" aria-label="Possible patients">
      {patients.slice(0, 3).map((patient) => (
        <div className="possible-patient" key={patient}>
          <span>{avatarInitials(patient).slice(0, 1)}</span>
          <strong>{patient}</strong>
        </div>
      ))}
    </div>
  );
}

function VisitMetadata({ session, tone }: { session: CaptureSession; tone: ClinicalTone }) {
  const patientName = session.patientName || session.patientId;
  const inputTime = formatSessionTime(latestSessionTime(session));
  const showNeedsInputSince = tone === "amber" && !patientName;
  const showUpdatedTodayStatus = tone === "blue";
  return (
    <div className="visit-metadata" aria-label="Visit details">
      {patientName ? (
        <div>
          <span>Patient:</span>
          <strong>{patientName}</strong>
        </div>
      ) : null}
      <div>
        <span>Session:</span>
        <strong>{sessionTimeLabel(session)}</strong>
      </div>
      {showNeedsInputSince ? (
        <div className="visit-metadata-attention">
          <span>Needs input since:</span>
          <strong>{inputTime}</strong>
        </div>
      ) : showUpdatedTodayStatus ? (
        <div className="visit-metadata-success">
          <span>Updated:</span>
          <strong>{formatSessionTime(latestSessionTime(session))}</strong>
        </div>
      ) : (
        <div>
          <span>Updated:</span>
          <strong>{formatSessionTime(latestSessionTime(session))}</strong>
        </div>
      )}
    </div>
  );
}

// The edit-patient form (controlled open). The "Edit details" trigger lives in the patient-detail
// action row so it sits beside "Share with patient" with matched styling.
function PatientIdentityEditor({
  patient,
  open,
  onClose,
  onUpdatePatient,
  onFetchPatient,
}: {
  patient: PatientRowModel;
  open: boolean;
  onClose: () => void;
  onUpdatePatient?: (patientId: string, draft: PatientEditDraft) => Promise<void>;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
}) {
  const [saving, setSaving] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [initial, setInitial] = React.useState<Partial<{ displayName: string; nationalId: string; phone: string; dateOfBirth: string; sex: string; notes: string }>>({ displayName: patient.name || "" });
  const loadedRef = React.useRef(false);

  React.useEffect(() => {
    if (!open || loadedRef.current || !onFetchPatient) return;
    loadedRef.current = true;
    setLoading(true);
    void onFetchPatient(patient.id)
      .then((info) => {
        if (!info) return;
        setInitial({
          displayName: info.displayName || patient.name || "",
          nationalId: info.nationalId || "",
          phone: info.phone || "",
          dateOfBirth: info.dateOfBirth || "",
          sex: info.sex || "",
          notes: info.notes || "",
        });
      })
      .finally(() => setLoading(false));
  }, [open, onFetchPatient, patient.id, patient.name]);

  if (!open || !onUpdatePatient) return null;

  return (
    <section className="patient-edit-card" aria-label="Edit patient details">
      <PatientForm
        busy={saving}
        initial={initial}
        loading={loading}
        onCancel={onClose}
        onSubmit={(values) => {
          setSaving(true);
          // Pre-filled = WYSIWYG, so send every field (a cleared field clears it).
          void onUpdatePatient(patient.id, {
            displayName: values.displayName,
            nationalId: values.nationalId,
            phone: values.phone,
            dateOfBirth: values.dateOfBirth,
            sex: values.sex,
            notes: values.notes,
          })
            .then(onClose)
            .finally(() => setSaving(false));
        }}
        submitLabel="Save details"
      />
    </section>
  );
}

function PatientTimelineDetail({
  activeSession,
  detail,
  loading,
  loadError,
  patient,
  isPro,
  sessions,
  onAssignPatient,
  onBack,
  onContinueSession,
  onOpenSession,
  onReviewSummary,
  onUpdatePatient,
  onFetchPatient,
  onLoadSessionCaptures,
  onResolveFile,
  onShare,
  currentUserId,
  onOpenQaChannel,
  onToast,
}: {
  activeSession: CaptureSession | null;
  detail?: PatientMemoryDetailResponse;
  loading: boolean;
  loadError: boolean;
  patient: PatientRowModel;
  isPro: boolean;
  sessions: CaptureSession[];
  onAssignPatient: (sessionId: string) => void;
  onBack: () => void;
  onContinueSession: (sessionId: string) => void;
  onOpenSession: (sessionId: string, context?: ClinicalMemoryReturnContext) => void;
  onReviewSummary: (sessionId: string) => void;
  onUpdatePatient?: (patientId: string, draft: PatientEditDraft) => Promise<void>;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  onLoadSessionCaptures?: (sessionId: string) => Promise<CaptureItem[]>;
  onResolveFile?: (endpoint: string) => Promise<string>;
  onShare?: (visits: GalleryVisit[]) => void;
  currentUserId?: string;
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
}) {
  const [editingPatient, setEditingPatient] = React.useState(false);
  const localSessions = patientSessionsForDetail(patient, sessions, activeSession);
  const timelineGroups = buildTimelineGroups(detail, localSessions);
  const sessionCount = detail?.patient.sessionCount || patient.sessionCount || localSessions.length;
  const firstSeen = firstSeenLabel(detail?.sessions, localSessions);
  // AES-202 — recent visits, most-recent first, fed to the visit-grouped photo gallery (Basic).
  const galleryVisits: GalleryVisit[] = timelineGroups
    .flatMap((group) => group.sessions)
    .map((session) => ({
      sessionId: session.sessionId,
      title: sanitizeSessionLabel(session.title) || (session.localSession ? sessionVisitTitle(session.localSession) : "Visit"),
      dateLabel: timelineSessionTimeLabel(session, session.localSession),
    }))
    .filter((visit) => visit.sessionId);

  return (
    <div className="patient-detail" aria-label={`${patient.name} patient memory`}>
      <button className="context-back-button" onClick={onBack} type="button">
        <BackIcon />
        Patients
      </button>

      <section className="patient-detail-header">
        <Avatar label={patient.name} tone={patient.needsInput ? "amber" : "green"} />
        <div className="patient-detail-heading">
          <h1>{patient.name}</h1>
          <div className="patient-detail-meta" aria-label="Patient metadata">
            <span>{visitCountLabel(sessionCount)}</span>
            {firstSeen ? <span>First seen {firstSeen}</span> : null}
          </div>
        </div>
      </section>

      {(onUpdatePatient || onShare) && !editingPatient ? (
        <div className="patient-detail-actions">
          {onUpdatePatient ? (
            <button className="patient-detail-action" onClick={() => setEditingPatient(true)} type="button">
              <EditPatientIcon /> Edit details
            </button>
          ) : null}
          {onShare ? (
            <button className="patient-detail-action" onClick={() => onShare(galleryVisits)} type="button">
              <ShareSmallIcon /> Share with patient
            </button>
          ) : null}
          {isPro && onOpenQaChannel ? (
            <QaChannelButton patientName={patient.name} onOpen={() => onOpenQaChannel(patient.id)} onToast={onToast} />
          ) : null}
        </div>
      ) : null}

      <PatientIdentityEditor
        patient={patient}
        open={editingPatient}
        onClose={() => setEditingPatient(false)}
        onUpdatePatient={onUpdatePatient}
        onFetchPatient={onFetchPatient}
      />

      <PatientHistoryBlock
        history={detail?.history}
        isPro={isPro}
        loading={loading}
        fallbackSnapshot={detail?.patient.summary || patient.summary}
      />

      {!isPro ? (
        <TryProTeaser
          className="patient-file-teaser"
          title={'Try Pro — AI history & "what did we use last time?"'}
          subtitle="Basic lists the facts. Pro synthesizes the story and recalls products / units / lot."
        />
      ) : null}

      {onLoadSessionCaptures && onResolveFile && galleryVisits.length ? (
        <PatientPhotoGallery
          visits={galleryVisits}
          onLoadSessionCaptures={onLoadSessionCaptures}
          onResolveFile={onResolveFile}
          onOpenVisit={(sessionId) => onOpenSession(sessionId, { tab: "patients", patientId: patient.id })}
        />
      ) : null}

      {loadError ? <p className="clinical-offline-note"><InfoIcon /> Showing memory saved on this device.</p> : null}
      {loading && !timelineGroups.length ? <PatientTimelineLoading /> : null}

      <div className="patient-timeline" aria-label="Visit timeline">
        {timelineGroups.length ? (
          timelineGroups.map((group) => (
            <section className="patient-timeline-group" key={group.label}>
              <div className="patient-timeline-marker" aria-hidden="true" />
              <h2>{group.label}</h2>
              <div className="patient-timeline-cards">
                {group.sessions.map((session) => (
                  <PatientTimelineCard
                    key={session.sessionId}
                    localSession={session.localSession}
                    session={session}
                    currentUserId={currentUserId}
                    onAssignPatient={onAssignPatient}
                    onContinueSession={onContinueSession}
                    onOpenSession={(sessionId) => onOpenSession(sessionId, { tab: "patients", patientId: patient.id })}
                    onReviewSummary={onReviewSummary}
                  />
                ))}
              </div>
            </section>
          ))
        ) : loading ? null : (
          <EmptyClinicalState title="No visits yet." copy="Patient visits will appear here after capture." />
        )}
      </div>
    </div>
  );
}

type TimelineSessionModel = PatientMemoryTimelineSession & {
  localSession?: CaptureSession;
};

type TimelineGroupModel = {
  label: "Today" | "Earlier this week" | "Older";
  sessions: TimelineSessionModel[];
};

function PatientTimelineCard({
  localSession,
  session,
  currentUserId,
  onAssignPatient,
  onContinueSession,
  onOpenSession,
  onReviewSummary,
}: {
  localSession?: CaptureSession;
  session: TimelineSessionModel;
  currentUserId?: string;
  onAssignPatient: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onOpenSession: (sessionId: string) => void;
  onReviewSummary: (sessionId: string) => void;
}) {
  const status = timelineSessionStatus(session, localSession);
  const action = timelineSessionAction(session, localSession);
  const tone = status.startsWith("Needs input") ? "amber" : status === "Complete" ? "blue" : "green";
  const title = session.title || (localSession ? sessionVisitTitle(localSession) : "Visit");
  const summary = session.generatedSummary || session.summary || (localSession ? naturalSessionSummary(localSession) : "") || "This visit is saved in patient memory.";
  const updatedLabel = timelineUpdatedLabel(session, localSession);

  const runAction = () => {
    if (action.kind === "continue") onContinueSession(session.sessionId);
    else if (action.kind === "assign") onAssignPatient(session.sessionId);
    else if (action.kind === "review") onReviewSummary(session.sessionId);
    else onOpenSession(session.sessionId);
  };

  return (
    <Card className={["patient-timeline-card", `patient-timeline-card-${tone}`].join(" ")}>
      <div className="patient-timeline-card-icon" aria-hidden="true">
        <CalendarIcon />
      </div>
      <div className="patient-timeline-card-copy">
        <div className="visit-card-title-row">
          <h3>{title}</h3>
          <Badge tone={tone}>{status}</Badge>
        </div>
        <div className="visit-metadata" aria-label="Visit times">
          <div>
            <span>Session:</span>
            <strong>{timelineSessionTimeLabel(session, localSession)}</strong>
          </div>
          {updatedLabel ? (
            <div className={updatedLabel.startsWith("Updated today") ? "visit-metadata-success" : undefined}>
              {updatedLabel.startsWith("Updated today") ? null : <span>Updated:</span>}
              <strong>{updatedLabel}</strong>
            </div>
          ) : null}
          {session.createdBy ? (
            <div className="visit-metadata-attribution">
              <span>By:</span>
              <strong>{attributionName(session.createdBy, currentUserId)}</strong>
            </div>
          ) : null}
        </div>
        <p>{summary}</p>
        <TimelineCaptureChips session={session} localSession={localSession} tone={tone} />
      </div>
      <div className="patient-timeline-actions">
        <Button onClick={runAction} size="sm" type="button" variant={tone === "amber" ? "secondary" : action.kind === "open" ? "secondary" : "default"}>
          {action.label}
          <ChevronIcon />
        </Button>
      </div>
    </Card>
  );
}

function PatientTimelineLoading() {
  return (
    <Card className="clinical-row clinical-row-loading">
      <span className="clinical-avatar clinical-avatar-blue" />
      <div className="clinical-row-copy">
        <span />
        <p />
      </div>
      <span />
    </Card>
  );
}

function PatientRow({
  actionLabel,
  badges,
  latestVisitLabel,
  patientName,
  summary,
  summaryStatus,
  isPro = false,
  tone = "green",
  onAction,
  onSelect,
}: {
  actionLabel?: string;
  badges: string[];
  latestVisitLabel: string | null;
  patientName: string;
  summary: string;
  summaryStatus?: string;
  isPro?: boolean;
  tone?: ClinicalTone;
  onAction: () => void;
  onSelect: () => void;
}) {
  return (
    <ClinicalMemoryCard actionLabel={actionLabel} className="clinical-patient-row" tone={tone} onAction={onAction} onSelect={onSelect}>
      <Avatar label={patientName} tone={tone} />
      <div className="clinical-row-copy">
        <h3>{patientName}</h3>
        {latestVisitLabel ? <span className="patient-latest-visit">{latestVisitLabel}</span> : null}
        <MemorySummary text={summary} status={summaryStatus} isPro={isPro} />
        <div className="patient-memory-badges" aria-label="Patient memory status">
          {badges.map((badge) => (
            <span className={`patient-memory-badge ${badge.startsWith("Needs input") || badge.includes("need your input") ? "needs-input" : badge === "Complete" ? "verified" : ""}`} key={badge}>
              {badge}
            </span>
          ))}
        </div>
      </div>
    </ClinicalMemoryCard>
  );
}

// Pick the base direction per text so a mostly-English line keeps an LTR base (an embedded RTL
// name stays a coherent isolated run) while predominantly-Persian/Arabic content reads RTL.
function memoryTextDirection(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

// ✨ provenance mark: present whenever an AI-maintained (Pro) memory artifact is shown; it pulses
// while the artifact is refreshing. Basic memory is deterministic and carries no spark.
function MemorySpark({ working }: { working?: boolean }) {
  return (
    <span className={`ai-spark${working ? " working" : ""}`} aria-hidden="true">
      <SparkleIcon />
    </span>
  );
}

function MemoryUpdatingPill({ label = "Organizing memory" }: { label?: string }) {
  return (
    <span className="memory-updating-pill">
      <span className="memory-updating-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {label}…
    </span>
  );
}

// The patient summary line on a card. Keeps the current text legible while a refresh is in flight
// (a shimmer sweep + "Organizing memory" cue), then fades the new text in when it settles. The
// `key={text}` remounts on a content swap so the fade-in plays.
function MemorySummary({ text, status, isPro }: { text: string; status?: string; isPro: boolean }) {
  const updating = status === "updating";
  return (
    <div className={`patient-memory-summary${updating ? " updating" : ""}`}>
      <p className="patient-memory-summary-text" dir={memoryTextDirection(text)} key={text}>
        {isPro ? <MemorySpark working={updating} /> : null}
        <span className="memory-text">{text}</span>
        <span className="memory-sweep" aria-hidden="true" />
      </p>
      {updating ? <MemoryUpdatingPill /> : null}
    </div>
  );
}

// The richer "patient history" brief atop the timeline. Pro renders titled prose sections; Basic
// renders a structural recent-visits recap. Same updating→ready treatment as the card summary.
function PatientHistoryBlock({
  history,
  isPro,
  loading,
  fallbackSnapshot,
}: {
  history?: PatientMemoryHistory | null;
  isPro: boolean;
  loading: boolean;
  fallbackSnapshot?: string | null;
}) {
  const updating = history?.status === "updating";
  const heading = (
    <div className="patient-history-head">
      {isPro ? <MemorySpark working={updating} /> : null}
      <h2>Patient history</h2>
      {updating ? <MemoryUpdatingPill /> : null}
    </div>
  );

  if (!history) {
    if (loading) {
      return (
        <section className="patient-history-card">
          <div className="patient-history-head">
            {isPro ? <MemorySpark working /> : null}
            <h2>Patient history</h2>
          </div>
          <div className="patient-history-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </section>
      );
    }
    if (!fallbackSnapshot) return null;
    return (
      <section className="patient-history-card">
        {heading}
        <p className="patient-history-snapshot" dir={memoryTextDirection(fallbackSnapshot)}>{fallbackSnapshot}</p>
      </section>
    );
  }

  return (
    <section className={`patient-history-card${updating ? " updating" : ""}`}>
      {heading}
      <div className="patient-history-body" key={`${history.snapshot}|${history.sections.length}|${history.visits.length}`}>
        <p className="patient-history-snapshot" dir={memoryTextDirection(history.snapshot)}>{history.snapshot}</p>
        {history.mode === "pro"
          ? history.sections.map((section) => (
              <div className="patient-history-section" key={section.label}>
                <h3>{section.label}</h3>
                <p dir={memoryTextDirection(section.body)}>{section.body}</p>
              </div>
            ))
          : (
              <div className="patient-history-section">
                <h3>Recent visits</h3>
                <ul className="patient-history-visits">
                  {history.visits.map((visit, index) => (
                    <li key={index}>
                      <span className="patient-history-visit-dot" aria-hidden="true" />
                      <span dir={memoryTextDirection(visit)}>{visit}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
        <span className="memory-sweep" aria-hidden="true" />
      </div>
    </section>
  );
}

// AES-903 — the "next patient" recap popup. A light glance before starting: tier-aware patient
// history (Pro AI sections / Basic structural recap, via PatientHistoryBlock) + the prior visit's
// before/after (LastVisitStrip), with Start visit + a link to the full timeline. Avoids the
// open-patient-page → back → capture round-trip.
function PatientRecapSheet({
  patientId,
  patientName,
  worklistEntryId,
  canStartVisit,
  isPro,
  onGetPatientMemory,
  onLoadLastVisit,
  onResolveFile,
  onStartVisit,
  onOpenFullTimeline,
  onClose,
}: {
  patientId: string;
  patientName: string;
  worklistEntryId: string;
  canStartVisit: boolean;
  isPro: boolean;
  onGetPatientMemory?: (patientId: string) => Promise<PatientMemoryDetailResponse>;
  onLoadLastVisit?: (patientId: string) => Promise<LastVisitInfo>;
  onResolveFile?: (endpoint: string) => Promise<string>;
  onStartVisit?: (patientId: string, worklistEntryId?: string) => void;
  onOpenFullTimeline: () => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = React.useState<PatientMemoryDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(true);
  const [lastVisit, setLastVisit] = React.useState<LastVisitInfo | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setDetailLoading(true);
    if (onGetPatientMemory) {
      void onGetPatientMemory(patientId)
        .then((d) => {
          if (!cancelled) setDetail(d);
        })
        .catch(() => undefined)
        .finally(() => {
          if (!cancelled) setDetailLoading(false);
        });
    } else {
      setDetailLoading(false);
    }
    if (onLoadLastVisit) {
      void onLoadLastVisit(patientId)
        .then((v) => {
          if (!cancelled) setLastVisit(v);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [patientId, onGetPatientMemory, onLoadLastVisit]);

  return (
    <div className="resolver-backdrop patient-recap-backdrop" role="presentation">
      <Card className="resolver-sheet patient-recap-sheet" role="dialog" aria-modal="true" aria-label={`${patientName} recap`}>
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Up next</p>
            <h2>{patientName}</h2>
            <p>A quick recap before you start — {isPro ? "AI history" : "recent visits"} and before/after.</p>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>

        <div className="patient-recap-body">
          <PatientHistoryBlock
            history={detail?.history}
            isPro={isPro}
            loading={detailLoading}
            fallbackSnapshot={detail?.patient.summary}
          />
          {lastVisit?.hasPriorVisit && lastVisit.visit && onResolveFile ? (
            <LastVisitStrip lastVisit={lastVisit} onResolveFile={onResolveFile} />
          ) : !detailLoading ? (
            <p className="worklist-recap-note">No prior photos yet — this looks like a first visit.</p>
          ) : null}
        </div>

        <div className="patient-recap-actions">
          {canStartVisit && onStartVisit ? (
            <Button onClick={() => onStartVisit(patientId, worklistEntryId)} size="sm" type="button">
              Start visit
            </Button>
          ) : null}
          <Button onClick={onOpenFullTimeline} size="sm" type="button" variant="secondary">
            Open full timeline
          </Button>
        </div>
      </Card>
    </div>
  );
}

function PatientDecisionListSheet({
  onOpenMemory,
  patient,
  onClose,
  onItemAction,
}: {
  onOpenMemory?: () => void;
  patient: PatientRowModel;
  onClose: () => void;
  onItemAction: (item: PatientNeedsInputItem) => void;
}) {
  return (
    <div className="resolver-backdrop patient-decision-backdrop" role="presentation">
      <Card className="resolver-sheet patient-decision-sheet" role="dialog" aria-modal="true" aria-label={`${patient.name} needs input`}>
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Patient decisions</p>
            <h2>{patient.name} needs your input</h2>
            <p>Review the decisions needed to keep this memory accurate.</p>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>

        {patient.needsInputItems.length ? (
          <div className="patient-decision-list">
            {patient.needsInputItems.map((item) => (
              <div className="patient-decision-item" key={item.id}>
                <div className="patient-decision-copy">
                  <strong>{item.title}</strong>
                  <div className="visit-metadata" aria-label="Decision context">
                    <div>
                      <span>Session:</span>
                      <strong>{item.sessionLabel.replace(/^Session:\s*/, "")}</strong>
                    </div>
                  </div>
                  <p>{item.reason || item.detail}</p>
                </div>
                <Button onClick={() => onItemAction(item)} size="sm" type="button" variant="secondary">
                  {labelForDecisionAction(item.action)}
                  <ChevronIcon />
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <EmptyClinicalState title={`All caught up for ${patient.name}.`} copy="No patient decisions need review right now." />
        )}

        {onOpenMemory ? (
          <div className="patient-decision-secondary">
            <Button onClick={onOpenMemory} size="sm" type="button" variant="ghost">
              View patient history
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function SummaryReviewSheet({
  session,
  onClose,
  onConfirm,
  onOpenVisit,
}: {
  session: CaptureSession;
  onClose: () => void;
  onConfirm: (summary: string) => Promise<void>;
  onOpenVisit: () => void;
}) {
  const initialSummary = reviewSummaryText(session);
  const [summary, setSummary] = React.useState(initialSummary);
  const [editing, setEditing] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const trimmedSummary = summary.trim();
  const captureSummary = resolverCaptureSummary(session);

  const confirmSummary = () => {
    if (!trimmedSummary || saving) return;
    setSaving(true);
    void onConfirm(trimmedSummary).finally(() => setSaving(false));
  };

  return (
    <div className="resolver-backdrop" role="presentation">
      <Card className="resolver-sheet summary-review-sheet" role="dialog" aria-modal="true" aria-label="Review summary">
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Patient memory</p>
            <h2>Review summary</h2>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>

        <div className="summary-review-context" aria-label="Visit context">
          <div>
            <span>Patient:</span>
            <strong>{session.patientName || session.patientId || "Unassigned visit"}</strong>
          </div>
          <div>
            <span>Session:</span>
            <strong>{sessionTimeLabel(session)}</strong>
          </div>
          <div>
            <span>Captures:</span>
            <strong>{captureSummary}</strong>
          </div>
        </div>

        <section className="summary-review-section" aria-labelledby="summary-review-draft-title">
          <div className="summary-review-section-heading">
            <h3 id="summary-review-draft-title">Summary</h3>
            {editing ? <span>Editing</span> : null}
          </div>
          {editing ? (
            <textarea
              aria-label="Edit summary"
              className="summary-review-editor"
              onChange={(event) => setSummary(event.target.value)}
              rows={6}
              value={summary}
            />
          ) : (
            <p>{trimmedSummary}</p>
          )}
        </section>

        <section className="summary-review-section compact" aria-label="Source captures">
          <div className="summary-review-section-heading">
            <h3>Sources</h3>
          </div>
          <CaptureChips session={session} tone="blue" />
        </section>

        <div className="resolver-actions summary-review-actions">
          <Button disabled={!trimmedSummary || saving} onClick={confirmSummary} size="sm" type="button">
            Confirm summary
          </Button>
          <Button
            disabled={saving}
            onClick={() => setEditing((current) => !current)}
            size="sm"
            type="button"
            variant="secondary"
          >
            {editing ? "Save edit" : "Edit summary"}
          </Button>
          <Button disabled={saving} onClick={onOpenVisit} size="sm" type="button" variant="ghost">
            Open visit
          </Button>
        </div>
      </Card>
    </div>
  );
}

function StorageReviewSheet({
  onClose,
  onExport,
  storageWarning,
}: {
  onClose: () => void;
  onExport?: () => Promise<void> | void;
  storageWarning: StorageWarningDecision | null;
}) {
  const [exporting, setExporting] = React.useState(false);
  const percentUsed = storageWarning ? Math.round(storageWarning.usageRatio * 100) : null;
  const remaining = storageWarning ? formatBytes(storageWarning.remainingBytes) : null;
  const exportQueued = () => {
    if (!onExport || exporting) return;
    setExporting(true);
    void Promise.resolve(onExport()).finally(() => setExporting(false));
  };
  return (
    <div className="resolver-backdrop" role="presentation">
      <Card className="resolver-sheet" role="dialog" aria-modal="true" aria-label="Review storage">
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Offline safety warning</p>
            <h2>Storage getting full</h2>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>
        <div className="resolver-summary">
          <span>Device storage</span>
          <strong>{percentUsed ? `${percentUsed}% used${remaining ? ` · ${remaining} free` : ""}` : "Space is limited"}</strong>
          <p>Free device storage before capturing offline. Captures already saved remain available, but new offline captures may soon need more room. Export queued captures first to keep them safe.</p>
        </div>
        <div className="resolver-actions">
          {onExport ? (
            <Button disabled={exporting} onClick={exportQueued} size="sm" type="button" variant="secondary">
              {exporting ? "Exporting…" : "Export queued captures"}
            </Button>
          ) : null}
          <Button onClick={onClose} size="sm" type="button">
            Done
          </Button>
        </div>
      </Card>
    </div>
  );
}

function ChoosePatientResolver({
  session,
  onAssign,
  onClose,
  onKeepUnassigned,
  onSearchPatients,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onClose: () => void;
  onKeepUnassigned: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
}) {
  const candidatePatients = React.useMemo(() => patientChoiceCandidates(session), [session]);
  const [query, setQuery] = React.useState("");
  const [patients, setPatients] = React.useState<PatientSummary[]>([]);
  const [selectedPatient, setSelectedPatient] = React.useState<PatientSummary | null>(candidatePatients[0] || null);
  const [selectedMode, setSelectedMode] = React.useState<"patient" | "unassigned">(candidatePatients[0] ? "patient" : "unassigned");
  const [searching, setSearching] = React.useState(false);
  const [searchError, setSearchError] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const trimmedQuery = query.trim();
  const visiblePatients = React.useMemo(() => filterPatientMatches(patients, trimmedQuery), [patients, trimmedQuery]);
  const captureSummary = resolverCaptureSummary(session);
  const hint = extractedPatientMatchHint(session);

  React.useEffect(() => {
    let cancelled = false;
    setSearchError(false);
    if (!onSearchPatients || !trimmedQuery) {
      setPatients([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    void onSearchPatients(trimmedQuery)
      .then((result) => {
        if (cancelled) return;
        setPatients(result);
      })
      .catch(() => {
        if (cancelled) return;
        setSearchError(true);
        setPatients([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onSearchPatients, trimmedQuery]);

  const confirmPatient = () => {
    if (saving) return;
    if (selectedMode === "unassigned") {
      onKeepUnassigned();
      return;
    }
    if (!selectedPatient) return;
    setSaving(true);
    const shouldCreateOrFind = selectedPatient.id.startsWith("new-patient:") || selectedPatient.id.startsWith("candidate-");
    void onAssign({
      patientId: shouldCreateOrFind ? undefined : selectedPatient.id,
      displayName: selectedPatient.displayName,
      nationalId: selectedPatient.nationalId || undefined,
    }).finally(() => setSaving(false));
  };

  const choosePatient = (patient: PatientSummary) => {
    setSelectedMode("patient");
    setSelectedPatient(patient);
  };

  return (
    <div className="assign-resolver-backdrop" role="presentation">
      <section aria-labelledby="choose-patient-title" aria-modal="true" className="assign-resolver-sheet choose-patient-sheet" role="dialog">
        <div className="assign-resolver-handle" aria-hidden="true" />
        <div className="assign-resolver-heading">
          <div>
            <p className="eyebrow">Patient match</p>
            <h2 id="choose-patient-title">Choose patient</h2>
          </div>
          <Button aria-label="Close choose patient" onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>

        <p className="choose-patient-explanation">This visit may belong to more than one patient. Choose the correct patient.</p>

        <div className="assign-context" aria-label="Visit being resolved">
          <strong>{sessionVisitTitle(session)}</strong>
          <div className="assign-context-grid">
            <span>Session: {sessionTimeLabel(session)}</span>
            <span>Captures: {captureSummary}</span>
          </div>
          {hint ? <p>{hint}</p> : null}
        </div>

        <div className="assign-resolver-section">
          <div className="assign-section-heading">
            <h3>Suggested patients</h3>
          </div>
          <div className="assign-patient-list">
            {candidatePatients.map((patient, index) => (
              <PatientChoiceButton
                hint={patientHint(patient, index)}
                key={patient.id}
                patient={patient}
                selected={selectedMode === "patient" && selectedPatient?.id === patient.id}
                onChoose={() => choosePatient(patient)}
              />
            ))}
          </div>
        </div>

        <div className="assign-resolver-section">
          <div className="assign-section-heading">
            <h3>Search another patient</h3>
            {searching ? <span>Searching...</span> : null}
          </div>
          <label className="assign-search-field">
            <SearchIcon />
            <Input
              aria-label="Search another patient"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search another patient"
              value={query}
            />
          </label>
          {trimmedQuery ? (
            <div className="assign-patient-list" aria-live="polite">
              {visiblePatients.length ? (
                visiblePatients.slice(0, 5).map((patient, index) => (
                  <PatientChoiceButton
                    hint={patientHint(patient, index)}
                    key={patient.id}
                    patient={patient}
                    selected={selectedMode === "patient" && selectedPatient?.id === patient.id}
                    onChoose={() => choosePatient(patient)}
                  />
                ))
              ) : (
                <p className="assign-empty">{searchError ? "Patient search is unavailable right now." : "No patient matches yet."}</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="assign-manual-options choose-patient-options" aria-label="Additional patient options">
          <Button
            disabled={!trimmedQuery || saving}
            onClick={() => choosePatient({ id: `new-patient:${trimmedQuery.toLowerCase().replace(/\s+/g, "-")}`, displayName: trimmedQuery })}
            size="sm"
            type="button"
            variant="secondary"
          >
            Create new patient
          </Button>
          <Button
            aria-pressed={selectedMode === "unassigned"}
            disabled={saving}
            onClick={() => {
              setSelectedMode("unassigned");
              setSelectedPatient(null);
            }}
            size="sm"
            type="button"
            variant={selectedMode === "unassigned" ? "secondary" : "ghost"}
          >
            Keep unassigned
          </Button>
        </div>

        <div className="assign-confirm-bar">
          <Button disabled={saving || (selectedMode === "patient" && !selectedPatient)} onClick={confirmPatient} type="button">
            Confirm patient
          </Button>
        </div>
      </section>
    </div>
  );
}

function PatientChoiceButton({
  hint,
  patient,
  selected,
  onChoose,
}: {
  hint: string;
  patient: PatientSummary;
  selected: boolean;
  onChoose: () => void;
}) {
  return (
    <button
      aria-pressed={selected}
      className={["assign-patient-option", "choose-patient-option", selected ? "selected" : ""].filter(Boolean).join(" ")}
      onClick={onChoose}
      type="button"
    >
      <span className="assign-patient-initials" aria-hidden="true">
        {avatarInitials(patient.displayName)}
      </span>
      <span className="assign-patient-copy">
        <strong>{patient.displayName}</strong>
        <small>{hint}</small>
      </span>
      <span className="assign-patient-select">{selected ? "Selected" : "Select"}</span>
    </button>
  );
}

function AssignPatientResolver({
  session,
  onAssign,
  onClose,
  onKeepUnassigned,
  onOpenVisit,
  onSearchPatients,
  onLoadSuggestion,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onClose: () => void;
  onKeepUnassigned: () => void;
  onOpenVisit: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  /** AES-301/603 — the deterministic "Assign to …?" suggestion (active/recent patient). */
  onLoadSuggestion?: (sessionId: string) => Promise<AssignmentSuggestionResponse>;
}) {
  const [query, setQuery] = React.useState("");
  const [patients, setPatients] = React.useState<PatientSummary[]>([]);
  const [selectedPatient, setSelectedPatient] = React.useState<PatientSummary | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [searchError, setSearchError] = React.useState(false);
  const [suggestion, setSuggestion] = React.useState<AssignmentSuggestionResponse | null>(null);
  const trimmedQuery = query.trim();
  const canCreate = Boolean(trimmedQuery);
  const visiblePatients = React.useMemo(() => filterPatientMatches(patients, trimmedQuery), [patients, trimmedQuery]);

  React.useEffect(() => {
    if (!onLoadSuggestion || session.id.startsWith("local-session-")) return;
    let cancelled = false;
    void onLoadSuggestion(session.id)
      .then((result) => {
        if (!cancelled) setSuggestion(result);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [onLoadSuggestion, session.id]);

  React.useEffect(() => {
    let cancelled = false;
    setSearchError(false);
    if (!onSearchPatients) {
      setPatients([]);
      return;
    }
    setSearching(true);
    void onSearchPatients(trimmedQuery)
      .then((result) => {
        if (cancelled) return;
        setPatients(result);
      })
      .catch(() => {
        if (cancelled) return;
        setSearchError(true);
        setPatients([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onSearchPatients, trimmedQuery]);

  React.useEffect(() => {
    if (!selectedPatient) return;
    const stillVisible = visiblePatients.some((patient) => patient.id === selectedPatient.id);
    if (!stillVisible) setSelectedPatient(null);
  }, [selectedPatient, visiblePatients]);

  const assignDraft = (draft: PatientAssignmentDraft) => {
    if (saving) return;
    setSaving(true);
    void onAssign(draft).finally(() => setSaving(false));
  };

  const summary = naturalSessionSummary(session);
  const captureSummary = resolverCaptureSummary(session);

  return (
    <div className="assign-resolver-backdrop" role="presentation">
      <section aria-labelledby="assign-resolver-title" aria-modal="true" className="assign-resolver-sheet" role="dialog">
        <div className="assign-resolver-handle" aria-hidden="true" />
        <div className="assign-resolver-heading">
          <div>
            <p className="eyebrow">Patient assignment</p>
            <h2 id="assign-resolver-title">Assign patient</h2>
          </div>
          <Button aria-label="Close assign patient" onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>

        <div className="assign-context" aria-label="Visit being assigned">
          <strong>Unassigned visit</strong>
          <div className="assign-context-grid">
            <span>Session: {sessionTimeLabel(session)}</span>
            <span>Captures: {captureSummary}</span>
          </div>
          {summary ? <p>{summary}</p> : null}
        </div>

        {suggestion?.suggestion ? (
          <div className="assign-suggestion" aria-label="Suggested patient">
            <p className="assign-suggestion-label">
              Suggested {suggestion.suggestion.basis === "active_patient" ? "— in chair now" : "— recently seen"}
              <span className="det-note">deterministic</span>
            </p>
            <div className="assign-suggestion-row">
              <span className="assign-patient-initials" aria-hidden="true">{avatarInitials(suggestion.suggestion.displayName)}</span>
              <div className="assign-suggestion-copy">
                <strong>{suggestion.suggestion.displayName}</strong>
                <small>{suggestion.suggestion.reason}</small>
              </div>
              <Button
                disabled={saving}
                onClick={() =>
                  assignDraft({ patientId: suggestion.suggestion!.patientId, displayName: suggestion.suggestion!.displayName })
                }
                size="sm"
                type="button"
              >
                Assign
              </Button>
            </div>
          </div>
        ) : null}

        <label className="assign-search-field">
          <SearchIcon />
          <Input
            aria-label="Search patient"
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search patient"
            value={query}
          />
        </label>

        <div className="assign-resolver-section">
          <div className="assign-section-heading">
            <h3>{trimmedQuery ? "Matching patients" : "Suggested matches"}</h3>
            {searching ? <span>Searching...</span> : null}
          </div>
          <div className="assign-patient-list" aria-live="polite">
            {visiblePatients.length ? (
              visiblePatients.slice(0, 6).map((patient, index) => {
                const selected = selectedPatient?.id === patient.id;
                return (
                  <button
                    aria-pressed={selected}
                    className={["assign-patient-option", selected ? "selected" : ""].filter(Boolean).join(" ")}
                    key={patient.id}
                    onClick={() => setSelectedPatient(patient)}
                    type="button"
                  >
                    <span className="assign-patient-initials" aria-hidden="true">
                      {avatarInitials(patient.displayName)}
                    </span>
                    <span className="assign-patient-copy">
                      <strong>{patient.displayName}</strong>
                      <small>{patientHint(patient, index)}</small>
                    </span>
                    <span className="assign-patient-select">{selected ? "Selected" : "Select"}</span>
                  </button>
                );
              })
            ) : (
              <p className="assign-empty">{searchError ? "Patient search is unavailable right now." : "No patient matches yet."}</p>
            )}
          </div>
        </div>

        <div className="assign-manual-options" aria-label="Manual options">
          <Button
            disabled={!canCreate || saving}
            onClick={() => assignDraft({ displayName: trimmedQuery })}
            size="sm"
            type="button"
            variant="secondary"
          >
            Create new patient
          </Button>
          <Button disabled={saving} onClick={onKeepUnassigned} size="sm" type="button" variant="ghost">
            Keep unassigned
          </Button>
          <Button disabled={saving} onClick={onOpenVisit} size="sm" type="button" variant="ghost">
            Open visit
          </Button>
        </div>

        <div className="assign-confirm-bar">
          <Button
            disabled={!selectedPatient || saving}
            onClick={() => {
              if (!selectedPatient) return;
              assignDraft({
                patientId: selectedPatient.id,
                displayName: selectedPatient.displayName,
                nationalId: selectedPatient.nationalId || undefined,
              });
            }}
            type="button"
          >
            {selectedPatient ? `Assign to ${selectedPatient.displayName}` : "Choose a patient"}
          </Button>
        </div>
      </section>
    </div>
  );
}

function PatientListLoading() {
  return (
    <>
      <Card className="clinical-row clinical-patient-row clinical-row-loading">
        <span className="clinical-avatar clinical-avatar-blue" />
        <div className="clinical-row-copy">
          <span />
          <p />
          <div className="patient-memory-badges">
            <small />
            <small />
          </div>
        </div>
        <span />
      </Card>
      <Card className="clinical-row clinical-patient-row clinical-row-loading">
        <span className="clinical-avatar clinical-avatar-green" />
        <div className="clinical-row-copy">
          <span />
          <p />
          <div className="patient-memory-badges">
            <small />
          </div>
        </div>
        <span />
      </Card>
    </>
  );
}

function CaptureChips({ session, tone }: { session: CaptureSession; tone: ClinicalTone }) {
  const counts = captureCounts(session);
  if (!counts.length) return null;
  return (
    <div className="capture-chips" aria-label="Capture types">
      {counts.map((item) => (
        <span className={`capture-chip capture-chip-${tone}`} key={item.label}>
          {captureTypeIcon(item.type)}
          {item.count} {item.label}
        </span>
      ))}
    </div>
  );
}

function TimelineCaptureChips({
  localSession,
  session,
  tone,
}: {
  localSession?: CaptureSession;
  session: TimelineSessionModel;
  tone: ClinicalTone;
}) {
  if (localSession) return <CaptureChips session={localSession} tone={tone} />;
  if (!session.captureCount) return null;
  return (
    <div className="capture-chips" aria-label="Capture types">
      <span className={`capture-chip capture-chip-${tone}`}>
        {captureTypeIcon("note")}
        {session.captureCount} capture{session.captureCount === 1 ? "" : "s"}
      </span>
    </div>
  );
}

function EmptyClinicalState({ copy, title }: { copy: string; title: string }) {
  return (
    <Card className="clinical-empty">
      <strong>{title}</strong>
      <p>{copy}</p>
    </Card>
  );
}

function Avatar({ label, tone }: { label: string; tone: ClinicalTone }) {
  return <span className={`clinical-avatar clinical-avatar-${tone}`}>{avatarInitials(label)}</span>;
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m15 5-7 7 7 7" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m20 20-4.6-4.6M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z" />
    </svg>
  );
}

function FilterIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M4 6h16l-6.5 7.2V18l-3 1.5v-6.3L4 6Z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M7 3.5v3M17 3.5v3M4.5 9h15M6.5 5h11a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />
    </svg>
  );
}

function EditPatientIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M4.5 17.8 4 21l3.2-.5 10.9-10.9-2.7-2.7L4.5 17.8Z" />
      <path d="m15.4 6.9 1.4-1.4a1.9 1.9 0 0 1 2.7 2.7l-1.4 1.4" />
    </svg>
  );
}

function ShareSmallIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="6" cy="12" r="2.2" />
      <circle cx="18" cy="6" r="2.2" />
      <circle cx="18" cy="18" r="2.2" />
      <path d="m8 11 8-4M8 13l8 4" />
    </svg>
  );
}

function PatientsIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M9.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4 19a5.5 5.5 0 0 1 11 0M16.5 11.5a2.5 2.5 0 1 0 0-5M18 14.5a4.5 4.5 0 0 1 3 4.2" />
    </svg>
  );
}

function NeedsInputIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 4.5 20 8.8v6.4l-8 4.3-8-4.3V8.8l8-4.3Z" />
      <path d="M12 8.5v4.5M12 16.2v.1" />
    </svg>
  );
}

function NeedsInputDecisionIcon({ icon }: { icon: NeedsInputCardItem["icon"] }) {
  if (icon === "match") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.5 19a5 5 0 0 1 10 0M16.5 11a3 3 0 1 0 0-6M15.5 14.2a5 5 0 0 1 5 4.8" />
      </svg>
    );
  }
  if (icon === "summary") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M8 4.5h8l3 3V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6.5a2 2 0 0 1 2-2h1ZM15.5 4.8V8h3.2M8.5 12h7M8.5 15.5h5" />
      </svg>
    );
  }
  if (icon === "storage" || icon === "conflict") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M12 4 21 20H3L12 4ZM12 9.5V14M12 17.2v.1" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 17h.1M9.2 9a3 3 0 1 1 5.1 2.1c-.9.8-1.8 1.3-2.1 2.8M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m12 3 1.4 4.2L17.5 9l-4.1 1.8L12 15l-1.4-4.2L6.5 9l4.1-1.8L12 3ZM5.5 13l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM18 14l.9 2.6 2.6.9-2.6.9L18 21l-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

function OfflineIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m2 2 20 20M8.8 5.1A12.4 12.4 0 0 1 21 8.8M5.6 8.5a8.4 8.4 0 0 1 9.1-.8M8.5 12.1a4.3 4.3 0 0 1 3.8-.9M12 18h.1" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 8h.1M11 11h1v5h1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function captureTypeIcon(type: CaptureItemType) {
  if (type === "photo") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M8 7 9.5 5h5L16 7h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h2ZM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      </svg>
    );
  }
  if (type === "audio" || type === "voice") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3ZM5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M7 4h10a2 2 0 0 1 2 2v14l-4-3H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
    </svg>
  );
}

function possiblePatientNames(session: CaptureSession) {
  const metadata = session.extractedMetadata || {};
  const patientMatch = metadata.patient_match;
  const candidates = [
    ...namesFromUnknown((patientMatch && typeof patientMatch === "object" ? (patientMatch as Record<string, unknown>).candidates : null) || metadata.possible_patients),
    ...namesFromUnknown(metadata.patient_options),
  ];
  const matchedName =
    patientMatch && typeof patientMatch === "object" && typeof (patientMatch as Record<string, unknown>).display_name === "string"
      ? String((patientMatch as Record<string, unknown>).display_name)
      : "";
  return uniqueNames([matchedName, ...candidates]);
}

function patientChoiceCandidates(session: CaptureSession): PatientSummary[] {
  return uniqueNames(possiblePatientNames(session)).slice(0, 6).map((name) => ({
    id: `candidate-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    displayName: name,
  }));
}

function extractedPatientMatchHint(session: CaptureSession) {
  const metadata = session.extractedMetadata || {};
  const patientMatch = metadata.patient_match;
  if (patientMatch && typeof patientMatch === "object") {
    const record = patientMatch as Record<string, unknown>;
    const hint = [record.hint, record.reason, record.summary].find((value): value is string => typeof value === "string" && Boolean(value.trim()));
    if (hint) return sanitizePatientMatchHint(hint);
  }
  if (session.items.some((item) => item.type === "audio" || item.type === "voice")) {
    return "Audio from this visit mentions a patient name.";
  }
  return "";
}

function sanitizePatientMatchHint(value: string) {
  return value
    .replace(/\b(confidence|score|probability)\b\s*[:=]?\s*\d+(\.\d+)?%?/gi, "")
    .replace(/\b(ai|model|job|pipeline)\b/gi, "assistant")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function namesFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        return typeof record.display_name === "string" ? record.display_name : typeof record.name === "string" ? record.name : "";
      }
      return "";
    })
    .filter(Boolean);
}

function uniqueNames(names: string[]) {
  const seen = new Set<string>();
  return names.filter((name) => {
    const normalized = name.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

function formatNameList(names: string[]) {
  if (names.length <= 1) return names[0] || "a possible patient";
  if (names.length === 2) return `${names[0]} or ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, or ${names[names.length - 1]}`;
}

function filterPatientMatches(patients: PatientSummary[], query: string) {
  if (!query) return patients;
  const normalizedQuery = query.toLowerCase();
  return patients.filter((patient) =>
    [patient.displayName, patient.nationalId || "", patient.phone || ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
  );
}

function resolverCaptureSummary(session: CaptureSession) {
  const counts = captureCounts(session);
  if (!counts.length) return "No captures";
  return counts
    .map((item) => {
      const label = item.type === "audio" ? "audio" : item.count === 1 ? item.singular : item.label;
      return `${item.count} ${label}`;
    })
    .join(", ");
}

function patientHint(patient: PatientSummary, index: number) {
  if (patient.lastVisit) return `Recently active · ${formatPatientLastVisit(patient.lastVisit)}`;
  if (index === 0) return "Recently active";
  if (index === 1) return "Similar name mentioned";
  return "Existing patient";
}

function formatPatientLastVisit(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (isToday(date.toISOString())) return "today";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function hasMissingClinicalField(session: CaptureSession) {
  const text = `${session.reviewReason || ""} ${JSON.stringify(session.extractedMetadata || {})}`.toLowerCase();
  return text.includes("missing") && (text.includes("clinical") || text.includes("field") || text.includes("required"));
}

function isTechnicalNeedsInputText(value: string) {
  return [
    "ai failed",
    "ai unavailable",
    "backend unavailable",
    "backend",
    "job pending",
    "object storage",
    "retry sync",
    "retry transcription",
    "sync",
    "transcription failed",
    "upload queue",
  ].some((token) => value.includes(token));
}

function needsHumanInput(session: CaptureSession) {
  return Boolean(decisionActionForSession(session));
}

function needsInputTitle(session: CaptureSession) {
  const action = decisionActionForSession(session);
  if (action === "choose-patient") return "Patient match uncertain";
  if (action === "resolve-conflict") return "Conflicting patient information";
  if (action === "review-summary") return hasMissingClinicalField(session) ? "Clinically important field missing" : "Summary ready for confirmation";
  if (!session.patientName && !session.patientId) return "Unassigned visit";
  return sessionVisitTitle(session);
}

function needsInputSummary(session: CaptureSession) {
  if (!session.patientName && !session.patientId) {
    const count = session.items.length;
    return `${count || "No"} capture${count === 1 ? "" : "s"} saved. I could not confidently attach this visit to a patient.`;
  }
  return "Review this visit before it becomes part of patient memory.";
}

function sessionVisitTitle(session: CaptureSession) {
  const title = session.report?.title || session.reportModel?.title || sanitizeSessionLabel(session.label);
  if (title && title.toLowerCase() === "unassigned visit" && (session.patientName || session.patientId)) return "Visit";
  if (title) return title;
  if (!session.patientName && !session.patientId) return "Unassigned visit";
  return isActiveVisit(session) ? "Follow-up visit" : "Visit";
}

function sanitizeSessionLabel(label?: string | null) {
  const trimmed = label?.trim();
  if (!trimmed) return "";
  if (/^session\s+\d{1,2}:\d{2}/i.test(trimmed)) return "Follow-up visit";
  if (/^\d{1,2}:\d{2}\s*(am|pm)?\s*-\s*capture session$/i.test(trimmed)) return "Follow-up visit";
  if (/^session$/i.test(trimmed)) return "";
  return trimmed;
}

function updatedTodayStatus(session: CaptureSession, isOffline: boolean) {
  if (isOffline) return "Saved on this device";
  if (session.assignmentSource || session.patientName || session.patientId) return "Updated today · Patient assigned";
  return "Memory updated today";
}

function updatedTodaySummary(session: CaptureSession) {
  const counts = captureCounts(session);
  const typeSummary = captureTypeSummary(counts);
  if (typeSummary) return `${capitalize(typeSummary)} ${countsTotal(counts) === 1 ? "was" : "were"} attached to this visit today.`;
  const summary = naturalSessionSummary(session);
  return summary || "This visit was updated today.";
}

function visitCountLabel(count: number) {
  return `${count} visit${count === 1 ? "" : "s"}`;
}

function currentVisitSummary(session: CaptureSession, isOffline: boolean) {
  const counts = captureCounts(session);
  const captureTotal = session.items.length;
  if (isOffline) {
    return `${captureTotal || "No"} capture${captureTotal === 1 ? "" : "s"} saved on this device. I'll organize ${captureTotal === 1 ? "it" : "them"} when connection returns.`;
  }
  if (!captureTotal) return "No captures yet. Start with audio, photo, or note.";
  const typeSummary = captureTypeSummary(counts);
  return `${captureTotal} capture${captureTotal === 1 ? "" : "s"} saved${typeSummary ? `: ${typeSummary}` : ""}. I'm preparing the visit summary.`;
}

function patientCardSummary(sessions: CaptureSession[]) {
  const orderedSessions = [...sessions].sort((a, b) => latestSessionTime(b) - latestSessionTime(a));
  const aiSummary = orderedSessions
    .map((session) => session.summaries)
    .find((summary) => {
      if (!summary?.short) return false;
      const source = (summary.source || "").toLowerCase();
      return !source.includes("rule") && !source.includes("deterministic");
    });
  if (aiSummary?.short) return aiSummary.short;

  const ruleBased = orderedSessions.map((session) => naturalSessionSummary(session)).find(Boolean);
  if (ruleBased) return ruleBased;

  const latest = orderedSessions[0];
  if (latest && (sessionTouchTimestamps(latest).length || latest.items.length)) {
    const updated = naturalUpdatedDate(latest);
    const captureCount = latest.items.length;
    if (captureCount) return `Last updated ${updated}. ${captureCount} capture${captureCount === 1 ? "" : "s"} in the latest visit.`;
    return `Last updated ${updated}.`;
  }

  return "No memory summary yet.";
}

function patientSessionsForDetail(patient: PatientRowModel, sessions: CaptureSession[], activeSession: CaptureSession | null) {
  return uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => session.patientId === patient.id || session.patientName === patient.name)
    .sort((a, b) => sessionVisitTimestamp(b) - sessionVisitTimestamp(a));
}

function buildTimelineGroups(detail: PatientMemoryDetailResponse | undefined, localSessions: CaptureSession[]): TimelineGroupModel[] {
  const localById = new Map(localSessions.map((session) => [session.id, session]));
  const detailSessions = detail?.sessions.length
    ? detail.sessions.map((session) => ({ ...session, groupLabel: normalizeTimelineGroupLabel(session.groupLabel), localSession: localById.get(session.sessionId) }))
    : localSessions.map(timelineSessionFromLocal);
  const groups = new Map<TimelineGroupModel["label"], TimelineSessionModel[]>();
  detailSessions
    .sort((a, b) => timelineSortTime(b) - timelineSortTime(a))
    .forEach((session) => {
      const label = normalizeTimelineGroupLabel(session.groupLabel || timelineGroupLabel(timelineSortTime(session)));
      groups.set(label, [...(groups.get(label) || []), session]);
    });
  return (["Today", "Earlier this week", "Older"] as const)
    .map((label) => ({ label, sessions: groups.get(label) || [] }))
    .filter((group) => group.sessions.length);
}

function timelineSessionFromLocal(session: CaptureSession): TimelineSessionModel {
  const visitTime = sessionVisitTimestamp(session);
  return {
    sessionId: session.id,
    title: sessionVisitTitle(session),
    status: session.status,
    summary: naturalSessionSummary(session) || "This visit is saved in patient memory.",
    generatedSummary: session.summaries?.short || null,
    ruleBasedSummary: null,
    captureCount: session.items.length,
    complete: Boolean(session.complete),
    needsInput: needsHumanInput(session),
    groupLabel: timelineGroupLabel(visitTime),
    sortDate: visitTime ? new Date(visitTime).toISOString() : null,
    capturedAt: session.capturedAt || session.createdAt || null,
    updatedAt: session.updatedAt || session.report?.updatedAt || session.processingStatus?.updatedAt || null,
    localSession: session,
  };
}

function normalizeTimelineGroupLabel(label: string): TimelineGroupModel["label"] {
  if (label === "Today" || label === "Earlier this week") return label;
  return "Older";
}

function timelineGroupLabel(timestamp: number): TimelineGroupModel["label"] {
  if (!timestamp) return "Older";
  const date = new Date(timestamp);
  if (isToday(date.toISOString())) return "Today";
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const ageDays = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) / 86400000);
  return ageDays > 0 && ageDays < 7 ? "Earlier this week" : "Older";
}

function timelineSortTime(session: Pick<TimelineSessionModel, "sortDate" | "capturedAt" | "updatedAt">) {
  return [session.sortDate, session.capturedAt, session.updatedAt]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0] || 0;
}

function timelineSessionTimeLabel(session: TimelineSessionModel, localSession?: CaptureSession) {
  if (localSession) return sessionTimeLabel(localSession);
  const timestamp = timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  return explicitDateTimeLabel(timestamp);
}

function timelineUpdatedLabel(session: TimelineSessionModel, localSession?: CaptureSession) {
  const sessionTime = localSession ? sessionVisitTimestamp(localSession) : timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  const updatedTime = localSession ? latestSessionTime(localSession) : timelineSortTime({ sortDate: session.updatedAt, capturedAt: null, updatedAt: session.updatedAt });
  if (!updatedTime || !sessionTime || updatedTime - sessionTime < 60000) return "";
  if (isToday(new Date(updatedTime).toISOString()) && (localSession?.assignmentSource || localSession?.patientId)) return "Updated today · Patient assigned";
  return formatSessionTime(updatedTime);
}

function timelineSessionStatus(session: TimelineSessionModel, localSession?: CaptureSession) {
  const action = timelineDecisionAction(session, localSession);
  if (action) return needsInputLabelForAction(action);
  if (localSession && isActiveVisit(localSession)) return "In progress";
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return "In progress";
  if (session.complete || localSession?.complete) return "Complete";
  if (localSession?.id.startsWith("local-session-")) return "Saved on this device";
  return "Saved on this device";
}

function timelineSessionAction(session: TimelineSessionModel, localSession?: CaptureSession): { kind: "continue" | "open" | "review" | "assign"; label: string } {
  const action = timelineDecisionAction(session, localSession);
  if (action === "assign-patient" || action === "choose-patient" || action === "resolve-conflict") return { kind: "assign", label: labelForDecisionAction(action) };
  if (action === "verify") return { kind: "open", label: "Verify patient" };
  if (localSession && isActiveVisit(localSession)) return { kind: "continue", label: "Continue visit" };
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return { kind: "continue", label: "Continue visit" };
  if (session.complete || localSession?.complete) return { kind: "open", label: "Open visit" };
  return { kind: "open", label: "Open visit" };
}

function timelineDecisionAction(session: TimelineSessionModel, localSession?: CaptureSession): PatientNeedsInputItem["action"] | null {
  if (localSession) return decisionActionForSession(localSession);
  const status = session.status.toLowerCase();
  if (status === "unassigned") return "assign-patient";
  // The backend `needsInput` flag is the 3-category source of truth; on an assigned timeline
  // session that still needs input, the only remaining category is verify.
  if (session.needsInput) return "verify";
  return null;
}

function firstSeenLabel(detailSessions: PatientMemoryTimelineSession[] | undefined, localSessions: CaptureSession[]) {
  const timestamps = [
    ...(detailSessions || []).map((session) => timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null })),
    ...localSessions.map(sessionVisitTimestamp),
  ].filter(Boolean);
  if (!timestamps.length) return "";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(Math.min(...timestamps)));
}

function naturalSessionSummary(session: CaptureSession) {
  if (session.summaries?.short) return session.summaries.short;
  if (session.summaries?.patientHistory) return session.summaries.patientHistory;
  const summary = sanitizeSummary(session.summary);
  if (summary) return summary;
  const counts = captureCounts(session);
  const captureSummary = captureTypeSummary(counts);
  return captureSummary ? `Latest visit includes ${captureSummary}.` : "";
}

function reviewSummaryText(session: CaptureSession) {
  return (
    naturalSessionSummary(session) ||
    "Follow-up visit focused on headache patterns, sleep quality, and next steps. Photos and an audio note were captured. Education and follow-up plan are being prepared."
  );
}

function sanitizeSummary(summary?: string | null) {
  const trimmed = summary?.trim();
  if (!trimmed) return "";
  return trimmed.replace(/^Mock session summary:\s*/i, "");
}

function isActiveVisit(session: CaptureSession) {
  return ["current", "draft", "reopened", "processing"].includes(session.status);
}

function latestSessionTime(session: CaptureSession) {
  const timestamp = sessionTouchTimestamps(session)
    .map((value) => new Date(value).getTime())
    .filter((value) => !Number.isNaN(value))
    .sort((a, b) => b - a)[0];
  return timestamp || 0;
}

function sessionVisitTimestamp(session: CaptureSession) {
  const timestamp = [session.capturedAt, session.createdAt]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))[0];
  return timestamp || latestSessionTime(session);
}

function latestSessionTimeById(sessionId: string | null, sessions: CaptureSession[], activeSession: CaptureSession | null) {
  const session = [activeSession, ...sessions].find((candidate) => candidate?.id === sessionId);
  return session ? latestSessionTime(session) : 0;
}

function latestVisitLabelFromApi(row: ApiPatientMemoryRow) {
  const timestamp = latestApiVisitTimestamp(row);
  return latestVisitLabelFromTimestamp(timestamp);
}

function apiNeedsInputSessionLabel(row: ApiPatientMemoryRow, fallbackTimestamp?: string | null) {
  const timestamp = [
    row.latestSessionMetadata?.capturedAt,
    row.latestVisitAt,
    row.latestSessionMetadata?.updatedAt,
    fallbackTimestamp,
    row.updatedAt,
  ]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0];
  if (!timestamp) return "Session: Recent visit";
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
  const timeLabel = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
  return `Session: ${dateLabel} · ${timeLabel}`;
}

function latestApiVisitTimestamp(row: ApiPatientMemoryRow) {
  const candidates = [
    row.latestVisitAt,
    row.latestSessionMetadata?.capturedAt,
    row.latestSessionMetadata?.updatedAt,
    row.updatedAt,
  ];
  return candidates
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0] || 0;
}

function latestVisitLabelFromTimestamp(timestamp: number) {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
  const timeLabel = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
  return `Latest visit: ${dateLabel} · ${timeLabel}`;
}

function naturalUpdatedDate(session: CaptureSession) {
  const timestamp = latestSessionTime(session);
  if (!timestamp) return "recently";
  const date = new Date(timestamp);
  if (isToday(date.toISOString())) return "today";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function captureCounts(session: CaptureSession) {
  return [
    { label: "photos", singular: "photo", type: "photo" as const, count: session.items.filter((item) => item.type === "photo").length },
    { label: "audio", singular: "audio note", type: "audio" as const, count: session.items.filter((item) => item.type === "audio" || item.type === "voice").length },
    { label: "notes", singular: "note", type: "note" as const, count: session.items.filter((item) => item.type === "note").length },
  ].filter((item) => item.count);
}

function captureTypeSummary(counts: ReturnType<typeof captureCounts>) {
  const parts = counts.map((item) => `${item.count} ${item.count === 1 ? item.singular : item.label}`);
  if (parts.length <= 1) return parts[0] || "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

function countsTotal(counts: ReturnType<typeof captureCounts>) {
  return counts.reduce((total, item) => total + item.count, 0);
}

function capitalize(value: string) {
  if (!value) return value;
  return `${value[0].toUpperCase()}${value.slice(1)}`;
}

function sessionTimeLabel(session: CaptureSession) {
  return [session.dateLabel, session.time].filter(Boolean).join(" · ") || "Recent visit";
}

function formatSessionTime(timestamp: number) {
  if (!timestamp) return "recently";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

function explicitDateTimeLabel(timestamp: number) {
  if (!timestamp) return "Recent visit";
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
  return `${dateLabel} · ${formatSessionTime(timestamp)}`;
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 MB";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 10 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

function avatarInitials(label: string) {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (label.toLowerCase().includes("unassigned")) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("");
}

export function SearchHome({
  sessions,
  syncHealth,
  onOpenSession,
}: {
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  onOpenSession: (sessionId: string) => void;
}) {
  const [query, setQuery] = React.useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const results = normalizedQuery
    ? sessions.filter((session) =>
        [
          session.label,
          session.summary,
          session.patientName,
          session.reviewReason,
          ...session.items.flatMap((item) => [item.title, item.detail, item.sourceName, item.patientName]),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery),
      )
    : [];

  return (
    <section className="memory-home" aria-label="Search">
      <div>
        <p className="eyebrow">Search</p>
        <h1>Find clinical memory</h1>
        <p>Search loaded patients, sessions, and captures from this device session.</p>
      </div>
      {!syncHealth.online ? <p className="clinical-offline-note"><InfoIcon /> You're offline. Patient search may be limited.</p> : null}
      <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search patients, sessions, captures" value={query} />
      <div className="memory-section">
        <div className="section-heading">
          <div>
            <h2>Results</h2>
            <p>Matches include local session and capture text already loaded in the app.</p>
          </div>
          <Badge tone={results.length ? "blue" : "neutral"}>{results.length}</Badge>
        </div>
        <div className="stack">
          {results.map((session) => (
            <button className="search-result-card" key={session.id} onClick={() => onOpenSession(session.id)} type="button">
              <div>
                <strong>{session.label}</strong>
                <p>{session.summary}</p>
                <span>{session.patientName || session.reviewReason || "Unassigned session"}</span>
              </div>
              <SessionStatusBadge status={session.status} />
            </button>
          ))}
          {query && results.length === 0 ? <p>No matching loaded memory.</p> : null}
          {!query ? <p>Enter a term to search the currently loaded clinical memory.</p> : null}
        </div>
      </div>
    </section>
  );
}

export function CaptureDestinationPanel({
  kind,
  sessions,
  activeSession,
  selectedSession,
  onCancel,
  onNewSession,
  onUseSession,
}: {
  kind: CaptureDraft["kind"];
  sessions: CaptureSession[];
  activeSession: CaptureSession | null;
  selectedSession?: CaptureSession | null;
  onCancel: () => void;
  onNewSession: () => void;
  onUseSession: (sessionId: string) => void;
}) {
  const options = [selectedSession, activeSession, ...sessions]
    .filter((session): session is CaptureSession => Boolean(session))
    .filter((session, index, all) => all.findIndex((candidate) => candidate.id === session.id) === index)
    .slice(0, 3);
  return (
    <section className="capture-destination-panel" aria-label="Capture destination">
      <div>
        <p className="eyebrow">Capture destination</p>
        <h2>{captureKindLabel(kind)}</h2>
        <p>Choose where this capture should be saved.</p>
      </div>
      <div className="capture-destination-actions">
        {options.map((session) => (
          <Button key={session.id} onClick={() => onUseSession(session.id)} size="sm" type="button" variant="secondary">
            {session.label}
          </Button>
        ))}
        <Button onClick={onNewSession} size="sm" type="button">
          New session
        </Button>
        <Button onClick={onCancel} size="sm" type="button" variant="secondary">
          Cancel
        </Button>
      </div>
    </section>
  );
}

function captureKindLabel(kind: CaptureDraft["kind"]) {
  if (kind === "audio") return "Audio";
  if (kind === "photo") return "Take photo";
  return "Write note";
}
