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

/**
 * The pure auto-collapse **default** (AES-1302) — derived from the current signals, not from
 * transitions, so it is correct however the screen arrives at a state (including opening a session
 * whose report already has content). A manual toggle overrides this default until the next
 * assignment/undo-to-glance event. Rules:
 * - historical review → collapsed (no pending actions);
 * - **pre-capture** (no captures, no report content) → expanded (a glance aid before you capture);
 * - a patient **with history whose history hasn't been surfaced yet** → expanded (surface it —
 *   this is the (re)assignment auto-surface: `surfaced` resets on every assignment);
 * - otherwise (report/capture in progress, and history surfaced or absent) → collapsed.
 */
export function stripDefaultExpanded(opts: {
  isHistorical: boolean;
  hasCaptures: boolean;
  reportHasContent: boolean;
  hasHistory: boolean;
  surfaced: boolean;
}): boolean {
  if (opts.isHistorical) return false;
  const inProgress = opts.hasCaptures || opts.reportHasContent;
  if (!inProgress) return true;
  if (opts.hasHistory && !opts.surfaced) return true;
  return false;
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
  expandSignal,
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
  /** Bumped by the guided attention review to force the strip open (so the AI-created-patient verify
   *  panel is in the DOM to scroll to / highlight). A changing value expands; 0/undefined does nothing. */
  expandSignal?: number;
}) {
  const t = useT();
  // Whether the current patient's history has been surfaced (shown expanded while the report has
  // content) — gates the auto-collapse. Resets on every (re)assignment so history re-surfaces.
  const [surfaced, setSurfaced] = React.useState(false);
  // The clinician's explicit toggle, which overrides the derived default until the next
  // (re)assignment or undo-to-glance event. `null` = follow the default.
  const [override, setOverride] = React.useState<boolean | null>(null);
  const inProgress = hasCaptures || reportHasContent;

  // A (re)assignment re-surfaces the (new) patient's history and clears the manual choice.
  React.useEffect(() => {
    setSurfaced(false);
    setOverride(null);
  }, [assignmentSignal]);

  // Guided attention review asks the strip to open (the verify panel must exist to scroll to).
  React.useEffect(() => {
    if (expandSignal) setOverride(true);
  }, [expandSignal]);

  // Undoing back to the pre-capture glance clears the manual choice (returns to the default).
  const prevInProgress = React.useRef(inProgress);
  React.useEffect(() => {
    if (prevInProgress.current && !inProgress) setOverride(null);
    prevInProgress.current = inProgress;
  }, [inProgress]);

  const wantExpanded = stripDefaultExpanded({ isHistorical, hasCaptures, reportHasContent, hasHistory, surfaced });
  const expanded = override ?? wantExpanded;
  const setExpanded = (value: boolean) => setOverride(value);

  // Showing history while the report has content marks it surfaced → the strip may now auto-collapse
  // (the "collapse only after report-has-content AND history-surfaced" rule).
  React.useEffect(() => {
    if (expanded && hasHistory && reportHasContent && !surfaced) setSurfaced(true);
  }, [expanded, hasHistory, reportHasContent, surfaced]);

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
