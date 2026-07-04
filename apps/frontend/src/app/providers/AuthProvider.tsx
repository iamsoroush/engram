import React from "react";
import type { AuthSession, DevTier, Persona } from "../../domain/appTypes";
import { toLang, translate, type Translator } from "../../shared/i18n";
import {
  loginWithPassword,
  loginWithPersona,
  logoutSession,
  refreshAuthToken,
  registerClinic,
  type RegisterClinicInput,
  switchTenant,
} from "../../services/api/client";
import { clearStoredAuthProfile, loadStoredAuthProfile, persistAuthProfile } from "../../services/storage/authStorage";
import { clearWorkspaceState } from "../../services/storage/workspaceStorage";
import { markOnboardingPending } from "../../features/onboarding/onboardingState";
import { useApi, useRegisterAuthBridge } from "./ApiProvider";

// Seam A2 (frontend-refactor plan §2). The auth session + its lifecycle — bootstrap-from-storage,
// commit/clear, sign-in/register/switch-clinic/tier, and the token-refresh bridge for ApiProvider —
// lifted out of the App god-component. Consumers read one auth source via useAuth().
//
// It sits BELOW ApiProvider (so it can call apiFetch, e.g. switchTenant) and registers its refresh
// bridge upward via useRegisterAuthBridge. The load-bearing refs (§6) — `authRef` for stale-free async
// reads, `bootstrappedAuthRef` — live here and `authRef` is exposed so the still-in-App sync/session
// code can keep reading the latest tenant without a reactive dependency. `appT` (translate bound to the
// app language via authRef, always current) is provided too: App renders ABOVE <AppLangProvider> so it
// can't useT(), and needs a live translator for capture-flow chrome/toasts.

