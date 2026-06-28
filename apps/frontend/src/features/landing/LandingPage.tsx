import React from "react";
import type { Translator } from "../../shared/i18n";
import { Button } from "../../shared/ui/primitives";

type Modality = "audio" | "photo" | "note";

// Mirrors the real capture-bar icons (CaptureActions) so the landing shows the actual product.
function ModalityIcon({ name }: { name: Modality }) {
  if (name === "audio") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
        <path d="M24 5.5a8 8 0 0 0-8 8v12a8 8 0 0 0 16 0v-12a8 8 0 0 0-8-8Z" />
        <path d="M10.5 23.5v2a13.5 13.5 0 0 0 27 0v-2" />
        <path d="M24 39v5" />
        <path d="M17 44h14" />
      </svg>
    );
  }
  if (name === "photo") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
        <path d="M14.5 15.5h4.3l2.8-4h4.8l2.8 4h4.3a5 5 0 0 1 5 5v12a5 5 0 0 1-5 5h-19a5 5 0 0 1-5-5v-12a5 5 0 0 1 5-5Z" />
        <path d="M24 31.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path d="M10.5 11.5h27v22h-17l-10 8v-30Z" />
      <path d="M17.5 19.5h13" />
      <path d="M17.5 26.5h10" />
    </svg>
  );
}

// A stylized in-product preview (not a screenshot) built from the app's own tokens — RTL-safe and
// maintenance-free. Shows the capture-first surface: an unassigned visit + the audio/photo/note bar.
function AppPreview({ t }: { t: Translator }) {
  const modalities: Modality[] = ["note", "photo", "audio"];
  return (
    <figure className="landing-preview">
      <div className="landing-preview-screen" aria-hidden="true">
        <div className="landing-preview-topbar">
          <span className="landing-preview-brand">Engram</span>
        </div>
        <div className="landing-preview-session">
          <span className="landing-preview-dot" />
          <strong>{t("landing.preview.session")}</strong>
        </div>
        <div className="landing-preview-chip">{t("landing.preview.unassigned")}</div>
        <div className="landing-preview-card">
          <span className="landing-preview-line w70" />
          <span className="landing-preview-line w90" />
          <span className="landing-preview-line w55" />
        </div>
        <div className="landing-preview-bar">
          {modalities.map((m, index) => (
            <span className={`landing-preview-action${index === 0 ? " primary" : ""}`} key={m}>
              <ModalityIcon name={m} />
              {t(`landing.preview.${m}`)}
            </span>
          ))}
        </div>
      </div>
      <figcaption className="landing-preview-caption">{t("landing.preview.caption")}</figcaption>
    </figure>
  );
}

function HowStep({ t, n }: { t: Translator; n: "1" | "2" | "3" }) {
  return (
    <article className="landing-step">
      <span aria-hidden className="landing-step-index">
        {n}
      </span>
      <h3>{t(`landing.how.step${n}.title`)}</h3>
      <p>{t(`landing.how.step${n}.body`)}</p>
      {n === "1" ? (
        <div className="landing-step-modalities" aria-hidden="true">
          {(["audio", "photo", "note"] as Modality[]).map((m) => (
            <span className="landing-step-chip" key={m}>
              <ModalityIcon name={m} />
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function PlanTeaser({
  t,
  tier,
  onSignup,
}: {
  t: Translator;
  tier: "basic" | "pro";
  onSignup?: () => void;
}) {
  const isPro = tier === "pro";
  return (
    <article className={`landing-plan${isPro ? " landing-plan-pro" : ""}`}>
      <div className="landing-plan-head">
        <h3>{t(`landing.pricing.${tier}.name`)}</h3>
        {isPro ? <span className="landing-pro-tag">{t("landing.proTag")}</span> : null}
      </div>
      <p className="landing-plan-price">{t(`landing.pricing.${tier}.price`)}</p>
      <ul className="landing-plan-features">
        <li>{t(`landing.pricing.${tier}.f1`)}</li>
        <li>{t(`landing.pricing.${tier}.f2`)}</li>
        <li>{t(`landing.pricing.${tier}.f3`)}</li>
      </ul>
      {onSignup ? (
        <Button onClick={onSignup} type="button">
          {t("landing.cta.signup")}
        </Button>
      ) : null}
    </article>
  );
}

/**
 * Public marketing entry: what Engram is + how it works + trust + plans, with two calls to action.
 * Bilingual + RTL via the surrounding UnauthShell. Honest about tiers — Basic (the default for new
 * sign-ups) is presented on its own; the AI layer is shown as the Pro upgrade lane in Plans.
 */
export function LandingPage({ t, onSignup, onLogin }: { t: Translator; onSignup: () => void; onLogin: () => void }) {
  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <p className="eyebrow">{t("landing.eyebrow")}</p>
          <h1 className="landing-title">{t("landing.title")}</h1>
          <p className="landing-subtitle">{t("landing.subtitle")}</p>
          <div className="landing-cta">
            <Button onClick={onSignup} size="lg" type="button">
              {t("landing.cta.signup")}
            </Button>
            <Button onClick={onLogin} size="lg" type="button" variant="secondary">
              {t("landing.cta.login")}
            </Button>
          </div>
        </div>
        <div className="landing-hero-visual">
          <AppPreview t={t} />
        </div>
      </section>

      <section className="landing-section">
        <h2 className="landing-section-title">{t("landing.how.title")}</h2>
        <div className="landing-steps">
          <HowStep n="1" t={t} />
          <HowStep n="2" t={t} />
          <HowStep n="3" t={t} />
        </div>
      </section>

      <section className="landing-section">
        <h2 className="landing-section-title">{t("landing.trust.title")}</h2>
        <div className="landing-trust">
          {(["1", "2", "3"] as const).map((n) => (
            <article className="landing-trust-item" key={n}>
              <h3>{t(`landing.trust.${n}.title`)}</h3>
              <p>{t(`landing.trust.${n}.body`)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-pricing-head">
          <h2 className="landing-section-title">{t("landing.pricing.title")}</h2>
          <span className="landing-pricing-note">{t("landing.pricing.note")}</span>
        </div>
        <div className="landing-plans">
          <PlanTeaser onSignup={onSignup} t={t} tier="basic" />
          <PlanTeaser t={t} tier="pro" />
        </div>
      </section>

      <footer className="landing-footer">{t("landing.footer")}</footer>
    </main>
  );
}
