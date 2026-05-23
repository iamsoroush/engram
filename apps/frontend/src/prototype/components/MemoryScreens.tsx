import React from "react";
import type { CaptureDraft, PatientAssignmentDraft } from "../appTypes";
import type { CaptureSession } from "../types";
import { sessionUxState, sessionUxStateCopy, sessionUxStateTone, type SessionUxState } from "../status";
import { Badge, Button, Card, Input } from "../ui";
import { SessionStatusBadge } from "./StatusBadges";

export function PatientsHome({
  sessions,
  onOpenSession,
  onContinueSession,
  onVerifySession,
  onAssignPatient,
}: {
  sessions: CaptureSession[];
  onOpenSession: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onVerifySession: (sessionId: string) => void;
  onAssignPatient: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
}) {
  const [assigningSessionId, setAssigningSessionId] = React.useState("");
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
      badges: patientBadges(patientSessions),
    }));
  }, [sessions]);
  const unassigned = sessions.filter((session) => !session.patientName && !session.patientId);

  return (
    <section className="memory-home" aria-label="Patients">
      <div>
        <p className="eyebrow">Patients</p>
        <h1>Long-term clinical memory</h1>
        <p>Patient timelines, session memory, and unresolved work in one lightweight view.</p>
      </div>
      <section className="memory-section" aria-label="Patients">
        <div className="section-heading">
          <div>
            <h2>Patients</h2>
            <p>Longitudinal memory grouped by confirmed patient context.</p>
          </div>
          <Badge tone={patientGroups.length ? "blue" : "neutral"}>{patientGroups.length}</Badge>
        </div>
        <div className="patient-card-list">
          {patientGroups.map((patient) => (
            <Card className="patient-memory-card" key={patient.patientName}>
              <div className="patient-memory-header">
                <div>
                  <h3>{patient.patientName}</h3>
                  <p>{patient.summary}</p>
                </div>
                <div className="memory-badge-row">
                  {patient.badges.map((badge) => (
                    <Badge key={badge.label} tone={badge.tone}>{badge.label}</Badge>
                  ))}
                </div>
              </div>
              <div className="memory-session-list">
                {patient.sessions.map((session) => (
                  <MemorySessionCard
                    key={session.id}
                    session={session}
                    assigning={assigningSessionId === session.id}
                    onAssignPatient={onAssignPatient}
                    onBeginAssign={setAssigningSessionId}
                    onCancelAssign={() => setAssigningSessionId("")}
                    onContinueSession={onContinueSession}
                    onOpenSession={onOpenSession}
                    onVerifySession={onVerifySession}
                  />
                ))}
              </div>
            </Card>
          ))}
          {patientGroups.length === 0 ? <p>No patient-linked sessions loaded yet.</p> : null}
        </div>
      </section>
      <section className="memory-section" aria-label="Unassigned sessions">
        <div className="section-heading">
          <div>
            <h2>Unassigned sessions</h2>
            <p>Normal capture work that has not been attached to a patient yet.</p>
          </div>
          <Badge tone={unassigned.length ? "amber" : "neutral"}>{unassigned.length}</Badge>
        </div>
        <div className="memory-session-list">
          {unassigned.map((session) => (
            <MemorySessionCard
              key={session.id}
              session={session}
              showAssignAction
              assigning={assigningSessionId === session.id}
              onAssignPatient={onAssignPatient}
              onBeginAssign={setAssigningSessionId}
              onCancelAssign={() => setAssigningSessionId("")}
              onContinueSession={onContinueSession}
              onOpenSession={onOpenSession}
              onVerifySession={onVerifySession}
            />
          ))}
          {unassigned.length === 0 ? <p>No unassigned sessions.</p> : null}
        </div>
      </section>
      {/* TODO(ux-migration): Replace this session-derived grouping with patient timeline data when the Patients API lands. */}
      {/* TODO(ux-migration): Replace mocked patient history summaries with AI-generated longitudinal patient summaries. */}
    </section>
  );
}

