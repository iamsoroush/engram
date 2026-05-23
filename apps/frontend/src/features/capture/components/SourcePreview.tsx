import React from "react";
import type { CaptureItem } from "../../../domain/types";
import { CaptureMetadataSummary, generatedMetadataFor, metadataDisplay, metadataRecord, metadataText } from "../metadata";
import { getCachedCapture } from "../../../services/storage/captureStorage";
import { Card, Dialog } from "../../../shared/ui/primitives";
import { StatusBadge } from "./StatusBadges";

/**
 * Shows the best available source preview, preferring cached local blobs before
 * requesting protected backend file content.
 */
export function CaptureRawPreview({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const metadata = metadataRecord(item.metadata);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);
  const isAudio = item.type === "audio" || item.type === "voice";
  const fileEndpoint = item.fileEndpoint || (item.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setNoteText("");
    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);
    return () => {
      revoked = true;
    };
  }, [item.id, item.type]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    if (!fileEndpoint) return;
    onResolveFile(fileEndpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [fileEndpoint, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url || "";

  if (item.type === "note") {
    return <p className="capture-raw-text">{noteText || item.detail}</p>;
  }

  if (item.type === "photo") {
    return sourceUrl || thumbnail ? (
      <img alt={item.sourceName} className="capture-raw-photo" src={sourceUrl || thumbnail} />
    ) : (
      <div className="capture-raw-placeholder">Photo preview unavailable</div>
    );
  }

  if (isAudio) {
    return sourceUrl ? (
      <audio className="capture-raw-audio" controls src={sourceUrl} />
    ) : (
      <div className="capture-raw-placeholder">Audio preview unavailable</div>
    );
  }

  return null;
}

/**
 * Full source viewer used from both the live capture feed and inline review workspace.
 * It mirrors CaptureRawPreview's source resolution but exposes metadata too.
 */
export function SourcePreviewDialog({
  item,
  onClose,
  onResolveFile,
  onUpdateCaption,
  onUpdateTranscript,
}: {
  item: CaptureItem | null;
  onClose: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateCaption?: (captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateTranscript?: (captureId: string, transcript: string) => Promise<CaptureItem | null>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [cacheSourceName, setCacheSourceName] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [previewError, setPreviewError] = React.useState("");
  const fileEndpoint = item?.fileEndpoint || (item?.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");
  const closeButtonRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setCacheSourceName("");
    setNoteText("");
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;

    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        setCacheSourceName(cached.sourceName);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);

    return () => {
      revoked = true;
    };
  }, [item?.id, item?.type]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;
    if (!fileEndpoint) return;

    onResolveFile(fileEndpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPreviewError("Source preview is not available right now.");
      });

    return () => {
      cancelled = true;
    };
  }, [fileEndpoint, item?.id, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  React.useEffect(() => {
    if (!item) return;
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previousActive?.focus();
    };
  }, [item, onClose]);

  if (!item) return null;

  const isAudio = item.type === "audio" || item.type === "voice";
  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url;
  const sourceName = cacheSourceName || item.sourceName;
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedText = metadataText(generated.text);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);

  if (isAudio || item.type === "photo") {
    return (
      <CaptureDetailSheet
        closeButtonRef={closeButtonRef}
        generated={generated}
        generatedText={generatedText}
        item={item}
        noteText={noteText}
        onClose={onClose}
        sourceName={sourceName}
        sourceUrl={sourceUrl || ""}
        thumbnail={thumbnail}
        onUpdateCaption={onUpdateCaption}
        onUpdateTranscript={onUpdateTranscript}
      />
    );
  }

  return (
    <Dialog onClose={onClose} open title={item.title}>
      <div className="source-viewer">
        {previewError ? <div className="alert alert-red">{previewError}</div> : null}
        {item.type === "note" ? (
          <Card className="source-note">
            <p>{generatedText || noteText || item.detail}</p>
          </Card>
        ) : null}
        <div className="source-info-panel">
          <div className="source-info-header">
            <small>{item.time} · File: {sourceName}</small>
            <StatusBadge status={item.status} />
          </div>
          <CaptureMetadataSummary item={item} />
        </div>
      </div>
    </Dialog>
  );
}

