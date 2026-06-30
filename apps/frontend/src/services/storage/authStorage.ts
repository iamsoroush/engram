import type { AuthSession, StoredAuthProfile } from "../../domain/appTypes";
import { DEV_AUTH_STORAGE_KEY } from "../../shared/lib/config";

// Persist the refresh token + profile so a full page refresh can re-establish the session
// (App bootstrap reads this and re-issues an access token via /auth/refresh). This runs in ALL
// envs — without it, production users are logged out on every refresh (access token is in-memory).
//
// Alpha trade-off: the refresh token lives in localStorage, which is an XSS exposure. The hardening
// path is a Secure HTTP-only cookie (see docs/frontend/auth-login.md, docs/production-alpha-tradeoffs.md).
export function persistAuthProfile(auth: AuthSession) {
  const profile: StoredAuthProfile = {
    refreshToken: auth.refreshToken,
    user: auth.user,
    tenant: auth.tenant,
    memberships: auth.memberships,
  };
  window.localStorage.setItem(DEV_AUTH_STORAGE_KEY, JSON.stringify(profile));
}

export function loadStoredAuthProfile() {
  try {
    const raw = window.localStorage.getItem(DEV_AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuthProfile) : null;
  } catch {
    window.localStorage.removeItem(DEV_AUTH_STORAGE_KEY);
    return null;
  }
}

export function clearStoredAuthProfile() {
  window.localStorage.removeItem(DEV_AUTH_STORAGE_KEY);
}
