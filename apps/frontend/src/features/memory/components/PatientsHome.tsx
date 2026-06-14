// Clinical Memory home screen (Today / Patients / Needs input tabs).
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { AftercareTemplate, AssignmentSuggestionResponse, AuthSession, ClinicMember, CreatePatientShareInput, DuplicateCheckResponse, LastVisitInfo, PatientAssignmentDraft, PatientMemoryDetailResponse, PatientMemoryFilter, PatientMemoryListResponse, PatientMemoryRow as ApiPatientMemoryRow, PatientShare, PatientSummary, SmartPatientMatch, SmartPatientSearchResponse, SyncHealth, WorklistEntry, WorklistResponse } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import type { PatientEditDraft } from "../../../services/api/client";
import { Input } from "../../../shared/ui/primitives";
import { WorklistSection } from "./WorklistSection";
import { PatientForm } from "../../patient/PatientForm";
import { RegisterPatientForm } from "../../aesthetics/RegisterPatientForm";
import { type GalleryVisit } from "../../aesthetics/PatientPhotoGallery";
import { SharePatientSheet } from "../../aesthetics/SharePatientSheet";
import type { QaThreadSummary } from "../../qa/qaClient";
import { ClinicalMemoryTab, PatientFilter, ClinicalMemoryReturnContext, PatientRowModel, PatientNeedsInputItem, NeedsInputCardItem, StorageWarningDecision, buildNeedsInputItems, needsInputCardFromApi, buildTodayModel, buildPatientRows, patientRowFromApi, patientRowStub, patientRowFromSmartMatch, smartMatchBadges, todayNeedsInputActionLabel, activeSectionBadge, patientNeedsInputItemsFromApi, decisionActionForSession, decisionIdForSession, formatPatientLastVisit, visitCountLabel } from "./memoryModel";
import { SearchIcon, FilterIcon, CalendarIcon, PatientsIcon, NeedsInputIcon, SparkleIcon, ChevronIcon, OfflineIcon, InfoIcon } from "./MemoryIcons";
import { AssistantStatusPill, ClinicalSection, VisitCard, EmptyClinicalState, PatientRow, PatientListLoading, NeedsInputDecisionCard } from "./MemoryCards";
import { PatientDecisionListSheet, SummaryReviewSheet, StorageReviewSheet, PatientRecapSheet, ChoosePatientResolver, AssignPatientResolver } from "./MemorySheets";
import { PatientTimelineDetail } from "./PatientTimeline";

export const PATIENT_PAGE_SIZE = 25;
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

export const clinicalTabs: Array<{ value: ClinicalMemoryTab; label: string; icon: React.ReactNode }> = [
  { value: "today", label: "Today", icon: <CalendarIcon /> },
  { value: "patients", label: "Patients", icon: <PatientsIcon /> },
  { value: "needs-input", label: "Needs input", icon: <NeedsInputIcon /> },
];

export const patientFilters: Array<{ value: PatientFilter; label: string }> = [
  { value: "recent", label: "Recent" },
  { value: "active", label: "Active" },
  { value: "all", label: "All" },
];