export type AuthContextValue = {
  auth: AuthSession | null;
  authReady: boolean;
  authError: string;
  setAuthError: (message: string) => void;
  /** Always-current auth, for async closures that must not capture a stale session. */
  authRef: React.MutableRefObject<AuthSession | null>;
  /** Translator bound to the live app language (stable identity). */
  appT: Translator;
  commitAuth: (next: AuthSession) => void;
  clearAuth: () => void;
  /** Sign in with a dev persona. Sets authError and resolves null on failure. */
  signInWithPersona: (persona: Persona, tier?: DevTier) => Promise<AuthSession | null>;
  /** Sign in with email/password. Sets authError and resolves null on failure. */
  signInWithPassword: (email: string, password: string) => Promise<AuthSession | null>;
  /** Self-serve clinic sign-up. Lets the error propagate so the form can map 409/422. */
  register: (input: RegisterClinicInput) => Promise<AuthSession>;
  /** Re-issue a session for another of the user's clinics. Lets the error propagate. */
  switchClinic: (tenantId: string) => Promise<AuthSession>;
  /** Reflect a plan change in the in-app tenant so capabilities + UI follow. */
  applyTierChange: (tier: string) => void;
  /** Clear auth locally, then best-effort revoke the backend session. */
  logout: () => Promise<void>;
  onboardingDismissed: boolean;
  setOnboardingDismissed: React.Dispatch<React.SetStateAction<boolean>>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const apiFetch = useApi();
  const [auth, setAuth] = React.useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = React.useState(false);
  const [authError, setAuthError] = React.useState("");
  // First-run guided capture: shown once for a freshly signed-up founder (flagged in register),
  // dismissed (and the flag cleared) when they finish or skip the tour.
  const [onboardingDismissed, setOnboardingDismissed] = React.useState(false);
  const authRef = React.useRef<AuthSession | null>(null);
  const bootstrappedAuthRef = React.useRef(false);

  // App() renders ABOVE <AppLangProvider>, so it can't useT(); bind a translator to the live app
  // language (via authRef, always current) for the capture-flow chrome/toasts produced there.
  const appT = React.useCallback<Translator>(
    (key, vars) => translate(toLang(authRef.current?.tenant.appLanguage), key, vars),
    [],
  );

  const clearAuth = React.useCallback(() => {
    authRef.current = null;
    setAuth(null);
    clearStoredAuthProfile();
    clearWorkspaceState();
  }, []);

  const commitAuth = React.useCallback((nextAuth: AuthSession) => {
    authRef.current = nextAuth;
    setAuth(nextAuth);
    persistAuthProfile(nextAuth);
    setAuthError("");
  }, []);

  // Auth bridge for ApiProvider (seam A1): how apiFetch reads the current token and performs the single
  // token refresh (commit on success, clear on failure). Single-flight coalescing lives in ApiProvider.
  const refreshTokens = React.useCallback(async () => {
    const currentAuth = authRef.current;
    if (!currentAuth) throw new Error("No auth session");
    try {
      const tokens = await refreshAuthToken(currentAuth.refreshToken);
      const refreshed = { ...currentAuth, ...tokens };
      commitAuth(refreshed);
      return refreshed.accessToken;
    } catch (error) {
      clearAuth();
      throw error;
    }
  }, [clearAuth, commitAuth]);

  useRegisterAuthBridge({
    getAccessToken: () => authRef.current?.accessToken,
    refreshTokens,
  });

  // Restore a stored session on load: refresh its tokens (a stale refresh token clears it).
  React.useEffect(() => {
    if (bootstrappedAuthRef.current) return;
    bootstrappedAuthRef.current = true;
    const storedAuth = loadStoredAuthProfile();
    if (!storedAuth) {
      setAuthReady(true);
      return;
    }
    refreshAuthToken(storedAuth.refreshToken)
      .then((tokens) => commitAuth({ ...storedAuth, ...tokens }))
      .catch(() => clearAuth())
      .finally(() => setAuthReady(true));
  }, [clearAuth, commitAuth]);

  const signInWithPersona = React.useCallback<AuthContextValue["signInWithPersona"]>(
    async (persona, tier = "pro") => {
      setAuthError("");
      try {
        const next = await loginWithPersona(persona, tier);
        commitAuth(next);
        return next;
      } catch {
        setAuthError(appT("auth.toastCouldNotSignInPersona"));
        return null;
      }
    },
    [appT, commitAuth],
  );

  const signInWithPassword = React.useCallback<AuthContextValue["signInWithPassword"]>(
    async (email, password) => {
      setAuthError("");
      try {
        const next = await loginWithPassword(email, password);
        commitAuth(next);
        return next;
      } catch {
        setAuthError("Invalid email or password.");
        return null;
      }
    },
    [commitAuth],
  );

  const register = React.useCallback<AuthContextValue["register"]>(
    async (input) => {
      setAuthError("");
      const next = await registerClinic(input);
      markOnboardingPending(next.user.id);
      commitAuth(next);
      return next;
    },
    [commitAuth],
  );

  const switchClinic = React.useCallback<AuthContextValue["switchClinic"]>(
    async (tenantId) => {
      const next = await switchTenant(apiFetch, tenantId);
      commitAuth(next);
      return next;
    },
    [apiFetch, commitAuth],
  );

  const applyTierChange = React.useCallback<AuthContextValue["applyTierChange"]>((tier) => {
    const current = authRef.current;
    if (!current) return;
    const next = { ...current, tenant: { ...current.tenant, tier } };
    authRef.current = next;
    setAuth(next);
    persistAuthProfile(next);
  }, []);

  const logout = React.useCallback<AuthContextValue["logout"]>(async () => {
    const currentAuth = authRef.current;
    clearAuth();
    if (currentAuth) {
      try {
        await logoutSession(currentAuth.accessToken, currentAuth.refreshToken);
      } catch {
        // Local logout still wins when the backend cannot be reached.
      }
    }
  }, [clearAuth]);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      auth,
      authReady,
      authError,
      setAuthError,
      authRef,
      appT,
      commitAuth,
      clearAuth,
      signInWithPersona,
      signInWithPassword,
      register,
      switchClinic,
      applyTierChange,
      logout,
      onboardingDismissed,
      setOnboardingDismissed,
    }),
    [
      auth,
      authReady,
      authError,
      appT,
      commitAuth,
      clearAuth,
      signInWithPersona,
      signInWithPassword,
      register,
      switchClinic,
      applyTierChange,
      logout,
      onboardingDismissed,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
