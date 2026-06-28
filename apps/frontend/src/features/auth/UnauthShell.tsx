import React from "react";
import type { DevTier, Persona } from "../../domain/appTypes";
import type { RegisterClinicInput } from "../../services/api/client";
import { resetDocumentToAppDefault, useUiLang } from "../../shared/i18n";
import { LandingPage } from "../landing/LandingPage";
import { LoginGate, SignUpGate } from "./AuthGates";

type View = "landing" | "login" | "signup";

/**
 * The unauthenticated surface: a bilingual (fa/en) + RTL-aware shell that switches between the
 * landing page, login, and clinic sign-up. Owns the public UI language (the authed app reads the
 * tenant's app language instead). Resets <html> direction back to the app default on unmount.
 */
export function UnauthShell({
  error,
  pendingCount,
  onLogin,
  onPersonaLogin,
  onRegister,
}: {
  error: string;
  pendingCount: number;
  onLogin: (email: string, password: string) => Promise<void>;
  onPersonaLogin: (persona: Persona, tier: DevTier) => Promise<void>;
  onRegister: (input: RegisterClinicInput) => Promise<void>;
}) {
  const { lang, t, dir, toggleLang } = useUiLang();
  const [view, setView] = React.useState<View>("landing");

  React.useEffect(() => () => resetDocumentToAppDefault(), []);

  return (
    <div className="auth-root" dir={dir} lang={lang}>
      <header className="auth-topbar">
        <button className="auth-brand" onClick={() => setView("landing")} type="button">
          {t("brand.name")}
        </button>
        <button aria-label={t("lang.aria")} className="auth-lang-toggle" onClick={toggleLang} type="button">
          {t("lang.switchTo")}
        </button>
      </header>
      {view === "landing" ? (
        <LandingPage t={t} onLogin={() => setView("login")} onSignup={() => setView("signup")} />
      ) : view === "login" ? (
        <LoginGate
          error={error}
          onGotoSignup={() => setView("signup")}
          onLogin={onLogin}
          onPersonaLogin={onPersonaLogin}
          pendingCount={pendingCount}
          t={t}
        />
      ) : (
        <SignUpGate lang={lang} onGotoLogin={() => setView("login")} onRegister={onRegister} pendingCount={pendingCount} t={t} />
      )}
    </div>
  );
}
