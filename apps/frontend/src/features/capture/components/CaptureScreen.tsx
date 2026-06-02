import React from "react";
import type { PatientAssignmentDraft, PatientSummary } from "../../../domain/appTypes";
import type {
  CaptureItem,
  CaptureSession,
  SessionProcessingStatus,
  StructuredPatientInformation,
} from "../../../domain/types";
import { isLocalSessionId } from "../captureModel";
import { assignmentSourceLabel, metadataDisplay, metadataRecord, metadataText } from "../metadata";
import { sessionUxState } from "../../../domain/status";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { SourcePreviewDialog, CaptureRawPreview } from "./SourcePreview";

export function CaptureScreen({
  activeSession,
  onSaveSession,
  onResolveFile,
  onUpdateTitle,
  onRenameCapture,
  onUpdateCaptureCaption,
  onUpdateCaptureTranscript,
  onDeleteCapture,
  mode = "active",
  onBack,
  backLabel = "Clinical Memory",
  onResumeCapture,
  assignmentOpen,
  onAssignPatient,
  onCloseAssignment,
  onSearchPatients,
  onVerifySession,
  onStartNewSession,
}: {
  activeSession: CaptureSession | null;
  onSaveSession: (sessionId: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
  onRenameCapture?: (sessionId: string, captureId: string, title: string) => Promise<void>;
  onUpdateCaptureCaption?: (sessionId: string, captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateCaptureTranscript?: (sessionId: string, captureId: string, transcript: string) => Promise<CaptureItem | null>;
  onDeleteCapture?: (sessionId: string, captureId: string) => Promise<void>;
  mode?: "active" | "historical";
  onBack?: () => void;
  backLabel?: string;
  onResumeCapture?: () => void;
  assignmentOpen?: boolean;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onCloseAssignment?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onVerifySession?: (sessionId: string, verified?: boolean) => Promise<void>;
  onStartNewSession?: () => void;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [verifying, setVerifying] = React.useState(false);
  const [reportView, setReportView] = React.useState<"draft" | "structured">("draft");
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const isHistorical = mode === "historical";
  const processingState = activeSession?.processingStatus?.state;
  const hasCaptures = Boolean(activeSession?.items.length);
  const isGenerating = processingState === "processing" || activeSession?.report?.status === "generating";
  const hasFreshGeneratedReport = Boolean(
    activeSession &&
      !activeSession.report?.isStale &&
      (activeSession.report?.status === "processed" || activeSession.report?.status === "verified" || activeSession.status === "verified"),
  );
  const canSaveSession = activeSession
    ? !isHistorical && !isLocalSessionId(activeSession.id) && !isGenerating && !hasFreshGeneratedReport
    : false;
  const reportState = workspaceReportState(activeSession);
  const selectedReportView = reportView;
  const sessionTitle = sessionSummaryTitle(activeSession, isHistorical);
  const patientName = sessionPatientName(activeSession);
  const captureCount = activeSession?.items.length || 0;
  const captureCountLabel = `${captureCount} capture${captureCount === 1 ? "" : "s"}`;
  const sessionStatusChip = sessionSummaryStatusChip(activeSession);
  const sessionCreatedLabel = sessionSummaryCreatedLabel(activeSession);
  const sessionUpdatedLabel = sessionSummaryUpdatedLabel(activeSession);
  const previousGeneratingRef = React.useRef(isGenerating);

  React.useEffect(() => {
    setReportView("draft");
  }, [activeSession?.id]);

  React.useEffect(() => {
    if (!hasCaptures && reportView === "structured") setReportView("draft");
  }, [hasCaptures, reportView]);

  React.useEffect(() => {
    if (activeSession?.report?.isStale) setReportView("draft");
  }, [activeSession?.report?.isStale]);

  React.useEffect(() => {
    if (isGenerating) setReportView("structured");
  }, [isGenerating]);

  React.useEffect(() => {
    const wasGenerating = previousGeneratingRef.current;
    previousGeneratingRef.current = isGenerating;
    if (wasGenerating && !isGenerating && activeSession?.report?.status === "processed") {
      setReportView("structured");
      window.requestAnimationFrame(() => {
        document.querySelector(".workspace-report-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, [activeSession?.report?.status, isGenerating]);

  React.useEffect(() => {
    if (!activeSession) previousCaptureCountRef.current = 0;
  }, [activeSession]);

  React.useEffect(() => {
    const currentCaptureCount = activeSession?.items.length || 0;
    if (!currentCaptureCount) {
      previousCaptureCountRef.current = 0;
      return;
    }
    const previousCaptureCount = previousCaptureCountRef.current;
    previousCaptureCountRef.current = currentCaptureCount;
    if (currentCaptureCount > previousCaptureCount && previousCaptureCount === 0) {
      window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "instant" }));
    }
  }, [activeSession?.items.length]);

  return (
    <section className="capture-current session-workspace" aria-label={isHistorical ? "Historical session review" : "Active session workspace"}>
      {onBack ? (
        <button className="context-back-button" onClick={onBack} type="button">
          <BackIcon />
          {backLabel}
        </button>
      ) : null}
      <div className="active-session-summary">
        <div className="session-summary-copy">
          <div className="session-summary-heading">
            <h1>{sessionTitle}</h1>
            <span className={`status-chip ${sessionStatusChip.tone} ${sessionStatusChip.checked ? "checked" : ""}`}>
              <span aria-hidden="true" />
              {sessionStatusChip.label}
            </span>
          </div>
          <p>{sessionCreatedLabel} <span aria-hidden="true">&bull;</span> {captureCountLabel} <span aria-hidden="true">&bull;</span> {sessionUpdatedLabel}</p>
        </div>
        <div className="workspace-header-actions">
          {isHistorical && onResumeCapture ? (
            <Button disabled={!activeSession} onClick={onResumeCapture} size="sm" type="button" variant="secondary">
              Add capture
            </Button>
          ) : null}
          {!isHistorical && onStartNewSession ? (
            <Button className="current-new-session" onClick={onStartNewSession} size="sm" type="button" variant="secondary">
              <span aria-hidden="true">+</span>
              New session
            </Button>
          ) : null}
        </div>
      </div>
      <Card className="patient-context-card">
        <span className="patient-context-avatar" aria-hidden="true">
          <PatientIcon />
        </span>
        <div>
          <strong>{patientName}</strong>
          <p>{activeSession?.assignmentSource ? assignmentSourceLabel(activeSession.assignmentSource) : "Assigned manually"}</p>
        </div>
        {onAssignPatient ? (
          <Button className="edit-patient-button" onClick={onCloseAssignment} size="sm" type="button" variant="secondary">
            <EditIcon />
            Edit patient
          </Button>
        ) : null}
      </Card>
      <Card className={`workspace-report-card ${isGenerating ? "processing" : ""}`}>
        <div className="report-heading">
          <div className="report-title-lockup">
            <span className="report-title-icon" aria-hidden="true">
              <ClipboardIcon />
            </span>
            <h2>Clinical report</h2>
          </div>
          <div className="report-heading-actions">
            {!isHistorical ? (
              <Button
                className={`report-generate-button ${isGenerating ? "processing" : ""}`}
                disabled={!canSaveSession || !activeSession}
                title={hasFreshGeneratedReport ? "Add a capture or change the patient to generate again." : undefined}
                onClick={() => {
                  if (activeSession) {
                    setReportView("structured");
                    onSaveSession(activeSession.id);
                  }
                }}
                size="sm"
                type="button"
              >
                {activeSession && isLocalSessionId(activeSession.id)
                  ? "Saving first"
                  : processingState === "processing"
                    ? "Generating"
                    : "Generate"}
              </Button>
            ) : null}
          </div>
        </div>
        <div className="report-toolbar">
          <div className="report-toolbar-actions">
            <div className="report-view-switch" aria-label="Report view">
              <button className={selectedReportView === "draft" ? "active" : ""} onClick={() => setReportView("draft")} type="button">
                Live draft
              </button>
              <button
                className={selectedReportView === "structured" ? "active" : ""}
                disabled={!hasCaptures}
                onClick={() => setReportView("structured")}
                title={!hasCaptures ? "Create a capture first to open the structured report." : undefined}
                type="button"
              >
                Structured report
              </button>
            </div>
          </div>
        </div>
        {assignmentOpen && activeSession && onAssignPatient ? (
          <PatientAssignmentSheet
            session={activeSession}
            onAssign={(draft) => onAssignPatient(activeSession.id, draft)}
            onCancel={onCloseAssignment}
            onSearchPatients={onSearchPatients}
          />
        ) : null}
        <div className={`workspace-report-body ${reportState.kind}`}>
          {selectedReportView === "structured" ? (
            <StructuredReportView
              session={activeSession}
              onResolveFile={onResolveFile}
            />
          ) : (
            <LiveDraftReport
              session={activeSession}
              onDeleteCapture={onDeleteCapture}
              onOpenCapture={setSelectedCapture}
              onRenameCapture={onRenameCapture}
              onResolveFile={onResolveFile}
            />
          )}
        </div>
        <div className="workspace-report-footer">
          <div className="workspace-report-footer-copy">
            {activeSession?.processingStatus?.state === "processing" ? <span>Structured report is updating from the live draft</span> : null}
          </div>
          {onVerifySession ? (
            <button
              aria-checked={activeSession?.status === "verified"}
              className="report-verify-check"
              disabled={!activeSession || isLocalSessionId(activeSession.id) || verifying || isGenerating}
              onClick={() => {
                if (!activeSession) return;
                setVerifying(true);
                void onVerifySession(activeSession.id, activeSession.status !== "verified").finally(() => setVerifying(false));
              }}
              role="checkbox"
              type="button"
            >
              <span aria-hidden="true" />
              {activeSession?.status === "verified" ? "Verified" : verifying ? "Verifying" : "Verify structured report"}
            </button>
          ) : null}
        </div>
      </Card>
      <SourcePreviewDialog
        item={selectedCapture}
        onClose={() => setSelectedCapture(null)}
        onResolveFile={onResolveFile}
        onUpdateCaption={
          activeSession && onUpdateCaptureCaption
            ? async (captureId, caption) => {
                const updated = await onUpdateCaptureCaption(activeSession.id, captureId, caption);
                if (updated) setSelectedCapture(updated);
                return updated;
              }
            : undefined
        }
        onUpdateTranscript={
          activeSession && onUpdateCaptureTranscript
            ? async (captureId, transcript) => {
                const updated = await onUpdateCaptureTranscript(activeSession.id, captureId, transcript);
                if (updated) setSelectedCapture(updated);
                return updated;
              }
            : undefined
        }
      />
    </section>
  );
}

function PatientIcon() {
  return (
    <svg viewBox="0 0 40 40" focusable="false" aria-hidden="true">
      <path d="M20 18.2a6.2 6.2 0 1 0 0-12.4 6.2 6.2 0 0 0 0 12.4Z" />
      <path d="M9.5 33.5v-3.2c0-5.3 4.7-9.6 10.5-9.6s10.5 4.3 10.5 9.6v3.2H9.5Z" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m15 5-7 7 7 7" />
    </svg>
  );
}

function ClipboardIcon() {
  return (
    <svg viewBox="0 0 40 40" focusable="false" aria-hidden="true">
      <path d="M15 7.5h10v5H15v-5Z" />
      <path d="M11 10.5H8.5v24h23v-24H29" />
      <path d="M14 19h12" />
      <path d="M14 25h8" />
      <path d="M25.5 24.5l2 2 4-5" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M4.5 17.8 4 21l3.2-.5 10.9-10.9-2.7-2.7L4.5 17.8Z" />
      <path d="m15.4 6.9 1.4-1.4a1.9 1.9 0 0 1 2.7 2.7l-1.4 1.4" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="6.7" />
      <path d="m16 16 4.2 4.2" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M7 3.8v3.4M17 3.8v3.4M4.5 9.2h15" />
      <rect x="4.5" y="5.6" width="15" height="14.2" rx="2.2" />
    </svg>
  );
}

function CameraSummaryIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M8.3 7.4 9.8 5.5h4.4l1.5 1.9h2.1a2 2 0 0 1 2 2v7.2a2 2 0 0 1-2 2H6.2a2 2 0 0 1-2-2V9.4a2 2 0 0 1 2-2h2.1Z" />
      <circle cx="12" cy="13" r="3" />
    </svg>
  );
}

function ClinicianIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="12" cy="7.8" r="3.2" />
      <path d="M6.4 20.2v-2.4c0-3 2.5-5.4 5.6-5.4s5.6 2.4 5.6 5.4v2.4" />
    </svg>
  );
}

function ClinicIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M5.4 20V7.3h6.1V20M11.5 20V4.6h7.1V20M3.8 20h16.4M8.5 10.3h.1M8.5 13.5h.1M8.5 16.7h.1M14.7 8h.1M14.7 11.2h.1M14.7 14.4h.1M14.7 17.6h.1" />
    </svg>
  );
}

function IdCardIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
      <circle cx="9" cy="10.4" r="1.8" />
      <path d="M6.3 16c.5-1.8 1.5-2.7 2.7-2.7s2.2.9 2.7 2.7M14 10h3.5M14 14h3.5" />
    </svg>
  );
}

function AddPatientIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="10" cy="7.8" r="3" />
      <path d="M4.4 19.8v-2.1c0-2.8 2.5-5.1 5.6-5.1 1.2 0 2.4.4 3.3 1M17.8 12.5v6M14.8 15.5h6" />
    </svg>
  );
}

export function PatientAssignmentSheet({
  session,
  onAssign,
  onCancel,
  onSearchPatients,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onCancel?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [newPatientNationalId, setNewPatientNationalId] = React.useState("");
  const [apiMatches, setApiMatches] = React.useState<PatientSummary[]>([]);
  const [searching, setSearching] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const trimmedQuery = query.trim();
  const currentPatient = React.useMemo(() => currentSessionPatient(session), [session]);
  const currentAssignedPatient = currentPatient[0] || null;
  const localMatches = React.useMemo(() => filterPatientMatches(currentPatient, trimmedQuery), [currentPatient, trimmedQuery]);
  const matches = mergePatientMatches(localMatches, apiMatches).slice(0, 3);
  const canCreate = Boolean(trimmedQuery) && !saving;
  const summaryItems = assignmentSessionSummary(session);

  React.useEffect(() => {
    if (!onSearchPatients) {
      setApiMatches([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    void onSearchPatients(trimmedQuery)
      .then((patients) => {
        if (!cancelled) setApiMatches(patients);
      })
      .catch(() => {
        if (!cancelled) setApiMatches([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onSearchPatients, trimmedQuery]);

  const assignDraft = (draft: PatientAssignmentDraft) => {
    if (saving) return;
    setSaving(true);
    void onAssign(draft).finally(() => setSaving(false));
  };

  return (
    <div className="assignment-scrim" role="presentation">
      <section aria-labelledby="assignment-sheet-title" aria-modal="true" className="assignment-sheet" role="dialog">
        <div className="assignment-sheet-handle" aria-hidden="true" />
        <div className="assignment-sheet-header">
          <h2 id="assignment-sheet-title">{currentAssignedPatient ? "Change patient" : "Assign patient"}</h2>
          {onCancel ? (
            <Button aria-label="Close patient assignment" onClick={onCancel} size="sm" type="button" variant="ghost">
              <span aria-hidden="true">x</span>
            </Button>
          ) : null}
        </div>
        <div className="assignment-session-summary" aria-label="Current session summary">
          {summaryItems.map((item) => (
            <div className="assignment-summary-item" key={item.label}>
              <span className="assignment-summary-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>
                <strong>{item.value}</strong>
                <small>{item.label}</small>
              </span>
            </div>
          ))}
        </div>
        {currentAssignedPatient ? (
          <section className="assignment-current-patient" aria-label="Currently assigned patient">
            <span className="assignment-patient-avatar" aria-hidden="true">
              <PatientIcon />
            </span>
            <div className="assignment-patient-copy">
              <small>Currently assigned</small>
              <strong>{currentAssignedPatient.displayName}</strong>
              <span>{patientIdentifierLabel(currentAssignedPatient)}</span>
            </div>
          </section>
        ) : null}
        <label className="assignment-search-field">
          <span aria-hidden="true">
            <SearchIcon />
          </span>
          <Input
            className="assignment-search-input"
            aria-label="Search patients"
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by patient name, phone, or national ID"
            value={query}
          />
        </label>
        <div className="assignment-section-heading">
          <h3>Suggested matches</h3>
          {searching ? <span>Searching...</span> : null}
        </div>
        <div className="assignment-results" aria-live="polite">
          {matches.length ? (
            matches.map((patient) => {
              const alreadyAssigned = currentAssignedPatient ? samePatientSummary(patient, currentAssignedPatient) : false;
              return (
              <article className={`assignment-patient-row ${alreadyAssigned ? "assigned" : ""}`} key={patient.id}>
                <span className="assignment-patient-avatar" aria-hidden="true">
                  <PatientIcon />
                </span>
                <div className="assignment-patient-copy">
                  <strong>{patient.displayName}</strong>
                  <span>{patientIdentifierLabel(patient)}</span>
                  <small>{alreadyAssigned ? "Currently assigned to this visit" : `Last visit: ${formatLastVisit(patient.lastVisit)}`}</small>
                </div>
                <Button
                  disabled={saving || alreadyAssigned}
                  onClick={() =>
                    assignDraft({
                      patientId: patient.id,
                      displayName: patient.displayName,
                      nationalId: patient.nationalId || undefined,
                    })
                  }
                  size="sm"
                  type="button"
                  variant="secondary"
                >
                  {alreadyAssigned ? "Assigned" : saving ? "Saving" : "Select"}
                </Button>
              </article>
              );
            })
          ) : (
            <p className="assignment-empty">No suggested matches yet.</p>
          )}
        </div>
        <div className="assignment-divider"><span>or</span></div>
        <section className="assignment-create-panel" aria-label="Create a new patient">
          <h3>Create a new patient</h3>
          <label className="assignment-national-id-field">
            <span aria-hidden="true">
              <IdCardIcon />
            </span>
            <Input
              aria-label="New patient national ID"
              onChange={(event) => setNewPatientNationalId(event.target.value)}
              placeholder="National ID (optional)"
              value={newPatientNationalId}
            />
          </label>
          <Button
            className="assignment-create-button"
            disabled={!canCreate}
            onClick={() => assignDraft({ displayName: trimmedQuery, nationalId: newPatientNationalId.trim() || undefined })}
            type="button"
          >
            <AddPatientIcon />
            {saving ? "Creating patient" : "Create new patient"}
          </Button>
        </section>
      </section>
    </div>
  );
}

function assignmentSessionSummary(session: CaptureSession) {
  const metadata = metadataRecord(session.extractedMetadata);
  const clinical = metadataRecord(metadata.clinical_metadata);
  const sessionDate = formatAssignmentDate(session);
  return [
    { icon: <CalendarIcon />, value: sessionDate.date, label: sessionDate.time },
    { icon: <CameraSummaryIcon />, value: `${session.items.length}`, label: `capture${session.items.length === 1 ? "" : "s"}` },
    {
      icon: <ClinicianIcon />,
      value: metadataDisplay(clinical.clinician || metadata.clinician || metadata.doctor) || "AesMem clinician",
      label: "Clinician",
    },
    { icon: <ClinicIcon />, value: session.report?.template?.clinic?.name || "Clinic", label: "Clinic" },
  ];
}

function formatAssignmentDate(session: CaptureSession) {
  const source = session.report?.updatedAt || session.processingStatus?.updatedAt || session.time;
  const parsed = source ? new Date(source) : null;
  if (parsed && !Number.isNaN(parsed.getTime())) {
    return {
      date: new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(parsed),
      time: new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(parsed),
    };
  }
  return { date: session.dateLabel || "Current session", time: session.time || "Now" };
}

function currentSessionPatient(session: CaptureSession) {
  if (!session.patientName && !session.patientId) return [];
  return [
    {
      id: session.patientId || "current-session-patient",
      displayName: session.patientName || "Assigned patient",
      nationalId: session.patientId || null,
      lastVisit: session.report?.updatedAt || null,
    },
  ];
}

function filterPatientMatches(patients: PatientSummary[], query: string) {
  if (!query) return patients;
  const normalizedQuery = query.toLowerCase();
  return patients.filter((patient) =>
    [patient.displayName, patient.nationalId || "", patient.phone || ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
  );
}

function mergePatientMatches(primary: PatientSummary[], secondary: PatientSummary[]) {
  const seen = new Set<string>();
  return [...primary, ...secondary].filter((patient) => {
    const key = patient.id || `${patient.displayName}:${patient.nationalId || patient.phone || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function samePatientSummary(left: PatientSummary, right: PatientSummary) {
  if (left.id && right.id && left.id === right.id) return true;
  const leftName = left.displayName.trim().toLowerCase();
  const rightName = right.displayName.trim().toLowerCase();
  if (leftName && rightName && leftName === rightName) return true;
  return Boolean(left.nationalId && right.nationalId && left.nationalId === right.nationalId);
}

function patientIdentifierLabel(patient: PatientSummary) {
  if (patient.phone) return maskPhone(patient.phone);
  if (patient.nationalId) return `ID: ${maskIdentifier(patient.nationalId)}`;
  return "Existing patient";
}

function maskIdentifier(value: string) {
  const digits = value.replace(/\D/g, "");
  if (digits.length < 8) return value;
  return `${digits.slice(0, 4)}....${digits.slice(-4)}`;
}

function maskPhone(value: string) {
  const visible = value.slice(0, Math.max(0, value.length - 4));
  return `${visible}....`;
}

function formatLastVisit(value?: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function LiveDraftReport({
  session,
  onDeleteCapture,
  onOpenCapture,
  onRenameCapture,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onDeleteCapture?: (sessionId: string, captureId: string) => Promise<void>;
  onOpenCapture: (item: CaptureItem) => void;
  onRenameCapture?: (sessionId: string, captureId: string, title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [openMenuId, setOpenMenuId] = React.useState("");

  React.useEffect(() => {
    setOpenMenuId("");
  }, [session?.id]);

  if (!session?.items.length) {
    return (
      <div className="live-draft-empty">
        <h3>Start the draft with a capture</h3>
        <p>Audio, photos, and notes will appear here immediately as the session develops.</p>
      </div>
    );
  }

  return (
    <div className="live-draft">
      {session.items.map((item, index) => (
        <LiveDraftCaptureItem
          item={item}
          key={item.sourceUrl || item.id}
          menuOpen={openMenuId === item.id}
          onCloseMenu={() => setOpenMenuId("")}
          onDeleteCapture={onDeleteCapture ? () => onDeleteCapture(session.id, item.id) : undefined}
          onOpenCapture={() => onOpenCapture(item)}
          onRenameCapture={onRenameCapture ? (title) => onRenameCapture(session.id, item.id, title) : undefined}
          onResolveFile={onResolveFile}
          onToggleMenu={() => setOpenMenuId((current) => (current === item.id ? "" : item.id))}
          sequence={index + 1}
        />
      ))}
      {session.processingStatus?.state === "processing" ? (
        <div className="live-draft-processing">AesMem is preparing the structured report. The live draft remains reviewable while you wait.</div>
      ) : null}
    </div>
  );
}

function LiveDraftCaptureItem({
  item,
  menuOpen,
  onCloseMenu,
  onDeleteCapture,
  onOpenCapture,
  onRenameCapture,
  onResolveFile,
  onToggleMenu,
  sequence,
}: {
  item: CaptureItem;
  menuOpen: boolean;
  onCloseMenu: () => void;
  onDeleteCapture?: () => Promise<void>;
  onOpenCapture: () => void;
  onRenameCapture?: (title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onToggleMenu: () => void;
  sequence: number;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  const isPhoto = item.type === "photo";
  const title = captureDraftLabel(item, sequence);
  const generatedText = generatedTextForReport(item);
  const fallbackText = draftCaptureText(item);
  const decoratedNoteText = noteDecoratedText(item) || generatedText || fallbackText;
  const textAttribution = captureTextAttribution(item);
  const [busy, setBusy] = React.useState(false);

  const rename = () => {
    if (!onRenameCapture || busy) return;
    const nextTitle = window.prompt("Rename capture", title);
    if (!nextTitle?.trim() || nextTitle.trim() === title) return;
    setBusy(true);
    void onRenameCapture(nextTitle.trim()).finally(() => {
      setBusy(false);
      onCloseMenu();
    });
  };

  const remove = () => {
    if (!onDeleteCapture || busy) return;
    if (!window.confirm(`Delete ${title}? The structured report will move back to draft.`)) return;
    setBusy(true);
    void onDeleteCapture().finally(() => {
      setBusy(false);
      onCloseMenu();
    });
  };

  return (
    <article
      className={`live-draft-capture ${item.type}`}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest("audio, button, input, textarea, summary, details, .capture-item-menu")) return;
        onOpenCapture();
      }}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        if ((event.target as HTMLElement).closest("button, input, textarea, summary")) return;
        event.preventDefault();
        onOpenCapture();
      }}
      role="button"
      tabIndex={0}
    >
      <div className="live-draft-marker" aria-hidden="true">
        <CaptureTimelineIcon type={item.type} />
      </div>
      <div className="live-draft-capture-content">
        <header className="live-draft-capture-header">
          <div className="live-draft-capture-meta">
            <div className="live-draft-title-row">
              <h3>{title}</h3>
              <time>{item.time}</time>
            </div>
            <CaptureInlineStatus status={item.status} />
          </div>
          <button
            aria-expanded={menuOpen}
            aria-label={`Capture settings for ${title}`}
            className="live-draft-overflow"
            onClick={(event) => {
              event.stopPropagation();
              onToggleMenu();
            }}
            type="button"
          >
            <span aria-hidden="true" />
          </button>
          {menuOpen ? (
            <div className="capture-item-menu">
              <button disabled={!onRenameCapture || busy} onClick={rename} type="button">
                Rename
              </button>
              <button className="danger" disabled={!onDeleteCapture || busy} onClick={remove} type="button">
                Delete
              </button>
            </div>
          ) : null}
        </header>
        {isAudio ? (
          <>
            <div className="live-draft-audio-player">
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </div>
            <section className="capture-generated-section">
              <CaptureGeneratedHeading label="Transcript" attribution={textAttribution} />
              <p className="live-draft-preview">{generatedText || fallbackText}</p>
            </section>
          </>
        ) : null}
        {isPhoto ? (
          <div className="live-draft-photo-row">
            <div className="live-draft-photo-thumb">
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </div>
            <div className="live-draft-photo-copy">
              <CaptureGeneratedHeading label="Caption" attribution={textAttribution} />
              <p>{generatedText || fallbackText}</p>
            </div>
          </div>
        ) : null}
        {!isPhoto && !isAudio ? (
          <>
            <section className="capture-generated-section">
              <h4>Decorated text</h4>
              <p className="live-draft-preview">{decoratedNoteText}</p>
            </section>
            <details className="capture-raw-note">
              <summary>Raw note</summary>
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </details>
          </>
        ) : null}
      </div>
    </article>
  );
}

function CaptureInlineStatus({ status }: { status?: CaptureItem["status"] }) {
  if (status === "saved" || status === "syncing" || status === "uploading") {
    return (
      <span className="capture-inline-status active syncing">
        <span aria-hidden="true" />
        Saved on this device
      </span>
    );
  }
  if (status === "uploaded" || status === "processing") {
    return (
      <span className="capture-inline-status active processing">
        <span aria-hidden="true" />
        Organizing
      </span>
    );
  }
  if (status === "failed") return <span className="capture-inline-status issue">Saved on this device</span>;
  if (status === "needsReview") return <span className="capture-inline-status issue">Needs attention</span>;
  return null;
}

function CaptureGeneratedHeading({ attribution, label }: { attribution: string; label: string }) {
  return (
    <div className="capture-generated-heading">
      <h4>{label}</h4>
      <span>{attribution}</span>
    </div>
  );
}

function captureTextAttribution(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  const value = item.type === "photo" ? metadata.caption : metadata.transcript;
  const record = metadataRecord(value);
  const source = metadataDisplay(record.source);
  const editorName = metadataDisplay(record.edited_by_name || record.editedByName || record.edited_by_email || record.editedByEmail);
  if (source === "staff_edit" || editorName) return `Edited by ${editorName || "staff"}`;
  return "Generated by AI";
}

function CaptureTimelineIcon({ type }: { type: CaptureItem["type"] }) {
  if (type === "photo") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M8.5 7.5 10 5h4l1.5 2.5H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2h3.5Z" />
        <path d="M12 16.8a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2Z" />
      </svg>
    );
  }
  if (type === "note") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M6 3.5h9l3 3V20.5H6v-17Z" />
        <path d="M15 3.5v4h4" />
        <path d="M8.5 11h7" />
        <path d="M8.5 15h5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 14.5a3 3 0 0 0 3-3v-5a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0" />
      <path d="M12 17v3.5" />
      <path d="M9 20.5h6" />
    </svg>
  );
}

function StructuredReportView({
  session,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const clinic = session?.report?.template?.clinic;
  const patientInformation = session?.report?.patientInformation || patientInformationFromSession(session);
  const bodyParagraphs = workspaceStructuredReportCopy(session);
  return (
    <div className="structured-report-view">
      <section className="structured-report-section">
        <h3>Clinic Information</h3>
        <p>Clinic: {clinic?.name || "Clinic"}</p>
        {(clinic?.information?.length ? clinic.information : ["Clinical memory report"]).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </section>
      <section className="structured-report-section">
        <h3>Patient Information</h3>
        <PatientInformationRows patientInformation={patientInformation} />
      </section>
      <section className="structured-report-section structured-report-body">
        <h3>Body</h3>
        {session?.processingStatus?.state === "processing" || session?.report?.status === "generating" ? (
          <>
            <h3>Generating structured report</h3>
            <p>Please wait while AesMem prepares the full report from the latest captures.</p>
          </>
        ) : bodyParagraphs.length ? (
          bodyParagraphs.map((paragraph, index) => (
            <section className="workspace-report-section" key={`${index}-${paragraph.slice(0, 24)}`}>
              {formatReportParagraph(paragraph, onResolveFile)}
            </section>
          ))
        ) : (
          <>
            <h3>Structured report not generated yet</h3>
            <p>The live draft is available now. Generate a structured report when the session has enough source material.</p>
          </>
        )}
      </section>
    </div>
  );
}

function PatientInformationRows({ patientInformation }: { patientInformation: StructuredPatientInformation | null }) {
  if (!patientInformation || patientInformation.status !== "assigned") return <p>Patient: Unassigned</p>;
  const rows = [
    ["Full name", patientInformation.displayName],
    ["National ID", patientInformation.nationalId],
    ["Date of birth", patientInformation.dateOfBirth],
    ["Sex", patientInformation.sex],
    ["Phone", patientInformation.phone],
    ["Email", patientInformation.email],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) return <p>Patient assigned</p>;
  return (
    <dl className="structured-report-patient-info">
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function patientInformationFromSession(session: CaptureSession | null): StructuredPatientInformation | null {
  if (!session?.patientId && !session?.patientName) return { status: "unassigned" };
  return {
    status: "assigned",
    patientId: session.patientId || null,
    displayName: session.patientName || session.patientId || "Assigned patient",
  };
}

function workspaceReportState(
  session: CaptureSession | null,
): { badge: string; detail: string; kind: "partial" | "structured" | "verified"; label: string; tone: "neutral" | "blue" | "green" | "amber" } {
  const stageLabel = nonTechnicalStageLabel(session?.processingStatus);
  if (!session) {
    return {
      badge: "Empty",
      detail: "Start with audio, a photo, or a note. The draft will build here without changing screens.",
      kind: "partial",
      label: "Empty draft",
      tone: "neutral",
    };
  }
  if (session.report?.isStale) {
    return {
      badge: "Draft",
      detail: "New material has been added. Generate the structured report again when ready.",
      kind: "partial",
      label: "Draft updated",
      tone: "blue",
    };
  }
  if (session.report?.status === "generating" || session.processingStatus?.state === "processing") {
    return { badge: "Updating", detail: stageLabel, kind: "partial", label: "Report updating", tone: "blue" };
  }
  if (session.report?.status === "verified" || session.status === "verified") {
    return { badge: "Verified", detail: "Reviewed and accepted for this session.", kind: "verified", label: "Verified report", tone: "green" };
  }
  if (session.report?.status === "processed") {
    return {
      badge: "Structured",
      detail: "Structured draft is ready for review.",
      kind: "structured",
      label: "Structured report",
      tone: "green",
    };
  }
  if (session.report?.status === "failed" || sessionUxState(session.status) === "failed") {
    return { badge: "Needs attention", detail: "The latest report update did not complete. Existing captures remain available below.", kind: "partial", label: "Report needs attention", tone: "amber" };
  }
  if (isLocalSessionId(session.id) || sessionUxState(session.status) === "capturing") {
    return {
      badge: session.items.length ? "Partial" : "Empty",
      detail: session.items.length ? "Early draft from the current captures." : "Start with audio, a photo, or a note.",
      kind: "partial",
      label: session.items.length ? "Partial draft" : "Empty draft",
      tone: session.items.length ? "blue" : "neutral",
    };
  }
  return { badge: "Structured", detail: "Structured draft is ready for review.", kind: "structured", label: "Structured report", tone: "green" };
}

function workspaceStructuredReportCopy(session: CaptureSession | null) {
  const reportBody = session?.report?.body || session?.generatedReport;
  if (reportBody) return reportBody.split(/\n{2,}/).map((line) => line.trim()).filter(Boolean);
  return [];
}

function captureDraftLabel(item: CaptureItem, sequence: number) {
  if (item.title?.trim()) return item.title.trim();
  if (item.type === "audio" || item.type === "voice") return `Audio ${sequence}`;
  if (item.type === "photo") return `Photo ${sequence}`;
  return `Note ${sequence}`;
}

function draftCaptureText(item: CaptureItem) {
  const generated = generatedTextForReport(item);
  if (generated) return generated;
  if (item.type === "audio" || item.type === "voice") return "Audio capture added, processing...";
  if (item.type === "photo") return "Photo added, analyzing...";
  return item.detail || "Text note added to the draft.";
}

function generatedTextForReport(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  const generated =
    item.type === "audio" || item.type === "voice"
      ? metadata.transcript
      : item.type === "photo"
        ? metadata.caption || metadata.ocr
        : metadata.decorated_text || metadata.decoratedText || metadata.normalized_note || metadata.normalizedNote;
  const generatedRecord = metadataRecord(generated);
  const text =
    metadataText(generated) ||
    metadataText(generatedRecord.text) ||
    metadataText(generatedRecord.transcript) ||
    metadataText(generatedRecord.caption) ||
    metadataText(generatedRecord.decorated_text) ||
    metadataText(generatedRecord.decoratedText) ||
    metadataText(generatedRecord.normalized_note) ||
    metadataText(generatedRecord.normalizedNote);
  if (text) return text;
  if (item.type === "note") return item.detail;
  if (item.status === "processed" || item.status === "ready") {
    if (item.type === "audio" || item.type === "voice") {
      return `Mock transcript: clinical audio captured at ${item.time}. Source audio remains attached for review.`;
    }
    if (item.type === "photo") {
      return `Mock photo analysis: clinical photo captured at ${item.time}. Review the image above with this generated caption.`;
    }
  }
  return "";
}

function noteDecoratedText(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  const decorated = metadata.decorated_text || metadata.decoratedText || metadata.normalized_note || metadata.normalizedNote;
  const decoratedRecord = metadataRecord(decorated);
  return (
    metadataText(decorated) ||
    metadataText(decoratedRecord.text) ||
    metadataText(decoratedRecord.decorated_text) ||
    metadataText(decoratedRecord.decoratedText) ||
    metadataText(decoratedRecord.normalized_note) ||
    metadataText(decoratedRecord.normalizedNote)
  );
}

function nonTechnicalStageLabel(status?: SessionProcessingStatus) {
  if (!status || status.state !== "processing") return "Report is staying current with the latest captures.";
  if (status.stage === "transcripts") return "Reading the source captures.";
  if (status.stage === "report") return "Drafting the clinical report.";
  if (status.stage === "findings") return "Organizing key details.";
  if (status.stage === "summary") return "Condensing the session.";
  return status.label || "Updating the report.";
}

function workspaceReportMilestones(session: CaptureSession | null, state: ReturnType<typeof workspaceReportState>) {
  if (state.kind === "verified") {
    return ["Draft", "Structured", "Verified"].map((label) => ({
      label,
      state: "done",
      className: label === "Verified" ? "done verified" : "done",
    }));
  }
  if (state.kind === "structured") {
    return [
      { label: "Draft", state: "done", className: "done" },
      { label: "Structured", state: "done", className: "done" },
      { label: "Verified", state: "current", className: "current" },
    ];
  }
  return ["Draft", "Structured", "Verified"].map((label, index) => ({
    label,
    state: index === 0 ? "current" : "next",
    className: index === 0 ? "current" : "next",
  }));
}

function workspaceReportUpdatedLabel(value?: string | null) {
  if (!value) return "Live draft updates as captures arrive";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently updated";
  return `Updated ${new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date)}`;
}

function sessionSummaryStatusChip(session: CaptureSession | null) {
  if (session?.status === "verified" || session?.report?.status === "verified") {
    return { checked: true, label: "Verified", tone: "success" };
  }
  if (session?.report?.status === "processed" && !session.report.isStale) {
    return { checked: false, label: "Generated", tone: "success" };
  }
  if (session?.processingStatus?.state === "processing" || session?.report?.status === "generating") {
    return { checked: false, label: "Generating", tone: "info" };
  }
  return { checked: false, label: session?.items.length ? "Draft" : "Ready", tone: "neutral" };
}

function sessionSummaryTitle(session: CaptureSession | null, isHistorical: boolean) {
  if (isHistorical) return session?.label || "Session review";
  const title = (session?.report?.title || session?.label || "").trim();
  if (title && session && !isLocalSessionId(session.id)) return title;
  return "Current session";
}

function sessionPatientName(session: CaptureSession | null) {
  return session?.patientName || "Unassigned patient";
}

function sessionSummaryCreatedLabel(session: CaptureSession | null) {
  if (!session) return "Created now";
  const source = session.capturedAt || session.createdAt || session.dateLabel || session.time;
  const label = sessionDateTimeLabel(source, session.time);
  return label ? `Created ${label}` : "Created recently";
}

function sessionSummaryUpdatedLabel(session: CaptureSession | null) {
  const source = session?.report?.updatedAt || session?.processingStatus?.updatedAt || session?.time;
  const label = sessionDateTimeLabel(source);
  return `Updated ${label || "recently"}`;
}

function sessionDateTimeLabel(source?: string | null, fallbackTime?: string | null) {
  if (!source && !fallbackTime) return "";
  const date = source ? new Date(source) : null;
  if (date && !Number.isNaN(date.getTime())) {
    const dateLabel = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
    const timeLabel = new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
    return `${dateLabel} · ${timeLabel}`;
  }
  const datePart = source && !source.match(/\b\d{1,2}:\d{2}\b/) ? source : "";
  const time = source?.match(/\b\d{1,2}:\d{2}\b/)?.[0] || fallbackTime || "";
  return [datePart, time].filter(Boolean).join(" · ");
}

function formatReportParagraph(paragraph: string, onResolveFile?: (endpoint: string) => Promise<string>) {
  const image = paragraph.match(/^!\[(.*)]\((.*)\)$/);
  if (image) {
    return <MarkdownImage alt={image[1] || "Report image"} src={image[2]} onResolveFile={onResolveFile} />;
  }
  const italic = paragraph.match(/^\*(.*)\*$/);
  if (italic) return <p><em>{italic[1]}</em></p>;
  if (paragraph.startsWith("# ")) return <h3>{paragraph.replace(/^#\s+/, "")}</h3>;
  if (paragraph.startsWith("## ")) return <h4>{paragraph.replace(/^##\s+/, "")}</h4>;
  if (paragraph.startsWith("- ")) {
    return (
      <ul>
        {paragraph.split(/\n-\s+/).map((item) => (
          <li key={item}>{item.replace(/^-\s+/, "")}</li>
        ))}
      </ul>
    );
  }
  if (paragraph.includes("\n- ")) {
    const [intro, ...items] = paragraph.split(/\n-\s+/);
    return (
      <>
        {intro.trim() ? <p>{intro.trim()}</p> : null}
        <ul>
          {items.filter(Boolean).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </>
    );
  }
  return <p>{paragraph}</p>;
}

function MarkdownImage({
  alt,
  src,
  onResolveFile,
}: {
  alt: string;
  src: string;
  onResolveFile?: (endpoint: string) => Promise<string>;
}) {
  const [resolvedUrl, setResolvedUrl] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    if (!onResolveFile || !src.startsWith("/api/v1/")) return;
    onResolveFile(src)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [onResolveFile, src]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  const imageSrc = resolvedUrl || (src.startsWith("/api/v1/") ? "" : src);
  return imageSrc ? <img alt={alt} className="structured-report-body-image" src={imageSrc} /> : <p>Image preview unavailable</p>;
}

function workspaceFindings(session: CaptureSession | null) {
  if (session?.findings?.length) return session.findings;
  const metadata = metadataRecord(session?.extractedMetadata);
  const clinical = metadataRecord(metadata.clinical_metadata);
  const patient = metadataRecord(metadata.patient_information);
  const candidates = [
    ["Patient", session?.patientName || metadataDisplay(patient.full_name)],
    ["Procedure", metadataDisplay(clinical.procedure || clinical.visit_type || metadata.visit_type)],
    ["Body area", metadataDisplay(clinical.body_area || clinical.area || metadata.body_area)],
    ["Product", metadataDisplay(clinical.product || metadata.product)],
    ["Template", metadataDisplay(session?.reportTemplateKey)],
  ];
  return candidates
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([label, value]) => ({ label, value }));
}
