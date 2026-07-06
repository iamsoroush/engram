import React from "react";
import { useT } from "../../shared/i18n";

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
  onChange,
}: {
  initial?: Partial<PatientFormValues>;
  loading?: boolean;
  busy?: boolean;
  submitLabel: string;
  onSubmit: (values: PatientFormValues) => void;
  onCancel?: () => void;
  /** Observe the live values (e.g. to run the AES-205 duplicate-guard as fields are typed). */
  onChange?: (values: PatientFormValues) => void;
}) {
  const t = useT();
  const [values, setValues] = React.useState<PatientFormValues>({ ...EMPTY, ...initial });
  const seededRef = React.useRef(false);

  React.useEffect(() => {
    if (loading || seededRef.current) return;
    setValues({ ...EMPTY, ...initial });
    seededRef.current = true;
  }, [loading, initial]);

  React.useEffect(() => {
    onChange?.(values);
  }, [values, onChange]);

  const set = (key: keyof PatientFormValues) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  const canSubmit = values.displayName.trim().length > 0 && !busy && !loading;
  const submit = () => {
    if (!canSubmit) return;
    onSubmit({ ...values, displayName: values.displayName.trim() });
  };

  return (
    <div className="patient-form">
      {loading ? <p className="patient-form-loading">{t("patientform.loading")}</p> : null}
      <div className="patient-form-grid">
        <label className="patient-form-field">
          <span>{t("patientform.fullName")}</span>
          <input data-content disabled={loading} onChange={set("displayName")} placeholder={t("patientform.fullNamePlaceholder")} value={values.displayName} />
        </label>
        <label className="patient-form-field">
          <span>{t("patientform.nationalId")}</span>
          <input data-content disabled={loading} onChange={set("nationalId")} placeholder={t("patientform.optional")} value={values.nationalId} />
        </label>
        <label className="patient-form-field">
          <span>{t("patientform.phone")}</span>
          <input data-content disabled={loading} onChange={set("phone")} placeholder={t("patientform.optional")} value={values.phone} />
        </label>
        <label className="patient-form-field">
          <span>{t("patientform.dateOfBirth")}</span>
          <input data-content disabled={loading} onChange={set("dateOfBirth")} placeholder={t("patientform.dateOfBirthPlaceholder")} value={values.dateOfBirth} />
        </label>
        <label className="patient-form-field">
          <span>{t("patientform.sex")}</span>
          <select className="select" data-content disabled={loading} onChange={set("sex")} value={values.sex}>
            <option value="">{t("patientform.sexUnspecified")}</option>
            <option value="female">{t("patientform.sexFemale")}</option>
            <option value="male">{t("patientform.sexMale")}</option>
            <option value="other">{t("patientform.sexOther")}</option>
          </select>
        </label>
        <label className="patient-form-field patient-form-field-wide">
          <span>{t("patientform.notes")}</span>
          <textarea data-content disabled={loading} onChange={set("notes")} placeholder={t("patientform.optional")} rows={2} value={values.notes} />
        </label>
      </div>
      <div className="patient-form-actions">
        {onCancel ? (
          <button className="patient-form-cancel" onClick={onCancel} type="button">
            {t("patientform.cancel")}
          </button>
        ) : null}
        <button className="patient-form-save" disabled={!canSubmit} onClick={submit} type="button">
          {busy ? t("patientform.saving") : submitLabel}
        </button>
      </div>
    </div>
  );
}
