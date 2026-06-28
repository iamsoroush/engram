import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { setClinicPlan } from "../../services/api/client";
import { useT } from "../../shared/i18n";
import { Badge, Button, Card } from "../../shared/ui/primitives";

const BASIC_FEATURE_KEYS = [
  "plan.basicFeature1",
  "plan.basicFeature2",
  "plan.basicFeature3",
  "plan.basicFeature4",
];

const PRO_FEATURE_KEYS = [
  "plan.proFeature1",
  "plan.proFeature2",
  "plan.proFeature3",
  "plan.proFeature4",
  "plan.proFeature5",
  "plan.proFeature6",
];

function PlanCard({
  name,
  tagline,
  features,
  current,
  highlight,
  busy,
  onSwitch,
}: {
  name: string;
  tagline: string;
  features: string[];
  current: boolean;
  highlight?: boolean;
  busy: boolean;
  onSwitch: () => void;
}) {
  const t = useT();
  return (
    <Card className={`plan-card${highlight ? " plan-card-pro" : ""}${current ? " plan-card-current" : ""}`}>
      <div className="plan-card-head">
        <h2>{name}</h2>
        {current ? <Badge tone="blue">{t("plan.currentBadge")}</Badge> : null}
      </div>
      <p className="plan-card-tagline">{tagline}</p>
      <ul className="plan-features">
        {features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>
      {current ? (
        <Button disabled type="button" variant="secondary">
          {t("plan.currentButton")}
        </Button>
      ) : (
        <Button disabled={busy} onClick={onSwitch} type="button">
          {busy ? t("plan.switching") : t("plan.switchTo", { name })}
        </Button>
      )}
    </Card>
  );
}

/**
 * Owner/admin plan management: compare Basic vs Pro and switch between them. No payment yet — the
 * switch flips the tenant tier directly so a clinic can explore each plan. The backend gates this to
 * owner/admin; on success the parent updates the in-app tenant tier (capabilities follow).
 */
export function PlanScreen({
  auth,
  apiFetch,
  onBack,
  onTierChanged,
}: {
  auth: AuthSession;
  apiFetch: ApiFetch;
  onBack: () => void;
  onTierChanged: (tier: string) => void;
}) {
  const t = useT();
  const current = auth.tenant.tier === "pro" ? "pro" : "basic";
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const switchTo = async (tier: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await setClinicPlan(apiFetch, tier);
      onTierChanged(result.tier);
    } catch {
      setError(t("plan.switchError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="account-screen" data-screen="plan">
      <div className="account-header">
        <Button className="account-back" onClick={onBack} size="sm" type="button" variant="secondary">
          <span aria-hidden="true">←</span> {t("plan.back")}
        </Button>
        <h1>{t("plan.title")}</h1>
      </div>
      <p className="muted plan-intro">
        {t("plan.intro")} <span data-content="clinic-name">{auth.tenant.name}</span> {t("plan.introOn")}{" "}
        <strong>{current === "pro" ? "Pro" : "Basic"}</strong>.
      </p>
      <div className="plan-grid">
        <PlanCard
          busy={busy}
          current={current === "basic"}
          features={BASIC_FEATURE_KEYS.map((key) => t(key))}
          name="Basic"
          onSwitch={() => switchTo("basic")}
          tagline={t("plan.basicTagline")}
        />
        <PlanCard
          busy={busy}
          current={current === "pro"}
          features={PRO_FEATURE_KEYS.map((key) => t(key))}
          highlight
          name="Pro"
          onSwitch={() => switchTo("pro")}
          tagline={t("plan.proTagline")}
        />
      </div>
      {error ? <div className="alert alert-red">{error}</div> : null}
    </div>
  );
}
