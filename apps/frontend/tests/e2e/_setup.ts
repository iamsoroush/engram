import type { Page } from "@playwright/test";

// Hermetic e2e helpers: the frontend runs for real, the backend is mocked via page.route. These
// cover the launch-gap UI spine (landing/auth, onboarding gating + tier accuracy, account-menu role
// gating) without depending on a live backend.

export type AuthOptions = {
  tier?: "basic" | "pro";
  role?: string;
  userId?: string;
  tenantId?: string;
  memberships?: Array<{ tenantId: string; role: string; tenantName?: string }>;
};

export function authPayload(options: AuthOptions = {}) {
  const tenantId = options.tenantId ?? "tenant-1";
  const role = options.role ?? "owner";
  return {
    accessToken: "e2e-access",
    refreshToken: "e2e-refresh",
    user: { id: options.userId ?? "user-1", email: "owner@e2e.test", displayName: "Dr. E2E", persona: null },
    tenant: {
      id: tenantId,
      name: "E2E Clinic",
      tier: options.tier ?? "basic",
      appLanguage: "en",
      transcriptionLanguage: "auto",
      reportLanguage: null,
      matchStrictness: "strict",
      shareIncludeBrands: false,
      vertical: "aesthetics",
      encounterLabel: "Session",
      rolePermissions: {},
    },
    memberships: options.memberships ?? [{ tenantId, role, tenantName: "E2E Clinic" }],
  };
}

/** Force the public surfaces to English (skip the Persian default) for stable selectors. */
export async function useEnglish(page: Page) {
  await page.addInitScript(() => window.localStorage.setItem("memara-ui-lang", "en"));
}

/** Mock the endpoints the authenticated app touches so it renders the active-session shell. */
export async function installAppMocks(page: Page, payload: ReturnType<typeof authPayload>) {
  const json = (data: unknown) => async (route: import("@playwright/test").Route) =>
    route.fulfill({ contentType: "application/json", json: data as object });

  await page.route("**/api/v1/auth/dev-login", json(payload));
  await page.route("**/api/v1/auth/register", json(payload));
  await page.route("**/api/v1/auth/login", json(payload));
  await page.route("**/api/v1/auth/refresh", json({ accessToken: payload.accessToken, refreshToken: payload.refreshToken }));
  await page.route("**/api/v1/me", json({ user: payload.user, tenant: payload.tenant, memberships: payload.memberships }));
  await page.route("**/api/v1/sessions**", json([]));
  await page.route("**/api/v1/patients**", json([]));
  await page.route("**/api/v1/patient-memory**", json({ items: [], limit: 50, offset: 0, total: 0 }));
  await page.route("**/api/v1/worklist**", json({ items: [] }));
  await page.route("**/api/v1/clinic/members", json({ items: [] }));
}
