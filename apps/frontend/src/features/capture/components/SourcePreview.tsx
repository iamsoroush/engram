import React from "react";
import type { CaptureItem } from "../../../domain/types";
import { CaptureMetadataSummary, generatedMetadataFor, metadataDisplay, metadataRecord, metadataText } from "../metadata";
import { getCachedCapture } from "../../../services/storage/captureStorage";
import { Card, Dialog } from "../../../shared/ui/primitives";
import { appDateTimeFormat } from "../../../shared/lib/datetime";
import { useT, type Translator } from "../../../shared/i18n";
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
  const t = useT();
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
      <div className="capture-raw-placeholder">{t("source.photoPreviewUnavailable")}</div>
    );
  }

  if (isAudio) {
    return sourceUrl ? (
      <audio className="capture-raw-audio" controls src={sourceUrl} />
    ) : (
      <div className="capture-raw-placeholder">{t("source.audioPreviewUnavailable")}</div>
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
  isPro = true,
  onClose,
  onResolveFile,
  onUpdateCaption,
  onUpdateTranscript,
}: {
  item: CaptureItem | null;
  /** Basic is zero-AI: no "AI-generated"/transcript framing, no technical processing metadata. */
  isPro?: boolean;
  onClose: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateCaption?: (captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateTranscript?: (captureId: string, transcript: string) => Promise<CaptureItem | null>;
}) {
  const t = useT();
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [previewError, setPreviewError] = React.useState("");
  const fileEndpoint = item?.fileEndpoint || (item?.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");
  const closeButtonRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setNoteText("");
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;

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
        if (!cancelled) setPreviewError(t("source.previewUnavailableNow"));
      });

    return () => {
      cancelled = true;
    };
  }, [fileEndpoint, item?.id, onResolveFile, t]);

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
        isPro={isPro}
        item={item}
        noteText={noteText}
        onClose={onClose}
        sourceUrl={sourceUrl || ""}
        thumbnail={thumbnail}
        onUpdateCaption={onUpdateCaption}
        onUpdateTranscript={onUpdateTranscript}
      />
    );
  }

  // Basic note: the doctor's own words — no file name, no processing/status, no metadata table.
  const basicNoteText = noteText || item.detail || "";
  return (
    <Dialog onClose={onClose} open title={item.title}>
      <div className="source-viewer">
        {previewError ? <div className="alert alert-red">{previewError}</div> : null}
        {item.type === "note" ? (
          <Card className="source-note">
            <p dir={noteDirection(generatedText || basicNoteText)}>{generatedText || basicNoteText}</p>
          </Card>
        ) : null}
        {isPro ? (
          <div className="source-info-panel">
            <div className="source-info-header">
              <small>{item.time}</small>
              <StatusBadge status={item.status} />
            </div>
            <CaptureMetadataSummary item={item} />
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}

function noteDirection(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

function CaptureDetailSheet({
  closeButtonRef,
  generated,
  generatedText,
  isPro,
  item,
  noteText,
  onClose,
  sourceUrl,
  thumbnail,
  onUpdateCaption,
  onUpdateTranscript,
}: {
  closeButtonRef: React.RefObject<HTMLButtonElement | null>;
  generated: Record<string, unknown>;
  generatedText: string;
  isPro: boolean;
  item: CaptureItem;
  noteText: string;
  onClose: () => void;
  sourceUrl: string;
  thumbnail: string;
  onUpdateCaption?: (captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateTranscript?: (captureId: string, transcript: string) => Promise<CaptureItem | null>;
}) {
  const t = useT();
  const isAudio = item.type === "audio" || item.type === "voice";
  const generatedSource = generatedSourceFor(item);
  const isStaffEdited = generatedSource.source === "staff_edit";
  const editorName = generatedSource.editorName;
  // Basic is zero-AI: photo caption starts as the real caption only (no fake placeholder text),
  // and audio has no transcript at all (it's a voice memo).
  const text = isPro ? captureGeneratedText(item, generated, generatedText, noteText) : isAudio ? "" : item.caption || generatedText || "";
  const [textDraft, setTextDraft] = React.useState(text);
  const [savingText, setSavingText] = React.useState(false);
  const [textError, setTextError] = React.useState("");
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "failed">("idle");
  const status = captureStatusLabel(item.status, t);
  const duration = captureDuration(item, generated);
  const captured = captureDateTime(item, t);
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
      .catch(() => setTextError(isAudio ? t("source.transcriptSaveFailed") : t("source.captionSaveFailed")))
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
          aria-label={isAudio ? t("source.closeAudioDetails") : t("source.closePhotoDetails")}
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
          <h2 id="capture-detail-title">{isAudio ? t("source.audioNote") : t("source.photo")}</h2>
        </header>

        {isAudio ? (
          <div className="capture-detail-player">
            {sourceUrl ? <audio controls src={sourceUrl} /> : <div className="capture-detail-placeholder">{t("source.audioPreviewUnavailable")}</div>}
          </div>
        ) : (
          <div className="capture-detail-photo-frame">
            {sourceUrl || thumbnail ? (
              <img alt={item.sourceName || t("source.photoCaptureAlt")} src={sourceUrl || thumbnail} />
            ) : (
              <div className="capture-detail-placeholder">{t("source.photoPreviewUnavailable")}</div>
            )}
          </div>
        )}

        <dl className="capture-detail-metadata">
          <DetailRow icon={<CalendarIcon />} label={t("source.captured")} value={captured} />
          {isPro ? <DetailRow icon={isAudio ? <BadgeCheckIcon /> : <CheckCircleIcon />} label={t("source.status")} value={<span className="detail-status-pill">{status}</span>} /> : null}
          {isAudio ? <DetailRow icon={<ClockIcon />} label={t("source.duration")} value={duration} /> : null}
        </dl>

        {isAudio ? (
          // Basic audio is a voice memo — no transcript section (Pro only).
          isPro ? (
            <div className="capture-text-editor-card audio-transcript">
              <div className="capture-editor-heading">
                <label htmlFor="capture-transcript-editor">{isStaffEdited ? t("source.transcript") : t("source.aiTranscript")}</label>
                <button
                  aria-label={t("source.copyTranscript")}
                  className={`capture-transcript-copy ${copyState}`}
                  disabled={!textDraft.trim()}
                  onClick={copyText}
                  type="button"
                >
                  <ClipboardIcon />
                  {copyState === "copied" ? t("source.copied") : copyState === "failed" ? t("source.copyFailed") : t("source.copy")}
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
                <span>{savingText ? t("source.savingTranscript") : textError || editAttributionText(editorName, "transcript", t) || t("source.editsSaveOnBlur")}</span>
                <button disabled={!canUpdateText || savingText || !textDraft.trim() || textDraft.trim() === text} onClick={saveText} type="button">
                  {t("source.save")}
                </button>
              </div>
            </div>
          ) : null
        ) : (
          <div className="capture-text-editor-card">
            <label htmlFor="capture-caption-editor">{isPro ? (isStaffEdited ? t("source.caption") : t("source.aiGeneratedCaption")) : t("source.caption")}</label>
            <textarea
              disabled={!canUpdateText || savingText}
              id="capture-caption-editor"
              onBlur={saveText}
              onChange={(event) => setTextDraft(event.target.value)}
              placeholder={isPro ? undefined : t("source.addCaptionOptional")}
              rows={4}
              value={textDraft}
            />
            <div className="capture-editor-save-row">
              <span>{savingText ? t("source.savingCaption") : textError || (isPro ? editAttributionText(editorName, "caption", t) : "") || t("source.editsSaveOnBlur")}</span>
              <button disabled={!canUpdateText || savingText || textDraft.trim() === text.trim()} onClick={saveText} type="button">
                {t("source.save")}
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
  const generatedStatus = metadataDisplay(generated.status || generated.state).toLowerCase();
  const isWorking = generatedStatus === "processing" || generatedStatus === "queued" || generatedStatus === "running";
  const text =
    (isWorking ? "" : item.transcript) ||
    (isWorking ? "" : item.caption) ||
    (isWorking ? "" : generatedText) ||
    (isWorking ? "" : metadataText(generated.transcript)) ||
    (isWorking ? "" : metadataText(generated.caption)) ||
    (isWorking ? "" : metadataText(generated.text)) ||
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

function editAttributionText(editorName: string, field: "transcript" | "caption", t: Translator) {
  if (!editorName) return "";
  return field === "transcript"
    ? t("model.attribution.transcriptEditedBy", { name: editorName })
    : t("model.attribution.captionEditedBy", { name: editorName });
}

function captureDateTime(item: CaptureItem, t: Translator) {
  const value = item.capturedAt || item.time;
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    const dateLabel = appDateTimeFormat({
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
    const timeLabel = appDateTimeFormat({
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
    return t("model.capture.dateAtTime", { date: dateLabel, time: timeLabel });
  }
  return item.time || t("model.capture.recently");
}

function captureStatusLabel(status: CaptureItem["status"], t: Translator) {
  if (!status || status === "ready" || status === "processed") return t("model.captureStatus.processed");
  if (status === "needsReview") return t("model.captureStatus.needsReview");
  if (status === "saved") return t("model.captureStatus.saved");
  if (status === "syncing") return t("model.captureStatus.syncing");
  if (status === "uploaded") return t("model.captureStatus.uploaded");
  if (status === "uploading") return t("model.captureStatus.uploading");
  if (status === "processing") return t("model.captureStatus.processing");
  if (status === "failed") return t("model.captureStatus.failed");
  if (status === "missing") return t("model.captureStatus.missing");
  // Every member of the (closed) status union is handled above; this defensive fallback capitalizes
  // any unforeseen runtime value verbatim, as the original did.
  const raw = status as string;
  return raw.charAt(0).toUpperCase() + raw.slice(1);
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
