import React from "react";
import type { LastVisitInfo, LastVisitMedia } from "../../domain/appTypes";

/**
 * AES-106 — Last visit, one glance + "same as last time". For a returning patient the capture
 * strip surfaces the prior visit's typed note + that visit's photos (tap to open it), and offers a
 * one-tap pre-fill of a new editable note from the prior note. Deterministic retrieval — never AI,
 * never auto-saved. This is how Basic answers "what did we use last time".
 */
export function LastVisitStrip({
  lastVisit,
  onOpenVisit,
  onUseAsNote,
  onResolveFile,
}: {
  lastVisit: LastVisitInfo | null;
  onOpenVisit?: (sessionId: string) => void;
  onUseAsNote?: (text: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  if (!lastVisit?.hasPriorVisit || !lastVisit.visit) return null;
  const visit = lastVisit.visit;
  const dateLabel = formatVisitDate(visit.capturedAt || visit.updatedAt);
  const note = visit.note;
  const sameNote = lastVisit.sameAsLastTime?.note;

  return (
    <section className="last-visit-strip" aria-label="Last visit">
      <span className="last-visit-icon" aria-hidden="true">
        <CopyIcon />
      </span>
      <div className="last-visit-copy">
        <p className="last-visit-line">
          <strong>Last visit{dateLabel ? ` · ${dateLabel}` : ""}</strong>
          {note ? (
            <>
              {" — your note: "}
              <span className="last-visit-note" dir={textDir(note)}>&ldquo;{note}&rdquo;</span>
            </>
          ) : (
            " — no typed note on the prior visit."
          )}
          {onOpenVisit && visit.sessionId ? (
            <button className="last-visit-link" onClick={() => onOpenVisit(visit.sessionId)} type="button">
              View visit
            </button>
          ) : null}
        </p>
        {visit.media.length ? (
          <div className="last-visit-thumbs" aria-label="Last visit photos">
            {visit.media.slice(0, 4).map((media) => (
              <LastVisitThumb key={media.captureId} media={media} onResolveFile={onResolveFile} />
            ))}
            <span className="last-visit-thumbs-note">compare by eye</span>
          </div>
        ) : null}
      </div>
      {sameNote && onUseAsNote ? (
        <button className="last-visit-use" onClick={() => onUseAsNote(sameNote)} type="button">
          Same as last time
        </button>
      ) : null}
    </section>
  );
}

function LastVisitThumb({ media, onResolveFile }: { media: LastVisitMedia; onResolveFile: (endpoint: string) => Promise<string> }) {
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    let cancelled = false;
    const endpoint = media.contentEndpoint || media.fileEndpoint;
    if (!endpoint) return;
    void onResolveFile(endpoint)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [media.contentEndpoint, media.fileEndpoint, onResolveFile]);
  React.useEffect(() => () => {
    if (url.startsWith("blob:")) URL.revokeObjectURL(url);
  }, [url]);
  return <span className="last-visit-thumb">{url ? <img alt="Last visit photo" src={url} /> : null}</span>;
}

function formatVisitDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

function textDir(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <rect x="8" y="8" width="11" height="12" rx="2" />
      <path d="M5 15.5V5.5A1.5 1.5 0 0 1 6.5 4h8" />
    </svg>
  );
}
