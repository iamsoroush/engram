// Live report views (pro/basic) + markdown rendering for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { CaptureItem, CaptureSession, SessionTreatment, SessionTreatmentReview, StructuredPatientInformation, StructuredReportBlock, TreatmentOverlayEntry } from "../../../domain/types";
import { useT, type Translator } from "../../../shared/i18n";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { CaptureRawPreview } from "./SourcePreview";
import { CaptureTimelineIcon } from "./CaptureBadges";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { reportFreshness, patientInformationFromSession, workspaceStructuredReportCopy, workspaceTreatments, treatmentLabel, treatmentAttributeLines, isLowConfidenceTreatment, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionTreatmentOverlay, sessionTreatmentOverlayOrphans, sessionAiOrganizing, aiOrganizingNotice, generatedTextForReport, textDirection } from "../captureModel";

// Persian section titles, keyed by the fixed section id (mirrors the ai_engine's SYNTHESIS_SECTIONS).
// Applied at render so EXISTING reports (synthesized before titles were localized) and the
// deterministic baseline show Persian headings immediately when the report language is Persian.
const REPORT_SECTION_TITLES_FA: Record<string, string> = {
  "visit-summary": "خلاصه ویزیت",
  "concern-goals": "نگرانی‌ها و اهداف",
  "assessment": "ارزیابی",
  "treatment-performed": "درمان انجام‌شده",
  "media": "تصاویر",
  "plan-followup": "برنامه و پیگیری",
  "aftercare": "مراقبت‌های بعد از درمان",
  "clinical-report": "گزارش بالینی",
};

function isPersianReport(reportLanguage?: string | null): boolean {
  return Boolean(reportLanguage && reportLanguage.trim().toLowerCase().startsWith("fa"));
}

// (G7) Planned treatments (future-tense / stated intent) rendered as a calm line under Plan & follow-up
// — NOT as performed. The treatment content (area/product/dose) follows the report language; only the
// "Planned" chrome label is localized via t(). A tap on the line opens its source capture.
function PlannedTreatments({
  treatments,
  isPersian,
  onOpenSource,
}: {
  treatments: SessionTreatment[];
  isPersian: boolean;
  onOpenSource?: (captureId: string) => void;
}) {
  const t = useT();
  if (!treatments.length) return null;
  return (
    <ul className="report-planned-treatments" dir={isPersian ? "rtl" : "ltr"}>
      {treatments.map((treatment, index) => (
        <li className="report-planned-treatment" key={treatment.treatmentKey || `${treatment.area}-${treatment.product}-${index}`}>
          <span className="report-planned-label">{t("report.plannedLabel")}</span>{" "}
          <span className="report-planned-body" dir={textDirection(treatmentLabel(treatment))}>{treatmentLabel(treatment)}</span>
          <SourceCitation captureIds={treatment.sourceCaptureIds} onOpenSource={onOpenSource} />
        </li>
      ))}
    </ul>
  );
}

