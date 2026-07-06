import React from "react";
import type { AftercareTemplate, AftercareTemplateDraft, AiUsageState, ApiFetch, AuthSession, RolePermissions } from "../../domain/appTypes";
import { Button, Card } from "../../shared/ui/primitives";
import { SelectMenu } from "../../shared/ui/SelectMenu";
import { isAdmin as isAdminViewer } from "../../shared/lib/multiseat";
import { AftercareTemplatesSettings } from "../aesthetics/AftercareTemplatesSettings";
import { AiUsageCard } from "../aiUsage/AiUsageCard";
import { useT } from "../../shared/i18n";

type TenantSettingsUpdate = {
  transcriptionLanguage?: string;
  reportLanguage?: string | null;
  appLanguage?: string;
  matchStrictness?: string;
  shareIncludeBrands?: boolean;
  highRiskClinic?: boolean;
  rolePermissions?: RolePermissions;
};

// AES-905 — the non-owner roles an admin can configure + the ordered presets.
// Labels/hints are resolved through the i18n seam at render time (see RolePermissionsSettings).
const CONFIGURABLE_ROLES: Array<{ role: string; labelKey: string; hintKey: string }> = [
  { role: "assistant", labelKey: "settings.roleAssistantLabel", hintKey: "settings.roleAssistantHint" },
  { role: "doctor", labelKey: "settings.roleDoctorLabel", hintKey: "settings.roleDoctorHint" },
];
const PERMISSION_PRESETS: Array<{ value: string; labelKey: string }> = [
  { value: "contribute", labelKey: "settings.permPresetContribute" },
  { value: "reassign", labelKey: "settings.permPresetReassign" },
  { value: "full", labelKey: "settings.permPresetFull" },
];
const PRESET_DEFAULTS: RolePermissions = { assistant: "reassign", doctor: "contribute" };

function RolePermissionsSettings({
  auth,
  saving,
  onSave,
}: {
  auth: AuthSession;
  saving: boolean;
  onSave: (settings: TenantSettingsUpdate) => void;
}) {
  const t = useT();
  const resolved = auth.tenant.rolePermissions || {};
  return (
    <Card className="settings-group">
      <div className="settings-group-head">
        <h2>{t("settings.rolePermissionsTitle")}</h2>
        <p>{t("settings.rolePermissionsHint")}</p>
      </div>
      {CONFIGURABLE_ROLES.map(({ role, labelKey, hintKey }) => {
        const label = t(labelKey);
        return (
          <SettingRow key={role} label={label} hint={t(hintKey)}>
            <select
              aria-label={t("settings.rolePermissionAria", { role: label })}
              disabled={saving}
              onChange={(event) => onSave({ rolePermissions: { [role]: event.target.value } })}
              value={String(resolved[role] || PRESET_DEFAULTS[role] || "contribute")}
            >
              {PERMISSION_PRESETS.map((preset) => (
                <option key={preset.value} value={preset.value}>
                  {t(preset.labelKey)}
                </option>
              ))}
            </select>
          </SettingRow>
        );
      })}
    </Card>
  );
}

const capitalize = (value: string) => (value ? value[0].toUpperCase() + value.slice(1) : value);

function AccountHeader({ title, onBack }: { title: string; onBack: () => void }) {
  const t = useT();
  return (
    <div className="account-header">
      <Button className="account-back" onClick={onBack} size="sm" variant="secondary" type="button">
        <span aria-hidden="true">←</span> {t("settings.back")}
      </Button>
      <h1>{title}</h1>
    </div>
  );
}

