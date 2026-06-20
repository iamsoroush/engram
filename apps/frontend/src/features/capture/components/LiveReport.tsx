// Live report views (pro/basic) + markdown rendering for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { CaptureItem, CaptureSession, SessionTreatment, StructuredPatientInformation, StructuredReportBlock } from "../../../domain/types";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { CaptureRawPreview } from "./SourcePreview";
import { CaptureTimelineIcon } from "./CaptureBadges";
import { reportFreshness, patientInformationFromSession, workspaceStructuredReportCopy, workspaceTreatments, treatmentLabel, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionAiOrganizing, AI_ORGANIZING_NOTICE, generatedTextForReport, textDirection } from "../captureModel";

export function LiveReportView({
  isPro,
  session,
  onResolveFile,
  onConfirmCarriedForward,
}: {
  isPro: boolean;
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
}) {
  // A document in both tiers: clinic + patient header from template/DB. Pro is a synthesized,
  // template-driven report; Basic is a clean chronological body with transcripts + images.
  return isPro ? (
    <ProLiveReport session={session} onResolveFile={onResolveFile} onConfirmCarriedForward={onConfirmCarriedForward} />
  ) : (
    <BasicLiveReport session={session} onResolveFile={onResolveFile} />
  );
}

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
}: {
  session: CaptureSession | null;
  onResolveFile: (endpoint: string) => Promise<string>;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
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
  // Q3: carried-forward doses the clinician has already confirmed (so they read as done, not pending).
  const confirmedCarriedForward = new Set(sessionConfirmedCarriedForward(session));
  const [confirming, setConfirming] = React.useState<string | null>(null);
  // Pro "organizing with AI": the deterministic baseline is visible and complete, but the synthesis
  // job is still in flight — show a calm, persistent notice instead of a (false) "current" line.
  const organizing = sessionAiOrganizing(session);
  const isUpdating = session?.processingStatus?.state === "processing" || session?.report?.status === "generating";
  const templateLabel = session?.report?.template?.key === "default" || !session?.report?.template?.key ? "Default template" : `${session?.report?.template?.key} template`;
  // Explicit "what this report is based on" status (Pro): current = reflects all captures.
  const freshness = reportFreshness(session, true);
  return (
    <div className="structured-report-view">
      <ReportDocHeader session={session} />
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
                {section.title ? <h3>{section.title}</h3> : null}
                {renderTreatmentTable ? (
                  <TreatmentsList treatments={treatments} confirmedCarriedForward={confirmedCarriedForward} />
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
          <h3>Treatments performed</h3>
          <TreatmentsList treatments={treatments} confirmedCarriedForward={confirmedCarriedForward} />
        </section>
      ) : null}
      {review.length ? (
        <section className="structured-report-section report-review" aria-label="Items that need your confirmation">
          <h3>Needs your confirmation</h3>
          <ul className="report-review-chips">
            {review.map((item, index) => {
              const isCarriedForward = item.category === "carried_forward" && Boolean(item.key);
              const isConfirmed = isCarriedForward && confirmedCarriedForward.has(item.key as string);
              return (
                <li
                  className={`report-review-chip ${item.category}${isConfirmed ? " confirmed" : ""}`}
                  dir={textDirection(item.reason)}
                  key={`${index}-${item.reason.slice(0, 32)}`}
                >
                  <span className="report-review-chip-reason">{item.reason}</span>
                  {isCarriedForward && isConfirmed ? (
                    <span className="report-review-chip-confirmed" aria-label="Dose confirmed">✓ confirmed</span>
                  ) : isCarriedForward && onConfirmCarriedForward && session ? (
                    <button
                      type="button"
                      className="report-review-confirm"
                      disabled={confirming === item.key}
                      onClick={async () => {
                        if (!item.key) return;
                        setConfirming(item.key);
                        try {
                          await onConfirmCarriedForward(session.id, item.key);
                        } finally {
                          setConfirming(null);
                        }
                      }}
                    >
                      {confirming === item.key ? "Confirming…" : "Confirm dose"}
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/**
 * The structured performed-treatments list — the single treatment representation in the report
 * (area · product · dose · lot, verbatim quantity preserved). Carried-forward rows are flagged and,
 * until confirmed (Q3), point to the "Needs your confirmation" action below.
 */
function TreatmentsList({
  treatments,
  confirmedCarriedForward,
}: {
  treatments: SessionTreatment[];
  confirmedCarriedForward: Set<string>;
}) {
  return (
    <ul className="treatments-list">
      {treatments.map((treatment, index) => {
        const label = treatmentLabel(treatment);
        return (
          <li className="treatment-item" dir={textDirection(label)} key={`${index}-${label.slice(0, 24)}`}>
            {label}
            {treatment.carriedForward ? (
              confirmedCarriedForward.has(`${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`) ? (
                <span className="treatment-flag confirmed"> · carried forward (confirmed)</span>
              ) : (
                <span className="treatment-flag"> · carried forward — confirm below</span>
              )
            ) : null}
          </li>
        );
      })}
    </ul>
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
      <ReportDocHeader session={session} />
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
