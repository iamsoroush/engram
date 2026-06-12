import React from "react";

/**
 * The ✨ Try Pro upsell line (AES-801–804). Lightweight AI appears in Basic ONLY as a clearly
 * labelled, violet, **non-functional** teaser — a conversion lever, never a Basic feature. It never
 * runs AI on Basic content; tapping only reveals a "Pro feature" note.
 *
 * Two shapes:
 * - `compact` → a small inline chip (used on capture cards, one per type) that expands on tap and
 *   can be dismissed, so the feed stays calm.
 * - default → a full card (used once per surface: the Basic report, the patient file).
 */
export function TryProTeaser({
  title,
  subtitle,
  cta = "Try Pro →",
  className,
  compact = false,
  chipLabel,
}: {
  title: string;
  subtitle?: string;
  cta?: string;
  className?: string;
  compact?: boolean;
  chipLabel?: string;
}) {
  const [dismissed, setDismissed] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  if (dismissed) return null;

  if (compact) {
    return (
      <div className={`try-pro-chip-wrap${className ? ` ${className}` : ""}`}>
        <button className="try-pro-chip" onClick={() => setOpen((value) => !value)} type="button" aria-expanded={open}>
          <span className="try-pro-chip-spark" aria-hidden="true"><TrySparkIcon /></span>
          <span className="try-pro-chip-label">{chipLabel || title}</span>
        </button>
        <button className="try-pro-chip-dismiss" onClick={() => setDismissed(true)} type="button" aria-label="Dismiss Try Pro">×</button>
        {open ? (
          <div className="try-pro-chip-panel">
            <p className="try-pro-chip-title">{title}</p>
            {subtitle ? <p className="try-pro-chip-sub">{subtitle}</p> : null}
            <p className="try-pro-chip-note">Pro feature — upgrade your plan to enable this. Basic stays AI-free.</p>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <button
      className={`try-pro-teaser${className ? ` ${className}` : ""}`}
      onClick={() => setOpen(true)}
      type="button"
      aria-label={`${title} — Pro feature`}
    >
      <span className="try-pro-spark" aria-hidden="true"><TrySparkIcon /></span>
      <span className="try-pro-copy">
        <span className="try-pro-title">{title}</span>
        {subtitle ? <span className="try-pro-subtitle">{subtitle}</span> : null}
        {open ? <span className="try-pro-note">Pro feature — upgrade your plan to enable this. Basic stays AI-free.</span> : null}
      </span>
      <span className="try-pro-go" aria-hidden="true">{cta}</span>
    </button>
  );
}

export function TrySparkIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m12 3 1.4 4.2L17.5 9l-4.1 1.8L12 15l-1.4-4.2L6.5 9l4.1-1.8L12 3ZM5.5 13l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM18 14l.9 2.6 2.6.9-2.6.9L18 21l-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
    </svg>
  );
}
