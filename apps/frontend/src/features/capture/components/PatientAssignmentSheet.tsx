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
import { useT } from "../../../shared/i18n";

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
  const t = useT();
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
          <h2 id="assignment-sheet-title">{currentAssignedPatient ? t("assign.changePatient") : t("assign.assignPatient")}</h2>
          {onCancel ? (
            <Button aria-label={t("assign.closeAssignment")} onClick={onCancel} size="sm" type="button" variant="ghost">
              <span aria-hidden="true">x</span>
            </Button>
          ) : null}
        </div>
        {currentAssignedPatient ? (
          <section className="assignment-current-patient" aria-label={t("assign.currentlyAssignedPatientRegion")}>
            <span className="assignment-patient-avatar" aria-hidden="true">
              <PatientIcon />
            </span>
            <div className="assignment-patient-copy">
              <small>{session.assignmentSource ? t("assign.currentlyAssignedSource", { source: assignmentSourceLabel(session.assignmentSource, t) }) : t("assign.currentlyAssigned")}</small>
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
                <span>{patientIdentifierLabel(currentAssignedPatient, t)}</span>
              )}
            </div>
            <button
              className="assignment-unassign"
              disabled={saving}
              onClick={() => assignDraft({ unassign: true, displayName: "" })}
              type="button"
            >
              {t("assign.unassign")}
            </button>
          </section>
        ) : (
          <p className="assignment-no-patient">{t("assign.noPatientAssigned")}</p>
        )}
        <label className="assignment-search-field">
          <span aria-hidden="true">
            <SearchIcon />
          </span>
          <Input
            className="assignment-search-input"
            aria-label={t("assign.searchPatients")}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("assign.searchPlaceholder")}
            value={query}
          />
        </label>
        <div className="assignment-section-heading">
          <h3>{t("assign.suggestedMatches")}</h3>
          {searching ? <span>{t("assign.searching")}</span> : null}
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
                  <span>{patientIdentifierLabel(patient, t)}</span>
                  <small>
                    {alreadyAssigned
                      ? t("assign.matchAssignedToVisit")
                      : detectedIds.has(patient.id)
                        ? t("assign.matchDetectedInSession")
                        : t("assign.matchLastVisit", { date: formatLastVisit(patient.lastVisit) })}
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
                  {alreadyAssigned ? t("assign.assigned") : saving ? t("assign.saving") : t("assign.select")}
                </Button>
              </article>
              );
            })
          ) : (
            <p className="assignment-empty">{t("assign.noMatchesYet")}</p>
          )}
        </div>
        <div className="assignment-divider"><span>{t("assign.or")}</span></div>
        <section className="assignment-create-panel" aria-label={t("assign.createNewPatientPanel")}>
          <h3>{t("assign.createNewPatientHeading")}</h3>
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
              submitLabel={t("assign.createNewPatientSubmit")}
            />
          ) : (
            <Button className="assignment-create-button" onClick={() => setCreating(true)} type="button">
              <AddPatientIcon />
              {trimmedQuery ? t("assign.createNewPatientQuery", { q: trimmedQuery }) : t("assign.createNewPatient")}
            </Button>
          )}
        </section>
      </section>
    </div>
  );
}
