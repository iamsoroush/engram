import React from "react";

/**
 * The ✨ Try Pro upsell line (AES-801–804). Lightweight AI appears in Basic ONLY as a clearly
 * labelled, violet, **non-functional** teaser — a conversion lever, never a Basic feature. Tapping
 * it just surfaces a "Pro only" note here (the upgrade flow lives outside the alpha); it never runs
 * AI on Basic content.
 */
export function TryProTeaser({
  title,
  subtitle,
  cta = "Try Pro →",
  className,
}: {
  title: string;
  subtitle?: string;
  cta?: string;
  className?: string;
}) {
  const [acknowledged, setAcknowledged] = React.useState(false);
  return (
    <button
      className={`try-pro-teaser${className ? ` ${className}` : ""}`}
      onClick={() => setAcknowledged(true)}
      type="button"
      aria-label={`${title} — Pro feature`}
    >
      <span className="try-pro-spark" aria-hidden="true">
        <TrySparkIcon />
      </span>
      <span className="try-pro-copy">
        <span className="try-pro-title">{title}</span>
        {subtitle ? <span className="try-pro-subtitle">{subtitle}</span> : null}
        {acknowledged ? <span className="try-pro-note">Pro feature — upgrade your plan to enable this. Basic stays AI-free.</span> : null}
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