function MemorySessionCard({
  session,
  showAssignAction,
  assigning,
  onOpenSession,
  onContinueSession,
  onVerifySession,
  onAssignPatient,
  onBeginAssign,
  onCancelAssign,
}: {
  session: CaptureSession;
  showAssignAction?: boolean;
  assigning?: boolean;
  onOpenSession: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onVerifySession: (sessionId: string) => void;
  onAssignPatient: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onBeginAssign: (sessionId: string) => void;
  onCancelAssign: () => void;
}) {
  const [displayName, setDisplayName] = React.useState(session.patientName || "");
  const [nationalId, setNationalId] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const canAssign = Boolean(displayName.trim()) && !saving;
  return (
    <article className="memory-session-card">
      <div>
        <div className="memory-session-meta">
          <span>{sessionTimestamp(session)}</span>
          <SessionStatusBadge status={session.status} />
        </div>
        <h4>{session.label}</h4>
        <p>{session.summary || "Session details will appear as captures are processed."}</p>
      </div>
      <div className="memory-session-actions">
        <Button onClick={() => onOpenSession(session.id)} size="sm" variant="secondary">Open session</Button>
        <Button onClick={() => onContinueSession(session.id)} size="sm" variant="secondary">Continue</Button>
        <Button disabled={session.status === "verified"} onClick={() => onVerifySession(session.id)} size="sm" variant="secondary">
          {session.status === "verified" ? "Verified" : "Verify"}
        </Button>
        <Button onClick={() => onBeginAssign(session.id)} size="sm" variant="secondary">
          {showAssignAction ? "Assign patient" : "Reassign"}
        </Button>
      </div>
      {assigning ? (
        <form
          className="inline-assignment memory-inline-assignment"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canAssign) return;
            setSaving(true);
            void onAssignPatient(session.id, { displayName: displayName.trim(), nationalId: nationalId.trim() || undefined }).finally(() => {
              setSaving(false);
              onCancelAssign();
            });
          }}
        >
          <Input aria-label="Patient name" onChange={(event) => setDisplayName(event.target.value)} placeholder="Patient name" value={displayName} />
          <Input aria-label="National ID" onChange={(event) => setNationalId(event.target.value)} placeholder="National ID, optional" value={nationalId} />
          <div className="inline-assignment-actions">
            <Button disabled={!canAssign} size="sm" type="submit" variant="secondary">{saving ? "Assigning" : "Assign"}</Button>
            <Button onClick={onCancelAssign} size="sm" type="button" variant="secondary">Cancel</Button>
          </div>
        </form>
      ) : null}
    </article>
  );
}

function patientMemorySummary(sessions: CaptureSession[]) {
  const reviewed = sessions.find((session) => session.status === "verified" && session.summary);
  const recent = sessions.find((session) => session.summary);
  const source = reviewed || recent;
  if (source?.summary) return source.summary;
  return "AI-generated longitudinal summary will appear as patient history accumulates.";
}

function patientBadges(sessions: CaptureSession[]): Array<{ label: string; tone: "neutral" | "blue" | "green" | "amber" | "red" }> {
  const badges: Array<{ label: string; tone: "neutral" | "blue" | "green" | "amber" | "red" }> = [
    { label: `${sessions.length} session${sessions.length === 1 ? "" : "s"}`, tone: "neutral" },
  ];
  const visibleStates: SessionUxState[] = ["failed", "needs_review", "processing", "unassigned", "verified", "capturing"];
  visibleStates.forEach((state) => {
    if (sessions.some((session) => sessionUxState(session.status) === state)) {
      badges.push({ label: sessionUxStateCopy[state], tone: sessionUxStateTone[state] });
    }
  });
  return badges;
}

function sessionTimestamp(session: CaptureSession) {
  return [session.dateLabel, session.time].filter(Boolean).join(" · ") || "Recent session";
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
      {/* TODO(ux-migration): Wire this screen to global backend search across patients, sessions, captures, and extracted findings. */}
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
