import React from "react";
import type { PatientAssignmentTarget } from "../appTypes";
import type { CaptureItem, CaptureSession, Patient, SessionStatus } from "../types";
import { isLocalSessionId } from "../captureModel";
import { assignmentSourceLabel, metadataDisplay, metadataRecord } from "../metadata";
import { Badge, Button, Card, Input, Skeleton, Textarea } from "../ui";
import { CaptureItemCard, SourcePreviewDialog } from "./CaptureWorkflow";
import { SessionStatusBadge } from "./StatusBadges";

/**
 * Buckets sessions by workflow status while keeping search local to the loaded
 * session list.
 */
export function OrganizeHome({
  sessions,
  onOpenSession,
}: {
  sessions: CaptureSession[];
  onOpenSession: (sessionId: string) => void;
}) {
  const [query, setQuery] = React.useState("");
  const drafts = sessions.filter((session) => session.status === "draft");
  const unassigned = sessions.filter((session) => session.status === "unassigned");
  const needsReview = sessions.filter((session) => session.status === "needs_review" || session.status === "reopened" || session.status === "organized");
  const verified = sessions.filter((session) => session.status === "verified");
  const inProgress = sessions.filter((session) => session.status === "processing" || session.status === "reviewing");
  const failed = sessions.filter((session) => session.status === "failed");
  const filtered = sessions.filter((session) =>
    `${session.label} ${session.summary} ${session.patientName ?? ""}`.toLowerCase().includes(query.toLowerCase()),
  );
  const filterByStatuses = (source: CaptureSession[], statuses: SessionStatus[]) =>
    source.filter((session) => statuses.includes(session.status));

  return (
    <section className="organize-home" aria-label="Organize">
      <div>
        <p className="eyebrow">Organize</p>
        <h1>Review when there is a pause</h1>
      </div>
      <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search sessions" value={query} />
      <SessionBucket
        badgeTone={drafts.length ? "blue" : "neutral"}
        className="bucket-drafts"
        emptyCopy="No draft sessions."
        sessions={query ? filtered.filter((session) => session.status === "draft") : drafts}
        summary="Captured sessions that have not been explicitly saved."
        title="Drafts"
        total={drafts.length}
        onOpenSession={onOpenSession}
      />
      <SessionBucket
        badgeTone={unassigned.length ? "amber" : "neutral"}
        className="bucket-unassigned"
        emptyCopy="No unassigned sessions."
        sessions={query ? filtered.filter((session) => session.status === "unassigned") : unassigned}
        summary="Processed sessions waiting for patient assignment."
        title="Unassigned"
        total={unassigned.length}
        onOpenSession={onOpenSession}
      />
      <SessionBucket
        badgeTone={needsReview.length ? "amber" : "neutral"}
        className="bucket-review"
        emptyCopy="No captures waiting here."
        sessions={query ? filterByStatuses(filtered, ["needs_review", "reopened", "organized"]) : needsReview}
        summary="Patient-linked sessions ready for verification."
        title="Needs review"
        total={needsReview.length}
        onOpenSession={onOpenSession}
      />
      <SessionBucket
        badgeTone="green"
        className="bucket-verified"
        emptyCopy="Verified sessions will appear after staff review."
        sessions={query ? filtered.filter((session) => session.status === "verified") : verified}
        summary="Sessions reviewed and accepted by staff."
        title="Verified"
        total={verified.length}
        onOpenSession={onOpenSession}
      />
      <SessionBucket
        badgeTone={inProgress.length ? "blue" : "neutral"}
        className="bucket-processing"
        emptyCopy="No active processing."
        sessions={query ? filterByStatuses(filtered, ["processing", "reviewing"]) : inProgress}
        summary="Backend processing is still underway."
        title="Processing"
        total={inProgress.length}
        onOpenSession={onOpenSession}
      />
      {failed.length ? (
        <SessionBucket
          badgeTone="red"
          className="bucket-failed"
          emptyCopy="No failed sessions match this search."
          sessions={query ? filtered.filter((session) => session.status === "failed") : failed}
          summary="Retry these sessions when the source is available."
          title="Failed"
          total={failed.length}
          onOpenSession={onOpenSession}
        />
      ) : null}
    </section>
  );
}

