import React from "react";
import type {
  CaptureDraft,
  PatientAssignmentDraft,
  PatientMemoryFilter,
  PatientMemoryListResponse,
  PatientMemoryRow as ApiPatientMemoryRow,
  PatientSummary,
  SyncHealth,
} from "../../../domain/appTypes";
import type { CaptureItemType, CaptureSession } from "../../../domain/types";
import { Badge, Button, Card, Input } from "../../../shared/ui/primitives";
import { SessionStatusBadge } from "../../capture/components/StatusBadges";

export function PatientsHome({
  activeSession,
  sessions,
  syncHealth,
  onOpenSession,
  onContinueSession,
  onListPatientMemory,
  onSearchPatients,
  onVerifySession,
  onAssignPatient,
}: {
  activeSession: CaptureSession | null;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  onOpenSession: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onListPatientMemory?: (params: { query?: string; filter: PatientMemoryFilter; limit?: number; offset?: number }) => Promise<PatientMemoryListResponse>;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onVerifySession?: (sessionId: string) => void;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
}) {
  const [activeTab, setActiveTab] = React.useState<ClinicalMemoryTab>("today");
  const [query, setQuery] = React.useState("");
  const [patientFilter, setPatientFilter] = React.useState<PatientFilter>("recent");
  const [backendPatientRows, setBackendPatientRows] = React.useState<ApiPatientMemoryRow[]>([]);
  const [patientRowsLoading, setPatientRowsLoading] = React.useState(false);
  const [patientRowsError, setPatientRowsError] = React.useState(false);
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const [summaryReviewSessionId, setSummaryReviewSessionId] = React.useState("");
  const [decisionListPatientId, setDecisionListPatientId] = React.useState("");
  const [storageReviewOpen, setStorageReviewOpen] = React.useState(false);
  const [storageWarning, setStorageWarning] = React.useState<StorageWarningDecision | null>(null);
  const today = React.useMemo(() => buildTodayModel({ activeSession, sessions, syncHealth }), [activeSession, sessions, syncHealth]);
  const localPatientRows = React.useMemo(() => buildPatientRows({ activeSession, sessions }), [activeSession, sessions]);
  const needsInputItems = React.useMemo(
    () => buildNeedsInputItems({ activeSession, sessions, storageWarning }),
    [activeSession, sessions, storageWarning],
  );
  React.useEffect(() => {
    if (activeTab !== "patients" || !onListPatientMemory) return;
    let cancelled = false;
    setPatientRowsLoading(true);
    setPatientRowsError(false);
    void onListPatientMemory({ query, filter: patientFilter, limit: 50 })
      .then((result) => {
        if (cancelled) return;
        setBackendPatientRows(result.items);
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
  }, [activeTab, onListPatientMemory, patientFilter, query]);
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
    if (targetItem?.action === "assign-patient" || targetItem?.action === "choose-patient") {
      if (targetItem.sessionId) setAssignmentSessionId(targetItem.sessionId);
      else if (patient.latestSessionId) onOpenSession(patient.latestSessionId);
      return;
    }
    if (targetItem?.action === "review-summary" || targetItem?.action === "resolve-conflict") {
      if (targetItem.sessionId) setSummaryReviewSessionId(targetItem.sessionId);
      else if (patient.latestSessionId) onOpenSession(patient.latestSessionId);
      return;
    }
    if (patient.latestSessionId) onOpenSession(patient.latestSessionId);
  };

  const handleDecisionAction = (item: PatientNeedsInputItem, patient?: PatientRowModel) => {
    if (item.action === "assign-patient" || item.action === "choose-patient") {
      if (item.sessionId) setAssignmentSessionId(item.sessionId);
      else if (patient?.latestSessionId) onOpenSession(patient.latestSessionId);
      return;
    }
    if (item.action === "review-summary" || item.action === "resolve-conflict") {
      if (item.sessionId) setSummaryReviewSessionId(item.sessionId);
      else if (patient?.latestSessionId) onOpenSession(patient.latestSessionId);
    }
  };

  const handleNeedsInputAction = (item: NeedsInputCardItem) => {
    if (item.action === "review-storage") {
      setStorageReviewOpen(true);
      return;
    }
    if (!item.session) return;
    if (item.action === "assign-patient" || item.action === "choose-patient") {
      setAssignmentSessionId(item.session.id);
      return;
    }
    setSummaryReviewSessionId(item.session.id);
  };

  return (
    <section className="clinical-memory" aria-label="Clinical Memory">
      {decisionListPatient ? (
        <PatientDecisionListSheet
          patient={decisionListPatient}
          onClose={() => setDecisionListPatientId("")}
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
          onReview={() => {
            onVerifySession?.(summaryReviewSession.id);
            setSummaryReviewSessionId("");
          }}
        />
      ) : null}
      {storageReviewOpen ? <StorageReviewSheet onClose={() => setStorageReviewOpen(false)} storageWarning={storageWarning} /> : null}
      {assignmentSession && onAssignPatient ? (
        <AssignPatientResolver
          session={assignmentSession}
          onAssign={async (draft) => {
            await onAssignPatient(assignmentSession.id, draft);
            setAssignmentSessionId("");
          }}
          onClose={() => setAssignmentSessionId("")}
          onKeepUnassigned={() => setAssignmentSessionId("")}
          onOpenVisit={() => {
            onOpenSession(assignmentSession.id);
            setAssignmentSessionId("");
          }}
          onSearchPatients={onSearchPatients}
        />
      ) : null}
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
          Offline - Captures are saved on this device
        </AssistantStatusPill>
      ) : null}

      <label className="clinical-search">
        <SearchIcon />
        <Input
          aria-label="Search clinical memory"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search patients, visits, notes..."
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
          <ClinicalSection title="Active session" badge={today.currentVisit ? "In progress" : undefined} badgeTone="green">
            {today.currentVisit ? (
              <VisitCard
                primaryActionLabel={today.currentVisit.session.patientName || today.currentVisit.session.patientId ? "Continue visit" : "Assign patient"}
                summary={today.currentVisit.summary}
                session={today.currentVisit.session}
                statusLabel={today.currentVisit.statusLabel}
                tone={today.currentVisit.tone}
                title={today.currentVisit.title}
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
                  secondaryActionLabel="Open visit"
                  summary={today.needsInputPreview.summary}
                  session={today.needsInputPreview.session}
                  statusLabel={today.needsInputPreview.statusLabel}
                  title={today.needsInputPreview.title}
                  tone="amber"
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
                  onSecondaryAction={() => {
                    const preview = today.needsInputPreview;
                    if (preview) onOpenSession(preview.session.id);
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
                    primaryActionLabel="Open visit"
                    session={memory.session}
                    statusLabel={memory.statusLabel}
                    summary={memory.summary}
                    title={memory.title}
                    tone={memory.tone}
                    onPrimaryAction={() => onOpenSession(memory.session.id)}
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
          <div className="clinical-list">
            {patientRowsError ? (
              <p className="clinical-offline-note"><InfoIcon /> Patient memory is showing saved items from this device.</p>
            ) : null}
            {patientRowsLoading && !filteredPatients.length ? (
              <PatientListLoading />
            ) : filteredPatients.length ? (
              filteredPatients.map((patient) => (
                <PatientRow
                  actionLabel={patient.actionLabel}
                  badges={patient.badges}
                  latestVisitLabel={patient.latestVisitLabel}
                  key={patient.id}
                  patientName={patient.name}
                  summary={patient.summary}
                  tone={patient.needsInput ? "amber" : "green"}
                  onOpen={() => handlePatientAction(patient)}
                />
              ))
            ) : (
              <EmptyClinicalState
                title={patientRows.length ? "No matching patients found." : "No patients yet."}
                copy={patientRows.length ? "Try another search or filter." : "Start by capturing audio, photo, or a note."}
              />
            )}
          </div>
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
                  onOpenVisit={item.session ? () => onOpenSession(item.session!.id) : undefined}
                  onPrimaryAction={() => handleNeedsInputAction(item)}
                />
              ))
            ) : (
              <EmptyClinicalState title="All caught up." copy="Nothing needs your input." />
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

type ClinicalMemoryTab = "today" | "patients" | "needs-input";
type PatientFilter = "recent" | "active" | "all";
type ClinicalTone = "blue" | "green" | "amber";

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
  badges: string[];
  action: PatientPrimaryAction;
  actionLabel: "Continue" | "Open memory" | "Review summary" | "Assign patient" | "Choose patient" | "Resolve conflict" | "Review items";
  isActive: boolean;
  needsInput: boolean;
  needsInputItems: PatientNeedsInputItem[];
  latestVisitLabel: string | null;
  latestSessionId: string | null;
  activeSessionId: string | null;
};

type PatientPrimaryAction = "continue" | "open-memory" | "review-summary" | "assign-patient" | "choose-patient" | "resolve-conflict" | "review-items";

type PatientNeedsInputItem = {
  id: string;
  sessionId: string | null;
  label: "Needs input: review summary" | "Needs input: assign patient" | "Needs input: choose patient" | "Needs input: resolve conflict";
  action: Exclude<PatientPrimaryAction, "continue" | "open-memory" | "review-items">;
  title: string;
  detail: string;
  sortTime: number;
};

type NeedsInputAction = PatientNeedsInputItem["action"] | "review-storage";
type NeedsInputKind = "assign-patient" | "choose-patient" | "review-summary" | "review-storage" | "resolve-conflict" | "missing-field";

type NeedsInputCardItem = {
  id: string;
  kind: NeedsInputKind;
  title: string;
  contextLabel?: string;
  session?: CaptureSession;
  sessionLabel?: string;
  needsInputSinceLabel?: string;
  explanation: string;
  action: NeedsInputAction;
  actionLabel: string;
  secondaryActionLabel?: string;
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
  sessions,
  storageWarning,
}: {
  activeSession: CaptureSession | null;
  sessions: CaptureSession[];
  storageWarning: StorageWarningDecision | null;
}): NeedsInputCardItem[] {
  const sessionItems = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
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
    sessionLabel: `Session: ${sessionTimeLabel(session)}`,
    needsInputSinceLabel: `Needs input since: ${formatSessionTime(sortTime)}`,
    sortTime,
  };
  if (action === "assign-patient") {
    return {
      ...base,
      kind: "assign-patient",
      title: "Unassigned visit",
      explanation: needsInputSummary(session),
      action,
      actionLabel: "Assign patient",
      secondaryActionLabel: "Open visit",
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
      secondaryActionLabel: "Open visit",
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
      secondaryActionLabel: "Open visit",
      tone: "amber",
      icon: "conflict",
    };
  }
  const missingField = hasMissingClinicalField(session);
  return {
    ...base,
    kind: missingField ? "missing-field" : "review-summary",
    title: missingField ? "Clinically important field missing" : "Summary ready for confirmation",
    contextLabel: patientLabel ? `Patient: ${patientLabel}` : undefined,
    explanation: missingField
      ? "This visit is missing a clinically important detail before it becomes patient memory."
      : "I drafted a summary of this visit before adding it to long-term memory.",
    action,
    actionLabel: "Review summary",
    secondaryActionLabel: "Open visit",
    tone: "blue",
    icon: "summary",
  };
}

