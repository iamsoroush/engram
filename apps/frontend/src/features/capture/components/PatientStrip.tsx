// Session-layout-diet epic (AES-1301..1305): the pinned, collapsible **patient strip** that absorbs
// identity + context + verify state + safety into one line above the report, so the phone above-the-fold
// becomes [thin AI-usage bar] → [one-line strip] → [report] with everything one tap away. Active
// conflicts stay in a thin always-visible band above the report (never buried); the strip is a second
// entry point. Safety is never buried: a red chip is always shown collapsed, and a high-risk tenant pins
// the full panel open. On (re)assignment of a patient WITH history the strip auto-surfaces that history.
import React from "react";
import { useT } from "../../../shared/i18n";
import { textDirection } from "../captureModel";
import { PatientIcon, EditIcon, AddPatientIcon, ClockHistoryIcon } from "./CaptureIcons";

/** The transition inputs the auto-collapse state machine watches. */
export type StripSignals = { assignmentSignal: string; reportHasContent: boolean; hasCaptures: boolean };

/** Pre-capture the strip is a glance aid (expanded); everything else opens collapsed. */
export function stripInitialExpanded(isHistorical: boolean, hasCaptures: boolean): boolean {
  return !isHistorical && !hasCaptures;
}

/**
 * The pure auto-collapse decision (AES-1302). Given the previous → next signals and whether the
 * patient's history has been surfaced yet, returns the expanded state to force (`null` = no change,
 * leave a manual toggle intact) and the updated `surfaced` flag. Rules, later-wins:
 * - undo all captures → re-expand (return to the pre-capture glance);
 * - report gains content → collapse, but only once history is surfaced (or there is none);
 * - a (re)assignment of a patient WITH history → surface it (expand) — wins over a simultaneous collapse.
 */
export function stripTransition(
  prev: StripSignals,
  next: StripSignals,
  opts: { hasHistory: boolean; surfaced: boolean },
): { expanded: boolean | null; surfaced: boolean } {
  let expanded: boolean | null = null;
  let surfaced = opts.surfaced;
  if (prev.hasCaptures && !next.hasCaptures) expanded = true;
  if (!prev.reportHasContent && next.reportHasContent && (opts.surfaced || !opts.hasHistory)) expanded = false;
  if (next.assignmentSignal !== prev.assignmentSignal && opts.hasHistory) {
    expanded = true;
    surfaced = true;
  }
  return { expanded, surfaced };
}

