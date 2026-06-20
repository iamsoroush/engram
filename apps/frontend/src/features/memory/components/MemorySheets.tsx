// Resolver/review sheets for the Clinical Memory screens.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { AssignmentSuggestionResponse, LastVisitInfo, PatientAssignmentDraft, PatientMemoryDetailResponse, PatientSummary } from "../../../domain/appTypes";
import type { CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import type { PatientEditDraft } from "../../../services/api/client";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { PatientForm } from "../../patient/PatientForm";
import { LastVisitStrip } from "../../aesthetics/LastVisitStrip";
import { PatientRowModel, PatientNeedsInputItem, StorageWarningDecision, labelForDecisionAction, patientChoiceCandidates, extractedPatientMatchHint, filterPatientMatches, resolverCaptureSummary, patientHint, sessionVisitTitle, naturalSessionSummary, reviewSummaryText, sessionTimeLabel, formatBytes, avatarInitials } from "./memoryModel";
import { SearchIcon, ChevronIcon } from "./MemoryIcons";
import { PatientHistoryBlock, EmptyClinicalState, CaptureChips, LineupCard } from "./MemoryCards";

export function PatientIdentityEditor({
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

export function PatientRecapSheet({
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
          {/* The glanceable line-up card (Pro): hero photo + ≤2 paragraphs + since-last-visit + flags. */}
          <LineupCard card={detail?.lineupCard} isPro={isPro} onResolveFile={onResolveFile} />
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

export function PatientDecisionListSheet({
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

export function SummaryReviewSheet({
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

export function StorageReviewSheet({
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

export function ChoosePatientResolver({
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

export function PatientChoiceButton({
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

export function AssignPatientResolver({
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
