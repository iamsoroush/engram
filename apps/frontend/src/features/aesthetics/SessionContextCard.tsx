import React from "react";
import type { LastVisitMedia, SessionContext } from "../../domain/appTypes";

/**
 * Session patient-context card (deterministic, both tiers — redesign of the single-note
 * LastVisitStrip). The moment a patient is determined for the active session it answers, glanceably:
 * who is this (visit ordinal + pinned key facts), what happened last (the full last-visit *digest* —
 * note(s), photos, playable voice memos), and progress across visits (a compact cross-visit photo
 * strip). Zero AI: this is Basic's "smart deterministic" surface AND the base the Pro intelligent
 * window layers on top of / falls back to (so Pro is never blank). Capture is never blocked — this is
 * a glanceable aid beside the flow, never a gate.
 */
export function SessionContextCard({
  context,
  isPro,
  onOpenVisit,
  onUseAsNote,
  onResolveFile,
}: {
  context: SessionContext | null;
  isPro?: boolean;
  onOpenVisit?: (sessionId: string) => void;
  onUseAsNote?: (text: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  if (!context) return null;
  const { lastVisit, recentVisits, visitOrdinal, totalPriorVisits, keyFacts } = context;
  const visit = lastVisit.hasPriorVisit ? lastVisit.visit : null;
  // Nothing worth a card for a brand-new patient with no pinned facts.
  if (!visit && !keyFacts) return null;

  const dateLabel = formatVisitDate(visit?.capturedAt || visit?.updatedAt);
  const sameNote = lastVisit.sameAsLastTime?.note;
  const photoCount = visit?.media.length ?? 0;
  const audioCount = visit?.audioCount ?? visit?.audio?.length ?? 0;
  const counts = visit
    ? [
        visit.captureCount ? `${visit.captureCount} capture${visit.captureCount === 1 ? "" : "s"}` : null,
        photoCount ? `${photoCount} photo${photoCount === 1 ? "" : "s"}` : null,
        audioCount ? `${audioCount} voice memo${audioCount === 1 ? "" : "s"}` : null,
      ].filter(Boolean).join(" · ")
    : "";
  // The progress strip is only meaningful across ≥2 visits with photos.
  const showProgress = recentVisits.length >= 2;

  return (
    <section className="session-context-card" aria-label="Patient context">
      <header className="session-context-head">
        <span className="session-context-ordinal">
          {ordinalText(visitOrdinal)} visit
          {totalPriorVisits > 0 ? ` · ${totalPriorVisits} prior` : " · new patient"}
        </span>
        {isPro ? <span className="session-context-tier">Pro</span> : null}
      </header>

      {keyFacts ? (
        <p className="session-context-facts" dir={textDir(keyFacts)}>
          <span className="session-context-facts-label">Key facts</span> {keyFacts}
        </p>
      ) : null}

      {visit ? (
        <div className="session-context-digest">
          <div className="session-context-digest-head">
            <strong>Last visit{dateLabel ? ` · ${dateLabel}` : ""}</strong>
            {counts ? <span className="session-context-counts">{counts}</span> : null}
            {onOpenVisit && visit.sessionId ? (
              <button className="session-context-link" onClick={() => onOpenVisit(visit.sessionId)} type="button">
                View visit
              </button>
            ) : null}
          </div>
          {visit.note ? (
            <p className="session-context-note" dir={textDir(visit.note)}>
              &ldquo;{visit.note}&rdquo;
            </p>
          ) : null}
          {visit.media.length ? (
            <div className="session-context-thumbs" aria-label="Last visit photos">
              {visit.media.slice(0, 4).map((media) => (
                <MediaThumb key={media.captureId} media={media} onResolveFile={onResolveFile} />
              ))}
              {visit.media.length > 4 ? <span className="session-context-more">+{visit.media.length - 4}</span> : null}
              <span className="session-context-thumbs-note">compare by eye</span>
            </div>
          ) : null}
          {visit.audio?.length ? (
            <div className="session-context-audio" aria-label="Last visit voice memos">
              {visit.audio.map((memo, index) => (
                <VoiceMemo key={memo.captureId} memo={memo} index={index} onResolveFile={onResolveFile} />
              ))}
            </div>
          ) : null}
          {sameNote && onUseAsNote ? (
            <button className="session-context-use" onClick={() => onUseAsNote(sameNote)} type="button">
              Same as last time
            </button>
          ) : null}
        </div>
      ) : null}

      {showProgress ? (
        <div className="session-context-progress" aria-label="Progress across recent visits">
          <span className="session-context-progress-label">Progress · recent visits</span>
          <div className="session-context-progress-row">
            {recentVisits.map((recent) =>
              recent.photos.length ? (
                <button
                  key={recent.sessionId}
                  className="session-context-progress-visit"
                  type="button"
                  onClick={onOpenVisit ? () => onOpenVisit(recent.sessionId) : undefined}
                  disabled={!onOpenVisit}
                  title={formatVisitDate(recent.capturedAt) || recent.title}
                >
                  <MediaThumb media={recent.photos[0]} onResolveFile={onResolveFile} />
                  <span className="session-context-progress-date">{formatVisitDate(recent.capturedAt) || "—"}</span>
                  {recent.photoCount > 1 ? <span className="session-context-progress-count">{recent.photoCount}</span> : null}
                </button>
              ) : null,
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function MediaThumb({ media, onResolveFile }: { media: LastVisitMedia; onResolveFile: (endpoint: string) => Promise<string> }) {
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
  React.useEffect(
    () => () => {
      if (url.startsWith("blob:")) URL.revokeObjectURL(url);
    },
    [url],
  );
  return <span className="session-context-thumb">{url ? <img alt={media.caption || "Visit photo"} src={url} /> : null}</span>;
}

/** A playable prior-visit voice memo (resolved lazily on first play to avoid eager downloads). */
function VoiceMemo({ memo, index, onResolveFile }: { memo: LastVisitMedia; index: number; onResolveFile: (endpoint: string) => Promise<string> }) {
  const [url, setUrl] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  React.useEffect(
    () => () => {
      if (url.startsWith("blob:")) URL.revokeObjectURL(url);
    },
    [url],
  );
  const load = () => {
    const endpoint = memo.contentEndpoint || memo.fileEndpoint;
    if (url || loading || !endpoint) return;
    setLoading(true);
    void onResolveFile(endpoint)
      .then((resolved) => setUrl(resolved))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  };
  if (url) return <audio className="session-context-audio-player" controls src={url} />;
  return (
    <button className="session-context-audio-play" type="button" onClick={load} disabled={loading}>
      ▶ Voice memo {index + 1}
      {loading ? "…" : ""}
    </button>
  );
}

function ordinalText(n: number): string {
  if (!Number.isFinite(n) || n < 1) return "Next";
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] || "th"}`;
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
