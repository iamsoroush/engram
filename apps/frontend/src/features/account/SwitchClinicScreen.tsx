import React from "react";
import type { AuthSession } from "../../domain/appTypes";
import { Badge, Button } from "../../shared/ui/primitives";

/**
 * Clinic switcher for a user who belongs to more than one clinic (the cross-clinic case Team
 * enables). Lists their clinics from the auth memberships; choosing one re-issues a session for it.
 */
export function SwitchClinicScreen({
  auth,
  onBack,
  onSwitch,
}: {
  auth: AuthSession;
  onBack: () => void;
  onSwitch: (tenantId: string) => Promise<void>;
}) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");

  // One row per clinic (current first).
  const clinics = auth.memberships
    .filter((membership, index, all) => all.findIndex((other) => other.tenantId === membership.tenantId) === index)
    .sort((a, b) => (a.tenantId === auth.tenant.id ? -1 : b.tenantId === auth.tenant.id ? 1 : 0));

  const choose = async (tenantId: string) => {
    setBusy(tenantId);
    setError("");
    try {
      await onSwitch(tenantId);
    } catch {
      setError("Could not switch clinic. Please try again.");
      setBusy(null);
    }
  };

  return (
    <div className="account-screen" data-screen="switch-clinic">
      <div className="account-header">
        <Button className="account-back" onClick={onBack} size="sm" type="button" variant="secondary">
          <span aria-hidden="true">←</span> Back
        </Button>
        <h1>Switch clinic</h1>
      </div>
      <p className="muted">You're a member of more than one clinic. Choose which one to work in.</p>
      <ul className="team-list">
        {clinics.map((clinic) => {
          const current = clinic.tenantId === auth.tenant.id;
          return (
            <li className="team-member" key={clinic.tenantId}>
              <div className="team-member-id">
                <strong>{clinic.tenantName || clinic.tenantId}</strong>
                <small>{clinic.role}</small>
              </div>
              <div className="team-member-controls">
                {current ? (
                  <Badge tone="blue">Current</Badge>
                ) : (
                  <Button disabled={busy !== null} onClick={() => void choose(clinic.tenantId)} size="sm" type="button">
                    {busy === clinic.tenantId ? "Switching…" : "Switch"}
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {error ? <div className="alert alert-red">{error}</div> : null}
    </div>
  );
}
