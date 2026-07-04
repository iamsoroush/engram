import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// Navigation-race rule (frontend-refactor plan increment 7, seam D): on a fresh load an explicit
// location hash ALWAYS wins over restore-last-screen; the persisted screen is only restored when the
// load carried no hash. Reading a live `window.location.hash` at async-hydrate time was the source of
// the old visual-suite flake — a full reload raced restore against the URL hash and randomly landed on
// Active visit (see the comment in tests/visual/clinical-memory-today.spec.ts). These pin the rule so a
// regression is caught by a fast hermetic e2e, not by a one-in-N flaky screenshot.

const payload = authPayload({ role: "doctor" });
const authProfile = {
  refreshToken: payload.refreshToken,
  user: payload.user,
  tenant: payload.tenant,
  memberships: payload.memberships,
};

/** Seed a restored session + a persisted workspace whose last screen is `screen`. */
function seedStorage(page: import("@playwright/test").Page, screen: string) {
  const workspace = {
    schemaVersion: 1,
    tenantId: payload.tenant.id,
    screen,
    activeSession: null,
    selectedSessionId: "",
    assignmentSessionId: "",
    pendingCaptureKind: null,
    updatedAt: 1,
  };
  return page.addInitScript(
    ([auth, ws]) => {
      window.localStorage.setItem("engram-ui-lang", "en");
      window.localStorage.setItem("engram-dev-auth", JSON.stringify(auth));
      window.localStorage.setItem("engram-active-workspace", JSON.stringify(ws));
    },
    [authProfile, workspace] as const,
  );
}

test("an explicit #patients hash wins over a persisted active-session, deterministically", async ({ page }) => {
  // Adversarial setup: the persisted last screen is the capture screen, so WITHOUT the rule the
  // async restore would flip the app off Clinical Memory (the historical flake).
  await seedStorage(page, "active-session");
  await installAppMocks(page, payload);

  await page.goto("/#patients");

  await expect(page.getByRole("heading", { name: "Clinical Memory" })).toBeVisible();
  await expect(page).toHaveURL(/#patients$/);
  // Settle past the async hydrate/restore and re-assert: a late restore-flip would fail here.
  await page.waitForTimeout(600);
  await expect(page.getByRole("heading", { name: "Clinical Memory" })).toBeVisible();
  await expect(page).toHaveURL(/#patients$/);
});

test("with no explicit hash, restore-last-screen still applies", async ({ page }) => {
  // The other half of the rule: when the load carries no hash, the persisted screen is restored.
  await seedStorage(page, "patients");
  await installAppMocks(page, payload);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Clinical Memory" })).toBeVisible();
});