export function PatientStrip({
  patientName,
  assigned,
  assignmentStateLabel,
  visitOrdinalLabel,
  onAssignOrChange,
  onViewHistory,
  verifyCount,
  onReview,
  safetyChipCount,
  hasCaptures,
  reportHasContent,
  hasHistory,
  assignmentSignal,
  isHistorical,
  contextCard,
  safetyPanel,
  aiCreatedPanel,
  verifyRef,
}: {
  patientName: string;
  /** Whether a patient is assigned (vs. the soft-amber unassigned state). */
  assigned: boolean;
  /** "✓ assigned" / "Matched by AI" / "Unassigned · Assign" — chrome; the name is content. */
  assignmentStateLabel: string;
  visitOrdinalLabel: string | null;
  onAssignOrChange?: () => void;
  onViewHistory?: () => void;
  /** Sticky "N to confirm" count (blockers only) — an amber chip; 0 hides it. */
  verifyCount: number;
  /** Expand the strip + scroll to the verify surface. */
  onReview: () => void;
  /** Kept safety flags on record — a red chip when >0 (unless the panel is pinned open by the parent). */
  safetyChipCount: number;
  hasCaptures: boolean;
  reportHasContent: boolean;
  hasHistory: boolean;
  /** Changes on every (re)assignment (patientId + source) so the machine can re-surface history. */
  assignmentSignal: string;
  isHistorical: boolean;
  /** The deterministic session-context digest (rendered in the expansion). */
  contextCard?: React.ReactNode;
  /** The full safety panel (rendered in the expansion; the parent renders it pinned when high-risk). */
  safetyPanel?: React.ReactNode;
  /** The AI-created-patient verification panel (rendered in the expansion, reached by the ⚠ chip). */
  aiCreatedPanel?: React.ReactNode;
  /** Ref on the verify surface inside the expansion (the "Review" scroll target). */
  verifyRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const t = useT();
  const [expanded, setExpanded] = React.useState(() => stripInitialExpanded(isHistorical, hasCaptures));
  const surfacedRef = React.useRef(false);
  const prevRef = React.useRef<StripSignals>({ assignmentSignal, reportHasContent, hasCaptures });

  // Pre-capture (or any) expansion of a patient WITH history counts as surfacing it.
  React.useEffect(() => {
    if (expanded && hasHistory) surfacedRef.current = true;
  }, [expanded, hasHistory]);

  // Drive the default expanded state off signal TRANSITIONS (a manual toggle in between still sticks —
  // the effect only re-decides when an input actually changes).
  React.useEffect(() => {
    const prev = prevRef.current;
    const next: StripSignals = { assignmentSignal, reportHasContent, hasCaptures };
    prevRef.current = next;
    if (isHistorical) return;
    const { expanded: forced, surfaced } = stripTransition(prev, next, { hasHistory, surfaced: surfacedRef.current });
    surfacedRef.current = surfaced;
    if (forced !== null) setExpanded(forced);
  }, [assignmentSignal, reportHasContent, hasCaptures, hasHistory, isHistorical]);

  const review = () => {
    setExpanded(true);
    onReview();
  };

  const collapsedLine = (
    <div className={`patient-strip-line${assigned ? " assigned" : " unassigned"}`}>
      <span className="patient-strip-avatar" aria-hidden="true">
        <PatientIcon />
      </span>
      <button
        type="button"
        className="patient-strip-identity"
        onClick={() => setExpanded(true)}
        aria-expanded={false}
        title={t("strip.showContext")}
      >
        <strong dir={textDirection(patientName)}>{patientName}</strong>
        {visitOrdinalLabel ? <span className="patient-strip-ordinal">· {visitOrdinalLabel}</span> : null}
        <span className={`patient-strip-state${assigned ? "" : " unassigned"}`}>{assignmentStateLabel}</span>
      </button>
      <span className="patient-strip-chips">
        {verifyCount > 0 ? (
          <button type="button" className="patient-strip-chip verify" onClick={review}>
            <span aria-hidden="true">⚠</span> {t("strip.toConfirm", { count: verifyCount })}
          </button>
        ) : null}
        {safetyChipCount > 0 ? (
          <button type="button" className="patient-strip-chip safety" onClick={review} aria-label={t("strip.safetyAria", { count: safetyChipCount })}>
            <span aria-hidden="true">🩹</span>
          </button>
        ) : null}
        {/* Never hide the pending Assign action while unassigned (soft-amber, a decision is pending). */}
        {!assigned && onAssignOrChange ? (
          <button type="button" className="patient-strip-assign" onClick={onAssignOrChange}>
            {t("capture.assign")}
          </button>
        ) : null}
      </span>
      <button type="button" className="patient-strip-chevron" onClick={() => setExpanded(true)} aria-label={t("strip.showContext")} title={t("strip.showContext")}>
        <span aria-hidden="true">⌄</span>
      </button>
    </div>
  );

  if (!expanded) return <section className="patient-strip collapsed">{collapsedLine}</section>;

  return (
    <section className="patient-strip expanded">
      <header className="patient-strip-header">
        <span className="patient-strip-avatar" aria-hidden="true">
          <PatientIcon />
        </span>
        <div className="patient-strip-copy">
          <strong dir={textDirection(patientName)}>{patientName}</strong>
          <p>
            {assignmentStateLabel}
            {visitOrdinalLabel ? <span className="patient-strip-ordinal"> · {visitOrdinalLabel}</span> : null}
          </p>
        </div>
        <div className="patient-strip-actions">
          {assigned && onViewHistory ? (
            <button type="button" className="patient-strip-action" onClick={onViewHistory}>
              <ClockHistoryIcon />
              {t("capture.history")}
            </button>
          ) : null}
          {onAssignOrChange ? (
            <button type="button" className={`patient-strip-action${assigned ? "" : " primary"}`} onClick={onAssignOrChange}>
              {assigned ? (
                <>
                  <EditIcon />
                  {t("capture.change")}
                </>
              ) : (
                <>
                  <AddPatientIcon />
                  {t("capture.assign")}
                </>
              )}
            </button>
          ) : null}
          {!isHistorical ? (
            <button type="button" className="patient-strip-chevron" onClick={() => setExpanded(false)} aria-label={t("strip.hideContext")} title={t("strip.hideContext")}>
              <span aria-hidden="true">⌃</span>
            </button>
          ) : null}
        </div>
      </header>
      {safetyPanel}
      {contextCard}
      {aiCreatedPanel ? (
        <div className="patient-strip-verify" ref={verifyRef}>
          {aiCreatedPanel}
        </div>
      ) : null}
    </section>
  );
}