// Persian / Arabic script range — used to infer the report's language from its own content when the
// tenant's `report_language` is unset (NULL), so section TITLES match the (Persian) body instead of
// silently falling back to English headings (R1).
const PERSIAN_SCRIPT_RE = /[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/;

/** Resolve whether the report should render Persian section titles.
 *
 * Order: an explicit `report_language` wins (fa → Persian; en/ar → not Persian, English headings).
 * When it is NULL/unknown, infer from the report's OWN content script (the body the AI wrote follows
 * the transcript), then fall back to the app language. This keeps titles and body in agreement even
 * for a tenant whose `report_language` was never set. */
function resolveReportIsPersian(
  reportLanguage: string | null | undefined,
  contentSample: string,
  appLanguage: string | null | undefined,
): boolean {
  const rl = (reportLanguage || "").trim().toLowerCase();
  if (rl.startsWith("fa")) return true;
  if (rl.startsWith("en") || rl.startsWith("ar")) return false;
  if (contentSample && PERSIAN_SCRIPT_RE.test(contentSample)) return true;
  return (appLanguage || "").trim().toLowerCase().startsWith("fa");
}

/** A small text sample of the report's own content, to infer its language when unset. */
function reportContentSample(
  sections: Array<{ blocks?: StructuredReportBlock[] }>,
  bodyParagraphs: string[],
  treatments: SessionTreatment[],
): string {
  const parts: string[] = [];
  for (const section of sections) for (const block of section.blocks || []) if (block.text) parts.push(block.text);
  for (const paragraph of bodyParagraphs) parts.push(paragraph);
  for (const treatment of treatments) {
    if (treatment.area) parts.push(treatment.area);
    if (treatment.product) parts.push(treatment.product);
  }
  return parts.join(" ");
}

/** Localized section title, given the already-resolved report-is-Persian flag (English by default). */
function localizedSectionTitle(sectionId: string, fallback: string, isPersian: boolean): string {
  if (isPersian) return REPORT_SECTION_TITLES_FA[sectionId] || fallback;
  return fallback;
}

export function LiveReportView({
  isPro,
  session,
  onResolveFile,
  onConfirmCarriedForward,
  onFixAtSource,
  onOpenSource,
  onEditTreatmentField,
  onRevertTreatmentField,
  canEditTreatments,
  currentUserId,
  reportLanguage,
  appLanguage,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  /** Open the Sources drawer to correct a flagged treatment at its capture (Pro, unified layout). */
  onFixAtSource?: () => void;
  /** Tap a claim (treatment row / cited block) → open its source capture ("assistive + cited"). */
  onOpenSource?: (captureId: string) => void;
  /** AES-1102: record a human field edit on a treatment row (deterministic overlay, no re-synthesis). */
  onEditTreatmentField?: (treatmentKey: string, field: string, value: string) => Promise<void> | void;
  /** AES-1103: Revert-to-AI / Use-AI for one (treatmentKey, field). */
  onRevertTreatmentField?: (treatmentKey: string, field: string) => Promise<void> | void;
  /** Whether the viewer may author treatment edits (owner-default gating; false = read-only rows). */
  canEditTreatments?: boolean;
  /** The signed-in user's id, so an edit reads "Edited by you" vs a colleague's. */
  currentUserId?: string | null;
  /** Report-content language — localizes the section titles (distinct from app UI language). */
  reportLanguage?: string | null;
  /** App UI language — coarse fallback for the section-title language when reportLanguage is unset. */
  appLanguage?: string | null;
}) {
  // A document in both tiers: clinic + patient header from template/DB. Pro is a synthesized,
  // template-driven report; Basic is a clean chronological body with transcripts + images.
  return isPro ? (
    <ProLiveReport
      session={session}
      onResolveFile={onResolveFile}
      onConfirmCarriedForward={onConfirmCarriedForward}
      onFixAtSource={onFixAtSource}
      onOpenSource={onOpenSource}
      onEditTreatmentField={onEditTreatmentField}
      onRevertTreatmentField={onRevertTreatmentField}
      canEditTreatments={canEditTreatments}
      currentUserId={currentUserId}
      reportLanguage={reportLanguage}
      appLanguage={appLanguage}
    />
  ) : (
    <BasicLiveReport session={session} onResolveFile={onResolveFile} />
  );
}

/**
 * Clinic + patient header for the report. NOT shown in the live in-session view (that's for glancing
 * at the report as it builds); reserved for the export / shared-report surfaces where the document
 * needs its letterhead. The patient share renders its own clinic header (PatientSharePage).
 */
export function ReportDocHeader({ session }: { session: CaptureSession | null }) {
  const t = useT();
  const clinic = session?.report?.template?.clinic;
  const patientInformation = session?.report?.patientInformation || patientInformationFromSession(session, t);
  return (
    <>
      <section className="structured-report-section">
        <h3>{t("report.clinicInfo")}</h3>
        <p>{t("report.clinicPrefix", { name: clinic?.name || t("report.clinicFallback") })}</p>
        {(clinic?.information?.length ? clinic.information : [t("report.clinicFallbackLine")]).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </section>
      <section className="structured-report-section">
        <h3>{t("report.patientInfo")}</h3>
        <PatientInformationRows patientInformation={patientInformation} />
      </section>
    </>
  );
}

export function ProLiveReport({
  session,
  onResolveFile,
  onConfirmCarriedForward,
  onFixAtSource,
  onOpenSource,
  onEditTreatmentField,
  onRevertTreatmentField,
  canEditTreatments,
  currentUserId,
  reportLanguage,
  appLanguage,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  onFixAtSource?: () => void;
  onOpenSource?: (captureId: string) => void;
  onEditTreatmentField?: (treatmentKey: string, field: string, value: string) => Promise<void> | void;
  onRevertTreatmentField?: (treatmentKey: string, field: string) => Promise<void> | void;
  canEditTreatments?: boolean;
  currentUserId?: string | null;
  reportLanguage?: string | null;
  appLanguage?: string | null;
}) {
  const t = useT();
  const overlayEntries = sessionTreatmentOverlay(session);
  const bodyParagraphs = workspaceStructuredReportCopy(session);
  // Render the report's structured sections (with their headers). This one path serves both report
  // models: the deterministic baseline's by-type grouping (Audio notes / Written notes / Photos) AND
  // the Pro synthesis's fixed clinical sections (visit-summary, concern-goals, assessment,
  // treatment-performed, media, plan-followup, aftercare) — each is just {id, title, blocks}.
  const sections = (session?.reportModel?.sections || []).filter((section) => section.blocks?.length);
  // Performed treatments extracted by the Pro synthesis (queryable store + the clinical source of
  // truth that powers carry-forward/recall/exports). It is the SINGLE treatment representation: it
  // renders in place of the synthesis's prose `treatment-performed` section (no duplicate), and as a
  // fallback below the report when no such section exists (e.g. the deterministic baseline).
  const TREATMENT_SECTION_ID = "treatment-performed";
  const PLAN_SECTION_ID = "plan-followup";
  const treatments = workspaceTreatments(session);
  // (G7) Split by lifecycle status: PLANNED treatments (future-tense / stated intent) are NOT performed
  // — they never render in the treatment-performed table; they show as a calm "Planned" line under Plan
  // & follow-up. PERFORMED + UNCERTAIN stay in the performed list (uncertain keeps low-confidence styling).
  const performedTreatments = treatments.filter((treatment) => treatment.status !== "planned");
  const plannedTreatments = treatments.filter((treatment) => treatment.status === "planned");
  const hasTreatmentSection = sections.some((section) => section.id === TREATMENT_SECTION_ID);
  // Resolve the section-title language ONCE for the whole report: an explicit report_language wins,
  // else infer from the report's own (Persian) content, else the app language (R1 — a NULL tenant
  // report_language must not leave English headings above a Persian body).
  const persianReport = resolveReportIsPersian(reportLanguage, reportContentSample(sections, bodyParagraphs, treatments), appLanguage);
  // Clinician-confirmation items the synthesis surfaced (ambiguous correction, carried-forward dose,
  // low confidence, missing lot, free-text uncertainty) from the coded uncertainty_reasons (S-F11) —
  // rendered inline on the matching row where they have a home, else as calm notes below the list.
  const review = sessionTreatmentReview(session);
  // Products the synthesis flagged as missing a lot/batch number — drives a soft inline "lot not
  // captured · fix at source" hint on the matching treatment row (never counted as a blocker).
  const missingLotProducts = new Set(
    review.filter((item) => item.category === "missing_lot").map((item) => (item.product || "").trim()).filter(Boolean),
  );
  // Q3: carried-forward doses the clinician has already confirmed (so they read as done, not pending).
  const confirmedCarriedForward = new Set(sessionConfirmedCarriedForward(session));
  // Carried-forward doses awaiting confirmation, keyed by `area|product` so the inline "Confirm dose"
  // affordance lands on the matching treatment row (the confirmation now lives in the report itself,
  // not in a separate section above it).
  const carriedForwardReasons: Record<string, string> = {};
  review
    .filter((item) => item.category === "carried_forward" && item.key)
    .forEach((item) => {
      carriedForwardReasons[item.key as string] = item.reason;
    });
  const onConfirmCarried =
    onConfirmCarriedForward && session ? (key: string) => onConfirmCarriedForward(session.id, key) : undefined;
  // Which review items already have an INLINE home on a rendered row (so a note would double-surface):
  // a carried-forward dose with a matching row, a missing-lot / low-confidence flag on a matching row.
  const treatmentKeySet = new Set(performedTreatments.map((treatment) => `${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`));
  const missingLotInline = new Set(
    performedTreatments.filter((treatment) => !treatment.lot && treatment.product && missingLotProducts.has((treatment.product || "").trim())).map((treatment) => (treatment.product || "").trim()),
  );
  const lowConfidenceInline = new Set(
    performedTreatments.filter(isLowConfidenceTreatment).map((treatment) => (treatment.product || "").trim()).filter(Boolean),
  );
  const surfacedInline = (item: (typeof review)[number]): boolean => {
    if (item.category === "carried_forward") return Boolean(item.key && treatmentKeySet.has(item.key));
    if (item.category === "missing_lot") return Boolean(item.product && missingLotInline.has(item.product.trim()));
    if (item.category === "low_confidence") return Boolean(item.product && lowConfidenceInline.has(item.product.trim()));
    return false; // an ambiguous / free-text uncertainty has no inline row — it is always a note
  };
  // Every coded review item NOT already surfaced inline becomes a calm note (never silently dropped —
  // e.g. a missing-lot flag whose product didn't render a row). Kept as objects so a note can carry an
  // action: deep-link to its source capture, or fix-at-source for a source-correctable code.
  const reviewNoteItems = review.filter((item) => !surfacedInline(item));
  // Pro "organizing with AI": the deterministic baseline is visible and complete, but the synthesis
  // job is still in flight — show a calm, persistent notice instead of a (false) "current" line.
  const organizing = sessionAiOrganizing(session);
  const isUpdating = session?.processingStatus?.state === "processing" || session?.report?.status === "generating";
  const templateKey = session?.report?.template?.key;
  const templateLabel = templateKey === "default" || !templateKey ? t("report.templateDefault") : t("report.templateNamed", { key: templateKey });
  // Explicit "what this report is based on" status (Pro): current = reflects all captures.
  const freshness = reportFreshness(session, true);
  return (
    <div className="structured-report-view">
      <div className="report-meta-strip">
        <span className="report-meta-template">{templateLabel}</span>
        {organizing ? (
          <span className="report-freshness updating" aria-live="polite">
            <span className="report-freshness-dot" aria-hidden="true" />
            {aiOrganizingNotice(t)}
          </span>
        ) : freshness ? (
          <span className={`report-freshness ${freshness.current ? "current" : "updating"}`} aria-live="polite">
            {freshness.current ? (
              <>
                {t("report.reflectsAll", { n: freshness.included })}
                {freshness.setAside > 0 ? t("report.setAside", { n: freshness.setAside }) : ""}
              </>
            ) : (
              <>
                <span className="report-freshness-dot" aria-hidden="true" />
                {t("report.updatingCount", { pending: freshness.pending, total: freshness.included + freshness.pending })}
              </>
            )}
          </span>
        ) : null}
      </div>
      {/* CONTENT region — report prose/blocks render here in the REPORT language (reportLanguage),
          never app `t()`. `data-content` marks it so a no-English-leak chrome scan can exclude it. */}
      <section className="structured-report-section structured-report-body" data-content data-testid="report-body">
        {sections.length ? (
          sections.map((section) => {
            // The treatment slot renders the structured table (single source of truth), not the
            // synthesis's prose mirror — unless extraction produced nothing, then keep the prose.
            const renderTreatmentTable = section.id === TREATMENT_SECTION_ID && performedTreatments.length > 0;
            return (
              <section className="workspace-report-section" key={section.id}>
                {section.title ? <h3 data-testid="report-section-title" dir={textDirection(localizedSectionTitle(section.id, section.title, persianReport))}>{localizedSectionTitle(section.id, section.title, persianReport)}</h3> : null}
                {renderTreatmentTable ? (
                  <TreatmentsList
                    treatments={performedTreatments}
                    confirmedCarriedForward={confirmedCarriedForward}
                    missingLotProducts={missingLotProducts}
                    onFixAtSource={onFixAtSource}
                    onOpenSource={onOpenSource}
                    isPersian={persianReport}
                    carriedForwardReasons={carriedForwardReasons}
                    onConfirmCarried={onConfirmCarried}
                    reviewNotes={reviewNoteItems}
                    overlayEntries={overlayEntries}
                    canEditTreatments={canEditTreatments}
                    currentUserId={currentUserId}
                    onEditField={onEditTreatmentField}
                    onRevertField={onRevertTreatmentField}
                  />
                ) : section.id === "media" ? (
                  <MediaSection blocks={section.blocks} onResolveFile={onResolveFile} isPersian={persianReport} />
                ) : (
                  section.blocks.map((block, index) => (
                    <React.Fragment key={index}>
                      {formatReportBlock(block, onResolveFile)}
                      <SourceCitation captureIds={block.sourceCaptureIds} onOpenSource={onOpenSource} />
                    </React.Fragment>
                  ))
                )}
                {section.id === PLAN_SECTION_ID ? (
                  <PlannedTreatments treatments={plannedTreatments} isPersian={persianReport} onOpenSource={onOpenSource} />
                ) : null}
              </section>
            );
          })
        ) : bodyParagraphs.length ? (
          bodyParagraphs.map((paragraph, index) => (
            <section className="workspace-report-section" key={`${index}-${paragraph.slice(0, 24)}`}>
              {formatReportParagraph(paragraph, onResolveFile)}
            </section>
          ))
        ) : isUpdating || session?.items.length ? (
          <p className="report-doc-status">{t("report.preparing")}</p>
        ) : (
          <p className="report-doc-status">{t("report.buildsHere")}</p>
        )}
      </section>
      {performedTreatments.length && !hasTreatmentSection ? (
        <section className="structured-report-section treatments-performed">
          <h3 dir={textDirection(localizedSectionTitle("treatment-performed", "Treatments performed", persianReport))}>
            {localizedSectionTitle("treatment-performed", "Treatments performed", persianReport)}
          </h3>
          <TreatmentsList
            treatments={performedTreatments}
            confirmedCarriedForward={confirmedCarriedForward}
            missingLotProducts={missingLotProducts}
            onFixAtSource={onFixAtSource}
            onOpenSource={onOpenSource}
            isPersian={persianReport}
            carriedForwardReasons={carriedForwardReasons}
            onConfirmCarried={onConfirmCarried}
            reviewNotes={reviewNoteItems}
            overlayEntries={overlayEntries}
            canEditTreatments={canEditTreatments}
            currentUserId={currentUserId}
            onEditField={onEditTreatmentField}
            onRevertField={onRevertTreatmentField}
          />
        </section>
      ) : null}
      {/* (G7) Planned treatments when no Plan & follow-up section rendered to host them (deterministic
          baseline, or the model emitted planned items but no plan section) — a calm standalone "Planned" block. */}
      {plannedTreatments.length && !sections.some((section) => section.id === PLAN_SECTION_ID) ? (
        <section className="structured-report-section treatments-planned">
          <h3 dir={textDirection(localizedSectionTitle("plan-followup", "Plan & follow-up", persianReport))}>
            {localizedSectionTitle("plan-followup", "Plan & follow-up", persianReport)}
          </h3>
          <PlannedTreatments treatments={plannedTreatments} isPersian={persianReport} onOpenSource={onOpenSource} />
        </section>
      ) : null}
      {/* Orphaned-overlay review chips (AES-1101): a human edit a re-synthesis couldn't re-bind — parked,
          never deleted, and re-applied if its row returns. Surfaced so a correction is never silently
          lost; Revert drops it if it's genuinely stale. */}
      <TreatmentOverlayOrphans orphans={sessionTreatmentOverlayOrphans(session)} canEdit={canEditTreatments} onRevertField={onRevertTreatmentField} t={t} />
      {/* The clinician's confirmations are embedded in the report itself — the carried-forward dose
          confirm sits on its treatment row (above), not in a separate section. The report thumbs
          rating is an end-cap rendered by CaptureScreen AFTER the aftercare section (rate-after-
          reading), not here mid-report. */}
    </div>
  );
}

/** Parked overlay orphans — surfaced as calm review chips so a re-keyed/removed human edit is never lost. */
function TreatmentOverlayOrphans({
  orphans,
  canEdit,
  onRevertField,
  t,
}: {
  orphans: TreatmentOverlayEntry[];
  canEdit?: boolean;
  onRevertField?: (treatmentKey: string, field: string) => Promise<void> | void;
  t: Translator;
}) {
  const [busy, setBusy] = React.useState<string | null>(null);
  if (!orphans.length) return null;
  return (
    <ul className="treatment-orphans" aria-label={t("overlay.orphansLabel")}>
      {orphans.map((entry) => {
        const id = `${entry.treatmentKey}|${entry.field}`;
        return (
          <li key={id} dir={textDirection(entry.value)}>
            <span className="treatment-orphan-icon" aria-hidden="true">✎</span>
            <span className="treatment-orphan-text">{t("overlay.orphanNote", { field: overlayFieldLabel(entry.field, t), value: entry.value })}</span>
            {canEdit && onRevertField ? (
              <button
                type="button"
                className="treatment-revert-btn"
                disabled={busy === id}
                onClick={() => {
                  setBusy(id);
                  void Promise.resolve(onRevertField(entry.treatmentKey, entry.field)).finally(() => setBusy(null));
                }}
              >
                {busy === id ? t("overlay.reverting") : t("overlay.discardEdit")}
              </button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * A per-claim source citation: a small "↗ source" tap that opens the cited capture (the redesign's
 * "assistive + cited" principle — every clinical claim is traceable to a capture). Renders nothing
 * when there's no citation or no handler, so it's safe to drop next to any treatment row or block.
 */
function SourceCitation({
  captureIds,
  onOpenSource,
}: {
  captureIds?: string[];
  onOpenSource?: (captureId: string) => void;
}) {
  // The citation is a clinician action (chrome), so its label follows the APP language via t() —
  // like every other action chip on the row. (It used to follow the report's content language,
  // which put "منبع" next to an English "Fix at source" on the same row.)
  const t = useT();
  const first = captureIds?.find((id) => typeof id === "string" && id.trim());
  if (!onOpenSource || !first) return null;
  const label = t("report.sourceCitation");
  const title = t("report.sourceCitationTitle");
  const more = (captureIds?.length || 0) > 1 ? ` ·${captureIds?.length}` : "";
  return (
    <button type="button" className="source-citation" onClick={() => onOpenSource(first)} title={title}>
      ↗ {label}
      {more}
    </button>
  );
}

/**
 * The structured performed-treatments list — the single treatment representation in the report
 * (area · product · dose · lot, verbatim quantity preserved). The clinician's confirmations live
 * INLINE here, where the data is: a carried-forward dose shows a "Confirm dose" action right on its
 * own row (Q3), and the synthesis's softer uncertainties render as calm notes beneath the list — so
 * there is no separate "Needs your confirmation" section floating above the report.
 */
function TreatmentsList({
  treatments,
  confirmedCarriedForward,
  missingLotProducts,
  onFixAtSource,
  onOpenSource,
  isPersian,
  carriedForwardReasons,
  onConfirmCarried,
  reviewNotes,
  overlayEntries,
  canEditTreatments,
  currentUserId,
  onEditField,
  onRevertField,
}: {
  treatments: SessionTreatment[];
  confirmedCarriedForward: Set<string>;
  /** Products the synthesis flagged as missing a lot # (soft inline hint, not a counted blocker). */
  missingLotProducts?: Set<string>;
  /** Jump to the Sources drawer to correct a flagged treatment at its capture. */
  onFixAtSource?: () => void;
  /** Tap a treatment row's citation → open its source capture (§2.3 traceability). */
  onOpenSource?: (captureId: string) => void;
  /** Localize the citation label to the report language. */
  isPersian?: boolean;
  /** `area|product` → reason for carried-forward doses awaiting confirmation (Q3). */
  carriedForwardReasons?: Record<string, string>;
  /** Confirm a carried-forward dose by its `area|product` key. */
  onConfirmCarried?: (key: string) => Promise<void>;
  /** Coded review items with no inline home — rendered calmly under the list, source-correctable ones
   *  (missing lot / low confidence) carry a fix action; any item with a source capture deep-links to it. */
  reviewNotes?: SessionTreatmentReview[];
  /** AES-1101 overlay entries for this session (field-edit provenance + reconcile lookup). */
  overlayEntries?: TreatmentOverlayEntry[];
  /** Whether the viewer may author treatment edits (owner-default gating; false = read-only rows). */
  canEditTreatments?: boolean;
  /** The signed-in user's id, so an edit reads "Edited by you" vs a colleague's edit. */
  currentUserId?: string | null;
  /** AES-1102: record a human field edit (deterministic, no re-synthesis). */
  onEditField?: (treatmentKey: string, field: string, value: string) => Promise<void> | void;
  /** AES-1103: Revert-to-AI / Use-AI for one (treatmentKey, field). */
  onRevertField?: (treatmentKey: string, field: string) => Promise<void> | void;
}) {
  const t = useT();
  // treatmentKey → { field → overlay entry } — the row's provenance/reconcile lookup.
  const overlayByKey = React.useMemo(() => {
    const map = new Map<string, Record<string, TreatmentOverlayEntry>>();
    for (const entry of overlayEntries || []) {
      const forKey = map.get(entry.treatmentKey) || {};
      forKey[entry.field] = entry;
      map.set(entry.treatmentKey, forKey);
    }
    return map;
  }, [overlayEntries]);
  return (
    <>
      <ul className="treatments-list">
        {treatments.map((treatment, index) => (
          <TreatmentRow
            key={`${index}-${(treatment.treatmentKey || treatmentLabel(treatment)).slice(0, 32)}`}
            treatment={treatment}
            index={index}
            confirmedCarriedForward={confirmedCarriedForward}
            missingLotProducts={missingLotProducts}
            onFixAtSource={onFixAtSource}
            onOpenSource={onOpenSource}
            isPersian={isPersian}
            carriedForwardReasons={carriedForwardReasons}
            onConfirmCarried={onConfirmCarried}
            overlayByField={treatment.treatmentKey ? overlayByKey.get(treatment.treatmentKey) : undefined}
            canEdit={Boolean(canEditTreatments && treatment.treatmentKey && onEditField)}
            currentUserId={currentUserId}
            onEditField={onEditField}
            onRevertField={onRevertField}
            t={t}
          />
        ))}
      </ul>
      {reviewNotes?.length ? (
        <ul className="treatment-review-notes" aria-label={t("report.notesToReview")}>
          {reviewNotes.map((item, index) => {
            const source = item.sourceCaptureIds?.find((id) => typeof id === "string" && id.trim());
            // A source-correctable code (missing lot / low confidence) offers fix-at-source; any coded
            // item that cites a capture deep-links to it. An ambiguous/free-text note stays informational.
            const fixable = item.category === "missing_lot" || item.category === "low_confidence";
            return (
              <li key={`${index}-${item.reason.slice(0, 24)}`} dir={textDirection(item.reason)}>
                <span className="treatment-review-note-icon" aria-hidden="true">ⓘ</span>
                <span className="treatment-review-note-text">{item.reason}</span>
                {source && onOpenSource ? (
                  <SourceCitation captureIds={item.sourceCaptureIds} onOpenSource={onOpenSource} />
                ) : fixable && onFixAtSource ? (
                  <button type="button" className="treatment-fix-at-source" onClick={onFixAtSource}>
                    {t("report.fixAtSource")}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}

// The treatment fields a clinician may override via the overlay (mirrors the backend
// TREATMENT_OVERLAY_FIELDS). A dose edit targets `quantity` (the verbatim display anchor).
const OVERLAY_FIELDS = ["area", "product", "brand", "quantity", "lot"] as const;
type OverlayField = (typeof OVERLAY_FIELDS)[number];

/** The current displayed value of an editable field (the same anchor the human value replaces). */
function currentFieldValue(treatment: SessionTreatment, field: OverlayField): string {
  if (field === "quantity") {
    return treatment.quantityText || (treatment.quantity != null && treatment.unit ? `${treatment.quantity} ${treatment.unit}` : treatment.quantity != null ? String(treatment.quantity) : "");
  }
  return (treatment[field] as string | null | undefined) || "";
}

function overlayFieldLabel(field: string, t: Translator): string {
  return t(`overlay.field.${field}`);
}

/**
 * One structured treatment row (area · product · brand · quantity · lot). The clinician's inline
 * confirmations live here (carried-forward dose, AES-1101 field-edit overlay). An edited field flips to
 * a human-owned presentation — an "Edited by you" chip + a provenance/reconcile subline preserving the
 * AI value (the verbatim dictation for a dose) — with one-tap Revert-to-AI. The edit is deterministic,
 * instant, and immune to re-mis-extraction (it overrides synthesis on render; a later disagreement
 * surfaces, never overwrites). Editing a carried-forward dose auto-satisfies its confirm blocker (Q4).
 */
function TreatmentRow({
  treatment,
  index,
  confirmedCarriedForward,
  missingLotProducts,
  onFixAtSource,
  onOpenSource,
  isPersian,
  carriedForwardReasons,
  onConfirmCarried,
  overlayByField,
  canEdit,
  currentUserId,
  onEditField,
  onRevertField,
  t,
}: {
  treatment: SessionTreatment;
  index: number;
  confirmedCarriedForward: Set<string>;
  missingLotProducts?: Set<string>;
  onFixAtSource?: () => void;
  onOpenSource?: (captureId: string) => void;
  isPersian?: boolean;
  carriedForwardReasons?: Record<string, string>;
  onConfirmCarried?: (key: string) => Promise<void>;
  overlayByField?: Record<string, TreatmentOverlayEntry>;
  canEdit?: boolean;
  currentUserId?: string | null;
  onEditField?: (treatmentKey: string, field: string, value: string) => Promise<void> | void;
  onRevertField?: (treatmentKey: string, field: string) => Promise<void> | void;
  t: Translator;
}) {
  const [confirming, setConfirming] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [busyField, setBusyField] = React.useState<string | null>(null);
  const label = treatmentLabel(treatment);
  const lowConfidence = isLowConfidenceTreatment(treatment);
  const attributeLines = treatmentAttributeLines(treatment);
  const lotMissing = !treatment.lot && Boolean(treatment.product) && Boolean(missingLotProducts?.has((treatment.product || "").trim()));
  const fixable = lowConfidence || lotMissing;
  const key = `${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`;
  const editedFields = (treatment.overlayEditedFields || []).filter((field): field is OverlayField => (OVERLAY_FIELDS as readonly string[]).includes(field));
  const doseEdited = editedFields.includes("quantity");
  const isCarried = Boolean(treatment.carriedForward);
  const isConfirmed = isCarried && confirmedCarriedForward.has(key);
  // Q4: editing a carried-forward dose IS the confirmation — the row stops asking "Confirm dose".
  const needsConfirm = isCarried && !isConfirmed && !doseEdited && Boolean(onConfirmCarried) && Boolean(carriedForwardReasons && key in carriedForwardReasons);
  const confirmReason = carriedForwardReasons?.[key];
  const treatmentKey = treatment.treatmentKey || "";
  const revert = (field: string) => {
    if (!onRevertField || !treatmentKey || busyField) return;
    setBusyField(field);
    void Promise.resolve(onRevertField(treatmentKey, field)).finally(() => setBusyField(null));
  };
  return (
    <li
      className={`treatment-item${lowConfidence ? " low-confidence" : ""}${lotMissing ? " missing-lot" : ""}${needsConfirm ? " needs-confirm" : ""}${editedFields.length ? " edited" : ""}`}
      dir={textDirection(label)}
    >
      <span className="treatment-item-line">
        {label}
        {isCarried && !needsConfirm ? (
          <span className={`treatment-flag${isConfirmed || doseEdited ? " confirmed" : ""}`}>{t("report.flagCarriedForward")}{isConfirmed || doseEdited ? t("report.flagConfirmedSuffix") : ""}</span>
        ) : null}
        {/* A human-confirmed value clears the amber uncertainty chip (a human vouched for it). */}
        {lowConfidence && !editedFields.length ? <span className="treatment-flag low">{t("report.flagLowConfidence")}</span> : null}
        {lotMissing && !editedFields.includes("lot") ? <span className="treatment-flag low">{t("report.flagLotMissing")}</span> : null}
        {/* A low-confidence / missing-lot row is corrected via the inline ✎ Edit (an instant overlay
            write — the treatment-overlay decision: never route a field correction through a
            re-synthesis). "Fix at source" is gone from the row; the ↗ source citation stays for
            traceability. Coded review NOTES with no editable row keep fix-at-source below the list. */}
        {editedFields.length ? (
          <span className="treatment-edited-chip">
            <span aria-hidden="true">✎</span>{" "}
            {overlayByField && editedFields.every((field) => overlayByField[field]?.editedByUserId === currentUserId)
              ? t("overlay.editedByYou")
              : t("overlay.editedByClinician")}
          </span>
        ) : null}
        <SourceCitation captureIds={treatment.sourceCaptureIds} onOpenSource={onOpenSource} />
        {canEdit ? (
          <button type="button" className="treatment-edit-btn" onClick={() => setEditing((open) => !open)} aria-expanded={editing} aria-label={t("overlay.editRow")} title={t("overlay.editRow")}>
            <span aria-hidden="true">✎</span>
          </button>
        ) : null}
      </span>
      {attributeLines.length ? (
        <span className="treatment-attributes" dir={textDirection(attributeLines.join(" · "))}>
          {attributeLines.join(" · ")}
        </span>
      ) : null}
      {/* Provenance + reconcile per edited field: the AI value stays visible (verbatim dictation for a
          dose) and one tap adopts it — the guarantee that synthesis can never overwrite a human value
          without it being seen. Backend ships {aiValue, value}; Keep-yours is the default (do nothing). */}
      {editedFields.map((field) => {
        const entry = overlayByField?.[field];
        const aiValue = entry?.aiValue?.trim();
        if (!aiValue) return null;
        return (
          <span className="treatment-provenance" key={field} dir={textDirection(aiValue)}>
            <span className="treatment-provenance-text">
              {t("overlay.aiReads", { field: overlayFieldLabel(field, t), value: aiValue })}
            </span>
            {onRevertField ? (
              <button type="button" className="treatment-revert-btn" disabled={busyField === field} onClick={() => revert(field)}>
                {busyField === field ? t("overlay.reverting") : t("overlay.useAi")}
              </button>
            ) : null}
          </span>
        );
      })}
      {editing && canEdit && treatmentKey ? (
        <TreatmentFieldEditor
          treatment={treatment}
          onClose={() => setEditing(false)}
          onSave={async (field, value) => {
            if (!onEditField) return;
            setBusyField(field);
            try {
              await onEditField(treatmentKey, field, value);
            } finally {
              setBusyField(null);
            }
          }}
          t={t}
        />
      ) : null}
      {needsConfirm ? (
        <span className="treatment-confirm">
          <span className="treatment-confirm-reason" dir={textDirection(confirmReason || "")}>
            {confirmReason || t("report.confirmReasonDefault")}
          </span>
          <button
            type="button"
            className="treatment-confirm-btn"
            disabled={confirming}
            onClick={async () => {
              if (!onConfirmCarried) return;
              setConfirming(true);
              try {
                await onConfirmCarried(key);
              } finally {
                setConfirming(false);
              }
            }}
          >
            {confirming ? t("report.confirming") : t("report.confirmDose")}
          </button>
        </span>
      ) : isConfirmed ? (
        <span className="treatment-confirmed">{t("report.doseConfirmed")}</span>
      ) : null}
    </li>
  );
}

/** The compact per-field editor a row's ✎ opens. Editable: area · product · brand · quantity · lot.
 *  Each changed field is saved as its own overlay entry (deterministic, instant, no synthesis). Values
 *  are clinical CONTENT, per-line RTL (a Latin brand/lot stays LTR inside an RTL row); only chrome via t. */
function TreatmentFieldEditor({
  treatment,
  onClose,
  onSave,
  t,
}: {
  treatment: SessionTreatment;
  onClose: () => void;
  onSave: (field: OverlayField, value: string) => Promise<void>;
  t: Translator;
}) {
  const [drafts, setDrafts] = React.useState<Record<OverlayField, string>>(() => {
    const initial = {} as Record<OverlayField, string>;
    for (const field of OVERLAY_FIELDS) initial[field] = currentFieldValue(treatment, field);
    return initial;
  });
  const [saving, setSaving] = React.useState(false);
  const save = async () => {
    if (saving) return;
    setSaving(true);
    try {
      // Only write fields the clinician actually changed to a non-empty value (clearing → use Revert).
      for (const field of OVERLAY_FIELDS) {
        const next = drafts[field].trim();
        if (next && next !== currentFieldValue(treatment, field).trim()) await onSave(field, next);
      }
      onClose();
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="treatment-editor">
      {OVERLAY_FIELDS.map((field) => (
        <label className="treatment-editor-field" key={field}>
          <span className="treatment-editor-label">{overlayFieldLabel(field, t)}</span>
          <input
            value={drafts[field]}
            dir={textDirection(drafts[field])}
            onChange={(event) => setDrafts((current) => ({ ...current, [field]: event.target.value }))}
            aria-label={overlayFieldLabel(field, t)}
          />
        </label>
      ))}
      <div className="treatment-editor-actions">
        <button type="button" className="treatment-editor-cancel" onClick={onClose} disabled={saving}>
          {t("badge.cancel")}
        </button>
        <button type="button" className="treatment-editor-save" onClick={save} disabled={saving}>
          {saving ? t("badge.saving") : t("badge.save")}
        </button>
      </div>
    </div>
  );
}

/** Render one structured report block (paragraph or image) for the Pro live report. */
export function formatReportBlock(block: StructuredReportBlock, onResolveFile?: (endpoint: string) => Promise<string>) {
  if (block.type === "image" && block.captureId) {
    return formatReportParagraph(`![${block.caption || "Source image"}](/api/v1/captures/${block.captureId}/file-content)`, onResolveFile);
  }
  if (block.text) return formatReportParagraph(block.text, onResolveFile);
  return null;
}

type MediaUnit =
  | { kind: "pair"; before: StructuredReportBlock; after: StructuredReportBlock }
  | { kind: "block"; block: StructuredReportBlock };

/** Group a media section's image blocks into before/after pairs from their deterministic
 * `photo_pairing` (the rendering consumes pairs, it never pairs). Unpaired blocks pass through. */
export function pairMediaBlocks(blocks: StructuredReportBlock[]): MediaUnit[] {
  const byCapture = new Map<string, StructuredReportBlock>();
  for (const block of blocks) if (block.type === "image" && block.captureId) byCapture.set(block.captureId, block);
  const consumed = new Set<string>();
  const units: MediaUnit[] = [];
  for (const block of blocks) {
    if (block.type === "image" && block.captureId && consumed.has(block.captureId)) continue;
    const partnerId = block.pairing?.pairedCaptureId || undefined;
    const role = block.pairing?.role;
    if (block.type === "image" && block.captureId && partnerId && byCapture.has(partnerId) && !consumed.has(partnerId) && (role === "before" || role === "after")) {
      const partner = byCapture.get(partnerId) as StructuredReportBlock;
      const before = role === "after" ? partner : block;
      const after = role === "after" ? block : partner;
      consumed.add(block.captureId);
      consumed.add(partnerId);
      units.push({ kind: "pair", before, after });
    } else {
      units.push({ kind: "block", block });
    }
  }
  return units;
}

/** The report `media` section: before/after pairs render as the slider, the rest as plain images. */
export function MediaSection({
  blocks,
  onResolveFile,
  isPersian,
}: {
  blocks: StructuredReportBlock[];
  onResolveFile: (endpoint: string) => Promise<string>;
  isPersian?: boolean;
}) {
  return (
    <>
      {pairMediaBlocks(blocks).map((unit, index) =>
        unit.kind === "pair" ? (
          <BeforeAfterSlider
            key={`pair-${unit.before.captureId}-${unit.after.captureId}`}
            before={{ captureId: unit.before.captureId, caption: unit.before.caption }}
            after={{ captureId: unit.after.captureId, caption: unit.after.caption }}
            onResolveFile={onResolveFile}
            isPersian={isPersian}
          />
        ) : (
          <React.Fragment key={`block-${index}`}>{formatReportBlock(unit.block, onResolveFile)}</React.Fragment>
        ),
      )}
    </>
  );
}

export function BasicLiveReport({
  session,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const t = useT();
  const items = session?.items || [];
  return (
    <div className="structured-report-view basic-live-report">
      <section className="structured-report-section structured-report-body" data-content data-testid="report-body">
        {items.length ? (
          items.map((item) => <BasicReportEntry item={item} key={item.sourceUrl || item.id} onResolveFile={onResolveFile} />)
        ) : (
          <p className="report-doc-status">{t("report.basicEmpty")}</p>
        )}
      </section>
      {items.length ? (
        <TryProTeaser
          className="report-teaser"
          title={t("report.tryProTitle")}
          subtitle={t("report.tryProSubtitle")}
        />
      ) : null}
    </div>
  );
}

export function BasicReportEntry({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const text = generatedTextForReport(item) || (item.type === "note" ? item.detail : "");
  const isPhoto = item.type === "photo";
  return (
    <div className={`basic-report-entry ${item.type}`}>
      <span className="basic-report-entry-node" aria-hidden="true">
        <CaptureTimelineIcon type={item.type} />
      </span>
      <div className="basic-report-entry-body">
        <div className="basic-report-entry-time">{item.time}</div>
        {text ? <p dir={textDirection(text)}>{text}</p> : null}
        {isPhoto ? (
          <div className="basic-report-entry-photo">
            <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Whether the live report currently reflects EVERY in-context capture (Pro), for an explicit
 * freshness line so the doctor knows the report's basis. A capture is "in the report" once its
 * report_contribution is `added` (the deterministic regen folds processed, in-context captures in
 * and marks them added); anything else (still processing, or pending/updating) is not yet included.
 */
export function PatientInformationRows({ patientInformation }: { patientInformation: StructuredPatientInformation | null }) {
  const t = useT();
  if (!patientInformation || patientInformation.status !== "assigned") return <p>{t("report.patientUnassigned")}</p>;
  const rows = [
    [t("report.field.fullName"), patientInformation.displayName],
    [t("report.field.nationalId"), patientInformation.nationalId],
    [t("report.field.dob"), patientInformation.dateOfBirth],
    [t("report.field.sex"), patientInformation.sex],
    [t("report.field.phone"), patientInformation.phone],
    [t("report.field.email"), patientInformation.email],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) return <p>{t("report.patientAssigned")}</p>;
  return (
    <dl className="structured-report-patient-info">
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

export function formatReportParagraph(paragraph: string, onResolveFile?: (endpoint: string) => Promise<string>) {
  const image = paragraph.match(/^!\[(.*)]\((.*)\)$/);
  if (image) {
    return <MarkdownImage alt={image[1] || "Report image"} src={image[2]} onResolveFile={onResolveFile} />;
  }
  const italic = paragraph.match(/^\*(.*)\*$/);
  if (italic) return <p dir={textDirection(italic[1])}><em>{italic[1]}</em></p>;
  if (paragraph.startsWith("# ")) {
    const heading = paragraph.replace(/^#\s+/, "");
    return <h3 dir={textDirection(heading)}>{heading}</h3>;
  }
  if (paragraph.startsWith("## ")) {
    const heading = paragraph.replace(/^##\s+/, "");
    return <h4 dir={textDirection(heading)}>{heading}</h4>;
  }
  if (paragraph.startsWith("- ")) {
    return (
      <ul>
        {paragraph.split(/\n-\s+/).map((item) => {
          const text = item.replace(/^-\s+/, "");
          return (
            <li dir={textDirection(text)} key={item}>{text}</li>
          );
        })}
      </ul>
    );
  }
  if (paragraph.includes("\n- ")) {
    const [intro, ...items] = paragraph.split(/\n-\s+/);
    return (
      <>
        {intro.trim() ? <p dir={textDirection(intro.trim())}>{intro.trim()}</p> : null}
        <ul>
          {items.filter(Boolean).map((item) => (
            <li dir={textDirection(item)} key={item}>{item}</li>
          ))}
        </ul>
      </>
    );
  }
  return <p dir={textDirection(paragraph)}>{paragraph}</p>;
}

export function MarkdownImage({
  alt,
  src,
  onResolveFile,
}: {
  alt: string;
  src: string;
  onResolveFile?: (endpoint: string) => Promise<string>;
}) {
  const t = useT();
  const [resolvedUrl, setResolvedUrl] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    if (!onResolveFile || !src.startsWith("/api/v1/")) return;
    onResolveFile(src)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [onResolveFile, src]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  const imageSrc = resolvedUrl || (src.startsWith("/api/v1/") ? "" : src);
  return imageSrc ? <img alt={alt} className="structured-report-body-image" src={imageSrc} /> : <p>{t("report.imageUnavailable")}</p>;
}
