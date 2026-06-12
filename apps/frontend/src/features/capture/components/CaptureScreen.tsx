import React from "react";
import type { LastVisitInfo, PatientAssignmentDraft, PatientSummary } from "../../../domain/appTypes";
import type {
  CaptureItem,
  CaptureSession,
  SessionProcessingStatus,
  StructuredPatientInformation,
  StructuredReportBlock,
} from "../../../domain/types";
import { isLocalSessionId } from "../captureModel";
import { assignmentSourceLabel, metadataDisplay, metadataRecord, metadataText } from "../metadata";
import { sessionUxState } from "../../../domain/status";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { PatientForm } from "../../patient/PatientForm";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { LastVisitStrip } from "../../aesthetics/LastVisitStrip";
import { SourcePreviewDialog, CaptureRawPreview } from "./SourcePreview";

export function CaptureScreen({
  activeSession,
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
  onOpenResolver,
  onSearchPatients,
  onCompleteAiCreatedPatient,
  onStartNewSession,
  onMarkRelevant,
  onFetchPatient,
  tier,
  lastVisit,
  onOpenVisit,
  onUseAsNote,
}: {
  activeSession: CaptureSession | null;
  /** Deprecated: the live report regenerates automatically (Epic E); kept for the retry path. */
  onSaveSession?: (sessionId: string) => void;
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
  /** Open the assignment resolver from a capture-card "Choose another" quick action (H4). */
  onOpenResolver?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onCompleteAiCreatedPatient?: (
    sessionId: string,
    patientId: string,
    draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
    action: Record<string, unknown>,
  ) => Promise<void>;
  onStartNewSession?: () => void;
  onMarkRelevant?: (sessionId: string, captureId: string) => Promise<void>;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  tier?: string | null;
  /** AES-106 — the returning patient's prior visit (note + photos), surfaced at capture (Basic). */
  lastVisit?: LastVisitInfo | null;
  onOpenVisit?: (sessionId: string) => void;
  onUseAsNote?: (text: string) => void;
}) {
  const isPro = tier !== "basic";
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [reportView, setReportView] = React.useState<"draft" | "structured">("draft");
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const isHistorical = mode === "historical";
  const processingState = activeSession?.processingStatus?.state;
  // The live report regenerates automatically as captures land (Epic E); "updating" is a calm
  // inline state, never a gate. Pro = synthesized; Basic = chronological.
  const isUpdatingReport = isPro && (processingState === "processing" || activeSession?.report?.status === "generating");
  const reportState = workspaceReportState(activeSession);
  const selectedReportView = reportView;
  const sessionTitle = sessionSummaryTitle(activeSession, isHistorical);
  const patientName = sessionPatientName(activeSession);
  const aiPatientAction = aiPatientActionForSession(activeSession);
  const captureCount = activeSession?.items.length || 0;
  const captureCountLabel = `${captureCount} capture${captureCount === 1 ? "" : "s"}`;
  const sessionStatusChip = sessionSummaryStatusChip(activeSession);
  const sessionCreatedLabel = sessionSummaryCreatedLabel(activeSession);
  const sessionUpdatedLabel = sessionSummaryUpdatedLabel(activeSession);

  // The report is always live; default to the Captures feed and let the user toggle tabs.
  React.useEffect(() => {
    setReportView("draft");
  }, [activeSession?.id]);

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
          <p>
            {activeSession?.patientId
              ? activeSession.assignmentSource
                ? assignmentSourceLabel(activeSession.assignmentSource)
                : "Assigned manually"
              : "No patient assigned"}
          </p>
        </div>
        {onAssignPatient ? (
          <Button className="edit-patient-button" onClick={onCloseAssignment} size="sm" type="button" variant="secondary">
            <EditIcon />
            Edit patient
          </Button>
        ) : null}
      </Card>
      {!isPro && !isHistorical && activeSession?.patientId && lastVisit ? (
        <LastVisitStrip lastVisit={lastVisit} onOpenVisit={onOpenVisit} onUseAsNote={onUseAsNote} onResolveFile={onResolveFile} />
      ) : null}
      {activeSession && aiPatientAction && onCompleteAiCreatedPatient ? (
        <AiCreatedPatientPanel
          action={aiPatientAction}
          session={activeSession}
          onComplete={onCompleteAiCreatedPatient}
        />
      ) : null}
      <Card className={`workspace-report-card ${isUpdatingReport ? "processing" : ""}`}>
        <div className="report-heading">
          <div className="report-title-lockup">
            <span className="report-title-icon" aria-hidden="true">
              <ClipboardIcon />
            </span>
            <h2>Clinical report</h2>
            <span className={`report-tier-badge ${isPro ? "pro" : "basic"}`}>{isPro ? "Pro" : "Basic"}</span>
          </div>
          <div className="report-heading-actions">
            {isUpdatingReport ? (
              <span className="report-updating" aria-live="polite">
                <span className="report-updating-spinner" aria-hidden="true" />
                {reportUpdatingLabel(activeSession)}
              </span>
            ) : null}
          </div>
        </div>
        <div className="report-toolbar">
          <div className="report-toolbar-actions">
            <div className="report-view-switch" aria-label="Report view">
              <button className={selectedReportView === "draft" ? "active" : ""} onClick={() => setReportView("draft")} type="button">
                Captures
              </button>
              <button
                className={selectedReportView === "structured" ? "active" : ""}
                onClick={() => setReportView("structured")}
                type="button"
              >
                Live report
              </button>
            </div>
          </div>
        </div>
        {assignmentOpen && activeSession && onAssignPatient ? (
          <PatientAssignmentSheet
            session={activeSession}
            onAssign={(draft) => onAssignPatient(activeSession.id, draft)}
            onCancel={onCloseAssignment}
            onFetchPatient={onFetchPatient}
            onSearchPatients={onSearchPatients}
          />
        ) : null}
        <div className={`workspace-report-body ${reportState.kind}`}>
          {selectedReportView === "structured" ? (
            <LiveReportView
              isPro={isPro}
              session={activeSession}
              onResolveFile={onResolveFile}
            />
          ) : (
            <LiveDraftReport
              isPro={isPro}
              session={activeSession}
              onApplyRelevant={onMarkRelevant}
              onAssignPatient={onAssignPatient}
              onDeleteCapture={onDeleteCapture}
              onOpenCapture={setSelectedCapture}
              onOpenResolver={onOpenResolver}
              onRenameCapture={onRenameCapture}
              onResolveFile={onResolveFile}
              onUpdateCaptureCaption={onUpdateCaptureCaption}
              onUpdateCaptureTranscript={onUpdateCaptureTranscript}
            />
          )}
        </div>
        <div className="workspace-report-footer">
          <div className="workspace-report-footer-copy">
            {isUpdatingReport ? (
              <span>{reportUpdatingLabel(activeSession)}</span>
            ) : activeSession?.complete ? (
              <span className="report-complete-note">✓ Complete · captures processed, patient assigned, report up to date</span>
            ) : null}
          </div>
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
  onFetchPatient,
  onSearchPatients,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onCancel?: () => void;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [apiMatches, setApiMatches] = React.useState<PatientSummary[]>([]);
  const [searching, setSearching] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const trimmedQuery = query.trim();
  const currentPatient = React.useMemo(() => currentSessionPatient(session), [session]);
  const currentAssignedPatient = currentPatient[0] || null;
  const localMatches = React.useMemo(() => filterPatientMatches(currentPatient, trimmedQuery), [currentPatient, trimmedQuery]);
  // Smart suggestions: patients already detected in this session's captures come first.
  const detected = React.useMemo(() => detectedSessionPatients(session, currentAssignedPatient?.id), [session, currentAssignedPatient]);
  const detectedIds = React.useMemo(() => new Set(detected.map((patient) => patient.id)), [detected]);
  const detectedMatches = React.useMemo(() => filterPatientMatches(detected, trimmedQuery), [detected, trimmedQuery]);
  const matches = mergePatientMatches([...detectedMatches, ...localMatches], apiMatches).slice(0, 4);
  // Prefer the DB patient info the report carries; otherwise fetch it (covers sessions without
  // a report model — e.g. Basic, or before the first Pro report job runs).
  const [fetchedPatient, setFetchedPatient] = React.useState<StructuredPatientInformation | null>(null);
  const reportDetails = patientDetailRows(session.report?.patientInformation);
  const assignedDetails = reportDetails.length ? reportDetails : patientDetailRows(fetchedPatient);

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

  React.useEffect(() => {
    const patientId = currentAssignedPatient?.id;
    // Only fetch when the report didn't already carry the patient's details.
    if (!onFetchPatient || !patientId || reportDetails.length) {
      setFetchedPatient(null);
      return;
    }
    let cancelled = false;
    void onFetchPatient(patientId).then((info) => {
      if (!cancelled) setFetchedPatient(info);
    });
    return () => {
      cancelled = true;
    };
  }, [onFetchPatient, currentAssignedPatient?.id, reportDetails.length]);

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
        {currentAssignedPatient ? (
          <section className="assignment-current-patient" aria-label="Currently assigned patient">
            <span className="assignment-patient-avatar" aria-hidden="true">
              <PatientIcon />
            </span>
            <div className="assignment-patient-copy">
              <small>Currently assigned{session.assignmentSource ? ` · ${assignmentSourceLabel(session.assignmentSource)}` : ""}</small>
              <strong>{currentAssignedPatient.displayName}</strong>
              {assignedDetails.length ? (
                <dl className="assignment-patient-details">
                  {assignedDetails.map(([label, value]) => (
                    <div className="assignment-patient-detail" key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <span>{patientIdentifierLabel(currentAssignedPatient)}</span>
              )}
            </div>
            <button
              className="assignment-unassign"
              disabled={saving}
              onClick={() => assignDraft({ unassign: true, displayName: "" })}
              type="button"
            >
              Unassign
            </button>
          </section>
        ) : (
          <p className="assignment-no-patient">No patient assigned yet — search below or create a new patient.</p>
        )}
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
                  <small>
                    {alreadyAssigned
                      ? "Currently assigned to this visit"
                      : detectedIds.has(patient.id)
                        ? "Detected in this session"
                        : `Last visit: ${formatLastVisit(patient.lastVisit)}`}
                  </small>
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
          {creating ? (
            <PatientForm
              busy={saving}
              initial={{ displayName: trimmedQuery }}
              onCancel={() => setCreating(false)}
              onSubmit={(values) =>
                assignDraft({
                  displayName: values.displayName,
                  nationalId: values.nationalId || undefined,
                  phone: values.phone || undefined,
                  dateOfBirth: values.dateOfBirth || undefined,
                  sex: values.sex || undefined,
                  notes: values.notes || undefined,
                })
              }
              submitLabel="Create new patient"
            />
          ) : (
            <Button className="assignment-create-button" onClick={() => setCreating(true)} type="button">
              <AddPatientIcon />
              Create new patient{trimmedQuery ? ` “${trimmedQuery}”` : ""}
            </Button>
          )}
        </section>
      </section>
    </div>
  );
}

function patientDetailRows(info?: StructuredPatientInformation | null): Array<[string, string]> {
  if (!info || info.status !== "assigned") return [];
  return ([
    ["National ID", info.nationalId],
    ["Phone", info.phone],
    ["Date of birth", info.dateOfBirth],
  ] as Array<[string, string | null | undefined]>).filter((row): row is [string, string] => Boolean(row[1]));
}

function detectedSessionPatients(session: CaptureSession, excludeId?: string): PatientSummary[] {
  // Patients that surfaced in this session (assigned, matched, suggested, or candidate) — the
  // "smart" suggestions to show first, instead of an arbitrary search list.
  const out: PatientSummary[] = [];
  const seen = new Set<string>();
  const push = (id: string, displayName: string, nationalId?: string) => {
    if (!id || !displayName || id === excludeId || seen.has(id)) return;
    seen.add(id);
    out.push({ id, displayName, nationalId: nationalId || null, lastVisit: null });
  };
  const timeline = metadataRecord(session.extractedMetadata).patient_assignment_timeline;
  if (Array.isArray(timeline)) {
    for (const raw of timeline) {
      const event = metadataRecord(raw);
      push(metadataDisplay(event.patientId), metadataDisplay(event.displayName));
    }
  }
  for (const item of session.items || []) {
    const meta = metadataRecord(item.metadata);
    const candidate = metadataRecord(meta.patient_match_candidate);
    push(metadataDisplay(candidate.patientId), metadataDisplay(candidate.displayName) || suggestionNameFromInformation(candidate), suggestionNationalId(candidate));
    if (Array.isArray(candidate.candidateSet)) {
      for (const raw of candidate.candidateSet) {
        const entry = metadataRecord(raw);
        push(metadataDisplay(entry.patientId), metadataDisplay(entry.displayName));
      }
    }
    const action = metadataRecord(meta.ai_patient_action);
    push(metadataDisplay(action.patientId), metadataDisplay(action.displayName));
  }
  return out;
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
  isPro,
  session,
  onApplyRelevant,
  onAssignPatient,
  onDeleteCapture,
  onOpenCapture,
  onOpenResolver,
  onRenameCapture,
  onResolveFile,
  onUpdateCaptureCaption,
  onUpdateCaptureTranscript,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onApplyRelevant?: (sessionId: string, captureId: string) => Promise<void>;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onDeleteCapture?: (sessionId: string, captureId: string) => Promise<void>;
  onOpenCapture: (item: CaptureItem) => void;
  onOpenResolver?: () => void;
  onRenameCapture?: (sessionId: string, captureId: string, title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateCaptureCaption?: (sessionId: string, captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateCaptureTranscript?: (sessionId: string, captureId: string, transcript: string) => Promise<CaptureItem | null>;
}) {
  const [openMenuId, setOpenMenuId] = React.useState("");
  const activePatientAction = activePatientAssignmentActionForSession(session);
  const candidates = sessionAssignmentCandidates(session);

  React.useEffect(() => {
    setOpenMenuId("");
  }, [session?.id]);

  // Smoothly bring a newly added capture into view (handy in a long timeline) — only when a capture
  // is appended to the *same* session, not on session switch / refresh / edit.
  const newestCaptureRef = React.useRef<HTMLElement | null>(null);
  const captureCountRef = React.useRef(0);
  const feedSessionIdRef = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    const count = session?.items.length || 0;
    const sameSession = session?.id === feedSessionIdRef.current;
    if (sameSession && count > captureCountRef.current) {
      newestCaptureRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    captureCountRef.current = count;
    feedSessionIdRef.current = session?.id;
  }, [session?.id, session?.items.length]);

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
          activePatientAction={activePatientAction}
          alternateCandidate={alternateCandidateForCapture(candidates, item.id)}
          isPro={isPro}
          item={item}
          key={item.sourceUrl || item.id}
          menuOpen={openMenuId === item.id}
          onApplyReassignment={onAssignPatient ? (draft) => onAssignPatient(session.id, draft) : undefined}
          onApplyRelevant={onApplyRelevant ? () => onApplyRelevant(session.id, item.id) : undefined}
          onChooseAnother={onOpenResolver}
          onCloseMenu={() => setOpenMenuId("")}
          onDeleteCapture={onDeleteCapture ? () => onDeleteCapture(session.id, item.id) : undefined}
          onEditCaption={onUpdateCaptureCaption ? (text) => onUpdateCaptureCaption(session.id, item.id, text).then(() => undefined) : undefined}
          onEditTranscript={onUpdateCaptureTranscript ? (text) => onUpdateCaptureTranscript(session.id, item.id, text).then(() => undefined) : undefined}
          onOpenCapture={() => onOpenCapture(item)}
          onRenameCapture={onRenameCapture ? (title) => onRenameCapture(session.id, item.id, title) : undefined}
          onResolveFile={onResolveFile}
          onToggleMenu={() => setOpenMenuId((current) => (current === item.id ? "" : item.id))}
          rootRef={index === session.items.length - 1 ? newestCaptureRef : undefined}
          sequence={index + 1}
        />
      ))}
      {isPro && session.processingStatus?.state === "processing" ? (
        <div className="live-draft-processing">Memara is refining the live report. Your captures stay reviewable while it updates.</div>
      ) : null}
    </div>
  );
}

