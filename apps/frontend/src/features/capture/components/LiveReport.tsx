// Live report views (pro/basic) + markdown rendering for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { CaptureItem, CaptureSession, SessionTreatment, StructuredPatientInformation, StructuredReportBlock } from "../../../domain/types";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { CaptureRawPreview } from "./SourcePreview";
import { CaptureTimelineIcon } from "./CaptureBadges";
import { reportFreshness, patientInformationFromSession, workspaceStructuredReportCopy, workspaceTreatments, treatmentLabel, treatmentAttributeLines, isLowConfidenceTreatment, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionAiOrganizing, AI_ORGANIZING_NOTICE, generatedTextForReport, textDirection } from "../captureModel";

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
  reportLanguage,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  /** Open the Sources drawer to correct a flagged treatment at its capture (Pro, unified layout). */
  onFixAtSource?: () => void;
  /** Report-content language — localizes the section titles (distinct from app UI language). */
  reportLanguage?: string | null;
}) {
  // A document in both tiers: clinic + patient header from template/DB. Pro is a synthesized,
  // template-driven report; Basic is a clean chronological body with transcripts + images.
  return isPro ? (
    <ProLiveReport session={session} onResolveFile={onResolveFile} onConfirmCarriedForward={onConfirmCarriedForward} onFixAtSource={onFixAtSource} reportLanguage={reportLanguage} />
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
  const clinic = session?.report?.template?.clinic;
  const patientInformation = session?.report?.patientInformation || patientInformationFromSession(session);
  return (
    <>
      <section className="structured-report-section">
        <h3>Clinic Information</h3>
        <p>Clinic: {clinic?.name || "Clinic"}</p>
        {(clinic?.information?.length ? clinic.information : ["Clinical memory report"]).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </section>
      <section className="structured-report-section">
        <h3>Patient Information</h3>
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
  reportLanguage,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  onFixAtSource?: () => void;
  reportLanguage?: string | null;
}) {
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
  const templateLabel = session?.report?.template?.key === "default" || !session?.report?.template?.key ? "Default template" : `${session?.report?.template?.key} template`;
  // Explicit "what this report is based on" status (Pro): current = reflects all captures.
  const freshness = reportFreshness(session, true);
  return (
    <div className="structured-report-view">
      <div className="report-meta-strip">
        <span className="report-meta-template">{templateLabel}</span>
        {organizing ? (
          <span className="report-freshness updating" aria-live="polite">
            <span className="report-freshness-dot" aria-hidden="true" />
            {AI_ORGANIZING_NOTICE}
          </span>
        ) : freshness ? (
          <span className={`report-freshness ${freshness.current ? "current" : "updating"}`} aria-live="polite">
            {freshness.current ? (
              <>
                ✓ Reflects all {freshness.included} capture{freshness.included === 1 ? "" : "s"}
                {freshness.setAside > 0 ? ` · ${freshness.setAside} set aside` : ""}
              </>
            ) : (
              <>
                <span className="report-freshness-dot" aria-hidden="true" />
                Updating · {freshness.pending} of {freshness.included + freshness.pending} captures not yet in this report
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
                    carriedForwardReasons={carriedForwardReasons}
                    onConfirmCarried={onConfirmCarried}
                    reviewNotes={reviewNotes}
                  />
                ) : (
                  section.blocks.map((block, index) => (
                    <React.Fragment key={index}>{formatReportBlock(block, onResolveFile)}</React.Fragment>
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
          <p className="report-doc-status">Preparing the report from your captures…</p>
        ) : (
          <p className="report-doc-status">The report builds here automatically as captures land.</p>
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
            carriedForwardReasons={carriedForwardReasons}
            onConfirmCarried={onConfirmCarried}
            reviewNotes={reviewNotes}
          />
        </section>
      ) : null}
      {/* The clinician's confirmations are embedded in the report itself — the carried-forward dose
          confirm sits on its treatment row (above), not in a separate section. */}
    </div>
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
  /** `area|product` → reason for carried-forward doses awaiting confirmation (Q3). */
  carriedForwardReasons?: Record<string, string>;
  /** Confirm a carried-forward dose by its `area|product` key. */
  onConfirmCarried?: (key: string) => Promise<void>;
  /** The synthesis's softer uncertainties (ambiguous notes), rendered calmly under the list. */
  reviewNotes?: string[];
}) {
  const [confirmingKey, setConfirmingKey] = React.useState<string | null>(null);
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
                  <span className={`treatment-flag${isConfirmed ? " confirmed" : ""}`}> · carried forward{isConfirmed ? " (confirmed)" : ""}</span>
                ) : null}
                {lowConfidence ? <span className="treatment-flag low"> · low confidence</span> : null}
                {lotMissing ? <span className="treatment-flag low"> · lot not captured</span> : null}
                {fixable && onFixAtSource ? (
                  <button type="button" className="treatment-fix-at-source" onClick={onFixAtSource}>
                    ✎ Fix at source
                  </button>
                ) : null}
              </span>
              {attributeLines.length ? (
                <span className="treatment-attributes" dir={textDirection(attributeLines.join(" · "))}>
                  {attributeLines.join(" · ")}
                </span>
              ) : null}
              {needsConfirm ? (
                <span className="treatment-confirm">
                  <span className="treatment-confirm-reason" dir={textDirection(confirmReason || "")}>
                    {confirmReason || "Carried forward from a previous visit — confirm the dose."}
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
                    {confirmingKey === key ? "Confirming…" : "Confirm dose"}
                  </button>
                </span>
              ) : isConfirmed ? (
                <span className="treatment-confirmed">✓ Dose confirmed</span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {reviewNotes?.length ? (
        <ul className="treatment-review-notes" aria-label="Notes to review">
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

export function BasicLiveReport({
  session,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const items = session?.items || [];
  return (
    <div className="structured-report-view basic-live-report">
      <section className="structured-report-section structured-report-body">
        {items.length ? (
          items.map((item) => <BasicReportEntry item={item} key={item.sourceUrl || item.id} onResolveFile={onResolveFile} />)
        ) : (
          <p className="report-doc-status">Captures will appear here, in order, as the session develops.</p>
        )}
      </section>
      {items.length ? (
        <TryProTeaser
          className="report-teaser"
          title="Try Pro — turn your notes into a structured treatment report"
          subtitle="Visit summary, assessment, and a Treatment-performed table extracted from your words — no form-filling."
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
  if (!patientInformation || patientInformation.status !== "assigned") return <p>Patient: Unassigned</p>;
  const rows = [
    ["Full name", patientInformation.displayName],
    ["National ID", patientInformation.nationalId],
    ["Date of birth", patientInformation.dateOfBirth],
    ["Sex", patientInformation.sex],
    ["Phone", patientInformation.phone],
    ["Email", patientInformation.email],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) return <p>Patient assigned</p>;
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
  return imageSrc ? <img alt={alt} className="structured-report-body-image" src={imageSrc} /> : <p>Image preview unavailable</p>;
}
