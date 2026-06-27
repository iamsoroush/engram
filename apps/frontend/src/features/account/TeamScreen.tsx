import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { createTeamMember, fetchTeamMembers, type TeamMember, updateTeamMember } from "../../services/api/client";
import { Badge, Button, Card, Input } from "../../shared/ui/primitives";
import { SelectMenu } from "../../shared/ui/SelectMenu";

const ROLE_OPTIONS = [
  { value: "doctor", label: "Doctor" },
  { value: "assistant", label: "Assistant" },
  { value: "admin", label: "Admin" },
];

const roleLabel = (role: string) => ROLE_OPTIONS.find((option) => option.value === role)?.label ?? role;

/**
 * Owner/admin Team management: list members and add new ones. MVP model — the owner creates the
 * account with a temporary password they hand over (no email invite infra). English-only, like the
 * other account screens. Backend enforces the owner/admin gate + protects the owner and self.
 */
export function TeamScreen({ auth, apiFetch, onBack }: { auth: AuthSession; apiFetch: ApiFetch; onBack: () => void }) {
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
      setListError("Could not load your team.");
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const submitAdd = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAddError("");
    setAddNotice("");
    if (password && password.length < 8) {
      setAddError("A temporary password must be at least 8 characters.");
      return;
    }
    setAdding(true);
    try {
      const member = await createTeamMember(apiFetch, { fullName, email, password: password || undefined, role });
      setAddNotice(
        member.created
          ? `Added ${member.displayName}. Share their email + temporary password so they can sign in.`
          : `Added ${member.displayName} to your clinic — they sign in with their existing account.`,
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
          ? "An account with this email already exists."
          : status === 422
            ? "Enter a valid email and a password of at least 8 characters."
            : "Could not add the member.",
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
      setListError("Could not update the member.");
    }
  };

  return (
    <div className="account-screen" data-screen="team">
      <div className="account-header">
        <Button className="account-back" onClick={onBack} size="sm" type="button" variant="secondary">
          <span aria-hidden="true">←</span> Back
        </Button>
        <h1>Team</h1>
      </div>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>Add a member</h2>
          <p>Create a teammate's account and share the temporary password with them. They sign in with their email.</p>
        </div>
        <form className="stack team-add-form" onSubmit={submitAdd}>
          <label className="field-label">
            Full name
            <Input autoComplete="off" onChange={(event) => setFullName(event.target.value)} required value={fullName} />
          </label>
          <label className="field-label">
            Email
            <Input autoComplete="off" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="field-label">
            Role
            <SelectMenu ariaLabel="Member role" disabled={adding} onChange={setRole} options={ROLE_OPTIONS} value={role} />
          </label>
          <label className="field-label">
            Temporary password
            <Input
              autoComplete="off"
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              type="text"
              value={password}
            />
            <span className="field-hint">
              For a new person (≥ 8 chars), to share with them. Leave blank if they already have a Engram account.
            </span>
          </label>
          <Button disabled={adding} type="submit">
            {adding ? "Adding…" : "Add member"}
          </Button>
        </form>
        {addError ? <div className="alert alert-red">{addError}</div> : null}
        {addNotice ? <div className="alert alert-green">{addNotice}</div> : null}
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>Members</h2>
          <p>Everyone with access to {auth.tenant.name}.</p>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : listError ? (
          <div className="alert alert-red">{listError}</div>
        ) : (
          <ul className="team-list">
            {members.map((member) => (
              <li className="team-member" key={member.userId}>
                <div className="team-member-id">
                  <strong>
                    {member.displayName}
                    {member.isSelf ? " (you)" : ""}
                  </strong>
                  <small>{member.email}</small>
                </div>
                <div className="team-member-controls">
                  {member.status === "disabled" ? <Badge tone="amber">Disabled</Badge> : null}
                  {member.isOwner ? (
                    <Badge tone="blue">Owner</Badge>
                  ) : member.isSelf ? (
                    <Badge tone="neutral">{roleLabel(member.role)}</Badge>
                  ) : (
                    <>
                      <SelectMenu
                        ariaLabel={`Role for ${member.displayName}`}
                        onChange={(value) => void patchMember(member, { role: value })}
                        options={ROLE_OPTIONS}
                        value={member.role}
                      />
                      <Button
                        onClick={() => void patchMember(member, { status: member.status === "active" ? "disabled" : "active" })}
                        size="sm"
                        type="button"
                        variant={member.status === "active" ? "secondary" : "default"}
                      >
                        {member.status === "active" ? "Disable" : "Enable"}
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