function LiveDraftCaptureItem({
  activePatientAction,
  alternateCandidate,
  isPro,
  item,
  menuOpen,
  onApplyReassignment,
  onApplyRelevant,
  onChooseAnother,
  onCloseMenu,
  onDeleteCapture,
  onEditCaption,
  onEditTranscript,
  onOpenCapture,
  onRenameCapture,
  onResolveFile,
  onToggleMenu,
  rootRef,
  sequence,
}: {
  activePatientAction: Record<string, unknown> | null;
  alternateCandidate: AssignmentCandidate | null;
  isPro: boolean;
  item: CaptureItem;
  menuOpen: boolean;
  onApplyReassignment?: (draft: PatientAssignmentDraft) => Promise<void>;
  onApplyRelevant?: () => Promise<void>;
  onChooseAnother?: () => void;
  onCloseMenu: () => void;
  onDeleteCapture?: () => Promise<void>;
  onEditCaption?: (text: string) => Promise<void>;
  onEditTranscript?: (text: string) => Promise<void>;
  onOpenCapture: () => void;
  onRenameCapture?: (title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onToggleMenu: () => void;
  rootRef?: React.Ref<HTMLElement>;
  sequence: number;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  const isPhoto = item.type === "photo";
  const title = captureDraftLabel(item, sequence);
  const generatedText = generatedTextForReport(item);
  // Only Pro photos are AI-captioned, so only they show the "Reading image" cue while processing.
  // Basic photos are never captioned → go straight to a manual "Add caption" (no AI badge/spinner).
  const captionStillProcessing =
    isPro && item.status !== "processed" && item.status !== "ready" && item.status !== "needsReview";
  const fallbackText = draftCaptureText(item);
  const decoratedNoteText = noteDecoratedText(item) || generatedText || fallbackText;
  const textAttribution = captureTextAttribution(item);
  const [busy, setBusy] = React.useState(false);
  const [markedRelevant, setMarkedRelevant] = React.useState(false);
  const outOfContext = captureOutOfContext(item) && !markedRelevant;
  const assignmentInfo = captureAssignmentInfo(item, activePatientAction);
  // Persist "Mark relevant" (clears the AI out-of-context marker + re-folds into the report),
  // optimistically clearing the chip while the session refreshes.
  const markRelevant = () => {
    setMarkedRelevant(true);
    if (onApplyRelevant) void onApplyRelevant();
  };

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
    if (!window.confirm(`Delete ${title}? The live report will update.`)) return;
    setBusy(true);
    void onDeleteCapture().finally(() => {
      setBusy(false);
      onCloseMenu();
    });
  };

  return (
    <article
      ref={rootRef}
      className={`live-draft-capture ${item.type}${outOfContext ? " is-out-of-context" : ""}${assignmentInfo ? " is-assignment-source" : ""}`}
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
              <span className="live-draft-title-main">
                <h3>{title}</h3>
                <CaptureAssignmentBadge info={assignmentInfo} />
                <CaptureReportBadge isPro={isPro} item={item} outOfContext={outOfContext} />
              </span>
              <time>{item.time}</time>
            </div>
            <CaptureInlineStatus status={item.status} isPro={isPro} />
            <CapturePatientBadges
              activePatientAction={activePatientAction}
              alternateCandidate={alternateCandidate}
              item={item}
              onApplyReassignment={onApplyReassignment}
              onChooseAnother={onChooseAnother}
              outOfContext={outOfContext}
              onMarkRelevant={markRelevant}
            />
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
            {isPro ? (
              <section className={`capture-generated-section ${generatedText ? "ready" : "pending"}`}>
                {generatedText ? (
                  <CaptureGeneratedText attribution={textAttribution} dir={textDirection(generatedText)} label="Transcript" onSave={onEditTranscript} text={generatedText} />
                ) : (
                  <>
                    <CaptureGeneratedHeading label="Transcript" attribution={pendingGeneratedAttribution(item)} />
                    <CaptureWorkingPlaceholder label={audioPendingTranscriptLabel(item)} />
                  </>
                )}
              </section>
            ) : (
              // Basic: audio is a voice memo — no transcript, no AI job. (AES-101/802)
              <>
                <div className="capture-effect-chips" aria-label="Capture status">
                  <span className="effect-chip is-saved">Saved on this device · voice memo</span>
                </div>
                <TryProTeaser
                  title="Try Pro — transcribe &amp; structure this dictation"
                  subtitle="Basic keeps audio as a voice memo. Pro turns it into a structured treatment report."
                />
              </>
            )}
          </>
        ) : null}
        {isPhoto ? (
          <div className="live-draft-photo-row">
            <div className="live-draft-photo-thumb">
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </div>
            <div className="live-draft-photo-copy">
              {isPro ? (
                <section className={`capture-generated-section ${generatedText ? "ready" : captionStillProcessing ? "pending" : "ready"}`}>
                  {generatedText ? (
                    <CaptureGeneratedText attribution={textAttribution} dir={textDirection(generatedText)} label="Caption" onSave={onEditCaption} text={generatedText} />
                  ) : captionStillProcessing ? (
                    <>
                      <CaptureGeneratedHeading label="Caption" attribution={textAttribution} />
                      <CaptureWorkingPlaceholder label="Reading image" />
                    </>
                  ) : (
                    <CaptureGeneratedText addLabel="Add caption" attribution="" dir="ltr" label="Caption" onSave={onEditCaption} text="" />
                  )}
                </section>
              ) : (
                // Basic: photos are filed to the patient and shown — no tagging, no AI caption. (AES-103/803)
                <>
                  <p className="live-draft-photo-note">Filed to the patient, not your camera roll · you compare by eye.</p>
                  <TryProTeaser
                    title="Try Pro — caption &amp; prepare before/after"
                    subtitle="Basic files &amp; shows your photos. Pro captions them and builds the labelled before/after with a slider."
                  />
                </>
              )}
            </div>
          </div>
        ) : null}
        {!isPhoto && !isAudio ? (
          <>
            <section className="capture-generated-section ready">
              <h4>Decorated text</h4>
              <p className="live-draft-preview" dir={textDirection(decoratedNoteText)}>{decoratedNoteText}</p>
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

function CapturePatientBadges({
  activePatientAction,
  alternateCandidate,
  item,
  onApplyReassignment,
  onChooseAnother,
  outOfContext,
  onMarkRelevant,
}: {
  activePatientAction: Record<string, unknown> | null;
  alternateCandidate?: AssignmentCandidate | null;
  item: CaptureItem;
  onApplyReassignment?: (draft: PatientAssignmentDraft) => Promise<void>;
  onChooseAnother?: () => void;
  outOfContext?: boolean;
  onMarkRelevant?: () => void;
}) {
  const [dismissed, setDismissed] = React.useState(false);
  const [applying, setApplying] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [editName, setEditName] = React.useState("");
  const [editNationalId, setEditNationalId] = React.useState("");

  // The active assignment/creation effect renders as a badge beside the title
  // (CaptureAssignmentBadge); here we only need to know whether this capture is the source so we
  // don't also show a reassignment suggestion on it.
  const isSource = captureAssignmentInfo(item, activePatientAction) !== null;

  // A "Suggested: reassign" surface on a NON-source capture, from a partial (fuzzy) match or an
  // implicit mention (`patient_match_candidate`), or a prior assignment basis still in the
  // timeline (the alternate candidate) — so staff can resolve the partial match in place.
  const candidate = metadataRecord(metadataRecord(item.metadata).patient_match_candidate);
  const candidateStatus = metadataDisplay(candidate.status || candidate.decision);
  const isSuggestion = candidateStatus === "suggested_reassignment";
  const suggestedMatchedName = isSuggestion ? metadataDisplay(candidate.matchedName || candidate.displayName) || suggestionNameFromInformation(candidate) : "";
  const suggestedSpokenName = isSuggestion ? metadataDisplay(candidate.spokenName) : "";
  const suggestion: { name: string; patientId?: string; nationalId?: string; spokenName?: string } | null =
    isSuggestion && (suggestedMatchedName || suggestedSpokenName)
      ? {
          name: suggestedMatchedName || suggestedSpokenName,
          patientId: metadataDisplay(candidate.patientId) || undefined,
          nationalId: suggestionNationalId(candidate),
          spokenName: suggestedSpokenName || undefined,
        }
      : alternateCandidate
        ? { name: alternateCandidate.displayName, patientId: alternateCandidate.patientId }
        : null;
  const showSuggestion = Boolean(suggestion) && !isSource && !dismissed;
  // "Matched X · you said Y" — only for a real match (a patient to keep) whose names differ.
  const showMatchedVsSpoken = Boolean(suggestion?.patientId && suggestion?.spokenName && suggestion.spokenName !== suggestion.name);

  if (!showSuggestion && !outOfContext) return null;

  // Attribute the (re)assignment to this capture so it becomes the source and its chip clears.
  const applyDraft = (draft: PatientAssignmentDraft) => {
    if (!onApplyReassignment || applying) return;
    setApplying(true);
    void onApplyReassignment(draft).finally(() => setApplying(false));
  };
  const keepMatch = () => {
    if (!suggestion?.patientId) return;
    applyDraft({ patientId: suggestion.patientId, displayName: suggestion.name, basisCaptureId: item.id });
  };
  const createNew = (name: string, nationalId?: string) => {
    // Seed a NEW patient from the spoken identity (never rename the matched record).
    const display = name.trim();
    if (!display) return;
    applyDraft({ displayName: display, nationalId: nationalId?.trim() || undefined, basisCaptureId: item.id });
  };
  const openEditor = () => {
    setEditName(suggestion?.spokenName || suggestion?.name || "");
    setEditNationalId(suggestion?.nationalId || "");
    setEditing(true);
  };

  return (
    <div className="capture-effect-chips" aria-label="Capture effects">
      {showSuggestion && suggestion ? (
        <div className="partial-match-row">
        <div className="effect-chip is-suggested partial-match">
          <div className="partial-match-head">
            <span className="effect-chip-label">
              {suggestion.patientId ? (
                <>Suggested: reassign to <strong>{suggestion.name}</strong></>
              ) : (
                <>New patient: <strong>{suggestion.name}</strong></>
              )}
            </span>
            <button aria-label="Dismiss suggestion" className="partial-match-close" onClick={() => setDismissed(true)} type="button">
              ×
            </button>
          </div>
          {showMatchedVsSpoken ? (
            <span className="partial-match-identity">
              Matched <strong>{suggestion.name}</strong> · you said <strong>{suggestion.spokenName}</strong>
            </span>
          ) : null}
          {editing ? (
            <div className="partial-match-edit">
              <span className="partial-match-edit-title">New patient details</span>
              <input aria-label="Patient name" onChange={(event) => setEditName(event.target.value)} placeholder="Patient name" value={editName} />
              <input aria-label="National ID (optional)" onChange={(event) => setEditNationalId(event.target.value)} placeholder="National ID (optional)" value={editNationalId} />
              <div className="partial-match-edit-actions">
                <button className="effect-chip-action" disabled={applying || !editName.trim()} onClick={() => createNew(editName, editNationalId)} type="button">
                  {applying ? "Creating…" : "Create patient"}
                </button>
                <button className="effect-chip-ghost" onClick={() => setEditing(false)} type="button">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="partial-match-actions">
              {suggestion.patientId && onApplyReassignment ? (
                <button className="effect-chip-action" disabled={applying} onClick={keepMatch} type="button">
                  {applying ? "Applying…" : "Keep match"}
                </button>
              ) : null}
              {onApplyReassignment ? (
                <button className="effect-chip-secondary" disabled={applying} onClick={openEditor} type="button">
                  {suggestion.patientId ? "Create new instead" : "Create patient"}
                </button>
              ) : null}
              {onChooseAnother ? (
                <button className="effect-chip-secondary" onClick={onChooseAnother} type="button">
                  Choose another
                </button>
              ) : null}
            </div>
          )}
        </div>
        </div>
      ) : null}
      {outOfContext ? (
        <span className="effect-chip is-context">
          <span className="effect-chip-label">⌀ Out of context · not in report</span>
          {onMarkRelevant ? (
            <button className="effect-chip-dismiss" onClick={onMarkRelevant} type="button">
              Mark relevant
            </button>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

/** Report-contribution status (Pro), shown as a quiet badge beside the capture title. */
function CaptureReportBadge({ isPro, item, outOfContext }: { isPro?: boolean; item: CaptureItem; outOfContext?: boolean }) {
  const status = metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status);
  if (!isPro || outOfContext || !["added", "updating", "pending"].includes(status)) return null;
  return (
    <span className={`capture-title-badge effect-chip is-report ${status === "added" ? "added" : "pending"}`}>
      {status === "added" ? "✓ Added to report" : "Adding to report…"}
    </span>
  );
}

type CaptureAssignmentInfo = { kind: "assigned" | "created"; name: string; closeMatch: boolean; spokenName: string };

/** Whether this capture is the active assignment source, and the patient it (re)assigned. */
function captureAssignmentInfo(item: CaptureItem, activePatientAction: Record<string, unknown> | null): CaptureAssignmentInfo | null {
  const action = metadataRecord(activePatientAction);
  const actionMetadata = metadataRecord(action.actionMetadata);
  const actionCaptureId = metadataDisplay(action.captureId || action.basisCaptureId || actionMetadata.basisCaptureId);
  if (!actionCaptureId || actionCaptureId !== item.id) return null;
  if (action.assigned === false || !(action.patientId || actionMetadata.patientId)) return null;
  const created =
    action.created === true || actionMetadata.created === true || action.action === "created_and_assigned" || actionMetadata.action === "created_and_assigned";
  const matchedName = metadataDisplay(action.matchedName || actionMetadata.matchedName);
  const spokenName = metadataDisplay(action.spokenName || actionMetadata.spokenName);
  const closeMatch = (action.closeMatch === true || actionMetadata.closeMatch === true) && matchedName !== "" && spokenName !== "" && matchedName !== spokenName;
  return { kind: created ? "created" : "assigned", name: metadataDisplay(action.displayName || actionMetadata.displayName), closeMatch, spokenName };
}

/** Assignment-source badge, shown beside the capture title (the patient this capture (re)assigned). */
function CaptureAssignmentBadge({ info }: { info: CaptureAssignmentInfo | null }) {
  if (!info) return null;
  return (
    <span className={`capture-title-badge effect-chip ${info.kind === "created" ? "is-created" : "is-assign"}`}>
      {info.kind === "created" ? "New patient + assigned" : "Patient assigned"}
      {info.name ? ` → ${info.name}` : ""}
      {info.closeMatch ? <span className="effect-chip-note"> · close match · you said {info.spokenName}</span> : null}
    </span>
  );
}

function captureOutOfContext(item: CaptureItem): boolean {
  const meta = metadataRecord(item.metadata);
  const marker = metadataRecord(meta.out_of_context);
  // A staff "Mark relevant" override clears the AI marker (see backend update_capture).
  if (marker.overridden_by_staff === true) return false;
  if (marker.present === true) return true;
  if ("present" in marker) return false;
  const intents = metadataRecord(metadataRecord(meta.ai_processing).intents);
  return metadataRecord(intents.out_of_context).present === true;
}

function suggestionNameFromInformation(candidate: Record<string, unknown>): string {
  const info = metadataRecord(candidate.patientInformation);
  return metadataDisplay(info.standardized_display_name || info.raw_mentioned_name || info.full_name);
}

function suggestionNationalId(candidate: Record<string, unknown>): string | undefined {
  const info = metadataRecord(candidate.patientInformation);
  return metadataDisplay(info.national_id) || undefined;
}

function AiCreatedPatientPanel({
  action,
  session,
  onComplete,
}: {
  action: Record<string, unknown>;
  session: CaptureSession;
  onComplete: (
    sessionId: string,
    patientId: string,
    draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
    action: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const patientInfo = metadataRecord(action.patientInformation);
  const patientId = metadataDisplay(action.patientId || session.patientId);
  const [saving, setSaving] = React.useState(false);
  const status = metadataDisplay(action.status);
  const needsVerification = action.needsVerification !== false && status !== "verified";
  if (!patientId || action.action !== "created_and_assigned" || !needsVerification) return null;
  // Seed the unified create/edit form from the AI-extracted identity.
  const initial = {
    displayName: metadataDisplay(action.displayName || session.patientName || patientInfo.raw_mentioned_name),
    nationalId: metadataDisplay(patientInfo.national_id),
    phone: metadataDisplay(patientInfo.phone),
    dateOfBirth: metadataDisplay(patientInfo.date_of_birth),
    sex: metadataDisplay(patientInfo.sex),
    notes: "",
  };
  return (
    <Card className="ai-patient-review-card">
      <div className="ai-patient-review-copy">
        <strong>AI created this patient from audio</strong>
        <p>Complete the details now and verify the patient record while staying in this visit.</p>
      </div>
      <PatientForm
        busy={saving}
        initial={initial}
        onSubmit={(values) => {
          setSaving(true);
          void onComplete(
            session.id,
            patientId,
            { displayName: values.displayName, nationalId: values.nationalId, phone: values.phone, dateOfBirth: values.dateOfBirth, sex: values.sex, notes: values.notes },
            action,
          ).finally(() => setSaving(false));
        }}
        submitLabel="Save & verify patient"
      />
    </Card>
  );
}

function CaptureInlineStatus({ status, isPro = true }: { status?: CaptureItem["status"]; isPro?: boolean }) {
  if (status === "saved" || status === "syncing") {
    return (
      <span className="capture-inline-status active syncing">
        <span aria-hidden="true" />
        Syncing
      </span>
    );
  }
  if (status === "uploading") {
    return (
      <span className="capture-inline-status active syncing">
        <span aria-hidden="true" />
        Uploading
      </span>
    );
  }
  if (status === "uploaded" || status === "processing") {
    // Basic is zero-AI — a saved capture never enters a "Processing" state.
    if (!isPro) return null;
    return (
      <span className="capture-inline-status active processing">
        <span aria-hidden="true" />
        Processing
      </span>
    );
  }
  if (status === "failed") return <span className="capture-inline-status issue">Needs attention</span>;
  if (status === "needsReview") return <span className="capture-inline-status issue">Needs attention</span>;
  return null;
}

function CaptureWorkingPlaceholder({ label }: { label: string }) {
  return (
    <div className="capture-working-placeholder" aria-live="polite">
      <span className="capture-working-copy">
        <span>{label}</span>
        <span className="capture-working-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </span>
      <span className="capture-working-track" aria-hidden="true" />
    </div>
  );
}

function pendingGeneratedAttribution(item: CaptureItem) {
  if (item.status === "saved") return "Pending upload";
  if (item.status === "syncing" || item.status === "uploading") return "Uploading";
  return "Generated by AI";
}

function audioPendingTranscriptLabel(item: CaptureItem) {
  if (item.status === "saved") return "Waiting to upload";
  if (item.status === "syncing" || item.status === "uploading") return "Uploading audio";
  return "Transcribing audio";
}

// The ✨ AI provenance mark, shared with the patient-memory surfaces (`.ai-spark`). It animates
// (twinkle + glow) while `working`, so the icon itself signals "AI is processing".
function AiSpark({ working }: { working?: boolean }) {
  return (
    <span className={`ai-spark${working ? " working" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="m12 3 1.4 4.2L17.5 9l-4.1 1.8L12 15l-1.4-4.2L6.5 9l4.1-1.8L12 3ZM5.5 13l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM18 14l.9 2.6 2.6.9-2.6.9L18 21l-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
      </svg>
    </span>
  );
}

// AI-generated text shows the ✨ icon instead of a "Generated by AI" badge; staff edits / upload
// states keep their text label. `working` animates the icon (processing).
function CaptureAttribution({ value, working }: { value: string; working?: boolean }) {
  if (!value) return null;
  if (value === "Generated by AI") {
    return (
      <span className="capture-ai-tag" role="img" aria-label="Generated by AI" title="Generated by AI">
        <AiSpark working={working} />
      </span>
    );
  }
  return <span>{value}</span>;
}

function CaptureGeneratedHeading({ attribution, label }: { attribution: string; label: string }) {
  return (
    <div className="capture-generated-heading">
      <h4>{label}</h4>
      <CaptureAttribution value={attribution} working />
    </div>
  );
}

/** A generated text block (transcript/caption) with an inline Edit affordance (A4). Saved edits
 * carry edited-vs-AI attribution and feed the live report via the same handlers as the source sheet. */
function CaptureGeneratedText({
  label,
  text,
  attribution,
  dir,
  onSave,
  addLabel = "Add",
}: {
  label: string;
  text: string;
  attribution: string;
  dir?: "rtl" | "ltr";
  onSave?: (text: string) => Promise<void>;
  addLabel?: string;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(text);
  const [saving, setSaving] = React.useState(false);
  // No text yet (e.g. an un-captioned Basic photo) → offer a manual "Add" instead of a placeholder.
  const hasText = !!text.trim();
  const start = () => {
    setDraft(text);
    setEditing(true);
  };
  const save = () => {
    if (!onSave || saving || !draft.trim()) return;
    setSaving(true);
    void onSave(draft.trim())
      .then(() => setEditing(false))
      .finally(() => setSaving(false));
  };
  return (
    <>
      <div className="capture-generated-heading">
        <h4>{label}</h4>
        <div className="capture-generated-heading-meta">
          {hasText ? <CaptureAttribution value={attribution} /> : null}
          {onSave && !editing ? (
            <button className="capture-generated-edit" onClick={start} type="button">
              {hasText ? "Edit" : addLabel}
            </button>
          ) : null}
        </div>
      </div>
      {editing ? (
        <div className="capture-generated-editor">
          <textarea aria-label={`Edit ${label.toLowerCase()}`} dir={dir} onChange={(event) => setDraft(event.target.value)} rows={Math.min(8, Math.max(3, Math.ceil(draft.length / 56)))} value={draft} />
          <div className="capture-generated-editor-actions">
            <button className="capture-generated-cancel" onClick={() => setEditing(false)} type="button">
              Cancel
            </button>
            <button className="capture-generated-save" disabled={saving || !draft.trim()} onClick={save} type="button">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : hasText ? (
        <p className="live-draft-preview" dir={dir}>{text}</p>
      ) : null}
    </>
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

function LiveReportView({
  isPro,
  session,
  onResolveFile,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  // A document in both tiers: clinic + patient header from template/DB. Pro is a synthesized,
  // template-driven report; Basic is a clean chronological body with transcripts + images.
  return isPro ? (
    <ProLiveReport session={session} onResolveFile={onResolveFile} />
  ) : (
    <BasicLiveReport session={session} onResolveFile={onResolveFile} />
  );
}

function ReportDocHeader({ session }: { session: CaptureSession | null }) {
  const clinic = session?.report?.template?.clinic;
  const patientInformation = session?.report?.patientInformation || patientInformationFromSession(session);
  return (
    <>
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
    </>
  );
}

function ProLiveReport({
  session,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const bodyParagraphs = workspaceStructuredReportCopy(session);
  // Pro is a deterministic, grouped-by-type document (Audio notes / Written notes / Photos) built
  // without an LLM — render the structured sections (with their headers) so the grouping is visible.
  const sections = (session?.reportModel?.sections || []).filter((section) => section.blocks?.length);
  const isUpdating = session?.processingStatus?.state === "processing" || session?.report?.status === "generating";
  const summary = reportContributionSummary(session);
  const templateLabel = session?.report?.template?.key === "default" || !session?.report?.template?.key ? "Default template" : `${session?.report?.template?.key} template`;
  return (
    <div className="structured-report-view">
      <ReportDocHeader session={session} />
      <div className="report-meta-strip">
        <span className="report-meta-template">{templateLabel}</span>
        {summary ? <span className="report-meta-counts">{summary}</span> : null}
      </div>
      <section className="structured-report-section structured-report-body">
        {sections.length ? (
          sections.map((section) => (
            <section className="workspace-report-section" key={section.id}>
              {section.title ? <h3>{section.title}</h3> : null}
              {section.blocks.map((block, index) => (
                <React.Fragment key={index}>{formatReportBlock(block, onResolveFile)}</React.Fragment>
              ))}
            </section>
          ))
        ) : bodyParagraphs.length ? (
          bodyParagraphs.map((paragraph, index) => (
            <section className="workspace-report-section" key={`${index}-${paragraph.slice(0, 24)}`}>
              {formatReportParagraph(paragraph, onResolveFile)}
            </section>
          ))
        ) : isUpdating || session?.items.length ? (
          <p className="report-doc-status">Preparing the report from your captures…</p>
        ) : (
          <p className="report-doc-status">The report builds here automatically as captures land.</p>
        )}
      </section>
    </div>
  );
}

/** Render one structured report block (paragraph or image) for the Pro live report. */
function formatReportBlock(block: StructuredReportBlock, onResolveFile?: (endpoint: string) => Promise<string>) {
  if (block.type === "image" && block.captureId) {
    return formatReportParagraph(`![${block.caption || "Source image"}](/api/v1/captures/${block.captureId}/file-content)`, onResolveFile);
  }
  if (block.text) return formatReportParagraph(block.text, onResolveFile);
  return null;
}

function BasicLiveReport({
  session,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const items = session?.items || [];
  return (
    <div className="structured-report-view basic-live-report">
      <ReportDocHeader session={session} />
      <section className="structured-report-section structured-report-body">
        {items.length ? (
          items.map((item) => <BasicReportEntry item={item} key={item.sourceUrl || item.id} onResolveFile={onResolveFile} />)
        ) : (
          <p className="report-doc-status">Captures will appear here, in order, as the session develops.</p>
        )}
      </section>
      {items.length ? (
        <TryProTeaser
          className="report-teaser"
          title="Try Pro — turn your notes into a structured treatment report"
          subtitle="Visit summary, assessment, and a Treatment-performed table extracted from your words — no form-filling."
        />
      ) : null}
    </div>
  );
}

function BasicReportEntry({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const text = generatedTextForReport(item) || (item.type === "note" ? item.detail : "");
  const isPhoto = item.type === "photo";
  return (
    <div className={`basic-report-entry ${item.type}`}>
      <span className="basic-report-entry-node" aria-hidden="true">
        <CaptureTimelineIcon type={item.type} />
      </span>
      <div className="basic-report-entry-body">
        <div className="basic-report-entry-time">{item.time}</div>
        {text ? <p dir={textDirection(text)}>{text}</p> : null}
        {isPhoto ? (
          <div className="basic-report-entry-photo">
            <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function reportContributionSummary(session: CaptureSession | null): string {
  const summary = metadataRecord(metadataRecord(session?.extractedMetadata).report_contribution_summary);
  const included = Number(summary.included);
  const setAside = Number(summary.set_aside);
  if (!Number.isFinite(included) || included <= 0) return "";
  const base = `Generated from ${included} capture${included === 1 ? "" : "s"}`;
  return Number.isFinite(setAside) && setAside > 0 ? `${base} · ${setAside} set aside` : base;
}

function reportUpdatingLabel(session: CaptureSession | null): string {
  const pending = (session?.items || []).filter((item) => {
    const status = metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status);
    return status === "pending" || status === "updating" || item.status === "processing" || item.status === "uploaded";
  });
  if (!pending.length) return "Updating the report…";
  const labels = pending.slice(0, 2).map((item, index) => captureDraftLabel(item, index + 1));
  const suffix = pending.length > 2 ? ` +${pending.length - 2}` : "";
  return `Updating for ${labels.join(", ")}${suffix}…`;
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
  if (session.complete) {
    return { badge: "Complete", detail: "Captures processed, patient assigned, and the report is up to date.", kind: "verified", label: "Complete report", tone: "green" };
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
  if (item.type === "audio" || item.type === "voice") return "Transcribing audio...";
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
  const status = metadataDisplay(generatedRecord.status || generatedRecord.state).toLowerCase();
  if (status === "processing" || status === "queued" || status === "running") return "";
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
  // Photos carry no AI caption in Basic (or when captioning is unavailable) — return nothing so the
  // UI offers a manual "Add caption" instead of a placeholder.
  return "";
}

/** Display direction for transcript/caption/note text: RTL when it's predominantly
 * Persian/Arabic script (covers farsi and mixed-farsi), otherwise LTR. */
function textDirection(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
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
    return ["Draft", "Structured", "Complete"].map((label) => ({
      label,
      state: "done",
      className: label === "Complete" ? "done verified" : "done",
    }));
  }
  if (state.kind === "structured") {
    return [
      { label: "Draft", state: "done", className: "done" },
      { label: "Structured", state: "done", className: "done" },
      { label: "Complete", state: "current", className: "current" },
    ];
  }
  return ["Draft", "Structured", "Complete"].map((label, index) => ({
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
  if (session?.complete) {
    return { checked: true, label: "Complete", tone: "success" };
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

function aiPatientActionForSession(session: CaptureSession | null) {
  if (!session?.extractedMetadata) return null;
  const action = metadataRecord(session.extractedMetadata.ai_patient_action);
  return Object.keys(action).length ? action : null;
}

function activePatientAssignmentActionForSession(session: CaptureSession | null) {
  if (!session?.extractedMetadata) return null;
  const action = metadataRecord(session.extractedMetadata.active_patient_assignment_action || session.extractedMetadata.ai_patient_action);
  return Object.keys(action).length ? action : null;
}

type AssignmentCandidate = { patientId: string; displayName: string };

/** Derive each capture's assignment candidate from the session's assignment timeline. */
function sessionAssignmentCandidates(session: CaptureSession | null): {
  activeCaptureId: string;
  activePatientId: string;
  byCapture: Record<string, AssignmentCandidate>;
} {
  const action = metadataRecord(activePatientAssignmentActionForSession(session));
  const actionMeta = metadataRecord(action.actionMetadata);
  const activeCaptureId = metadataDisplay(action.captureId || action.basisCaptureId || actionMeta.basisCaptureId);
  const activePatientId = metadataDisplay(action.patientId || actionMeta.patientId);
  const byCapture: Record<string, AssignmentCandidate> = {};
  const timeline = metadataRecord(session?.extractedMetadata).patient_assignment_timeline;
  if (Array.isArray(timeline)) {
    for (const raw of timeline) {
      const event = metadataRecord(raw);
      const captureId = metadataDisplay(event.captureId);
      const patientId = metadataDisplay(event.patientId);
      if (captureId && patientId) byCapture[captureId] = { patientId, displayName: metadataDisplay(event.displayName) };
    }
  }
  return { activeCaptureId, activePatientId, byCapture };
}

/** The reassignment a capture offers when it is not the current source (a switchable alternate). */
function alternateCandidateForCapture(
  candidates: ReturnType<typeof sessionAssignmentCandidates>,
  captureId: string,
): AssignmentCandidate | null {
  const candidate = candidates.byCapture[captureId];
  if (!candidate) return null;
  if (captureId === candidates.activeCaptureId) return null;
  if (candidate.patientId === candidates.activePatientId) return null;
  return candidate;
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
  if (italic) return <p dir={textDirection(italic[1])}><em>{italic[1]}</em></p>;
  if (paragraph.startsWith("# ")) {
    const heading = paragraph.replace(/^#\s+/, "");
    return <h3 dir={textDirection(heading)}>{heading}</h3>;
  }
  if (paragraph.startsWith("## ")) {
    const heading = paragraph.replace(/^##\s+/, "");
    return <h4 dir={textDirection(heading)}>{heading}</h4>;
  }
  if (paragraph.startsWith("- ")) {
    return (
      <ul>
        {paragraph.split(/\n-\s+/).map((item) => {
          const text = item.replace(/^-\s+/, "");
          return (
            <li dir={textDirection(text)} key={item}>{text}</li>
          );
        })}
      </ul>
    );
  }
  if (paragraph.includes("\n- ")) {
    const [intro, ...items] = paragraph.split(/\n-\s+/);
    return (
      <>
        {intro.trim() ? <p dir={textDirection(intro.trim())}>{intro.trim()}</p> : null}
        <ul>
          {items.filter(Boolean).map((item) => (
            <li dir={textDirection(item)} key={item}>{item}</li>
          ))}
        </ul>
      </>
    );
  }
  return <p dir={textDirection(paragraph)}>{paragraph}</p>;
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
