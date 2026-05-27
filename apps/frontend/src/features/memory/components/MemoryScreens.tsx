import React from "react";
import type { CaptureDraft, PatientAssignmentDraft, PatientSummary, SyncHealth } from "../../../domain/appTypes";
import type { CaptureItemType, CaptureSession } from "../../../domain/types";
import { Badge, Button, Card, Input } from "../../../shared/ui/primitives";
import { PatientAssignmentSheet } from "../../capture/components/CaptureScreen";
import { SessionStatusBadge } from "../../capture/components/StatusBadges";

export function PatientsHome({
  activeSession,
  sessions,
  syncHealth,
  onOpenSession,
  onContinueSession,
  onSearchPatients,
  onAssignPatient,
}: {
  activeSession: CaptureSession | null;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  onOpenSession: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onVerifySession?: (sessionId: string) => void;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
}) {
  const [activeTab, setActiveTab] = React.useState<ClinicalMemoryTab>("today");
  const [query, setQuery] = React.useState("");
  const [assignmentSessionId, setAssignmentSessionId] = React.useState("");
  const today = React.useMemo(() => buildTodayModel({ activeSession, sessions, syncHealth }), [activeSession, sessions, syncHealth]);
  const patientGroups = React.useMemo(() => {
    const groups = new Map<string, CaptureSession[]>();
    sessions
      .filter((session) => session.patientName || session.patientId)
      .forEach((session) => {
        const key = session.patientName || session.patientId || "Patient";
        groups.set(key, [...(groups.get(key) || []), session]);
      });
    return [...groups.entries()].map(([patientName, patientSessions]) => ({
      patientName,
      sessions: patientSessions,
      summary: patientMemorySummary(patientSessions),
    }));
  }, [sessions]);
  const needsInputSessions = today.needsInputSessions;
  const normalizedQuery = query.trim().toLowerCase();
  const filteredPatients = normalizedQuery
    ? patientGroups.filter((patient) => [patient.patientName, patient.summary].join(" ").toLowerCase().includes(normalizedQuery))
    : patientGroups;
  const assignmentSession = assignmentSessionId
    ? sessions.find((session) => session.id === assignmentSessionId) || (activeSession?.id === assignmentSessionId ? activeSession : null)
    : null;

  return (
    <section className="clinical-memory" aria-label="Clinical Memory">
      {assignmentSession && onAssignPatient ? (
        <PatientAssignmentSheet
          session={assignmentSession}
          onAssign={async (draft) => {
            await onAssignPatient(assignmentSession.id, draft);
            setAssignmentSessionId("");
          }}
          onCancel={() => setAssignmentSessionId("")}
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
          {needsInputSessions.length ? `${needsInputSessions.length} needs your input` : "All caught up"}
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
          <ClinicalSection title="Current visit" badge={today.currentVisit ? "In progress" : undefined} badgeTone="green">
            {today.currentVisit ? (
              <VisitCard
                actionLabel={today.currentVisit.session.patientName || today.currentVisit.session.patientId ? "Continue" : "Assign patient"}
                summary={today.currentVisit.summary}
                session={today.currentVisit.session}
                tone={today.currentVisit.tone}
                title={today.currentVisit.title}
                onAction={() => {
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
                  actionLabel={today.needsInputPreview.session.patientName ? "Review" : "Assign patient"}
                  summary={today.needsInputPreview.summary}
                  session={today.needsInputPreview.session}
                  title={today.needsInputPreview.title}
                  tone="amber"
                  onAction={() => {
                    const preview = today.needsInputPreview;
                    if (!preview) return;
                    if (preview.session.patientName || preview.session.patientId) {
                      onOpenSession(preview.session.id);
                      return;
                    }
                    setAssignmentSessionId(preview.session.id);
                  }}
                />
              ) : (
                <EmptyClinicalState title="All caught up." copy="Nothing needs your input right now." />
              )}
            </ClinicalSection>
          ) : (
            <p className="clinical-offline-note"><InfoIcon /> You're offline. Patient search may be limited.</p>
          )}
          <ClinicalSection title="Recent memory" badge={today.recentMemory.length ? today.recentMemoryBadge : undefined}>
            {today.recentMemory.length ? (
              <div className="clinical-list">
                {today.recentMemory.map((memory) => (
                  <PatientMemoryRow
                    actionLabel="Open"
                    key={memory.session.id}
                    patientName={memory.title}
                    summary={memory.summary}
                    timestamp={sessionTimestamp(memory.session)}
                    tone={memory.tone}
                    onOpen={() => onOpenSession(memory.session.id)}
                  />
                ))}
              </div>
            ) : (
              <EmptyClinicalState title="Recent patients will appear here." copy="Memory updates will show after visits are saved." />
            )}
          </ClinicalSection>
        </div>
      ) : null}

      {activeTab === "patients" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <div className="clinical-filter-row" aria-label="Patient filters">
            <button className="active" type="button">Recent</button>
            <button type="button">Active</button>
            <button type="button">All</button>
          </div>
          <div className="clinical-list">
            {filteredPatients.length ? (
              filteredPatients.map((patient) => (
                <PatientMemoryRow
                  actionLabel="Open memory"
                  key={patient.patientName}
                  patientName={patient.patientName}
                  summary={patient.summary}
                  timestamp={`${patient.sessions.length} visit${patient.sessions.length === 1 ? "" : "s"} saved`}
                  tone="green"
                  onOpen={() => onOpenSession(patient.sessions[0].id)}
                />
              ))
            ) : (
              <EmptyClinicalState title="No patient memory found" copy="Try another search or capture a new visit." />
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "needs-input" ? (
        <div className="clinical-tab-panel" role="tabpanel">
          <p className="clinical-helper">Only human decisions appear here, so the list stays focused on judgment instead of system work.</p>
          <div className="clinical-list">
            {needsInputSessions.length ? (
              needsInputSessions.map((session) => (
                <VisitCard
                  actionLabel={session.patientName ? "Review" : "Assign patient"}
                  key={session.id}
                  session={session}
                  summary={needsInputSummary(session)}
                  tone="amber"
                  title={needsInputTitle(session)}
                  onAction={() => {
                    if (session.patientName || session.patientId) {
                      onOpenSession(session.id);
                      return;
                    }
                    setAssignmentSessionId(session.id);
                  }}
                />
              ))
            ) : (
              <EmptyClinicalState title="All caught up." copy="Nothing needs your input right now." />
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

type ClinicalMemoryTab = "today" | "patients" | "needs-input";
type ClinicalTone = "blue" | "green" | "amber";

type TodayCardModel = {
  session: CaptureSession;
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
    .filter((session) => session.patientName || session.patientId)
    .slice(0, 3)
    .map((session) => ({
      session,
      title: session.patientName || session.label,
      summary: patientMemorySummary([session]),
      tone: "blue" as const,
    }));

  return {
    currentVisit: currentSession
      ? {
          session: currentSession,
          title: currentSession.patientName || "Unassigned visit",
          summary: currentVisitSummary(currentSession, isOffline),
          tone: currentSession.patientName || currentSession.patientId ? "green" : "amber",
        }
      : undefined,
    isOffline,
    needsInputPreview: needsInputPreview
      ? {
          session: needsInputPreview,
          title: needsInputTitle(needsInputPreview),
          summary: needsInputSummary(needsInputPreview),
          tone: "amber",
        }
      : undefined,
    needsInputSessions,
    recentMemory,
    recentMemoryBadge: isOffline ? `${recentMemory.length} saved on this device` : `${recentMemory.length} updated`,
  };
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
  tone = "blue",
  onAction,
}: {
  actionLabel: string;
  children: React.ReactNode;
  tone?: ClinicalTone;
  onAction: () => void;
}) {
  return (
    <Card className={`clinical-row clinical-row-${tone}`}>
      {children}
      <Button onClick={onAction} size="sm" type="button" variant={tone === "amber" ? "secondary" : "default"}>
        {actionLabel}
        <ChevronIcon />
      </Button>
    </Card>
  );
}

function VisitCard({
  actionLabel,
  session,
  summary,
  title,
  tone,
  onAction,
}: {
  actionLabel: string;
  session: CaptureSession;
  summary: string;
  title: string;
  tone: ClinicalTone;
  onAction: () => void;
}) {
  return (
    <ClinicalMemoryCard actionLabel={actionLabel} tone={tone} onAction={onAction}>
      <Avatar label={title} tone={tone} />
      <div className="clinical-row-copy">
        <h3>{title}</h3>
        <span>{sessionTimestamp(session)}</span>
        <p>{summary}</p>
        <CaptureChips session={session} tone={tone} />
      </div>
    </ClinicalMemoryCard>
  );
}

function PatientMemoryRow({
  actionLabel,
  patientName,
  summary,
  timestamp,
  tone = "blue",
  onOpen,
}: {
  actionLabel: string;
  patientName: string;
  summary: string;
  timestamp: string;
  tone?: ClinicalTone;
  onOpen: () => void;
}) {
  return (
    <ClinicalMemoryCard actionLabel={actionLabel} tone={tone} onAction={onOpen}>
      <Avatar label={patientName} tone={tone} />
      <div className="clinical-row-copy">
        <h3>{patientName}</h3>
        <span>{timestamp}</span>
        <p>{summary}</p>
      </div>
    </ClinicalMemoryCard>
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

function needsHumanInput(session: CaptureSession) {
  return !session.patientName && !session.patientId;
}

function needsInputTitle(session: CaptureSession) {
  if (!session.patientName && !session.patientId) return "Unassigned visit";
  return "Review visit";
}

function needsInputSummary(session: CaptureSession) {
  if (!session.patientName && !session.patientId) {
    const count = session.items.length;
    return `${count || "No"} capture${count === 1 ? "" : "s"} saved. I could not confidently attach this visit to a patient.`;
  }
  return "Review this visit before it becomes part of patient memory.";
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
  return `${captureTotal} capture${captureTotal === 1 ? "" : "s"} saved from today's visit${typeSummary ? `, including ${typeSummary}` : ""}. I'm organizing the summary in the background.`;
}

function patientMemorySummary(sessions: CaptureSession[]) {
  const reviewed = sessions.find((session) => session.status === "verified" && session.summary);
  const recent = sessions.find((session) => session.summary);
  const source = reviewed || recent;
  if (source?.summaries?.short) return source.summaries.short;
  if (source?.summary) return source.summary;
  const last = sessions[0];
  if (last?.items.length) return `Recent visit includes ${captureTypeSummary(captureCounts(last)) || `${last.items.length} saved captures`}.`;
  return "Patient memory is saved.";
}

function captureCounts(session: CaptureSession) {
  return [
    { label: "photos", singular: "photo", type: "photo" as const, count: session.items.filter((item) => item.type === "photo").length },
    { label: "audio", singular: "audio note", type: "audio" as const, count: session.items.filter((item) => item.type === "audio" || item.type === "voice").length },
    { label: "notes", singular: "note", type: "note" as const, count: session.items.filter((item) => item.type === "note").length },
  ].filter((item) => item.count);
}

function captureTypeSummary(counts: ReturnType<typeof captureCounts>) {
  const parts = counts.map((item) => `${item.count === 1 ? "an" : item.count} ${item.count === 1 ? item.singular : item.label}`);
  if (parts.length <= 1) return parts[0] || "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

function sessionTimestamp(session: CaptureSession) {
  return [session.dateLabel, session.time].filter(Boolean).join(" - ") || "Recent visit";
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
