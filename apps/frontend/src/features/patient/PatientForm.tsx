import React from "react";

export type PatientFormValues = {
  displayName: string;
  nationalId: string;
  phone: string;
  dateOfBirth: string;
  sex: string;
  notes: string;
};

const EMPTY: PatientFormValues = { displayName: "", nationalId: "", phone: "", dateOfBirth: "", sex: "", notes: "" };

/**
 * One shared patient identity form (B3) — used for creating a new patient and for editing an
 * existing one. `initial` may arrive asynchronously (e.g. a getPatient prefill); the form seeds
 * itself once those values land and disables inputs while `loading`.
 */
export function PatientForm({
  initial,
  loading,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Partial<PatientFormValues>;
  loading?: boolean;
  busy?: boolean;
  submitLabel: string;
  onSubmit: (values: PatientFormValues) => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = React.useState<PatientFormValues>({ ...EMPTY, ...initial });
  const seededRef = React.useRef(false);

  React.useEffect(() => {
    if (loading || seededRef.current) return;
    setValues({ ...EMPTY, ...initial });
    seededRef.current = true;
  }, [loading, initial]);

  const set = (key: keyof PatientFormValues) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  const canSubmit = values.displayName.trim().length > 0 && !busy && !loading;
  const submit = () => {
    if (!canSubmit) return;
    onSubmit({ ...values, displayName: values.displayName.trim() });
  };

  return (
    <div className="patient-form">
      {loading ? <p className="patient-form-loading">Loading current details…</p> : null}
      <div className="patient-form-grid">
        <label className="patient-form-field">
          <span>Full name</span>
          <input disabled={loading} onChange={set("displayName")} placeholder="Patient name" value={values.displayName} />
        </label>
        <label className="patient-form-field">
          <span>National ID</span>
          <input disabled={loading} onChange={set("nationalId")} placeholder="Optional" value={values.nationalId} />
        </label>
        <label className="patient-form-field">
          <span>Phone</span>
          <input disabled={loading} onChange={set("phone")} placeholder="Optional" value={values.phone} />
        </label>
        <label className="patient-form-field">
          <span>Date of birth</span>
          <input disabled={loading} onChange={set("dateOfBirth")} placeholder="YYYY-MM-DD" value={values.dateOfBirth} />
        </label>
        <label className="patient-form-field">
          <span>Sex</span>
          <select disabled={loading} onChange={set("sex")} value={values.sex}>
            <option value="">Unspecified</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="patient-form-field patient-form-field-wide">
          <span>Notes</span>
          <textarea disabled={loading} onChange={set("notes")} placeholder="Optional" rows={2} value={values.notes} />
        </label>
      </div>
      <div className="patient-form-actions">
        {onCancel ? (
          <button className="patient-form-cancel" onClick={onCancel} type="button">
            Cancel
          </button>
        ) : null}
        <button className="patient-form-save" disabled={!canSubmit} onClick={submit} type="button">
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </div>
  );
}
