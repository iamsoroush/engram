import React from "react";
import type { AftercareTemplate, CreatePatientShareInput, LastVisitInfo, PatientShare } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, SessionTreatment } from "../../domain/types";
import { workspaceTreatments } from "../capture/captureModel";
import { Button } from "../../shared/ui/primitives";
import { useT } from "../../shared/i18n";
import type { GalleryVisit } from "./PatientPhotoGallery";

/** The synthesized 1–2 line visit summary (patient-friendly), from the report's visit-summary section. */
function synthesizedVisitSummary(session: CaptureSession): string {
  const section = (session.reportModel?.sections || []).find((entry) => entry.id === "visit-summary");
  return (section?.blocks || []).map((block) => block.text).filter(Boolean).join("\n").trim();
}

/** Client mirror of the server's curated "what we did" lines (for the preview only). */
function treatmentShareLines(treatments: SessionTreatment[], includeBrands: boolean): string[] {
  return treatments
    .map((treatment) => {
      const head = [treatment.area, treatment.product].map((part) => (part || "").trim()).filter(Boolean).join(" — ");
      if (!head) return "";
      return includeBrands && treatment.brand?.trim() ? `${head} (${treatment.brand.trim()})` : head;
    })
    .filter(Boolean);
}

type MediaChoice = { captureId: string; caption: string; included: boolean; endpoint: string; visitLabel: string };

/**
 * AES-303 / AES-304 / AES-403 — curate & share. A clinic-side curation sheet: staff pick which
 * before/after photos + sections + aftercare template the patient sees, preview it, then send a
 * read-only, revocable tokenized link. Sharing is an EXPLICIT outward-facing action (confirm before
 * sending); clinical internals (raw captures, notes, lots, national ID, other visits) are always
 * withheld — the backend only copies the curated snapshot.
 */