function CaptureDetailSheet({
  closeButtonRef,
  generated,
  generatedText,
  item,
  noteText,
  onClose,
  sourceName,
  sourceUrl,
  thumbnail,
  onUpdateCaption,
  onUpdateTranscript,
}: {
  closeButtonRef: React.RefObject<HTMLButtonElement | null>;
  generated: Record<string, unknown>;
  generatedText: string;
  item: CaptureItem;
  noteText: string;
  onClose: () => void;
  sourceName: string;
  sourceUrl: string;
  thumbnail: string;
  onUpdateCaption?: (captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateTranscript?: (captureId: string, transcript: string) => Promise<CaptureItem | null>;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  const generatedSource = generatedSourceFor(item);
  const isStaffEdited = generatedSource.source === "staff_edit";
  const editorName = generatedSource.editorName;
  const text = captureGeneratedText(item, generated, generatedText, noteText);
  const [textDraft, setTextDraft] = React.useState(text);
  const [savingText, setSavingText] = React.useState(false);
  const [textError, setTextError] = React.useState("");
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "failed">("idle");
  const fileName = item.fileName || sourceName || "capture-file";
  const status = captureStatusLabel(item.status);
  const duration = captureDuration(item, generated);
  const captured = captureDateTime(item);
  const canUpdateText = isAudio ? Boolean(onUpdateTranscript) : Boolean(onUpdateCaption);

  React.useEffect(() => {
    setTextDraft(text);
  }, [item.id, text]);

  const copyText = () => {
    const value = textDraft.trim();
    if (!value) return;
    setCopyState("idle");
    void copyToClipboard(value)
      .then(() => setCopyState("copied"))
      .catch(() => setCopyState("failed"))
      .finally(() => window.setTimeout(() => setCopyState("idle"), 1600));
  };

  const saveText = () => {
    const nextText = textDraft.trim();
    if (!nextText || nextText === text || savingText) return;
    const update = isAudio ? onUpdateTranscript : onUpdateCaption;
    if (!update) return;
    setSavingText(true);
    setTextError("");
    void update(item.id, nextText)
      .catch(() => setTextError(`${isAudio ? "Transcript" : "Caption"} could not be saved. Try again.`))
      .finally(() => setSavingText(false));
  };

  return (
    <div className="overlay capture-detail-overlay" role="presentation">
      <aside
        aria-labelledby="capture-detail-title"
        aria-modal="true"
        className={`capture-detail-sheet ${isAudio ? "audio" : "photo"}`}
        role="dialog"
      >
        <div className="capture-detail-handle" aria-hidden="true" />
        <button
          aria-label={`Close ${isAudio ? "audio note" : "photo"} details`}
          className="capture-detail-close"
          onClick={onClose}
          ref={closeButtonRef}
          type="button"
        >
          <CloseIcon />
        </button>
        <header className="capture-detail-header">
          {!isAudio ? (
            <span className="capture-detail-title-icon" aria-hidden="true">
              <CameraIcon />
            </span>
          ) : null}
          <h2 id="capture-detail-title">{isAudio ? "Audio note" : "Photo"}</h2>
        </header>

        {isAudio ? (
          <div className="capture-detail-player">
            {sourceUrl ? <audio controls src={sourceUrl} /> : <div className="capture-detail-placeholder">Audio preview unavailable</div>}
          </div>
        ) : (
          <div className="capture-detail-photo-frame">
            {sourceUrl || thumbnail ? (
              <img alt={item.sourceName || "Photo capture"} src={sourceUrl || thumbnail} />
            ) : (
              <div className="capture-detail-placeholder">Photo preview unavailable</div>
            )}
          </div>
        )}

        <dl className="capture-detail-metadata">
          <DetailRow icon={<CalendarIcon />} label="Captured" value={captured} />
          <DetailRow icon={<FileIcon />} label="File name" value={fileName} />
          <DetailRow icon={isAudio ? <BadgeCheckIcon /> : <CheckCircleIcon />} label="Status" value={<span className="detail-status-pill">{status}</span>} />
          {isAudio ? <DetailRow icon={<ClockIcon />} label="Duration" value={duration} /> : null}
        </dl>

        {isAudio ? (
          <div className="capture-text-editor-card audio-transcript">
            <div className="capture-editor-heading">
              <label htmlFor="capture-transcript-editor">{isStaffEdited ? "Transcript" : "AI transcript"}</label>
              <button
                aria-label="Copy transcript"
                className={`capture-transcript-copy ${copyState}`}
                disabled={!textDraft.trim()}
                onClick={copyText}
                type="button"
              >
                <ClipboardIcon />
                {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
              </button>
            </div>
            <textarea
              disabled={!canUpdateText || savingText}
              id="capture-transcript-editor"
              onBlur={saveText}
              onChange={(event) => setTextDraft(event.target.value)}
              rows={8}
              value={textDraft}
            />
            <div className="capture-editor-save-row">
              <span>{savingText ? "Saving transcript..." : textError || editAttributionText(editorName, "Transcript") || "Edits save when you leave the field."}</span>
              <button disabled={!canUpdateText || savingText || !textDraft.trim() || textDraft.trim() === text} onClick={saveText} type="button">
                Save
              </button>
            </div>
          </div>
        ) : (
          <div className="capture-text-editor-card">
            <label htmlFor="capture-caption-editor">{isStaffEdited ? "Caption" : "AI-generated caption"}</label>
            <textarea
              disabled={!canUpdateText || savingText}
              id="capture-caption-editor"
              onBlur={saveText}
              onChange={(event) => setTextDraft(event.target.value)}
              rows={4}
              value={textDraft}
            />
            <div className="capture-editor-save-row">
              <span>{savingText ? "Saving caption..." : textError || editAttributionText(editorName, "Caption") || "Edits save when you leave the field."}</span>
              <button disabled={!canUpdateText || savingText || !textDraft.trim() || textDraft.trim() === text} onClick={saveText} type="button">
                Save
              </button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

async function copyToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard copy failed");
}

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>
        <span aria-hidden="true">{icon}</span>
        {label}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

function captureGeneratedText(item: CaptureItem, generated: Record<string, unknown>, generatedText: string, noteText: string) {
  const text =
    item.transcript ||
    item.caption ||
    generatedText ||
    metadataText(generated.transcript) ||
    metadataText(generated.caption) ||
    metadataText(generated.text) ||
    noteText;
  if (text) return text;
  if (item.type === "photo") {
    return `Clinical photo captured at ${item.time}. Add a caption for this source.`;
  }
  return `Clinical audio captured at ${item.time}. Transcript will appear here when processing is complete.`;
}

function generatedSourceFor(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  const value = item.type === "photo" ? metadata.caption : metadata.transcript;
  const record = metadataRecord(value);
  return {
    source: metadataDisplay(record.source),
    editorName: metadataDisplay(record.edited_by_name || record.editedByName || record.edited_by_email || record.editedByEmail),
  };
}

function editAttributionText(editorName: string, label: string) {
  return editorName ? `${label} edited by ${editorName}.` : "";
}

function captureDateTime(item: CaptureItem) {
  const value = item.capturedAt || item.time;
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    const dateLabel = new Intl.DateTimeFormat("en", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
    const timeLabel = new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
    return `${dateLabel} at ${timeLabel}`;
  }
  return item.time || "Recently";
}

function captureStatusLabel(status: CaptureItem["status"]) {
  if (!status || status === "ready" || status === "processed") return "Processed";
  if (status === "needsReview") return "Needs review";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function captureDuration(item: CaptureItem, generated: Record<string, unknown>) {
  return item.duration || metadataDisplay(generated.duration || item.metadata?.duration) || "0:05";
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m7 7 10 10" />
      <path d="m17 7-10 10" />
    </svg>
  );
}

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M6.8 7.2h2.1l1.4-2h3.4l1.4 2h2.1a3 3 0 0 1 3 3v6.4a3 3 0 0 1-3 3H6.8a3 3 0 0 1-3-3v-6.4a3 3 0 0 1 3-3Z" />
      <path d="M12 16.7a3.9 3.9 0 1 0 0-7.8 3.9 3.9 0 0 0 0 7.8Z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M7 3.8v3.4M17 3.8v3.4M4.5 9.2h15M6.5 5.5h11A2.5 2.5 0 0 1 20 8v10.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5V8a2.5 2.5 0 0 1 2.5-2.5Z" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M6.5 3.8h8l3 3V20H6.5V3.8Z" />
      <path d="M14.5 3.8v4h4" />
      <path d="M8.8 12h6.4M8.8 15.8h5" />
    </svg>
  );
}

function BadgeCheckIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 3.2 14 5l2.7-.1.8 2.6 2.1 1.7-.9 2.8.9 2.8-2.1 1.7-.8 2.6-2.7-.1-2 1.8-2-1.8-2.7.1-.8-2.6-2.1-1.7.9-2.8-.9-2.8 2.1-1.7.8-2.6L10 5l2-1.8Z" />
      <path d="m8.8 12.2 2.1 2.1 4.4-4.7" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />
      <path d="m8.5 12 2.2 2.2 4.8-5" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />
      <path d="M12 7.5v5l3 2" />
    </svg>
  );
}

function ClipboardIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M9 4h6v4H9V4Z" />
      <path d="M8 6H6.5v15h11V6H16" />
      <path d="M9 12h6M9 16h4" />
    </svg>
  );
}
