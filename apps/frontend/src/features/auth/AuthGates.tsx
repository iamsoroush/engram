import React from "react";
import type { AuthSession, DevTier, Persona } from "../../domain/appTypes";
import type { Lang, Translator } from "../../shared/i18n";
import { IS_DEV } from "../../shared/lib/config";
import type { RegisterClinicInput } from "../../services/api/client";
import { Badge, Button, Card, Input } from "../../shared/ui/primitives";

function PendingNotice({ t, pendingCount }: { t: Translator; pendingCount: number }) {
  if (!pendingCount) return null;
  return <div className="alert alert-amber">{t("pending.notice", { n: pendingCount })}</div>;
}

export function LoginGate({
  t,
  error,
  pendingCount,
  onLogin,
  onPersonaLogin,
  onGotoSignup,
}: {
  t: Translator;
  error: string;
  pendingCount: number;
  onLogin: (email: string, password: string) => Promise<void>;
  onPersonaLogin: (persona: Persona, tier: DevTier) => Promise<void>;
  onGotoSignup: () => void;
}) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busyPersona, setBusyPersona] = React.useState<Persona | null>(null);
  const [devTier, setDevTier] = React.useState<DevTier>("pro");
  const [submitting, setSubmitting] = React.useState(false);
  // Therapy is a single-plan vertical with its own demo tenant + a second therapist persona so the
  // federated caseload (a clinician sees only their own clients) is visible side-by-side.
  const personas: Array<{ value: Persona; label: string }> =
    devTier === "therapy"
      ? [
          { value: "doctor", label: "Therapist (Dr. Demo)" },
          { value: "therapist-b", label: "Therapist B (Dr. Rava)" },
        ]
      : [
          { value: "doctor", label: "Doctor" },
          { value: "assistant", label: "Assistant" },
          { value: "admin", label: "Admin" },
          { value: "patient-preview", label: "Patient preview" },
        ];

  const submitLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onLogin(email, password);
    } finally {
      setSubmitting(false);
    }
  };

  const loginPersona = async (persona: Persona) => {
    setBusyPersona(persona);
    try {
      await onPersonaLogin(persona, devTier);
    } finally {
      setBusyPersona(null);
    }
  };

  return (
    <main className="login-shell">
      <Card className="login-card">
        <div className="stack">
          <h1>{t("login.title")}</h1>
          <p>{t("login.subtitle")}</p>
        </div>
        <PendingNotice t={t} pendingCount={pendingCount} />
        {/* Production-style real login form — always available so dev can exercise real auth too. */}
        <form className="stack" onSubmit={submitLogin}>
          <label className="field-label">
            {t("auth.email")}
            <Input autoComplete="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="field-label">
            {t("auth.password")}
            <Input
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          <Button disabled={submitting} type="submit">
            {submitting ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>
        {error ? <div className="alert alert-red">{error}</div> : null}
        <button className="auth-link" onClick={onGotoSignup} type="button">
          {t("login.toSignup")}
        </button>
        {IS_DEV ? (
          <div className="dev-signin">
            <p className="eyebrow">{t("login.devPersonas")}</p>
            <div className="dev-tier-switch" role="radiogroup" aria-label="Development tenant tier">
              <span>Tier</span>
              {(["pro", "basic", "therapy"] as const).map((tier) => (
                <button
                  aria-checked={devTier === tier}
                  className={devTier === tier ? "active" : ""}
                  disabled={busyPersona !== null}
                  key={tier}
                  onClick={() => setDevTier(tier)}
                  role="radio"
                  type="button"
                >
                  {tier === "pro" ? "Pro" : tier === "basic" ? "Basic" : "Therapy"}
                </button>
              ))}
            </div>
            <div className="persona-grid" aria-label="Development personas">
              {personas.map((persona) => (
                <Button
                  disabled={busyPersona !== null}
                  key={persona.value}
                  onClick={() => void loginPersona(persona.value)}
                  type="button"
                  variant={persona.value === "patient-preview" ? "secondary" : "default"}
                >
                  {busyPersona === persona.value ? "Signing in..." : persona.label}
                </Button>
              ))}
            </div>
          </div>
        ) : null}
      </Card>
    </main>
  );
}

export function SignUpGate({
  t,
  lang,
  pendingCount,
  onRegister,
  onGotoLogin,
}: {
  t: Translator;
  lang: Lang;
  pendingCount: number;
  onRegister: (input: RegisterClinicInput) => Promise<void>;
  onGotoLogin: () => void;
}) {
  const [clinicName, setClinicName] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError(t("signup.error.password"));
      return;
    }
    setSubmitting(true);
    try {
      // On success the parent commits auth and unmounts this gate, so we leave `submitting` set.
      await onRegister({ clinicName, fullName, email, password, appLanguage: lang });
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 409
          ? t("signup.error.emailTaken")
          : status === 400
            ? t("signup.error.email")
            : status === 422
              ? t("signup.error.password")
              : t("signup.error.generic"),
      );
      setSubmitting(false);
    }
  };

  return (
    <main className="login-shell">
      <Card className="login-card">
        <div className="stack">
          <h1>{t("signup.title")}</h1>
          <p>{t("signup.subtitle")}</p>
        </div>
        <PendingNotice t={t} pendingCount={pendingCount} />
        <form className="stack" onSubmit={submit}>
          <label className="field-label">
            {t("signup.clinicName")}
            <Input autoComplete="organization" onChange={(event) => setClinicName(event.target.value)} required value={clinicName} />
          </label>
          <label className="field-label">
            {t("signup.fullName")}
            <Input autoComplete="name" onChange={(event) => setFullName(event.target.value)} required value={fullName} />
          </label>
          <label className="field-label">
            {t("auth.email")}
            <Input autoComplete="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="field-label">
            {t("auth.password")}
            <Input
              autoComplete="new-password"
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
            <span className="field-hint">{t("signup.password.hint")}</span>
          </label>
          <Button disabled={submitting} type="submit">
            {submitting ? t("signup.submitting") : t("signup.submit")}
          </Button>
        </form>
        {error ? <div className="alert alert-red">{error}</div> : null}
        <button className="auth-link" onClick={onGotoLogin} type="button">
          {t("signup.toLogin")}
        </button>
      </Card>
    </main>
  );
}

export function PatientPreviewGate({ auth, onLogout }: { auth: AuthSession; onLogout: () => void }) {
  return (
    <main className="login-shell">
      <Card className="login-card">
        <div className="stack">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Patient preview</p>
              <h1>Limited access</h1>
            </div>
            <Badge tone="neutral">{auth.tenant.name}</Badge>
          </div>
          <p>
            {auth.user.displayName || auth.user.email} is signed in for patient preview only. Staff capture and review tools are not available in
            this mode.
          </p>
        </div>
        <Button onClick={onLogout} variant="secondary">
          Logout
        </Button>
      </Card>
    </main>
  );
}
