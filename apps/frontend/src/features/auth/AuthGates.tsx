import React from "react";
import type { AuthSession, DevTier, Persona } from "../../domain/appTypes";
import { IS_DEV } from "../../shared/lib/config";
import { Badge, Button, Card, Input } from "../../shared/ui/primitives";

export function LoginGate({
  error,
  pendingCount,
  onLogin,
  onPersonaLogin,
}: {
  error: string;
  pendingCount: number;
  onLogin: (email: string, password: string) => Promise<void>;
  onPersonaLogin: (persona: Persona, tier: DevTier) => Promise<void>;
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
          <p className="eyebrow">Memara</p>
          <h1>Sign in to continue</h1>
          <p>Capture opens after an authenticated tenant session is ready.</p>
        </div>
        {pendingCount ? (
          <div className="alert alert-amber">
            {pendingCount} capture{pendingCount === 1 ? "" : "s"} saved on this device. Sign in and I'll organize {pendingCount === 1 ? "it" : "them"} when connection is available.
          </div>
        ) : null}
        {IS_DEV ? (
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
        ) : null}
        {IS_DEV ? (
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
        ) : (
          <form className="stack" onSubmit={submitLogin}>
            <label className="field-label">
              Email
              <Input autoComplete="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
            </label>
            <label className="field-label">
              Password
              <Input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <Button disabled={submitting} type="submit">
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        )}
        {error ? <div className="alert alert-red">{error}</div> : null}
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
