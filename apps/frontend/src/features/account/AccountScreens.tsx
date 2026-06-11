import React from "react";
import type { AiModelConfig, AuthSession } from "../../domain/appTypes";
import { Button, Card } from "../../shared/ui/primitives";

type TenantSettingsUpdate = { transcriptionLanguage?: string; reportLanguage?: string | null; matchStrictness?: string };

const capitalize = (value: string) => (value ? value[0].toUpperCase() + value.slice(1) : value);

function AccountHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div className="account-header">
      <Button className="account-back" onClick={onBack} size="sm" variant="secondary" type="button">
        <span aria-hidden="true">←</span> Back
      </Button>
      <h1>{title}</h1>
    </div>
  );
}

function SettingRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="setting-row">
      <span className="setting-row-main">
        <span className="setting-row-label">{label}</span>
        {hint ? <span className="setting-row-hint">{hint}</span> : null}
      </span>
      <span className="setting-row-control">{children}</span>
    </div>
  );
}

function AiModelsSettings({
  onListAiModels,
  onUpdateAiModels,
}: {
  onListAiModels: () => Promise<AiModelConfig>;
  onUpdateAiModels: (models: Record<string, string>) => Promise<AiModelConfig>;
}) {
  const [tasks, setTasks] = React.useState<AiModelConfig["tasks"]>([]);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const [loaded, setLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState(0);
  React.useEffect(() => {
    let cancelled = false;
    void onListAiModels()
      .then((config) => {
        if (cancelled) return;
        setTasks(config.tasks);
        setDrafts(Object.fromEntries(config.tasks.map((task) => [task.task, task.model])));
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [onListAiModels]);
  const dirty = tasks.some((task) => (drafts[task.task] || "") !== (task.model || ""));
  const save = () => {
    setSaving(true);
    void onUpdateAiModels(drafts)
      .then((config) => {
        setTasks(config.tasks);
        setDrafts(Object.fromEntries(config.tasks.map((task) => [task.task, task.model])));
        setSavedAt(Date.now());
      })
      .catch(() => undefined)
      .finally(() => setSaving(false));
  };
  return (
    <Card className="settings-group">
      <div className="settings-group-head">
        <h2>AI models</h2>
        <p>Pick the model for each AI task. Changes apply to the next request — no restart. Blank = the worker's default.</p>
      </div>
      {tasks.map((task) => (
        <SettingRow key={task.task} label={task.label}>
          <input
            aria-label={`${task.label} model`}
            className="setting-text-input"
            disabled={saving || !loaded}
            onChange={(event) => setDrafts((current) => ({ ...current, [task.task]: event.target.value }))}
            placeholder="Worker default"
            spellCheck={false}
            value={drafts[task.task] ?? ""}
          />
        </SettingRow>
      ))}
      <div className="settings-group-actions">
        <Button disabled={!dirty || saving} onClick={save} size="sm" type="button">
          {saving ? "Saving…" : "Save AI models"}
        </Button>
        {savedAt && !dirty ? <span className="setting-saved-note">Saved</span> : null}
      </div>
    </Card>
  );
}

export function SettingsScreen({
  auth,
  onBack,
  onUpdateSettings,
  onListAiModels,
  onUpdateAiModels,
}: {
  auth: AuthSession;
  onBack: () => void;
  onUpdateSettings: (settings: TenantSettingsUpdate) => Promise<void> | void;
  onListAiModels?: () => Promise<AiModelConfig>;
  onUpdateAiModels?: (models: Record<string, string>) => Promise<AiModelConfig>;
}) {
  const [saving, setSaving] = React.useState(false);
  const save = (settings: TenantSettingsUpdate) => {
    setSaving(true);
    void Promise.resolve(onUpdateSettings(settings)).finally(() => setSaving(false));
  };
  const tier = auth.tenant.tier === "basic" ? "basic" : "pro";
  return (
    <div className="account-screen">
      <AccountHeader title="Settings" onBack={onBack} />

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>Languages</h2>
          <p>How Memara transcribes audio and writes the report.</p>
        </div>
        <SettingRow label="Transcription" hint="Auto transcribes verbatim in the spoken script — best for mixed-language clinics; avoids romanization that breaks name matching.">
          <select aria-label="Transcription language" disabled={saving} onChange={(event) => save({ transcriptionLanguage: event.target.value })} value={auth.tenant.transcriptionLanguage || "auto"}>
            <option value="auto">Auto (verbatim)</option>
            <option value="fa">Persian</option>
            <option value="en">English</option>
            <option value="ar">Arabic</option>
          </select>
        </SettingRow>
        <SettingRow label="Report" hint="The language the synthesized report is written in.">
          <select aria-label="Report language" disabled={saving} onChange={(event) => save({ reportLanguage: event.target.value || null })} value={auth.tenant.reportLanguage || ""}>
            <option value="">Report default</option>
            <option value="fa">Persian</option>
            <option value="en">English</option>
            <option value="ar">Arabic</option>
          </select>
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>Patient matching</h2>
          <p>How aggressively AI auto-assigns a close (fuzzy) name match.</p>
        </div>
        <SettingRow
          label="Auto-apply"
          hint="Strict = deterministic matches only. Balanced/Lenient also auto-apply a single high-confidence close match on an explicit instruction. The national-ID conflict guard and ambiguous routing apply at every level."
        >
          <select aria-label="Auto-apply" disabled={saving} onChange={(event) => save({ matchStrictness: event.target.value })} value={auth.tenant.matchStrictness || "strict"}>
            <option value="strict">Strict (exact only)</option>
            <option value="balanced">Balanced (close match)</option>
            <option value="lenient">Lenient (looser)</option>
          </select>
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>Plan</h2>
        </div>
        <SettingRow label="Tier" hint={tier === "pro" ? "Pro: AI assignment, image captions, and a synthesized live report." : "Basic: transcription and manual patient assignment."}>
          <span className={`report-tier-badge ${tier}`}>{tier === "pro" ? "Pro" : "Basic"}</span>
        </SettingRow>
        <SettingRow label="Workspace" hint={`Each visit is recorded as a ${(auth.tenant.encounterLabel || "Session").toLowerCase()}.`}>
          <span className="profile-value">{capitalize(auth.tenant.vertical || "clinic")}</span>
        </SettingRow>
      </Card>

      {onListAiModels && onUpdateAiModels ? (
        <AiModelsSettings onListAiModels={onListAiModels} onUpdateAiModels={onUpdateAiModels} />
      ) : null}
    </div>
  );
}

export function ProfileScreen({
  auth,
  onBack,
  onLogout,
  onClearLocal,
}: {
  auth: AuthSession;
  onBack: () => void;
  onLogout: () => void;
  onClearLocal?: () => void;
}) {
  const displayName = auth.user.displayName || auth.user.email;
  const role = auth.memberships[0]?.role || auth.user.persona || "user";
  const isAdmin = auth.memberships.some((membership) => membership.role === "admin") || auth.user.persona === "admin";
  const initials =
    displayName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "A";
  return (
    <div className="account-screen">
      <AccountHeader title="Profile" onBack={onBack} />

      <Card className="profile-card">
        <span className="profile-avatar" aria-hidden="true">{initials}</span>
        <div className="profile-identity">
          <strong>{displayName}</strong>
          <span>{auth.user.email}</span>
        </div>
      </Card>

      <Card className="settings-group">
        <SettingRow label="Role"><span className="profile-value">{role}</span></SettingRow>
        <SettingRow label="Clinic"><span className="profile-value">{auth.tenant.name}</span></SettingRow>
      </Card>

      <Card className="settings-group profile-actions">
        <Button onClick={onLogout} size="sm" type="button" variant="secondary">
          Logout
        </Button>
      </Card>

      {isAdmin && onClearLocal ? (
        <Card className="settings-group">
          <div className="settings-group-head">
            <h2>Debug</h2>
          </div>
          <Button onClick={onClearLocal} size="sm" type="button" variant="ghost">
            Clear local capture cache
          </Button>
        </Card>
      ) : null}
    </div>
  );
}
