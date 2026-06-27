import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { setClinicPlan } from "../../services/api/client";
import { Badge, Button, Card } from "../../shared/ui/primitives";

const BASIC_FEATURES = [
  "Fast capture — audio, photo, or note",
  "Saved on device, synced when online",
  "Captures organized into visit sessions",
  "Last-visit reference at capture",
];

const PRO_FEATURES = [
  "Everything in Basic, plus:",
  "AI transcription + photo captions",
  "AI-drafted visit reports & summaries",
  "AI patient matching & out-of-context checks",
  "Longitudinal patient memory across visits",
  "Post-session patient Q&A (doctor-verified)",
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
  return (
    <Card className={`plan-card${highlight ? " plan-card-pro" : ""}${current ? " plan-card-current" : ""}`}>
      <div className="plan-card-head">
        <h2>{name}</h2>
        {current ? <Badge tone="blue">Current plan</Badge> : null}
      </div>
      <p className="plan-card-tagline">{tagline}</p>
      <ul className="plan-features">
        {features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>
      {current ? (
        <Button disabled type="button" variant="secondary">
          Your current plan
        </Button>
      ) : (
        <Button disabled={busy} onClick={onSwitch} type="button">
          {busy ? "Switching…" : `Switch to ${name}`}
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
      setError("Could not change your plan. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="account-screen" data-screen="plan">
      <div className="account-header">
        <Button className="account-back" onClick={onBack} size="sm" type="button" variant="secondary">
          <span aria-hidden="true">←</span> Back
        </Button>
        <h1>Plan</h1>
      </div>
      <p className="muted plan-intro">
        No payment yet — switch freely to explore each plan. {auth.tenant.name} is on{" "}
        <strong>{current === "pro" ? "Pro" : "Basic"}</strong>.
      </p>
      <div className="plan-grid">
        <PlanCard
          busy={busy}
          current={current === "basic"}
          features={BASIC_FEATURES}
          name="Basic"
          onSwitch={() => switchTo("basic")}
          tagline="Capture-first record keeping — fast, reliable, offline-friendly."
        />
        <PlanCard
          busy={busy}
          current={current === "pro"}
          features={PRO_FEATURES}
          highlight
          name="Pro"
          onSwitch={() => switchTo("pro")}
          tagline="Adds the full AI layer: reports, patient memory, and Q&A."
        />
      </div>
      {error ? <div className="alert alert-red">{error}</div> : null}
    </div>
  );
}
