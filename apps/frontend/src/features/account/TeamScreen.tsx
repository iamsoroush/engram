import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { createTeamMember, fetchTeamMembers, type TeamMember, updateTeamMember } from "../../services/api/client";
import { useT } from "../../shared/i18n";
import { Badge, Button, Card, Input, ScreenHeader } from "../../shared/ui/primitives";
import { SelectMenu } from "../../shared/ui/SelectMenu";

const ROLE_VALUES = ["doctor", "assistant", "admin"] as const;

/**
 * Owner/admin Team management: list members and add new ones. MVP model — the owner creates the
 * account with a temporary password they hand over (no email invite infra). Chrome is routed through
 * the i18n seam (useT); member names/emails are data and rendered verbatim. Backend enforces the
 * owner/admin gate + protects the owner and self.
 */
export function TeamScreen({ auth, apiFetch, onBack }: { auth: AuthSession; apiFetch: ApiFetch; onBack: () => void }) {
  const t = useT();
  const roleOptions = ROLE_VALUES.map((value) => ({ value, label: t(`role.${value}`) }));
  const roleLabel = (role: string) =>
    (ROLE_VALUES as readonly string[]).includes(role) ? t(`role.${role}`) : role;
  const [members, setMembers] = React.useState<TeamMember[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [listError, setListError] = React.useState("");

  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState("doctor");
  const [addError, setAddError] = React.useState("");
  const [addNotice, setAddNotice] = React.useState("");
  const [adding, setAdding] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      setMembers(await fetchTeamMembers(apiFetch));
    } catch {
      setListError(t("team.loadError"));
    } finally {
      setLoading(false);
    }
  }, [apiFetch, t]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const submitAdd = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAddError("");
    setAddNotice("");
    if (password && password.length < 8) {
      setAddError(t("team.passwordTooShort"));
      return;
    }
    setAdding(true);
    try {
      const member = await createTeamMember(apiFetch, { fullName, email, password: password || undefined, role });
      setAddNotice(
        member.created
          ? t("team.addedNoticeNew", { name: member.displayName })
          : t("team.addedNoticeExisting", { name: member.displayName }),
      );
      setFullName("");
      setEmail("");
      setPassword("");
      setRole("doctor");
      await load();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setAddError(
        status === 409
          ? t("team.addError409")
          : status === 422
            ? t("team.addError422")
            : t("team.addError"),
      );
    } finally {
      setAdding(false);
    }
  };

  const patchMember = async (member: TeamMember, patch: { role?: string; status?: string }) => {
    setListError("");
    try {
      const updated = await updateTeamMember(apiFetch, member.userId, patch);
      setMembers((prev) => prev.map((item) => (item.userId === updated.userId ? updated : item)));
    } catch {
      setListError(t("team.updateError"));
    }
  };

  return (
    <div className="account-screen" data-screen="team">
      <ScreenHeader title={t("team.title")} onBack={onBack} backLabel={t("team.back")} />

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("team.addMember")}</h2>
          <p>{t("team.addMemberHint")}</p>
        </div>
        <form className="stack team-add-form" onSubmit={submitAdd}>
          <label className="field-label">
            {t("team.fullName")}
            <Input autoComplete="off" onChange={(event) => setFullName(event.target.value)} required value={fullName} />
          </label>
          <label className="field-label">
            {t("team.email")}
            <Input autoComplete="off" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="field-label">
            {t("team.role")}
            <SelectMenu ariaLabel={t("team.roleAria")} disabled={adding} onChange={setRole} options={roleOptions} value={role} />
          </label>
          <label className="field-label">
            {t("team.tempPassword")}
            <Input
              autoComplete="off"
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              type="text"
              value={password}
            />
            <span className="field-hint">{t("team.tempPasswordHint")}</span>
          </label>
          <Button disabled={adding} type="submit">
            {adding ? t("team.adding") : t("team.addMemberButton")}
          </Button>
        </form>
        {addError ? <div className="alert alert-red">{addError}</div> : null}
        {addNotice ? <div className="alert alert-green">{addNotice}</div> : null}
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("team.members")}</h2>
          <p>
            {t("team.membersHint")} <span data-content="clinic-name">{auth.tenant.name}</span>
          </p>
        </div>
        {loading ? (
          <p className="muted">{t("team.loading")}</p>
        ) : listError ? (
          <div className="alert alert-red">{listError}</div>
        ) : (
          <ul className="team-list">
            {members.map((member) => (
              <li className="team-member" key={member.userId}>
                <div className="team-member-id">
                  <strong>
                    <span data-content="member-name">{member.displayName}</span>
                    {member.isSelf ? t("team.youSuffix") : ""}
                  </strong>
                  <small data-content="member-email">{member.email}</small>
                </div>
                <div className="team-member-controls">
                  {member.status === "disabled" ? <Badge tone="amber">{t("team.disabledBadge")}</Badge> : null}
                  {member.isOwner ? (
                    <Badge tone="blue">{t("role.owner")}</Badge>
                  ) : member.isSelf ? (
                    <Badge tone="neutral">{roleLabel(member.role)}</Badge>
                  ) : (
                    <>
                      <SelectMenu
                        ariaLabel={t("team.roleForMemberAria", { name: member.displayName })}
                        onChange={(value) => void patchMember(member, { role: value })}
                        options={roleOptions}
                        value={member.role}
                      />
                      <Button
                        onClick={() => void patchMember(member, { status: member.status === "active" ? "disabled" : "active" })}
                        size="sm"
                        type="button"
                        variant={member.status === "active" ? "secondary" : "default"}
                      >
                        {member.status === "active" ? t("team.disable") : t("team.enable")}
                      </Button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