function SessionBucket({
  title,
  summary,
  total,
  sessions,
  emptyCopy,
  badgeTone,
  className,
  onOpenSession,
}: {
  title: string;
  summary: string;
  total: number;
  sessions: CaptureSession[];
  emptyCopy: string;
  badgeTone: "neutral" | "blue" | "green" | "amber" | "red";
  className: string;
  onOpenSession: (sessionId: string) => void;
}) {
  return (
    <Card className={`session-bucket ${className}`}>
      <div className="section-heading">
        <div>
          <h2>{title}</h2>
          <p>{summary}</p>
        </div>
        <Badge tone={badgeTone}>{total}</Badge>
      </div>
      <div className="stack">
        {sessions.map((session) => (
          <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
        ))}
        {sessions.length === 0 ? <p>{emptyCopy}</p> : null}
      </div>
    </Card>
  );
}

export function SessionRow({ session, onOpen }: { session: CaptureSession; onOpen: () => void }) {
  const sourceLabel = assignmentSourceLabel(session.assignmentSource);
  return (
    <button className="session-row" onClick={onOpen} type="button">
      <div>
        <strong>{session.label}</strong>
        <p>{session.summary}</p>
        <span>
          {session.patientName ?? session.reviewReason ?? "Unassigned"}
          {sourceLabel ? ` - ${sourceLabel}` : ""}
        </span>
      </div>
      <SessionStatusBadge status={session.status} />
      <span className="session-row-arrow" aria-hidden="true">›</span>
    </button>
  );
}

export function PatientAssignmentPanel({
  selectedPatient,
  onSelectPatient,
  onSearch,
  onCreate,
}: {
  selectedPatient: Patient | null;
  onSelectPatient: (patient: Patient | null) => void;
  onSearch: (query: string) => Promise<Patient[]>;
  onCreate: (displayName: string, nationalId?: string) => Promise<Patient>;
}) {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Patient[]>([]);
  const [newName, setNewName] = React.useState("");
  const [newNationalId, setNewNationalId] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setBusy(true);
    onSearch(query)
      .then((patients) => {
        if (!cancelled) setResults(patients);
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, onSearch]);

  const create = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const patient = await onCreate(newName.trim(), newNationalId.trim());
      onSelectPatient(patient);
      setNewName("");
      setNewNationalId("");
      setQuery(patient.displayName);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="patient-assignment-panel">
      <div className="section-heading">
        <div>
          <h3>Patient assignment</h3>
          <p>Search or create a patient while reviewing this session.</p>
        </div>
        {selectedPatient ? <Badge tone="blue">{selectedPatient.displayName}</Badge> : <Badge tone="neutral">Unassigned</Badge>}
      </div>
      <div className="stack">
        <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search patients" value={query} />
        <div className="patient-result-list">
          {results.slice(0, 5).map((patient) => (
            <button
              className={selectedPatient?.id === patient.id ? "patient-result selected" : "patient-result"}
              key={patient.id}
              onClick={() => onSelectPatient(patient)}
              type="button"
            >
              <strong>{patient.displayName}</strong>
              <span>{patient.nationalId || patient.dateOfBirth || patient.phone || patient.email || "No identifiers"}</span>
            </button>
          ))}
          {!busy && results.length === 0 ? <p>No matching patients.</p> : null}
        </div>
        <div className="patient-create-row">
          <Input onChange={(event) => setNewName(event.target.value)} placeholder="New patient name" value={newName} />
          <Input onChange={(event) => setNewNationalId(event.target.value)} placeholder="National ID" value={newNationalId} />
          <Button disabled={busy || !newName.trim()} onClick={() => void create()} variant="secondary">
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}

function metadataValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