export function SharePatientSheet({
  patientId,
  patientName,
  visits,
  sessionId,
  onLoadLastVisit,
  onLoadSessionCaptures,
  onLoadSession,
  shareIncludeBrands,
  shareLanguage,
  onListAftercareTemplates,
  onResolveFile,
  onCreateShare,
  onRevokeShare,
  onClose,
  preferredAftercareId,
}: {
  patientId: string;
  patientName: string;
  /** The patient's recent visits — used to build the before/after photo pool to curate from. */
  visits: GalleryVisit[];
  /** Pre-select this aftercare template (the report's matched, non-dismissed clinic protocol) so the
   * share stays consistent with what the doctor sees in the report. */
  preferredAftercareId?: string;
  /** When sharing a SPECIFIC visit (from the session screen), the source session — its synthesized
   * summary, treatments, and id drive the share (not the patient's most-recent visit). */
  sessionId?: string;
  onLoadLastVisit: (patientId: string) => Promise<LastVisitInfo>;
  onLoadSessionCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  /** Load the visit's session (report model + treatments) for the synthesized summary + preview. */
  onLoadSession?: (sessionId: string) => Promise<CaptureSession>;
  shareIncludeBrands?: boolean;
  shareLanguage?: string | null;
  onListAftercareTemplates: () => Promise<AftercareTemplate[]>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onCreateShare: (input: CreatePatientShareInput) => Promise<PatientShare>;
  onRevokeShare?: (id: string) => Promise<PatientShare>;
  onClose: () => void;
}) {
  const t = useT();
  const [loading, setLoading] = React.useState(true);
  const [visit, setVisit] = React.useState<LastVisitInfo["visit"]>(null);
  const [title, setTitle] = React.useState("Your visit");
  const [noteIncluded, setNoteIncluded] = React.useState(true);
  const [noteBody, setNoteBody] = React.useState("");
  // Story C (decision 2): optional plain-words "what we did" line (server-derived, generic).
  const [treatmentsIncluded, setTreatmentsIncluded] = React.useState(false);
  const [treatmentLines, setTreatmentLines] = React.useState<string[]>([]);
  // Story C (decision 1): the clinical assessment is OPT-IN, default OFF — findings can alarm a
  // patient out of context, so the doctor must deliberately choose to include it.
  const [assessmentIncluded, setAssessmentIncluded] = React.useState(false);
  const [assessmentBody, setAssessmentBody] = React.useState("");
  const fa = (shareLanguage || "").toLowerCase().startsWith("fa");
  const summaryLabel = fa ? "خلاصهٔ ویزیت" : "Visit summary";
  const assessmentLabel = fa ? "ارزیابی" : "Assessment";
  const [media, setMedia] = React.useState<MediaChoice[]>([]);
  const [templates, setTemplates] = React.useState<AftercareTemplate[]>([]);
  const [aftercareId, setAftercareId] = React.useState<string>("");
  const [preview, setPreview] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [created, setCreated] = React.useState<PatientShare | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const recentVisits = visits.filter((entry) => entry.sessionId).slice(0, 6);
    void Promise.all([
      onLoadLastVisit(patientId).catch(() => null),
      onListAftercareTemplates().catch(() => []),
      // Pull photos across the patient's recent visits so there's a real pool to curate from.
      Promise.all(
        recentVisits.map((entry) =>
          onLoadSessionCaptures(entry.sessionId)
            .then((captures) => captures.filter((capture) => capture.type === "photo").map((capture) => ({ capture, visit: entry })))
            .catch(() => [] as Array<{ capture: CaptureItem; visit: GalleryVisit }>),
        ),
      ),
    ]).then(([lastVisit, aftercare, photoGroups]) => {
      if (cancelled) return;
      const sourceVisit = lastVisit?.visit || null;
      setVisit(sourceVisit);
      // A raw "Session <timestamp>" auto-name isn't patient-friendly — fall back to "Your visit".
      const rawTitle = sourceVisit?.title || "";
      setTitle(rawTitle && !/^session\b/i.test(rawTitle) ? `Your ${rawTitle.toLowerCase()}` : "Your visit");
      setNoteBody(sourceVisit?.note || "");
      setNoteIncluded(Boolean(sourceVisit?.note));
      // Prefer the synthesized visit-summary (patient-friendly, no manual typing) over the raw note,
      // and derive the "what we did" lines for the preview — both from the SHARED session (the
      // specific visit when shared from the session screen, else the patient's most-recent visit).
      const sourceSessionId = sessionId || sourceVisit?.sessionId;
      if (sourceSessionId && onLoadSession) {
        void onLoadSession(sourceSessionId)
          .then((session) => {
            if (cancelled) return;
            const summary = synthesizedVisitSummary(session);
            if (summary) {
              setNoteBody(summary);
              setNoteIncluded(true);
            }
            setTreatmentLines(treatmentShareLines(workspaceTreatments(session), Boolean(shareIncludeBrands)));
            // The clinical assessment section, for the opt-in toggle (kept OFF by default).
            const assessment = (session.reportModel?.sections || []).find((entry) => entry.id === "assessment");
            setAssessmentBody(
              (assessment?.blocks || [])
                .filter((block) => block.type === "paragraph" && block.text)
                .map((block) => block.text)
                .join("\n\n")
                .trim(),
            );
          })
          .catch(() => undefined);
      }
      // Flatten + dedupe photos; default the most-recent visit's photos included.
      const seen = new Set<string>();
      const pool: MediaChoice[] = [];
      (photoGroups || []).flat().forEach(({ capture, visit: entry }, index) => {
        if (!capture.id || seen.has(capture.id)) return;
        seen.add(capture.id);
        pool.push({
          captureId: capture.id,
          caption: capture.caption || "",
          included: index < 2,
          endpoint: capture.fileEndpoint || `/api/v1/captures/${capture.id}/file`,
          visitLabel: `${entry.dateLabel}${entry.title ? ` · ${entry.title}` : ""}`,
        });
      });
      setMedia(pool);
      const active = (aftercare || []).filter((template) => template.isActive);
      setTemplates(active);
      // Default to the report's matched protocol so the share matches what the doctor saw; if it was
      // removed from the report (not in `active` / not preferred), fall back to the first template.
      const preferred = active.find((template) => template.id === preferredAftercareId);
      setAftercareId(preferred?.id || active[0]?.id || "");
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientId, visits, sessionId, onLoadLastVisit, onLoadSessionCaptures, onListAftercareTemplates, onLoadSession, shareIncludeBrands, preferredAftercareId]);

  const selectedTemplate = templates.find((template) => template.id === aftercareId) || null;
  const includedMedia = media.filter((item) => item.included);

  const send = async () => {
    if (sending) return;
    if (!window.confirm(t("share.confirmSend", { name: patientName }))) return;
    setSending(true);
    setError("");
    const input: CreatePatientShareInput = {
      patientId,
      sessionId: sessionId || visit?.sessionId,
      title: title.trim() || "Your visit",
      sections: [
        ...(noteIncluded && noteBody.trim() ? [{ label: summaryLabel, body: noteBody.trim() }] : []),
        ...(assessmentIncluded && assessmentBody.trim() ? [{ label: assessmentLabel, body: assessmentBody.trim() }] : []),
      ],
      media: includedMedia.map((item) => ({ captureId: item.captureId, caption: item.caption || undefined })),
      aftercare: selectedTemplate ? { templateId: selectedTemplate.id } : undefined,
      includeTreatments: treatmentsIncluded,
    };
    try {
      const share = await onCreateShare(input);
      setCreated(share);
    } catch {
      setError(t("share.createError"));
    } finally {
      setSending(false);
    }
  };

  const shareUrl = created ? `${window.location.origin}${created.publicPath}` : "";
  const copyLink = () => {
    if (!shareUrl) return;
    void navigator.clipboard?.writeText(shareUrl).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    });
  };

  const revoke = async () => {
    if (!created || !onRevokeShare) return;
    if (!window.confirm(t("share.confirmRevoke"))) return;
    const updated = await onRevokeShare(created.id);
    setCreated(updated);
  };

  return (
    <div className="share-backdrop" role="presentation" onClick={onClose}>
      <section className="share-sheet" role="dialog" aria-modal="true" aria-label={t("share.dialogLabel")} onClick={(event) => event.stopPropagation()}>
        <header className="share-head">
          <span className="share-head-icon" aria-hidden="true"><ShareIcon /></span>
          <h2>{t("share.heading")}</h2>
          <button className="share-close" onClick={onClose} type="button" aria-label={t("share.close")}>×</button>
        </header>

        {loading ? (
          <p className="share-loading">{t("share.preparing")}</p>
        ) : created ? (
          <div className="share-created">
            <p className={`share-created-status ${created.status}`}>
              {created.status === "revoked" ? t("share.revokedStatus") : t("share.readyStatus", { name: patientName })}
            </p>
            {created.status !== "revoked" ? (
              <>
                <div className="share-link-row">
                  <input className="share-link-input" readOnly value={shareUrl} aria-label={t("share.patientLink")} onFocus={(event) => event.target.select()} />
                  <Button onClick={copyLink} size="sm" type="button">{copied ? t("share.copied") : t("share.copyLink")}</Button>
                </div>
                <p className="share-link-hint">{t("share.deliverHint", { n: created.mediaCount })}</p>
                {onRevokeShare ? (
                  <button className="share-revoke" onClick={() => void revoke()} type="button">{t("share.revokeAccess")}</button>
                ) : null}
              </>
            ) : null}
            <Button onClick={onClose} size="sm" type="button" variant="secondary">{t("share.done")}</Button>
          </div>
        ) : (
          <>
            <p className="share-instruction">{t("share.instruction", { name: patientName })}</p>

            <label className="share-field">
              <span>{t("share.titleLabel")}</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={t("share.titlePlaceholder")} />
            </label>

            <div className="share-incl-list">
              <div className="share-incl-group">
                <span className="share-incl-group-label">{t("share.beforeAfterPhotos")}</span>
                {media.length ? (
                  media.map((item, index) => (
                    <SharePhotoRow
                      key={item.captureId}
                      choice={item}
                      onResolveFile={onResolveFile}
                      onToggle={() => setMedia((current) => current.map((m, i) => (i === index ? { ...m, included: !m.included } : m)))}
                      onCaption={(caption) => setMedia((current) => current.map((m, i) => (i === index ? { ...m, caption } : m)))}
                    />
                  ))
                ) : (
                  <p className="share-empty-photos">{t("share.noPhotos")}</p>
                )}
              </div>

              <div className={`share-incl-row${noteIncluded ? "" : " off"}`}>
                <Toggle on={noteIncluded} onChange={() => setNoteIncluded((value) => !value)} label={t("share.includeVisitSummary")} />
                <div className="share-incl-copy">
                  <b>{t("share.visitSummaryTitle")}</b>
                  <span>{t("share.visitSummaryHint")}</span>
                </div>
              </div>
              {noteIncluded ? (
                <textarea className="share-note-input" rows={2} dir="auto" value={noteBody} onChange={(event) => setNoteBody(event.target.value)} placeholder={t("share.summaryPlaceholder")} />
              ) : null}

              <div className={`share-incl-row${treatmentsIncluded ? "" : " off"}`}>
                <Toggle on={treatmentsIncluded} onChange={() => setTreatmentsIncluded((value) => !value)} label={t("share.includeWhatWeDid")} />
                <div className="share-incl-copy">
                  <b>{t("share.whatWeDidTitle")}</b>
                  <span>{t("share.whatWeDidHint")}</span>
                </div>
              </div>

              {assessmentBody ? (
                <div className={`share-incl-row${assessmentIncluded ? "" : " off"}`}>
                  <Toggle on={assessmentIncluded} onChange={() => setAssessmentIncluded((value) => !value)} label={t("share.includeAssessment")} />
                  <div className="share-incl-copy">
                    <b>{t("share.assessmentTitle")}</b>
                    <span>{t("share.assessmentHint")}</span>
                  </div>
                </div>
              ) : null}

              <div className={`share-incl-row${aftercareId ? "" : " off"}`}>
                <Toggle on={Boolean(aftercareId)} onChange={() => setAftercareId(aftercareId ? "" : templates[0]?.id || "")} label={t("share.includeAftercare")} />
                <div className="share-incl-copy">
                  <b>{t("share.aftercareTitle")}</b>
                  <span>{templates.length ? t("share.aftercareChoose") : t("share.aftercareNoTemplates")}</span>
                </div>
              </div>
              {aftercareId && templates.length ? (
                <select className="share-aftercare-select" value={aftercareId} onChange={(event) => setAftercareId(event.target.value)} aria-label={t("share.aftercareTemplateLabel")}>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}{template.procedureType ? ` · ${template.procedureType}` : ""}</option>
                  ))}
                </select>
              ) : null}
            </div>

            <div className="share-withheld">
              <LockIcon />
              {t("share.alwaysWithheld")}
            </div>

            {preview ? (
              <SharePreviewPane
                patientName={patientName}
                title={title}
                note={noteIncluded ? noteBody : ""}
                treatments={treatmentsIncluded ? treatmentLines : []}
                media={includedMedia}
                onResolveFile={onResolveFile}
                aftercare={selectedTemplate}
              />
            ) : null}

            {error ? <p className="share-error">{error}</p> : null}

            <div className="share-actions">
              <button className="share-pillbtn" onClick={() => setPreview((value) => !value)} type="button">{preview ? t("share.hidePreview") : t("share.preview")}</button>
              <Button className="share-pillbtn primary" disabled={sending || (!includedMedia.length && !(noteIncluded && noteBody.trim()) && !selectedTemplate && !treatmentsIncluded)} onClick={() => void send()} type="button">
                <ShareIcon />
                {sending ? t("share.sending") : t("share.sendLink")}
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function SharePhotoRow({
  choice,
  onResolveFile,
  onToggle,
  onCaption,
}: {
  choice: MediaChoice;
  onResolveFile: (endpoint: string) => Promise<string>;
  onToggle: () => void;
  onCaption: (caption: string) => void;
}) {
  const t = useT();
  const url = useResolvedUrl(choice.endpoint, onResolveFile);
  return (
    <div className={`share-photo-row${choice.included ? "" : " off"}`}>
      <Toggle on={choice.included} onChange={onToggle} label={t("share.includePhoto")} />
      <span className="share-photo-thumb">{url ? <img alt={t("share.photoThumbAlt")} src={url} /> : null}</span>
      <div className="share-photo-copy">
        {choice.visitLabel ? <small className="share-photo-visit" data-content>{choice.visitLabel}</small> : null}
        <input className="share-photo-caption" value={choice.caption} onChange={(event) => onCaption(event.target.value)} placeholder={t("share.captionPlaceholder")} disabled={!choice.included} />
      </div>
    </div>
  );
}

