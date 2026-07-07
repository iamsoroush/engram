// Capture-screen region components (frontend-refactor plan §4, increment 8, seam E). Cohesive slices
// of the CaptureScreen render body lifted into self-contained components so the deferred capture-screen
// UX epics (session-layout diet, user-authored treatment overlay) attach to a region instead of a
// 700-line monolith. Behavior-preserving: each renders the exact JSX it replaced; the parent still
// composes them and owns the surrounding state/refs (the verify-region ref stays parent-owned so the
// "Review" scroll target is unchanged).
import React from "react";
import type { PatientAssignmentDraft, SafetyFlag } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Button } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
import { textDirection } from "../captureModel";
import { AiCreatedPatientPanel, PatientConflictResolver, type PatientConflictSuggestion } from "./CaptureBadges";

/** Session-level safety panel — auto-kept allergy/contraindication/consent flags, opt-out via ×. Sits
 *  above the context card + verify region. Flag body is report-language clinical content (dir auto);
 *  only the chrome routes through the app translator. */
export function SessionSafetyPanel({
  flags,
  sessionId,
  canEdit,
  onReject,
}: {
  flags: SafetyFlag[];
  sessionId: string;
  canEdit: boolean;
  onReject?: (sessionId: string, flagKey: string) => Promise<void> | void;
}) {
  const t = useT();
  if (!flags.length) return null;
  return (
    <section className="session-safety-panel" aria-label={t("capture.safety.label")}>
      <div className="session-safety-head">
        <span className="session-safety-label">{t("capture.safety.label")}</span>
        <span className="session-safety-hint">{t("capture.safety.hint")}</span>
      </div>
      {flags.map((flag) => (
        <div className={`session-safety-flag safety-${flag.kind}`} key={flag.key}>
          <span className="session-safety-kind">{t(`safety.kind.${flag.kind}`)}</span>
          <p className="session-safety-text" dir={textDirection(flag.text)}>
            {flag.text}
          </p>
          {canEdit && onReject ? (
            <button
              className="session-safety-remove"
              type="button"
              aria-label={t("capture.safety.reject")}
              title={t("capture.safety.reject")}
              onClick={() => onReject(sessionId, flag.key)}
            >
              ✕
            </button>
          ) : null}
        </div>
      ))}
    </section>
  );
}

/** AES-903/301 — a bar to file the current unassigned visit onto the doctor's next lined-up patient
 *  (or start their visit) without leaving capture. The parent decides whether it applies. */
export function NextLinedUpBar({
  patientName,
  hasCaptures,
  onAssignActiveToNext,
  onStartNextVisit,
}: {
  patientName: string;
  hasCaptures: boolean;
  onAssignActiveToNext?: () => void;
  onStartNextVisit?: () => void;
}) {
  const t = useT();
  return (
    <div className="next-lined-up" role="note">
      <span className="next-lined-up-copy">
        {t("capture.nextInYourList")} <strong dir={textDirection(patientName)}>{patientName}</strong>
      </span>
      <span className="next-lined-up-actions">
        {hasCaptures && onAssignActiveToNext ? (
          <Button size="sm" type="button" onClick={onAssignActiveToNext}>
            {t("capture.assignThisVisit")}
          </Button>
        ) : null}
        {onStartNextVisit ? (
          <Button size="sm" variant="secondary" type="button" onClick={onStartNextVisit}>
            {t("capture.startTheirVisit")}
          </Button>
        ) : null}
      </span>
    </div>
  );
}

type CompleteAiCreatedPatient = (
  sessionId: string,
  patientId: string,
  draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
  action: Record<string, unknown>,
) => Promise<void>;

/** The session verify region (FB8): patient conflicts + an AI-created-patient identity panel, above the
 *  report so every blocker is reachable without opening the Sources drawer. The parent renders it only
 *  when there is something to verify and owns the ref (the "Review" scroll target). */
export function SessionReviewRegion({
  session,
  aiPatientAction,
  onCompleteAiCreatedPatient,
  patientConflicts,
  onAssignPatient,
  onApplyNameCorrection,
  onUnassign,
  onOpenResolver,
  onDismissConflict,
  regionRef,
}: {
  session: CaptureSession;
  aiPatientAction: Record<string, unknown> | null;
  onCompleteAiCreatedPatient?: CompleteAiCreatedPatient;
  patientConflicts: Array<{ captureId: string; suggestion: PatientConflictSuggestion | null }>;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  /** E1 one-tap: apply a `suggested_name_correction` from the capture that raised it. */
  onApplyNameCorrection?: (basisCaptureId: string, spokenName: string) => void | Promise<void>;
  /** E1 one-tap: apply a `suggested_unassign` from the capture that raised it. */
  onUnassign?: (basisCaptureId: string) => void | Promise<void>;
  onOpenResolver?: () => void;
  onDismissConflict: (captureId: string) => void;
  regionRef: React.RefObject<HTMLDivElement | null>;
}) {
  const t = useT();
  return (
    <div className="session-verify-region" ref={regionRef}>
      {patientConflicts.length ? (
        <section className="session-patient-conflicts" aria-label={t("capture.patientNeedsConfirmation")}>
          <span className="session-patient-conflicts-label">{t("capture.patientNeedsConfirmation")}</span>
          {patientConflicts.map((conflict) => (
            <PatientConflictResolver
              key={conflict.captureId}
              suggestion={conflict.suggestion as Exclude<typeof conflict.suggestion, null>}
              basisCaptureId={conflict.captureId}
              onApply={onAssignPatient ? (draft) => onAssignPatient(session.id, draft) : undefined}
              onApplyNameCorrection={onApplyNameCorrection ? (spokenName) => onApplyNameCorrection(conflict.captureId, spokenName) : undefined}
              onUnassign={onUnassign ? () => onUnassign(conflict.captureId) : undefined}
              onChooseAnother={onOpenResolver}
              onDismiss={() => onDismissConflict(conflict.captureId)}
            />
          ))}
        </section>
      ) : null}
      {aiPatientAction && onCompleteAiCreatedPatient ? (
        <AiCreatedPatientPanel action={aiPatientAction} session={session} onComplete={onCompleteAiCreatedPatient} />
      ) : null}
    </div>
  );
}
