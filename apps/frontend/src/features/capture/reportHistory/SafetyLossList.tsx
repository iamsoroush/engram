// Shared safety-loss list for the E17 restore/undo confirm guards (finding 1): names exactly which
// safety flags a de-effect would drop — from the visit, and whether from the patient file too. Chrome is
// bilingual via t(); the clinical flag TEXT is CONTENT — rendered verbatim + bidi-isolated, never
// translated. Used by the ReportHistorySheet restore confirm and the Sources-drawer removal guard.
import React from "react";
import type { SafetyLossFlag } from "../../../domain/types";
import { useT } from "../../../shared/i18n";

export function SafetyLossList({ flags }: { flags: SafetyLossFlag[] }) {
  const t = useT();
  if (!flags.length) return null;
  return (
    <div className="report-history-safety-loss" role="alert">
      <p className="report-history-safety-loss-title">{t("capture.history.safetyLossTitle")}</p>
      <ul className="report-history-safety-loss-list">
        {flags.map((flag) => (
          <li className={`report-history-safety-loss-item safety-${flag.kind}`} key={flag.key}>
            <span className="report-history-safety-loss-kind">{t(`safety.kind.${flag.kind}`)}</span>
            {/* Clinical content: verbatim + bidi-isolated so a fa flag reads correctly under en chrome. */}
            <bdi className="report-history-safety-loss-text">{flag.text}</bdi>
            <span className="report-history-safety-loss-scope">
              {flag.alsoRemovedFromPatient
                ? t("capture.history.safetyLossFromPatient")
                : t("capture.history.safetyLossStaysOnPatient")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