export function SessionGeneratedOutputs({
  session,
  selectedPatient,
  onSelectPatient,
  onSearchPatients,
  onCreatePatient,
  onSaveMetadata,
}: {
  session: CaptureSession;
  selectedPatient: Patient | null;
  onSelectPatient: (patient: Patient | null) => void;
  onSearchPatients: (query: string) => Promise<Patient[]>;
  onCreatePatient: (displayName: string, nationalId?: string) => Promise<Patient>;
  onSaveMetadata: (sessionId: string, extractedMetadata: Record<string, unknown>) => Promise<void>;
}) {
  const extracted = metadataRecord(session.extractedMetadata);
  const patientInformation = metadataRecord(extracted.patient_information);
  const missingFields = Array.isArray(patientInformation.missing_fields)
    ? patientInformation.missing_fields.map(String).filter(Boolean)
    : [];
  const clinicalMetadata = metadataRecord(extracted.clinical_metadata);
  const isStale = extracted.generated_output_stale === true;
  const [patientName, setPatientName] = React.useState(metadataValue(patientInformation.full_name));
  const [patientNationalId, setPatientNationalId] = React.useState(metadataValue(patientInformation.national_id));
  const [metadataDraft, setMetadataDraft] = React.useState(JSON.stringify(session.extractedMetadata || {}, null, 2));
  const [metadataError, setMetadataError] = React.useState("");
  const [savingMetadata, setSavingMetadata] = React.useState(false);

  React.useEffect(() => {
    const nextExtracted = metadataRecord(session.extractedMetadata);
    const nextPatientInformation = metadataRecord(nextExtracted.patient_information);
    setPatientName(metadataValue(nextPatientInformation.full_name));
    setPatientNationalId(metadataValue(nextPatientInformation.national_id));
    setMetadataDraft(JSON.stringify(session.extractedMetadata || {}, null, 2));
    setMetadataError("");
  }, [session.id, session.extractedMetadata]);

  const saveMetadata = async () => {
    let parsed: Record<string, unknown>;
    try {
      const value = JSON.parse(metadataDraft || "{}") as unknown;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Metadata must be an object");
      parsed = value as Record<string, unknown>;
    } catch {
      setMetadataError("Metadata must be valid JSON object syntax.");
      return;
    }
    const nextPatientInformation = {
      ...metadataRecord(parsed.patient_information),
      full_name: patientName.trim() || undefined,
      national_id: patientNationalId.trim() || undefined,
    };
    const nextMetadata = {
      ...parsed,
      patient_information: nextPatientInformation,
    };
    setSavingMetadata(true);
    try {
      await onSaveMetadata(session.id, nextMetadata);
    } finally {
      setSavingMetadata(false);
    }
  };

  return (
    <div className="session-output-grid">
      <Card className="session-report-card">
        <div className="section-heading">
          <div>
            <h2>Session report</h2>
            <p>{session.reportTemplateKey ? `Template: ${session.reportTemplateKey}` : "Template output appears after saving."}</p>
          </div>
          <Badge tone={session.generatedReport ? "blue" : "neutral"}>{session.generatedReport ? "Generated" : "Waiting"}</Badge>
        </div>
        {isStale ? <p className="metadata-warning">Generated output is stale because new capture material was added.</p> : null}
        <pre className="session-report">{session.generatedReport || "Save the draft session to generate the report."}</pre>
      </Card>
      <Card>
        <div className="section-heading">
          <div>
            <h2>Metadata</h2>
            <p>Patient fields plus flexible extracted metadata.</p>
          </div>
          <Badge tone={missingFields.length ? "amber" : patientInformation.status === "complete" ? "green" : "neutral"}>
            {missingFields.length ? "Missing patient info" : patientInformation.status === "complete" ? "Complete" : "Pending"}
          </Badge>
        </div>
        <div className="editable-metadata">
          <label className="field-label">
            Patient full name
            <Input onChange={(event) => setPatientName(event.target.value)} value={patientName} />
          </label>
          <label className="field-label">
            Patient national ID
            <Input onChange={(event) => setPatientNationalId(event.target.value)} value={patientNationalId} />
          </label>
        </div>
        <PatientAssignmentPanel
          onCreate={onCreatePatient}
          onSearch={onSearchPatients}
          onSelectPatient={onSelectPatient}
          selectedPatient={selectedPatient}
        />
        <div className="metadata-list compact-metadata">
          <div>
            <span>Visit type</span>
            <strong>{metadataDisplay(clinicalMetadata.visit_type) || "Pending"}</strong>
          </div>
          <div>
            <span>Body area</span>
            <strong>{metadataDisplay(clinicalMetadata.body_area) || "Pending"}</strong>
          </div>
        </div>
        <label className="field-label raw-metadata-editor">
          Extracted metadata JSON
          <Textarea onChange={(event) => setMetadataDraft(event.target.value)} rows={10} value={metadataDraft} />
        </label>
        {missingFields.length ? <p className="metadata-warning">Missing: {missingFields.join(", ")}</p> : null}
        {metadataError ? <p className="metadata-warning">{metadataError}</p> : null}
        <Button disabled={savingMetadata || isLocalSessionId(session.id)} onClick={() => void saveMetadata()} variant="secondary">
          Save metadata
        </Button>
      </Card>
    </div>
  );
}

