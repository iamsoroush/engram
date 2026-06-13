import React from "react";
import type { AftercareTemplate, CreatePatientShareInput, LastVisitInfo, PatientShare } from "../../domain/appTypes";
import type { CaptureItem } from "../../domain/types";
import { Button } from "../../shared/ui/primitives";
import type { GalleryVisit } from "./PatientPhotoGallery";

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
  onLoadLastVisit,
  onLoadSessionCaptures,
  onListAftercareTemplates,
  onResolveFile,
  onCreateShare,
  onRevokeShare,
  onClose,
}: {
  patientId: string;
  patientName: string;
  /** The patient's recent visits — used to build the before/after photo pool to curate from. */
  visits: GalleryVisit[];
  onLoadLastVisit: (patientId: string) => Promise<LastVisitInfo>;
  onLoadSessionCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  onListAftercareTemplates: () => Promise<AftercareTemplate[]>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onCreateShare: (input: CreatePatientShareInput) => Promise<PatientShare>;
  onRevokeShare?: (id: string) => Promise<PatientShare>;
  onClose: () => void;
}) {
  const [loading, setLoading] = React.useState(true);
  const [visit, setVisit] = React.useState<LastVisitInfo["visit"]>(null);
  const [title, setTitle] = React.useState("Your visit");
  const [noteIncluded, setNoteIncluded] = React.useState(true);
  const [noteBody, setNoteBody] = React.useState("");
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
      setAftercareId(active[0]?.id || "");
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientId, visits, onLoadLastVisit, onLoadSessionCaptures, onListAftercareTemplates]);

  const selectedTemplate = templates.find((template) => template.id === aftercareId) || null;
  const includedMedia = media.filter((item) => item.included);

  const send = async () => {
    if (sending) return;
    if (!window.confirm(`Send ${patientName} a read-only link with the selected photos and aftercare? Internal notes, lots, and IDs are never included.`)) return;
    setSending(true);
    setError("");
    const input: CreatePatientShareInput = {
      patientId,
      sessionId: visit?.sessionId,
      title: title.trim() || "Your visit",
      sections: noteIncluded && noteBody.trim() ? [{ label: "Visit", body: noteBody.trim() }] : [],
      media: includedMedia.map((item) => ({ captureId: item.captureId, caption: item.caption || undefined })),
      aftercare: selectedTemplate ? { templateId: selectedTemplate.id } : undefined,
    };
    try {
      const share = await onCreateShare(input);
      setCreated(share);
    } catch {
      setError("Could not create the share link. Please try again.");
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
    if (!window.confirm("Revoke this link? The patient will immediately lose access.")) return;
    const updated = await onRevokeShare(created.id);
    setCreated(updated);
  };

  return (
    <div className="share-backdrop" role="presentation" onClick={onClose}>
      <section className="share-sheet" role="dialog" aria-modal="true" aria-label="Share with patient" onClick={(event) => event.stopPropagation()}>
        <header className="share-head">
          <span className="share-head-icon" aria-hidden="true"><ShareIcon /></span>
          <h2>Share with patient</h2>
          <button className="share-close" onClick={onClose} type="button" aria-label="Close">×</button>
        </header>

        {loading ? (
          <p className="share-loading">Preparing the share…</p>
        ) : created ? (
          <div className="share-created">
            <p className={`share-created-status ${created.status}`}>
              {created.status === "revoked" ? "Link revoked — the patient can no longer open it." : `Read-only link ready for ${patientName}.`}
            </p>
            {created.status !== "revoked" ? (
              <>
                <div className="share-link-row">
                  <input className="share-link-input" readOnly value={shareUrl} aria-label="Patient link" onFocus={(event) => event.target.select()} />
                  <Button onClick={copyLink} size="sm" type="button">{copied ? "Copied" : "Copy link"}</Button>
                </div>
                <p className="share-link-hint">Deliver by SMS / WhatsApp or any channel — it's a plain link. {created.mediaCount} photo{created.mediaCount === 1 ? "" : "s"} shared.</p>
                {onRevokeShare ? (
                  <button className="share-revoke" onClick={() => void revoke()} type="button">Revoke access</button>
                ) : null}
              </>
            ) : null}
            <Button onClick={onClose} size="sm" type="button" variant="secondary">Done</Button>
          </div>
        ) : (
          <>
            <p className="share-instruction">Pick what {patientName} sees. They get a read-only link — nothing else from the file.</p>

            <label className="share-field">
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Your visit" />
            </label>

            <div className="share-incl-list">
              <div className="share-incl-group">
                <span className="share-incl-group-label">Before / after photos</span>
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
                  <p className="share-empty-photos">No photos on file for this patient yet — capture some on a visit to share before/after.</p>
                )}
              </div>

              <div className={`share-incl-row${noteIncluded ? "" : " off"}`}>
                <Toggle on={noteIncluded} onChange={() => setNoteIncluded((value) => !value)} label="Include visit summary" />
                <div className="share-incl-copy">
                  <b>Visit summary</b>
                  <span>from your visit note</span>
                </div>
              </div>
              {noteIncluded ? (
                <textarea className="share-note-input" rows={2} value={noteBody} onChange={(event) => setNoteBody(event.target.value)} placeholder="A short summary for the patient" />
              ) : null}

              <div className={`share-incl-row${aftercareId ? "" : " off"}`}>
                <Toggle on={Boolean(aftercareId)} onChange={() => setAftercareId(aftercareId ? "" : templates[0]?.id || "")} label="Include aftercare" />
                <div className="share-incl-copy">
                  <b>Aftercare instructions</b>
                  <span>{templates.length ? "choose a template below" : "no templates yet — add one in Settings"}</span>
                </div>
              </div>
              {aftercareId && templates.length ? (
                <select className="share-aftercare-select" value={aftercareId} onChange={(event) => setAftercareId(event.target.value)} aria-label="Aftercare template">
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}{template.procedureType ? ` · ${template.procedureType}` : ""}</option>
                  ))}
                </select>
              ) : null}
            </div>

            <div className="share-withheld">
              <LockIcon />
              Always withheld: raw audio, internal notes, lot numbers, national ID, other visits.
            </div>

            {preview ? (
              <SharePreviewPane
                patientName={patientName}
                title={title}
                note={noteIncluded ? noteBody : ""}
                media={includedMedia}
                onResolveFile={onResolveFile}
                aftercare={selectedTemplate}
              />
            ) : null}

            {error ? <p className="share-error">{error}</p> : null}

            <div className="share-actions">
              <button className="share-pillbtn" onClick={() => setPreview((value) => !value)} type="button">{preview ? "Hide preview" : "Preview"}</button>
              <Button className="share-pillbtn primary" disabled={sending || (!includedMedia.length && !(noteIncluded && noteBody.trim()) && !selectedTemplate)} onClick={() => void send()} type="button">
                <ShareIcon />
                {sending ? "Sending…" : "Send link"}
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
  const url = useResolvedUrl(choice.endpoint, onResolveFile);
  return (
    <div className={`share-photo-row${choice.included ? "" : " off"}`}>
      <Toggle on={choice.included} onChange={onToggle} label="Include photo" />
      <span className="share-photo-thumb">{url ? <img alt="Shared photo" src={url} /> : null}</span>
      <div className="share-photo-copy">
        {choice.visitLabel ? <small className="share-photo-visit">{choice.visitLabel}</small> : null}
        <input className="share-photo-caption" value={choice.caption} onChange={(event) => onCaption(event.target.value)} placeholder="Caption (optional)" disabled={!choice.included} />
      </div>
    </div>
  );
}

function SharePreviewPane({
  patientName,
  title,
  note,
  media,
  onResolveFile,
  aftercare,
}: {
  patientName: string;
  title: string;
  note: string;
  media: MediaChoice[];
  onResolveFile: (endpoint: string) => Promise<string>;
  aftercare: AftercareTemplate | null;
}) {
  return (
    <div className="share-preview" aria-label="What the patient sees">
      <div className="share-preview-head">
        <strong>{title || "Your visit"}</strong>
        <span>For {patientName}</span>
      </div>
      {media.length ? (
        <div className="share-preview-photos">
          {media.map((item) => <SharePreviewPhoto key={item.captureId} endpoint={item.endpoint} caption={item.caption} onResolveFile={onResolveFile} />)}
        </div>
      ) : null}
      {note ? <p className="share-preview-note">{note}</p> : null}
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
