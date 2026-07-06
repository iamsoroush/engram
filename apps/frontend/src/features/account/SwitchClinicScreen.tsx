import React from "react";
import type { AuthSession } from "../../domain/appTypes";
import { useT } from "../../shared/i18n";
import { Badge, Button, ScreenHeader } from "../../shared/ui/primitives";

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
  const t = useT();
  const KNOWN_ROLES = ["owner", "admin", "doctor", "assistant", "therapist-b", "patient-preview", "user"];
  const roleLabel = (role: string) => (KNOWN_ROLES.includes(role) ? t(`role.${role}`) : role);
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
      setError(t("switchclinic.switchError"));
      setBusy(null);
    }
  };

  return (
    <div className="account-screen" data-screen="switch-clinic">
      <ScreenHeader title={t("switchclinic.title")} onBack={onBack} backLabel={t("switchclinic.back")} />
      <p className="muted">{t("switchclinic.intro")}</p>
      <ul className="team-list">
        {clinics.map((clinic) => {
          const current = clinic.tenantId === auth.tenant.id;
          return (
            <li className="team-member" key={clinic.tenantId}>
              <div className="team-member-id">
                <strong data-content="clinic-name">{clinic.tenantName || clinic.tenantId}</strong>
                <small>{roleLabel(clinic.role)}</small>
              </div>
              <div className="team-member-controls">
                {current ? (
                  <Badge tone="blue">{t("switchclinic.currentBadge")}</Badge>
                ) : (
                  <Button disabled={busy !== null} onClick={() => void choose(clinic.tenantId)} size="sm" type="button">
                    {busy === clinic.tenantId ? t("switchclinic.switching") : t("switchclinic.switch")}
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