function SharePreviewPane({
  patientName,
  title,
  note,
  treatments,
  media,
  onResolveFile,
  aftercare,
}: {
  patientName: string;
  title: string;
  note: string;
  treatments: string[];
  media: MediaChoice[];
  onResolveFile: (endpoint: string) => Promise<string>;
  aftercare: AftercareTemplate | null;
}) {
  const t = useT();
  return (
    <div className="share-preview" data-content data-testid="share-preview" aria-label={t("share.previewAria")}>
      <div className="share-preview-head">
        <strong data-content>{title || "Your visit"}</strong>
        <span data-content>For {patientName}</span>
      </div>
      {media.length ? (
        <div className="share-preview-photos">
          {media.map((item) => <SharePreviewPhoto key={item.captureId} endpoint={item.endpoint} caption={item.caption} onResolveFile={onResolveFile} />)}
        </div>
      ) : null}
      {note ? <p className="share-preview-note" dir="auto">{note}</p> : null}
      {treatments.length ? (
        <ul className="share-preview-treatments">
          {treatments.map((line, index) => (
            <li dir="auto" key={`${index}-${line.slice(0, 24)}`}>{line}</li>
          ))}
        </ul>
      ) : null}
      {aftercare ? (
        <div className="share-preview-aftercare">
          <h4>{aftercare.name}</h4>
          <p>{aftercare.body}</p>
        </div>
      ) : null}
    </div>
  );
}

function SharePreviewPhoto({ endpoint, caption, onResolveFile }: { endpoint: string; caption: string; onResolveFile: (endpoint: string) => Promise<string> }) {
  const url = useResolvedUrl(endpoint, onResolveFile);
  return (
    <figure className="share-preview-photo">
      {url ? <img alt={caption || "Photo"} src={url} /> : null}
      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  );
}

function useResolvedUrl(endpoint: string, onResolveFile: (endpoint: string) => Promise<string>) {
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    if (!endpoint) return;
    let cancelled = false;
    void onResolveFile(endpoint)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [endpoint, onResolveFile]);
  React.useEffect(() => () => {
    if (url.startsWith("blob:")) URL.revokeObjectURL(url);
  }, [url]);
  return url;
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: () => void; label: string }) {
  return (
    <button className={`share-toggle${on ? " on" : ""}`} onClick={onChange} type="button" role="switch" aria-checked={on} aria-label={label}>
      <span aria-hidden="true" />
    </button>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="6" cy="12" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="18" cy="18" r="2.4" />
      <path d="m8.1 10.9 7.8-3.8M8.1 13.1l7.8 3.8" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true" className="share-lock">
      <rect x="5.5" y="10.5" width="13" height="9" rx="2" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </svg>
  );
}