/**
 * Coordinates session-level and capture-level patient assignment within the
 * review dialog.
 */
export function SessionDetail({
  session,
  onAddCapture,
  onVerifySession,
  onRetrySession,
  onSaveSession,
  onSaveMetadata,
  onUpdateTitle,
  onLoadCaptures,
  onSearchPatients,
  onCreatePatient,
  onAssignSessionPatient,
  onAssignCapturePatient,
  onResolveFile,
}: {
  session?: CaptureSession;
  onAddCapture: () => void;
  onVerifySession: (sessionId: string) => Promise<void>;
  onRetrySession: (sessionId: string) => void;
  onSaveSession: (sessionId: string) => void;
  onSaveMetadata: (sessionId: string, extractedMetadata: Record<string, unknown>) => Promise<void>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
  onLoadCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  onSearchPatients: (query: string) => Promise<Patient[]>;
  onCreatePatient: (displayName: string, nationalId?: string) => Promise<Patient>;
  onAssignSessionPatient: (sessionId: string, target: PatientAssignmentTarget) => Promise<void>;
  onAssignCapturePatient: (sessionId: string, captureId: string, target: PatientAssignmentTarget) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [selectedPatient, setSelectedPatient] = React.useState<Patient | null>(null);
  const [assigning, setAssigning] = React.useState("");
  const [titleDraft, setTitleDraft] = React.useState(session?.label || "");
  const [savingTitle, setSavingTitle] = React.useState(false);
  const [verifying, setVerifying] = React.useState(false);

  React.useEffect(() => {
    if (!session || session.items.length || isLocalSessionId(session.id)) return;
    void onLoadCaptures(session.id);
  }, [session, onLoadCaptures]);

  React.useEffect(() => {
    setSelectedPatient(session?.patientId ? { id: session.patientId, displayName: session.patientName || "Selected patient" } : null);
  }, [session?.id, session?.patientId, session?.patientName]);

  React.useEffect(() => {
    setTitleDraft(session?.label || "");
  }, [session?.id, session?.label]);

  if (!session) {
    return (
      <section className="organize-home">
        <Skeleton className="h-16" />
      </section>
    );
  }

  const canVerify = session.status === "unassigned" || session.status === "needs_review" || session.status === "organized";
  const canSave = session.status === "draft" || session.status === "reopened";

  return (
    <section className="session-detail">
      <Card className="review-card">
        <p className="eyebrow">Session review</p>
        <div className="patient-create-row">
          <Input onChange={(event) => setTitleDraft(event.target.value)} value={titleDraft} />
          <Button
            disabled={savingTitle || !titleDraft.trim() || titleDraft.trim() === session.label || isLocalSessionId(session.id)}
            onClick={() => {
              setSavingTitle(true);
              void onUpdateTitle(session.id, titleDraft.trim()).finally(() => setSavingTitle(false));
            }}
            variant="secondary"
          >
            Save title
          </Button>
        </div>
        <p>{session.summary}</p>
        <div className="detail-meta">
          <SessionStatusBadge status={session.status} />
          <span>
            {session.patientName ?? "No patient selected"}
            {assignmentSourceLabel(session.assignmentSource) ? ` - ${assignmentSourceLabel(session.assignmentSource)}` : ""}
          </span>
        </div>
        <div className="action-row">
          {canVerify ? (
            <Button
              disabled={verifying || isLocalSessionId(session.id)}
              onClick={() => {
                setVerifying(true);
                void onVerifySession(session.id).finally(() => setVerifying(false));
              }}
            >
              Verify
            </Button>
          ) : null}
          <Button disabled={isLocalSessionId(session.id)} onClick={onAddCapture} variant="secondary">
            Add capture
          </Button>
          {canSave ? (
            <Button disabled={isLocalSessionId(session.id)} onClick={() => onSaveSession(session.id)} variant="secondary">
              {isLocalSessionId(session.id) ? "Syncing first" : "Save session"}
            </Button>
          ) : null}
          {session.status === "failed" ? (
            <Button disabled={isLocalSessionId(session.id)} onClick={() => onRetrySession(session.id)} variant="danger">
              Retry
            </Button>
          ) : null}
        </div>
      </Card>
      <SessionGeneratedOutputs
        onCreatePatient={onCreatePatient}
        onSaveMetadata={onSaveMetadata}
        onSearchPatients={onSearchPatients}
        onSelectPatient={setSelectedPatient}
        selectedPatient={selectedPatient}
        session={session}
      />
      <div className="action-row">
        <Button
          disabled={!selectedPatient || assigning === "session"}
          onClick={() => {
            if (!selectedPatient) return;
            setAssigning("session");
            void onAssignSessionPatient(session.id, {
              patientId: selectedPatient.id,
              patientName: selectedPatient.displayName,
              source: "staff",
            }).finally(() => setAssigning(""));
          }}
        >
          Assign session
        </Button>
        {session.patientId ? (
          <Button
            disabled={assigning === "session-clear"}
            onClick={() => {
              setAssigning("session-clear");
              void onAssignSessionPatient(session.id, { patientId: null, source: "staff" }).finally(() => setAssigning(""));
            }}
            variant="secondary"
          >
            Clear session patient
          </Button>
        ) : null}
      </div>
      <details className="captures-expander">
        <summary>
          <span>Captures</span>
          <Badge tone={session.items.length ? "blue" : "neutral"}>{session.items.length}</Badge>
        </summary>
        <div className="feed-focus">
          {session.items.map((item) => (
            <div className="capture-assignment-row" key={item.id}>
              <CaptureItemCard item={item} onOpen={() => setSelectedCapture(item)} onResolveFile={onResolveFile} />
              <div className="assignment-actions">
                <small>
                  {item.patientName || item.patientId || "No capture patient"}
                  {assignmentSourceLabel(item.assignmentSource) ? ` - ${assignmentSourceLabel(item.assignmentSource)}` : ""}
                </small>
                <Button
                  disabled={!selectedPatient || assigning === item.id}
                  onClick={() => {
                    if (!selectedPatient) return;
                    setAssigning(item.id);
                    void onAssignCapturePatient(session.id, item.id, {
                      patientId: selectedPatient.id,
                      patientName: selectedPatient.displayName,
                      source: "staff",
                    }).finally(() => setAssigning(""));
                  }}
                  size="sm"
                  variant={item.patientId ? "secondary" : "default"}
                >
                  {item.patientId ? "Override capture" : "Assign capture"}
                </Button>
              </div>
            </div>
          ))}
          {session.items.length === 0 ? <p>No captures loaded for this session yet.</p> : null}
        </div>
      </details>
      <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
    </section>
  );
}