function buildTodayModel({
  activeSession,
  sessions,
  syncHealth,
}: {
  activeSession: CaptureSession | null;
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
  const needsInputSessions = todaySessions.filter(needsHumanInput);
  const needsInputPreview = needsInputSessions.find((session) => session.id !== currentSession?.id) || needsInputSessions[0];
  const recentMemory = todaySessions
    .filter((session) => session.id !== currentSession?.id)
    .filter((session) => session.id !== needsInputPreview?.id)
    .filter((session) => session.patientName || session.patientId)
    .slice(0, 3)
    .map((session) => ({
      session,
      statusLabel: isOffline ? "Saved on this device" : "Updated today",
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

function buildPatientRows({ activeSession, sessions }: { activeSession: CaptureSession | null; sessions: CaptureSession[] }): PatientRowModel[] {
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
      const needsInputItems = sortedSessions.map(patientNeedsInputItem).filter((item): item is PatientNeedsInputItem => Boolean(item));
      const needsInput = needsInputItems.length > 0;
      const verified = sortedSessions.some((session) => session.status === "verified");
      const primary = patientPrimaryAction({ activeCount, needsInputItems });
      return {
        id,
        name,
        summary: patientCardSummary(sortedSessions),
        badges: [
          activeCount ? `${activeCount} active session${activeCount === 1 ? "" : "s"}` : visitCountLabel(sortedSessions.length),
          verified ? "Verified" : undefined,
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
    badges: [
      isActive ? `${row.activeSessionCount} active session${row.activeSessionCount === 1 ? "" : "s"}` : visitCountLabel(row.sessionCount),
      row.verified ? "Verified" : undefined,
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
  };
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
  return { action: "open-memory", label: "Open memory" };
}

function labelForDecisionAction(action: PatientNeedsInputItem["action"]): PatientRowModel["actionLabel"] {
  if (action === "review-summary") return "Review summary";
  if (action === "assign-patient") return "Assign patient";
  if (action === "choose-patient") return "Choose patient";
  return "Resolve conflict";
}

function todayNeedsInputActionLabel(session: CaptureSession) {
  const action = decisionActionForSession(session);
  return action ? labelForDecisionAction(action) : "Open visit";
}

function needsInputBadgeLabel(items: PatientNeedsInputItem[]) {
  if (items.length > 1) return `${items.length} items need your input`;
  return items[0]?.label;
}

function patientNeedsInputItemsFromApi(row: ApiPatientMemoryRow): PatientNeedsInputItem[] {
  const explicitItems = (row.needsInputItems || []).map((item, index) => {
    const action = decisionActionFromKind(item.kind || item.label || "");
    if (!action) return null;
    const label = needsInputLabelForAction(action);
    return {
      id: item.id || `${row.patientId}-needs-input-${index}`,
      sessionId: item.sessionId || row.latestSessionId || row.activeSessionId || null,
      label,
      action,
      title: label.replace("Needs input: ", ""),
      detail: "This patient memory has a decision waiting.",
      sortTime: item.createdAt ? new Date(item.createdAt).getTime() || 0 : 0,
    };
  }).filter((item): item is PatientNeedsInputItem => Boolean(item));
  if (explicitItems.length) return explicitItems.sort((a, b) => b.sortTime - a.sortTime);
  if (!row.needsInput) return [];
  return [
    {
      id: `${row.patientId}-review-summary`,
      sessionId: row.latestSessionId || row.activeSessionId || null,
      label: "Needs input: review summary",
      action: "review-summary",
      title: "Review summary",
      detail: "Confirm the latest generated summary before it updates patient memory.",
      sortTime: latestApiVisitTimestamp(row),
    },
  ];
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
    title: label.replace("Needs input: ", ""),
    detail: needsInputSummary(session),
    sortTime: latestSessionTime(session),
  };
}

function decisionActionForSession(session: CaptureSession): PatientNeedsInputItem["action"] | null {
  const reason = `${session.reviewReason || ""} ${JSON.stringify(session.extractedMetadata || {})}`.toLowerCase();
  const patientMatch = session.extractedMetadata?.patient_match;
  const matchStatus =
    patientMatch && typeof patientMatch === "object" && "status" in patientMatch ? String((patientMatch as Record<string, unknown>).status) : "";
  if (isTechnicalNeedsInputText(reason)) return null;
  if (reason.includes("conflict")) return "resolve-conflict";
  if (matchStatus === "possible_match" || reason.includes("possible_match") || reason.includes("choose patient") || reason.includes("match")) {
    return "choose-patient";
  }
  if (session.status === "unassigned") return "assign-patient";
  if (reason.includes("missing") && (reason.includes("clinical") || reason.includes("field") || reason.includes("required"))) return "review-summary";
  if ((session.status === "needs_review" || session.status === "reviewing") && (session.patientName || session.patientId)) return "review-summary";
  return null;
}

function decisionActionFromKind(value: string): PatientNeedsInputItem["action"] | null {
  const normalized = value.toLowerCase();
  if (isTechnicalNeedsInputText(normalized)) return null;
  if (normalized.includes("assign") || normalized.includes("unassigned")) return "assign-patient";
  if (normalized.includes("choose") || normalized.includes("uncertain") || normalized.includes("match")) return "choose-patient";
  if (normalized.includes("conflict")) return "resolve-conflict";
  if (normalized.includes("summary") || normalized.includes("confirm") || normalized.includes("review") || normalized.includes("missing")) return "review-summary";
  return null;
}

function needsInputLabelForAction(action: PatientNeedsInputItem["action"]): PatientNeedsInputItem["label"] {
  if (action === "assign-patient") return "Needs input: assign patient";
  if (action === "choose-patient") return "Needs input: choose patient";
  if (action === "resolve-conflict") return "Needs input: resolve conflict";
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
  onAction,
}: {
  actionLabel: string;
  children: React.ReactNode;
  className?: string;
  tone?: ClinicalTone;
  onAction: () => void;
}) {
  return (
    <Card className={["clinical-row", `clinical-row-${tone}`, className].filter(Boolean).join(" ")}>
      {children}
      <Button onClick={onAction} size="sm" type="button" variant={tone === "amber" ? "secondary" : "default"}>
        {actionLabel}
        <ChevronIcon />
      </Button>
    </Card>
  );
}

function VisitCard({
  primaryActionLabel,
  secondaryActionLabel,
  session,
  statusLabel,
  summary,
  title,
  tone,
  onPrimaryAction,
  onSecondaryAction,
}: {
  primaryActionLabel: string;
  secondaryActionLabel?: string;
  session: CaptureSession;
  statusLabel: string;
  summary: string;
  title: string;
  tone: ClinicalTone;
  onPrimaryAction: () => void;
  onSecondaryAction?: () => void;
}) {
  return (
    <Card className={["clinical-row", "visit-card", `clinical-row-${tone}`].join(" ")}>
      <Avatar label={title} tone={tone} />
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
        <Button onClick={onPrimaryAction} size="sm" type="button" variant={tone === "amber" ? "secondary" : "default"}>
          {primaryActionLabel}
          <ChevronIcon />
        </Button>
        {secondaryActionLabel && onSecondaryAction ? (
          <Button onClick={onSecondaryAction} size="sm" type="button" variant="ghost">
            {secondaryActionLabel}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

function NeedsInputDecisionCard({
  item,
  onOpenVisit,
  onPrimaryAction,
}: {
  item: NeedsInputCardItem;
  onOpenVisit?: () => void;
  onPrimaryAction: () => void;
}) {
  return (
    <Card className={["needs-input-card", `needs-input-card-${item.tone}`].join(" ")}>
      <Avatar label={item.title} tone={item.tone === "purple" ? "blue" : item.tone} />
      <div className="needs-input-card-icon" aria-hidden="true">
        <NeedsInputDecisionIcon icon={item.icon} />
      </div>
      <div className="needs-input-card-copy">
        <div className="needs-input-title-row">
          <h3>{item.title}</h3>
          {onOpenVisit ? (
            <button aria-label={`Open visit for ${item.title}`} className="needs-input-open-icon" onClick={onOpenVisit} type="button">
              <ChevronIcon />
            </button>
          ) : null}
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
          {item.kind === "assign-patient" && item.needsInputSinceLabel ? (
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
        <Button onClick={onPrimaryAction} size="sm" type="button">
          {item.actionLabel}
        </Button>
        {item.secondaryActionLabel && onOpenVisit ? (
          <Button onClick={onOpenVisit} size="sm" type="button" variant="ghost">
            {item.secondaryActionLabel}
          </Button>
        ) : null}
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
          <strong>{updatedTodayStatus(session, false)}</strong>
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

function PatientRow({
  actionLabel,
  badges,
  latestVisitLabel,
  patientName,
  summary,
  tone = "green",
  onOpen,
}: {
  actionLabel: string;
  badges: string[];
  latestVisitLabel: string | null;
  patientName: string;
  summary: string;
  tone?: ClinicalTone;
  onOpen: () => void;
}) {
  return (
    <ClinicalMemoryCard actionLabel={actionLabel} className="clinical-patient-row" tone={tone} onAction={onOpen}>
      <Avatar label={patientName} tone={tone} />
      <div className="clinical-row-copy">
        <h3>{patientName}</h3>
        {latestVisitLabel ? <span className="patient-latest-visit">{latestVisitLabel}</span> : null}
        <p>{summary}</p>
        <div className="patient-memory-badges" aria-label="Patient memory status">
          {badges.map((badge) => (
            <span className={`patient-memory-badge ${badge.startsWith("Needs input") || badge.includes("need your input") ? "needs-input" : badge === "Verified" ? "verified" : ""}`} key={badge}>
              {badge}
            </span>
          ))}
        </div>
      </div>
    </ClinicalMemoryCard>
  );
}

function PatientDecisionListSheet({
  patient,
  onClose,
  onItemAction,
}: {
  patient: PatientRowModel;
  onClose: () => void;
  onItemAction: (item: PatientNeedsInputItem) => void;
}) {
  return (
    <div className="resolver-backdrop" role="presentation">
      <Card className="resolver-sheet" role="dialog" aria-modal="true" aria-label={`${patient.name} needs input`}>
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Patient decisions</p>
            <h2>{patient.name}</h2>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>
        <div className="resolver-list">
          {patient.needsInputItems.map((item) => (
            <div className="resolver-item" key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
              <Button onClick={() => onItemAction(item)} size="sm" type="button" variant="secondary">
                {labelForDecisionAction(item.action)}
                <ChevronIcon />
              </Button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SummaryReviewSheet({
  session,
  onClose,
  onOpenVisit,
  onReview,
}: {
  session: CaptureSession;
  onClose: () => void;
  onOpenVisit: () => void;
  onReview: () => void;
}) {
  return (
    <div className="resolver-backdrop" role="presentation">
      <Card className="resolver-sheet" role="dialog" aria-modal="true" aria-label="Review summary">
        <div className="resolver-heading">
          <div>
            <p className="eyebrow">Summary review</p>
            <h2>{sessionVisitTitle(session)}</h2>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            Close
          </Button>
        </div>
        <div className="resolver-summary">
          <span>{session.patientName || session.patientId || "Unassigned visit"}</span>
          <strong>{sessionTimeLabel(session)}</strong>
          <p>{naturalSessionSummary(session) || session.summary || "Review the generated visit summary before it becomes patient memory."}</p>
        </div>
        <div className="resolver-actions">
          <Button onClick={onReview} size="sm" type="button">
            Mark reviewed
          </Button>
          <Button onClick={onOpenVisit} size="sm" type="button" variant="secondary">
            Open visit
          </Button>
        </div>
      </Card>
    </div>
  );
}

function StorageReviewSheet({
  onClose,
  storageWarning,
}: {
  onClose: () => void;
  storageWarning: StorageWarningDecision | null;
}) {
  const percentUsed = storageWarning ? Math.round(storageWarning.usageRatio * 100) : null;
  const remaining = storageWarning ? formatBytes(storageWarning.remainingBytes) : null;
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
          <p>Free device storage before capturing offline. Captures already saved remain available, but new offline captures may soon need more room.</p>
        </div>
        <div className="resolver-actions">
          <Button onClick={onClose} size="sm" type="button">
            Done
          </Button>
        </div>
      </Card>
    </div>
  );
}

function AssignPatientResolver({
  session,
  onAssign,
  onClose,
  onKeepUnassigned,
  onOpenVisit,
  onSearchPatients,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onClose: () => void;
  onKeepUnassigned: () => void;
  onOpenVisit: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [patients, setPatients] = React.useState<PatientSummary[]>([]);
  const [selectedPatient, setSelectedPatient] = React.useState<PatientSummary | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [searchError, setSearchError] = React.useState(false);
  const trimmedQuery = query.trim();
  const canCreate = Boolean(trimmedQuery);
  const visiblePatients = React.useMemo(() => filterPatientMatches(patients, trimmedQuery), [patients, trimmedQuery]);

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
  return "Updated today";
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

function naturalSessionSummary(session: CaptureSession) {
  if (session.summaries?.short) return session.summaries.short;
  if (session.summaries?.patientHistory) return session.summaries.patientHistory;
  const summary = sanitizeSummary(session.summary);
  if (summary) return summary;
  const counts = captureCounts(session);
  const captureSummary = captureTypeSummary(counts);
  return captureSummary ? `Latest visit includes ${captureSummary}.` : "";
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
  onOpenSession,
}: {
  sessions: CaptureSession[];
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
