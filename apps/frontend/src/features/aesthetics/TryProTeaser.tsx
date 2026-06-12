import React from "react";
import { createPortal } from "react-dom";

/**
 * The ✨ Try Pro upsell line (AES-801–804). Lightweight AI appears in Basic ONLY as a clearly
 * labelled, violet, **non-functional** teaser — a conversion lever, never a Basic feature. It never
 * runs AI on Basic content; tapping opens a small info box explaining the Pro feature.
 *
 * Two shapes, same style language:
 * - `compact` → a small "✨ Try Pro" badge (used on capture cards). Position with `className`.
 * - default → a full card (used once per surface: the Basic report, the patient file).
 */
export function TryProTeaser({
  title,
  subtitle,
  cta = "Try Pro →",
  className,
  compact = false,
}: {
  title: string;
  subtitle?: string;
  cta?: string;
  className?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = React.useState(false);

  const trigger = compact ? (
    <button className={`try-pro-badge${className ? ` ${className}` : ""}`} onClick={() => setOpen(true)} type="button" aria-label={`Try Pro — ${title}`}>
      <span className="try-pro-badge-spark" aria-hidden="true"><TrySparkIcon /></span>
      Try Pro
    </button>
  ) : (
    <button className={`try-pro-teaser${className ? ` ${className}` : ""}`} onClick={() => setOpen(true)} type="button" aria-label={`Try Pro — ${title}`}>
      <span className="try-pro-spark" aria-hidden="true"><TrySparkIcon /></span>
      <span className="try-pro-copy">
        <span className="try-pro-title">{title}</span>
        {subtitle ? <span className="try-pro-subtitle">{subtitle}</span> : null}
      </span>
      <span className="try-pro-go" aria-hidden="true">{cta}</span>
    </button>
  );

  return (
    <>
      {trigger}
      {open ? <TryProInfo title={title} subtitle={subtitle} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function TryProInfo({ title, subtitle, onClose }: { title: string; subtitle?: string; onClose: () => void }) {
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const node = (
    <div className="try-pro-info-backdrop" role="presentation" onClick={onClose}>
      <div className="try-pro-info" role="dialog" aria-modal="true" aria-label="Try Pro" onClick={(event) => event.stopPropagation()}>
        <button className="try-pro-info-x" onClick={onClose} type="button" aria-label="Close">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
        <span className="try-pro-info-spark" aria-hidden="true"><TrySparkIcon /></span>
        <span className="try-pro-info-eyebrow">Pro feature</span>
        <h3 className="try-pro-info-title">{title}</h3>
        {subtitle ? <p className="try-pro-info-sub">{subtitle}</p> : null}
        <p className="try-pro-info-note">This is part of the Pro plan — Basic stays AI-free. Upgrade to enable it.</p>
        <div className="try-pro-info-actions">
          <button className="try-pro-info-close" onClick={onClose} type="button">Got it</button>
        </div>
      </div>
    </div>
  );

  // Portal to the document body so the overlay is never trapped/clipped by an ancestor's stacking
  // or transform context (which made it render incomplete and undismissable inside the feed card).
  if (typeof document === "undefined") return node;
  return createPortal(node, document.body);
}

export function TrySparkIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m12 3 1.4 4.2L17.5 9l-4.1 1.8L12 15l-1.4-4.2L6.5 9l4.1-1.8L12 3ZM5.5 13l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM18 14l.9 2.6 2.6.9-2.6.9L18 21l-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
    </svg>
  );
}
