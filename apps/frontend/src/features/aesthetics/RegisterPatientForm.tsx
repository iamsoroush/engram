import React from "react";
import type { DuplicateCandidate, DuplicateCheckResponse } from "../../domain/appTypes";
import { PatientForm, type PatientFormValues } from "../patient/PatientForm";
import { useT } from "../../shared/i18n";

/**
 * AES-601 + AES-205 — register a patient (name required, rest fill-later) with the deterministic,
 * Persian-orthography-aware duplicate guard. As the name / national ID / phone are typed, a
 * near-match check runs; a STRONG match warns BEFORE a duplicate is created. "Use this" adopts the
 * existing record; "Create anyway" never blocks. Never auto-merges.
 */
export function RegisterPatientForm({
  initialName,
  busy,
  onDuplicateCheck,
  onSubmit,
  onUseExisting,
  onCancel,
}: {
  initialName?: string;
  busy?: boolean;
  onDuplicateCheck?: (body: { displayName?: string; nationalId?: string; phone?: string }) => Promise<DuplicateCheckResponse>;
  onSubmit: (values: PatientFormValues) => void;
  onUseExisting?: (candidate: DuplicateCandidate) => void;
  onCancel?: () => void;
}) {
  const t = useT();
  const [values, setValues] = React.useState<PatientFormValues | null>(null);
  const [result, setResult] = React.useState<DuplicateCheckResponse | null>(null);
  const [checking, setChecking] = React.useState(false);

  const displayName = values?.displayName.trim() || "";
  const nationalId = values?.nationalId.trim() || "";
  const phone = values?.phone.trim() || "";

  React.useEffect(() => {
    if (!onDuplicateCheck || (!displayName && !nationalId && !phone)) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setChecking(true);
    const timer = window.setTimeout(() => {
      void onDuplicateCheck({ displayName: displayName || undefined, nationalId: nationalId || undefined, phone: phone || undefined })
        .then((response) => {
          if (!cancelled) setResult(response);
        })
        .catch(() => {
          if (!cancelled) setResult(null);
        })
        .finally(() => {
          if (!cancelled) setChecking(false);
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [onDuplicateCheck, displayName, nationalId, phone]);

  const flagged = Boolean(result?.hasLikelyDuplicate);
  const candidates = result?.candidates || [];

  return (
    <div className="register-patient">
      {flagged ? (
        <section className="dup-guard" aria-label={t("patientform.dupGuardAria")}>
          <div className="dup-guard-head">
            <WarnIcon />
            {t("patientform.dupGuardHead")}
          </div>
          <p className="dup-guard-sub">
            {candidates.length === 1 ? t("patientform.dupGuardSubOne", { n: candidates.length }) : t("patientform.dupGuardSubMany", { n: candidates.length })}
          </p>
          <div className="dup-guard-matches">
            {candidates.map((candidate) => (
              <div className="dup-guard-match" key={candidate.patientId}>
                <span className="dup-guard-avatar" aria-hidden="true">{initials(candidate.displayName)}</span>
                <div className="dup-guard-copy">
                  <strong data-content dir={textDir(candidate.displayName)}>{candidate.displayName}</strong>
                  <span data-content>{candidate.reason}</span>
                </div>
                {onUseExisting ? (
                  <button className="dup-guard-use" onClick={() => onUseExisting(candidate)} type="button">
                    {t("patientform.dupGuardUse")}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <PatientForm
        busy={busy}
        initial={{ displayName: initialName || "" }}
        onCancel={onCancel}
        onChange={setValues}
        onSubmit={onSubmit}
        submitLabel={flagged ? t("patientform.createAnyway") : checking ? t("patientform.checking") : t("patientform.createPatient")}
      />
    </div>
  );
}

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "?"
  );
}

function textDir(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

function WarnIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true" className="dup-guard-icon">
      <path d="M12 4 3 19.5h18L12 4Z" />
      <path d="M12 10v4.5" />
      <path d="M12 17.2h.01" />
    </svg>
  );
}
