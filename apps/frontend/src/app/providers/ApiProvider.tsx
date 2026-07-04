import React from "react";
import type { ApiFetch } from "../../domain/appTypes";

// Seam A1 (frontend-refactor plan §2). The memoized `apiFetch` — bearer-token injection plus a
// single-flight 401 → refresh → retry — lifted out of the App god-component into shared infrastructure
// so every feature can consume it via `useApi()` instead of having it threaded down as a prop.
//
// apiFetch needs two things from auth: the current access token, and a way to refresh it. Auth lives
// in a provider NESTED BELOW this one (so it can itself call apiFetch, e.g. switchTenant), which means
// it can't hand those in as props. Instead a descendant registers an **auth bridge** into this
// provider's ref via `useRegisterAuthBridge`; apiFetch reads through the ref at call time, so it
// always sees the latest token/refresh without re-subscribing. The `refreshPromiseRef` single-flight
// (§6: coalesce concurrent 401 refreshes) lives here — it belongs with the fetch wrapper.

export type AuthBridge = {
  /** The current bearer token, or undefined when signed out. */
  getAccessToken: () => string | undefined;
  /**
   * Perform the actual token refresh (call the refresh endpoint, commit the new tokens, clear auth on
   * failure) and resolve to the new access token. Coalescing across concurrent 401s is handled here in
   * ApiProvider, so this just does the work once per call.
   */
  refreshTokens: () => Promise<string>;
};

type ApiContextValue = {
  apiFetch: ApiFetch;
  registerAuthBridge: (bridge: AuthBridge | null) => void;
};

const ApiContext = React.createContext<ApiContextValue | null>(null);

export function ApiProvider({ children }: { children: React.ReactNode }) {
  const bridgeRef = React.useRef<AuthBridge | null>(null);
  const refreshPromiseRef = React.useRef<Promise<string> | null>(null);

  const registerAuthBridge = React.useCallback((bridge: AuthBridge | null) => {
    bridgeRef.current = bridge;
  }, []);

  const refreshAccessToken = React.useCallback(async () => {
    const bridge = bridgeRef.current;
    if (!bridge) throw new Error("No auth session");
    if (!refreshPromiseRef.current) {
      refreshPromiseRef.current = bridge.refreshTokens().finally(() => {
        refreshPromiseRef.current = null;
      });
    }
    return refreshPromiseRef.current;
  }, []);

  /**
   * Adds the current bearer token to API requests and performs a single token
   * refresh/retry when the backend responds with 401.
   */
  const apiFetch = React.useCallback<ApiFetch>(
    async (input, init = {}) => {
      const token = bridgeRef.current?.getAccessToken();
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);

      const response = await fetch(input, { ...init, headers });
      if (response.status !== 401) return response;

      try {
        const nextToken = await refreshAccessToken();
        const retryHeaders = new Headers(init.headers);
        retryHeaders.set("Authorization", `Bearer ${nextToken}`);
        return await fetch(input, { ...init, headers: retryHeaders });
      } catch {
        return response;
      }
    },
    [refreshAccessToken],
  );

  const value = React.useMemo<ApiContextValue>(() => ({ apiFetch, registerAuthBridge }), [apiFetch, registerAuthBridge]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

/** The memoized, auth-aware fetch. Stable across renders. */
export function useApi(): ApiFetch {
  const ctx = React.useContext(ApiContext);
  if (!ctx) throw new Error("useApi must be used within ApiProvider");
  return ctx.apiFetch;
}

/**
 * Register how ApiProvider reads/refreshes the auth token. The supplied bridge's methods may close over
 * fresh state on every render — this hook re-points a stable wrapper at the latest one, so apiFetch
 * never captures a stale token or refresh closure.
 */
export function useRegisterAuthBridge(bridge: AuthBridge): void {
  const ctx = React.useContext(ApiContext);
  if (!ctx) throw new Error("useRegisterAuthBridge must be used within ApiProvider");
  const { registerAuthBridge } = ctx;
  const bridgeRef = React.useRef(bridge);
  bridgeRef.current = bridge;
  React.useEffect(() => {
    registerAuthBridge({
      getAccessToken: () => bridgeRef.current.getAccessToken(),
      refreshTokens: () => bridgeRef.current.refreshTokens(),
    });
    return () => registerAuthBridge(null);
  }, [registerAuthBridge]);
}