function SettingRow({ label, hint, children }: { label: React.ReactNode; hint?: string; children: React.ReactNode }) {
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

export function SettingsScreen({
  auth,
  onBack,
  onUpdateSettings,
  onListAftercareTemplates,
  onCreateAftercareTemplate,
  onUpdateAftercareTemplate,
  onDeleteAftercareTemplate,
  apiFetch,
  aiUsage = null,
  onRefreshAiUsage,
}: {
  auth: AuthSession;
  onBack: () => void;
  onUpdateSettings: (settings: TenantSettingsUpdate) => Promise<void> | void;
  onListAftercareTemplates?: () => Promise<AftercareTemplate[]>;
  onCreateAftercareTemplate?: (draft: AftercareTemplateDraft) => Promise<AftercareTemplate>;
  onUpdateAftercareTemplate?: (id: string, draft: Partial<AftercareTemplateDraft>) => Promise<AftercareTemplate>;
  onDeleteAftercareTemplate?: (id: string) => Promise<void>;
  /** Authed fetch — used only by the AI-usage card's dev control. */
  apiFetch: ApiFetch;
  /** Fair-use monthly AI usage (null while loading, on failure, or for Basic/no-AI). */
  aiUsage?: AiUsageState | null;
  onRefreshAiUsage?: () => void;
}) {
  const t = useT();
  // Localize the vertical name (aesthetics/therapy/…); fall back to the capitalized raw value if unkeyed.
  const verticalKey = `vertical.${auth.tenant.vertical || "clinic"}`;
  const verticalLabel = t(verticalKey) === verticalKey ? capitalize(auth.tenant.vertical || "clinic") : t(verticalKey);
  const [saving, setSaving] = React.useState(false);
  const save = (settings: TenantSettingsUpdate) => {
    setSaving(true);
    void Promise.resolve(onUpdateSettings(settings)).finally(() => setSaving(false));
  };
  const tier = auth.tenant.tier === "basic" ? "basic" : "pro";
  // Language-choice options are AUTONYMS: each language renders in its own script regardless of UI
  // language, so they are NOT routed through t(). The "auto"/"" rows ARE chrome → translated.
  const APP_LANGUAGE_OPTIONS = [
    { value: "en", label: "English" },
    { value: "fa", label: "فارسی" },
    { value: "ar", label: "العربية" },
  ];
  return (
    <div className="account-screen">
      <AccountHeader title={t("settings.title")} onBack={onBack} />

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("settings.languagesTitle")}</h2>
          <p>{t("settings.languagesHint")}</p>
        </div>
        <SettingRow label={t("settings.appLabel")} hint={t("settings.appHint")}>
          <SelectMenu
            ariaLabel={t("settings.appLanguageAria")}
            disabled={saving}
            value={auth.tenant.appLanguage || "en"}
            onChange={(value) => save({ appLanguage: value })}
            options={APP_LANGUAGE_OPTIONS}
          />
        </SettingRow>
        <SettingRow label={t("settings.transcriptionLabel")} hint={t("settings.transcriptionHint")}>
          <SelectMenu
            ariaLabel={t("settings.transcriptionLanguageAria")}
            disabled={saving}
            value={auth.tenant.transcriptionLanguage || "auto"}
            onChange={(value) => save({ transcriptionLanguage: value })}
            options={[{ value: "auto", label: t("settings.transcriptionAuto") }, ...APP_LANGUAGE_OPTIONS]}
          />
        </SettingRow>
        <SettingRow label={t("settings.reportLabel")} hint={t("settings.reportHint")}>
          <SelectMenu
            ariaLabel={t("settings.reportLanguageAria")}
            disabled={saving}
            value={auth.tenant.reportLanguage || ""}
            onChange={(value) => save({ reportLanguage: value || null })}
            options={[{ value: "", label: t("settings.reportDefault") }, ...APP_LANGUAGE_OPTIONS]}
          />
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("settings.patientMatchingTitle")}</h2>
          <p>{t("settings.patientMatchingHint")}</p>
        </div>
        <SettingRow
          label={t("settings.autoApplyLabel")}
          hint={t("settings.autoApplyHint")}
        >
          <SelectMenu
            ariaLabel={t("settings.autoApplyAria")}
            disabled={saving}
            value={auth.tenant.matchStrictness || "strict"}
            onChange={(value) => save({ matchStrictness: value })}
            options={[
              { value: "strict", label: t("settings.matchStrict") },
              { value: "balanced", label: t("settings.matchBalanced") },
              { value: "lenient", label: t("settings.matchLenient") },
            ]}
          />
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("settings.patientSharingTitle")}</h2>
          <p>{t("settings.patientSharingHint")}</p>
        </div>
        <SettingRow
          label={t("settings.includeBrandsLabel")}
          hint={t("settings.includeBrandsHint")}
        >
          <input
            type="checkbox"
            aria-label={t("settings.includeBrandsAria")}
            disabled={saving}
            checked={Boolean(auth.tenant.shareIncludeBrands)}
            onChange={(event) => save({ shareIncludeBrands: event.target.checked })}
          />
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("settings.safetyTitle")}</h2>
          <p>{t("settings.safetyHint")}</p>
        </div>
        <SettingRow label={t("settings.highRiskLabel")} hint={t("settings.highRiskHint")}>
          <input
            type="checkbox"
            aria-label={t("settings.highRiskAria")}
            disabled={saving}
            checked={Boolean(auth.tenant.highRiskClinic)}
            onChange={(event) => save({ highRiskClinic: event.target.checked })}
          />
        </SettingRow>
      </Card>

      <Card className="settings-group">
        <div className="settings-group-head">
          <h2>{t("settings.planTitle")}</h2>
        </div>
        <SettingRow label={t("settings.tierLabel")} hint={tier === "pro" ? t("settings.tierHintPro") : t("settings.tierHintBasic")}>
          <span className={`report-tier-badge ${tier}`}>{tier === "pro" ? "Pro" : "Basic"}</span>
        </SettingRow>
        <SettingRow label={t("settings.workspaceLabel")} hint={t("settings.workspaceHint", { encounter: (auth.tenant.encounterLabel || "Session").toLowerCase() })}>
          <span className="profile-value">{verticalLabel}</span>
        </SettingRow>
      </Card>

      <AiUsageCard state={aiUsage} apiFetch={apiFetch} onRefresh={() => onRefreshAiUsage?.()} />

      {isAdminViewer(auth) ? <RolePermissionsSettings auth={auth} saving={saving} onSave={save} /> : null}

      {onListAftercareTemplates && onCreateAftercareTemplate && onUpdateAftercareTemplate && onDeleteAftercareTemplate ? (
        <AftercareTemplatesSettings
          onList={onListAftercareTemplates}
          onCreate={onCreateAftercareTemplate}
          onUpdate={onUpdateAftercareTemplate}
          onDelete={onDeleteAftercareTemplate}
        />
      ) : null}
      {/* NOTE: AI model selection is intentionally NOT user-facing. Models are chosen and optimized
          centrally (see docs/technical-decisions.md "AI model selection is not a user setting" and
          docs/business/ai-usage-limits.md). Do not add a model picker to Settings. */}
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
  const t = useT();
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
      <AccountHeader title={t("settings.profileTitle")} onBack={onBack} />

      <Card className="profile-card">
        <span className="profile-avatar" aria-hidden="true" data-content>{initials}</span>
        <div className="profile-identity">
          <strong data-content>{displayName}</strong>
          <span data-content>{auth.user.email}</span>
        </div>
      </Card>

      <Card className="settings-group">
        <SettingRow label={t("settings.roleLabel")}><span className="profile-value" data-content>{role}</span></SettingRow>
        <SettingRow label={t("settings.clinicLabel")}><span className="profile-value" data-content>{auth.tenant.name}</span></SettingRow>
      </Card>

      <Card className="settings-group profile-actions">
        <Button onClick={onLogout} size="sm" type="button" variant="secondary">
          {t("settings.logout")}
        </Button>
      </Card>

      {isAdmin && onClearLocal ? (
        <Card className="settings-group">
          <div className="settings-group-head">
            <h2>{t("settings.debugTitle")}</h2>
          </div>
          <Button onClick={onClearLocal} size="sm" type="button" variant="ghost">
            {t("settings.clearLocalCache")}
          </Button>
        </Card>
      ) : null}
    </div>
  );
}
