// Patient assignment sheet for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { PatientAssignmentDraft, PatientSummary } from "../../../domain/appTypes";
import type { CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import { assignmentSourceLabel } from "../metadata";
import { Button, Input } from "../../../shared/ui/primitives";
import { PatientForm } from "../../patient/PatientForm";
import { patientDetailRows, detectedSessionPatients, currentSessionPatient, filterPatientMatches, mergePatientMatches, samePatientSummary, patientIdentifierLabel, formatLastVisit } from "../captureModel";
import { PatientIcon, SearchIcon, AddPatientIcon } from "./CaptureIcons";

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
