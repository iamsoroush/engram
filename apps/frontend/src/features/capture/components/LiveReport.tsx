// Live report views (pro/basic) + markdown rendering for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { CaptureItem, CaptureSession, SessionTreatment, StructuredPatientInformation, StructuredReportBlock } from "../../../domain/types";
import { useT } from "../../../shared/i18n";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { CaptureRawPreview } from "./SourcePreview";
import { CaptureTimelineIcon } from "./CaptureBadges";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { reportFreshness, patientInformationFromSession, workspaceStructuredReportCopy, workspaceTreatments, treatmentLabel, treatmentAttributeLines, isLowConfidenceTreatment, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionAiOrganizing, aiOrganizingNotice, generatedTextForReport, textDirection } from "../captureModel";

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

/** Localized section title for the report language (the stored/English title by default). */
function localizedSectionTitle(sectionId: string, fallback: string, reportLanguage?: string | null): string {
  if (isPersianReport(reportLanguage)) return REPORT_SECTION_TITLES_FA[sectionId] || fallback;
  return fallback;
}

export function LiveReportView({
  isPro,
  session,
  onResolveFile,
  onConfirmCarriedForward,
  onFixAtSource,
  onOpenSource,
  reportLanguage,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  /** Open the Sources drawer to correct a flagged treatment at its capture (Pro, unified layout). */
  onFixAtSource?: () => void;
  /** Tap a claim (treatment row / cited block) → open its source capture ("assistive + cited"). */
  onOpenSource?: (captureId: string) => void;
  /** Report-content language — localizes the section titles (distinct from app UI language). */
  reportLanguage?: string | null;
}) {
  // A document in both tiers: clinic + patient header from template/DB. Pro is a synthesized,
  // template-driven report; Basic is a clean chronological body with transcripts + images.
  return isPro ? (
    <ProLiveReport session={session} onResolveFile={onResolveFile} onConfirmCarriedForward={onConfirmCarriedForward} onFixAtSource={onFixAtSource} onOpenSource={onOpenSource} reportLanguage={reportLanguage} />
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
  const patientInformation = session?.report?.patientInformation || patientInformationFromSession(session);
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
  reportLanguage,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  onFixAtSource?: () => void;
  onOpenSource?: (captureId: string) => void;
  reportLanguage?: string | null;
}) {
  const t = useT();
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
  const treatments = workspaceTreatments(session);
  const hasTreatmentSection = sections.some((section) => section.id === TREATMENT_SECTION_ID);
  // Clinician-confirmation items the synthesis surfaced (ambiguous correction, carried-forward dose,
  // low confidence, missing lot, free-text uncertainty) — rendered as calm chips below the report.
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
  // The synthesis's softer uncertainties (not the carried-forward dose, not the per-row low-confidence
  // / missing-lot hints) — shown as calm notes beneath the treatments list.
  const reviewNotes = review
    .filter((item) => item.category !== "carried_forward" && item.category !== "low_confidence" && item.category !== "missing_lot")
    .map((item) => item.reason)
    .filter(Boolean);
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
      <section className="structured-report-section structured-report-body">
        {sections.length ? (
          sections.map((section) => {
            // The treatment slot renders the structured table (single source of truth), not the
            // synthesis's prose mirror — unless extraction produced nothing, then keep the prose.
            const renderTreatmentTable = section.id === TREATMENT_SECTION_ID && treatments.length > 0;
            return (
              <section className="workspace-report-section" key={section.id}>
                {section.title ? <h3 dir={textDirection(localizedSectionTitle(section.id, section.title, reportLanguage))}>{localizedSectionTitle(section.id, section.title, reportLanguage)}</h3> : null}
                {renderTreatmentTable ? (
                  <TreatmentsList
                    treatments={treatments}
                    confirmedCarriedForward={confirmedCarriedForward}
                    missingLotProducts={missingLotProducts}
                    onFixAtSource={onFixAtSource}
                    onOpenSource={onOpenSource}
                    isPersian={isPersianReport(reportLanguage)}
                    carriedForwardReasons={carriedForwardReasons}
                    onConfirmCarried={onConfirmCarried}
                    reviewNotes={reviewNotes}
                  />
                ) : section.id === "media" ? (
                  <MediaSection blocks={section.blocks} onResolveFile={onResolveFile} isPersian={isPersianReport(reportLanguage)} />
                ) : (
                  section.blocks.map((block, index) => (
                    <React.Fragment key={index}>
                      {formatReportBlock(block, onResolveFile)}
                      <SourceCitation captureIds={block.sourceCaptureIds} onOpenSource={onOpenSource} isPersian={isPersianReport(reportLanguage)} />
                    </React.Fragment>
                  ))
                )}
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
      {treatments.length && !hasTreatmentSection ? (
        <section className="structured-report-section treatments-performed">
          <h3 dir={textDirection(localizedSectionTitle("treatment-performed", "Treatments performed", reportLanguage))}>
            {localizedSectionTitle("treatment-performed", "Treatments performed", reportLanguage)}
          </h3>
          <TreatmentsList
            treatments={treatments}
            confirmedCarriedForward={confirmedCarriedForward}
            missingLotProducts={missingLotProducts}
            onFixAtSource={onFixAtSource}
            onOpenSource={onOpenSource}
            isPersian={isPersianReport(reportLanguage)}
            carriedForwardReasons={carriedForwardReasons}
            onConfirmCarried={onConfirmCarried}
            reviewNotes={reviewNotes}
          />
        </section>
      ) : null}
      {/* The clinician's confirmations are embedded in the report itself — the carried-forward dose
          confirm sits on its treatment row (above), not in a separate section. The report thumbs
          rating is an end-cap rendered by CaptureScreen AFTER the aftercare section (rate-after-
          reading), not here mid-report. */}
    </div>
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
  isPersian,
}: {
  captureIds?: string[];
  onOpenSource?: (captureId: string) => void;
  isPersian?: boolean;
}) {
  const first = captureIds?.find((id) => typeof id === "string" && id.trim());
  if (!onOpenSource || !first) return null;
  const label = isPersian ? "منبع" : "source";
  const title = isPersian ? "نمایش ضبط منبع" : "Open the source capture";
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
  /** The synthesis's softer uncertainties (ambiguous notes), rendered calmly under the list. */
  reviewNotes?: string[];
}) {
  const [confirmingKey, setConfirmingKey] = React.useState<string | null>(null);
  const t = useT();
  return (
    <>
      <ul className="treatments-list">
        {treatments.map((treatment, index) => {
          const label = treatmentLabel(treatment);
          const lowConfidence = isLowConfidenceTreatment(treatment);
          const attributeLines = treatmentAttributeLines(treatment);
          const lotMissing = !treatment.lot && Boolean(treatment.product) && Boolean(missingLotProducts?.has((treatment.product || "").trim()));
          // Soft, fixable extraction gaps point the doctor to the source capture (the lot/dose is fixed
          // by editing what was captured, then the AI re-extracts — never overwritten by a manual edit).
          const fixable = lowConfidence || lotMissing;
          const key = `${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`;
          const isCarried = Boolean(treatment.carriedForward);
          const isConfirmed = isCarried && confirmedCarriedForward.has(key);
          // A carried-forward dose needs confirmation only when the synthesis flagged it (key present) —
          // keeps the inline confirm in lock-step with the sticky "N to confirm" bar's count.
          const needsConfirm = isCarried && !isConfirmed && Boolean(onConfirmCarried) && Boolean(carriedForwardReasons && key in carriedForwardReasons);
          const confirmReason = carriedForwardReasons?.[key];
          return (
            <li
              className={`treatment-item${lowConfidence ? " low-confidence" : ""}${lotMissing ? " missing-lot" : ""}${needsConfirm ? " needs-confirm" : ""}`}
              dir={textDirection(label)}
              key={`${index}-${label.slice(0, 24)}`}
            >
              <span className="treatment-item-line">
                {label}
                {/* When the inline confirm box is shown it already says "carried forward", so the line
                    flag would be redundant — only show it when there's no pending confirm box. */}
                {isCarried && !needsConfirm ? (
                  <span className={`treatment-flag${isConfirmed ? " confirmed" : ""}`}>{t("report.flagCarriedForward")}{isConfirmed ? t("report.flagConfirmedSuffix") : ""}</span>
                ) : null}
                {lowConfidence ? <span className="treatment-flag low">{t("report.flagLowConfidence")}</span> : null}
                {lotMissing ? <span className="treatment-flag low">{t("report.flagLotMissing")}</span> : null}
                {fixable && onFixAtSource ? (
                  <button type="button" className="treatment-fix-at-source" onClick={onFixAtSource}>
                    {t("report.fixAtSource")}
                  </button>
                ) : null}
                <SourceCitation captureIds={treatment.sourceCaptureIds} onOpenSource={onOpenSource} isPersian={isPersian} />
              </span>
              {attributeLines.length ? (
                <span className="treatment-attributes" dir={textDirection(attributeLines.join(" · "))}>
                  {attributeLines.join(" · ")}
                </span>
              ) : null}
              {needsConfirm ? (
                <span className="treatment-confirm">
                  <span className="treatment-confirm-reason" dir={textDirection(confirmReason || "")}>
                    {confirmReason || t("report.confirmReasonDefault")}
                  </span>
                  <button
                    type="button"
                    className="treatment-confirm-btn"
                    disabled={confirmingKey === key}
                    onClick={async () => {
                      if (!onConfirmCarried) return;
                      setConfirmingKey(key);
                      try {
                        await onConfirmCarried(key);
                      } finally {
                        setConfirmingKey(null);
                      }
                    }}
                  >
                    {confirmingKey === key ? t("report.confirming") : t("report.confirmDose")}
                  </button>
                </span>
              ) : isConfirmed ? (
                <span className="treatment-confirmed">{t("report.doseConfirmed")}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {reviewNotes?.length ? (
        <ul className="treatment-review-notes" aria-label={t("report.notesToReview")}>
          {reviewNotes.map((note, index) => (
            <li key={`${index}-${note.slice(0, 24)}`} dir={textDirection(note)}>
              <span className="treatment-review-note-icon" aria-hidden="true">ⓘ</span>
              {note}
            </li>
          ))}
        </ul>
      ) : null}
    </>
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
      <section className="structured-report-section structured-report-body">
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
