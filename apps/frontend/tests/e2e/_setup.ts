import type { Page } from "@playwright/test";

// Hermetic e2e helpers: the frontend runs for real, the backend is mocked via page.route. These
// cover the launch-gap UI spine (landing/auth, onboarding gating + tier accuracy, account-menu role
// gating) without depending on a live backend.

export type AuthOptions = {
  tier?: "basic" | "pro";
  role?: string;
  userId?: string;
  tenantId?: string;
  /** App-UI language for the authed app. Set to "fa" to render the Persian/RTL chrome. */
  appLanguage?: string;
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
      appLanguage: options.appLanguage ?? "en",
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
  await page.addInitScript(() => window.localStorage.setItem("engram-ui-lang", "en"));
}

/** Mock the endpoints the authenticated app touches so it renders the active-session shell. */
export async function installAppMocks(page: Page, payload: ReturnType<typeof authPayload>) {
  const json = (data: unknown) => async (route: import("@playwright/test").Route) =>
    route.fulfill({ contentType: "application/json", json: data as object });

  // Catch-all FIRST (lowest Playwright priority — later routes win): any unmocked /api/v1/** call
  // returns an empty 200 instead of 401→refreshAccessToken→re-render→re-fetch (the 5c loop that
  // corrupted hermetic app-language tests). Specific routes below override per-endpoint.
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const body = /\/(inbox|members|threads|treating-doctors)/.test(url) ? { items: [], total: 0 } : {};
    await route.fulfill({ contentType: "application/json", json: body });
  });

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

/**
 * Mocks the Pro doctor Q&A inbox (`/patient-qa/*`) with one needs-approval conversation, so the
 * inbox renders its full chrome: scope tabs, routing toggle, status badges, the AI-draft reply box,
 * and Send / Dismiss / Re-route actions. Patient name + message bodies are DATA (verbatim, marked
 * `data-content` in the component) so the no-leak chrome scan excludes them. Navigate to the inbox
 * with `#qa-inbox` after a Pro + fa `installAppMocks`. Call AFTER installAppMocks so these win.
 */
export async function installQaMocks(page: Page) {
  const json = (data: unknown) => async (route: import("@playwright/test").Route) =>
    route.fulfill({ contentType: "application/json", json: data as object });

  const inbox = {
    scope: "mine",
    total: 1,
    items: [
      {
        threadId: "thread-1",
        patientId: "patient-1",
        patientName: "Sara Karimi",
        assignedDoctor: { userId: "user-1", name: "Dr. E2E" },
        routingSource: "treating",
        treatingDoctorCount: 1,
        needsApproval: true,
        pendingQuestion: {
          messageId: "msg-1",
          body: "Is the swelling normal after the filler?",
          askedAt: "2026-06-20T10:00:00Z",
        },
        messages: [
          { id: "msg-1", role: "patient", body: "Is the swelling normal after the filler?", status: "pending", inReplyToId: null, createdAt: "2026-06-20T10:00:00Z" },
        ],
        visits: [{ sessionId: "sess-1", title: "Lip filler", date: "2026-06-18T09:00:00Z" }],
        lastActivityAt: "2026-06-20T10:00:00Z",
      },
    ],
  };

  await page.route("**/api/v1/patient-qa/inbox**", json(inbox));
  await page.route("**/api/v1/patient-qa/settings", json({ routingMode: "ai_default" }));
  await page.route("**/api/v1/patient-qa/messages/*/draft", json({ draftStatus: "ready", draft: "", draftMode: "revise" }));
}
