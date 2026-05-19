import type { AuthSession, StoredAuthProfile } from "./appTypes";
import { DEV_AUTH_STORAGE_KEY, IS_DEV } from "./config";

export function persistAuthProfile(auth: AuthSession) {
  if (!IS_DEV) return;
  const profile: StoredAuthProfile = {
    refreshToken: auth.refreshToken,
    user: auth.user,
    tenant: auth.tenant,
    memberships: auth.memberships,
  };
  window.localStorage.setItem(DEV_AUTH_STORAGE_KEY, JSON.stringify(profile));
}

export function loadStoredAuthProfile() {
  if (!IS_DEV) return null;
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
