import React from "react";
import type { LastVisitMedia } from "../../domain/appTypes";

/**
 * Non-destructive media viewer for the session-context card. Captures and progress photos open
 * HERE — layered over the live session, which stays mounted underneath — instead of navigating away.
 * Two modes: a single-photo lightbox (page through a visit's photos) and a before/after comparator
 * (two visits side by side for eyeball progress, the aesthetics payoff).
 */
export type OverlayMedia = { media: LastVisitMedia; label: string };
export type MediaOverlayState =
  | { mode: "single"; items: OverlayMedia[]; index: number }
  | { mode: "compare"; left: OverlayMedia; right: OverlayMedia };

function useResolvedImage(endpoint: string | undefined, onResolveFile: (endpoint: string) => Promise<string>) {
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    let cancelled = false;
    setUrl("");
    if (!endpoint) return;
    void onResolveFile(endpoint)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [endpoint, onResolveFile]);
  React.useEffect(
    () => () => {
      if (url.startsWith("blob:")) URL.revokeObjectURL(url);
    },
    [url],
  );
  return url;
}

function OverlayImage({ item, onResolveFile }: { item: OverlayMedia; onResolveFile: (endpoint: string) => Promise<string> }) {
  const url = useResolvedImage(item.media.contentEndpoint || item.media.fileEndpoint, onResolveFile);
  return (
    <figure className="media-overlay-figure">
      {url ? <img alt={item.media.caption || item.label} src={url} /> : <div className="media-overlay-loading" aria-hidden="true" />}
      <figcaption className="media-overlay-caption">
        <span className="media-overlay-date">{item.label}</span>
        {item.media.caption ? (
          <span className="media-overlay-text" dir="auto">
            {item.media.caption}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

function SingleViewer({ items, initial, onResolveFile }: { items: OverlayMedia[]; initial: number; onResolveFile: (endpoint: string) => Promise<string> }) {
  const [index, setIndex] = React.useState(initial);
  const safe = Math.min(Math.max(index, 0), items.length - 1);
  return (
    <div className="media-overlay-single">
      <OverlayImage item={items[safe]} onResolveFile={onResolveFile} />
      {items.length > 1 ? (
        <div className="media-overlay-nav">
          <button type="button" onClick={() => setIndex((p) => (p - 1 + items.length) % items.length)} aria-label="Previous photo">
            ‹
          </button>
          <span>
            {safe + 1} / {items.length}
          </span>
          <button type="button" onClick={() => setIndex((p) => (p + 1) % items.length)} aria-label="Next photo">
            ›
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function MediaOverlay({
  state,
  onClose,
  onResolveFile,
}: {
  state: MediaOverlayState;
  onClose: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="media-overlay" role="dialog" aria-modal="true" aria-label="Photo viewer" onClick={onClose}>
      <div className="media-overlay-inner" onClick={(event) => event.stopPropagation()}>
        <button className="media-overlay-close" type="button" onClick={onClose} aria-label="Close">
          ✕
        </button>
        {state.mode === "compare" ? (
          <div className="media-overlay-compare">
            <OverlayImage item={state.left} onResolveFile={onResolveFile} />
            <span className="media-overlay-vs" aria-hidden="true">
              →
            </span>
            <OverlayImage item={state.right} onResolveFile={onResolveFile} />
          </div>
        ) : (
          <SingleViewer items={state.items} initial={state.index} onResolveFile={onResolveFile} />
        )}
      </div>
    </div>
  );
}
