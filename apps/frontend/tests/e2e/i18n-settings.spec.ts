import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// EVALUATOR-owned gating spec — S5 (settings / team / plan / share).
// Gates: settings + language-selector CHROME Persian under fa / English under en (language OPTIONS are
// autonyms English/فارسی/العربية, NOT translated); the RUNTIME app-language switch flips the UI LIVE
// (no reload) — the first real exercise of S1's live-reactivity; en unchanged.
//
// NB: a clean mock is REQUIRED — unmocked endpoints proxy to the real backend and 401, which triggers a
// pre-existing refresh→commit→refetch loop (a HARNESS artifact, proven harness-only: a catch-all that
// mocks every endpoint stops it cold). The live-switch only fails under the loop; with all endpoints
// mocked it works. So this spec catch-all-mocks /api/v1 so nothing leaks to the real backend.

type Lang = "fa" | "en";

function payload(appLanguage: Lang) {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

async function installSettingsMocks(page: import("@playwright/test").Page, p: ReturnType<typeof payload>) {
  await page.route("**/api/v1/**", (r) => r.fulfill({ contentType: "application/json", json: {} })); // catch-all → no real-backend 401 loop
  await installAppMocks(page, p);
  await page.route("**/api/v1/patient-qa/inbox**", (r) => r.fulfill({ json: { items: [], total: 0 } }));
  await page.route("**/api/v1/aftercare-templates**", (r) => r.fulfill({ json: { items: [] } }));
  // tenant-settings PATCH echoes back what was sent (App also falls back to the sent value)
  await page.route("**/api/v1/tenant/settings", (r) => r.fulfill({ contentType: "application/json", json: { ...p.tenant, ...(JSON.parse(r.request().postData() || "{}")) } }));
}

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
}

async function openSettings(page: import("@playwright/test").Page) {
  await page.locator(".user-menu summary").first().click();
  await page.locator(".user-menu-item").filter({ hasText: /Settings|تنظیمات/ }).click();
}

test.describe("S5 settings/share — chrome Persian, autonym lang options, LIVE app-language switch", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try { await installSettingsMocks(page, payload("fa")); await login(page); } catch { /* warmup */ } finally { await page.close(); }
  });

  test("fa: settings chrome is Persian; language options are autonyms (English/فارسی/العربية)", async ({ page }) => {
    await installSettingsMocks(page, payload("fa"));
    await login(page);
    await openSettings(page);
    await expect(page.getByRole("heading", { name: "تنظیمات" }).first()).toBeVisible(); // Settings title Persian
    await expect(page.getByText("برنامه", { exact: true }).first()).toBeVisible(); // "App" label Persian
    // open the app-language selector; options are autonyms (NOT «انگلیسی/فارسی»)
    await page.getByRole("button", { name: "زبان برنامه" }).click();
    await expect(page.getByRole("option", { name: "English" })).toBeVisible();
    await expect(page.getByRole("option", { name: "فارسی" })).toBeVisible();
    await expect(page.getByRole("option", { name: "العربية" })).toBeVisible();
  });

  test("en: settings chrome is English (unregressed)", async ({ page }) => {
    await installSettingsMocks(page, payload("en"));
    await login(page);
    await openSettings(page);
    await expect(page.getByRole("heading", { name: "Settings" }).first()).toBeVisible();
    await expect(page.getByText("App", { exact: true }).first()).toBeVisible();
  });

  test("5c LIVE app-language switch: en tenant ⇒ change selector to فارسی ⇒ html flips rtl/fa with NO reload", async ({ page }) => {
    await installSettingsMocks(page, payload("en"));
    await login(page);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr"); // start en/ltr
    await openSettings(page);
    await page.getByRole("button", { name: "App language" }).click(); // en aria
    await page.getByRole("option", { name: "فارسی" }).click();
    // LIVE: provider re-renders from the committed appLanguage — no navigation
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
    // and the chrome itself flipped live (Settings title is now Persian)
    await expect(page.getByRole("heading", { name: "تنظیمات" }).first()).toBeVisible();
  });
});
