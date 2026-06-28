import React from "react";
import { createPortal } from "react-dom";
import { useT } from "../../shared/i18n";

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
  features,
  cta,
  className,
  compact = false,
}: {
  title: string;
  subtitle?: string;
  /** When set, the info box lists these Pro capabilities as bullets (a consolidated explainer). */
  features?: string[];
  cta?: string;
  className?: string;
  compact?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const ctaLabel = cta ?? t("trypro.ctaGo");

  const trigger = compact ? (
    <button className={`try-pro-badge${className ? ` ${className}` : ""}`} onClick={() => setOpen(true)} type="button" aria-label={t("trypro.tryProFor", { title })}>
      <span className="try-pro-badge-spark" aria-hidden="true"><TrySparkIcon /></span>
      {t("trypro.tryPro")}
    </button>
  ) : (
    <button className={`try-pro-teaser${className ? ` ${className}` : ""}`} onClick={() => setOpen(true)} type="button" aria-label={t("trypro.tryProFor", { title })}>
      <span className="try-pro-spark" aria-hidden="true"><TrySparkIcon /></span>
      <span className="try-pro-copy">
        <span className="try-pro-title">{title}</span>
        {subtitle ? <span className="try-pro-subtitle">{subtitle}</span> : null}
      </span>
      <span className="try-pro-go" aria-hidden="true">{ctaLabel}</span>
    </button>
  );

  return (
    <>
      {trigger}
      {open ? <TryProInfo title={title} subtitle={subtitle} features={features} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function TryProInfo({ title, subtitle, features, onClose }: { title: string; subtitle?: string; features?: string[]; onClose: () => void }) {
  const t = useT();
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const node = (
    <div className="try-pro-info-backdrop" role="presentation" onClick={onClose}>
      <div className="try-pro-info" role="dialog" aria-modal="true" aria-label={t("trypro.tryPro")} onClick={(event) => event.stopPropagation()}>
        <button className="try-pro-info-x" onClick={onClose} type="button" aria-label={t("trypro.close")}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
        <span className="try-pro-info-spark" aria-hidden="true"><TrySparkIcon /></span>
        <span className="try-pro-info-eyebrow">{features && features.length ? t("trypro.upgradeEyebrow") : t("trypro.featureEyebrow")}</span>
        <h3 className="try-pro-info-title">{title}</h3>
        {subtitle ? <p className="try-pro-info-sub">{subtitle}</p> : null}
        {features && features.length ? (
          <ul className="try-pro-info-features">
            {features.map((feature) => (
              <li key={feature}>
                <span className="try-pro-info-feature-spark" aria-hidden="true"><TrySparkIcon /></span>
                {feature}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="try-pro-info-note">{t("trypro.note")}</p>
        <div className="try-pro-info-actions">
          <button className="try-pro-info-close" onClick={onClose} type="button">{t("trypro.gotIt")}</button>
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
