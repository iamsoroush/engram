import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// EVALUATOR-owned gating spec — S1 (i18n foundation for the authenticated app).
//
// Authored independently of the Generator's implementation; asserts ONLY the agreed contract surface.
// The S1 promise proven end-to-end here is:
//
//   The authenticated app's <html dir/lang> follows tenant.appLanguage — through the REAL auth path —
//   in BOTH fa and en, and OVERRIDES any leftover public-surface language (the `engram-ui-lang`
//   localStorage that drives the public landing/login via useUiLang).
//
// Covers contract checks A1 (dir/lang flips) + A7 (authed dir/lang = tenant.appLanguage, NOT the
// leftover public lang). S1 deliberately translates NO screen, so this spec makes ZERO chrome-copy
// assertions — those land per-surface in S2+.
//
// A2 (t() flips fa/en, ar/null→en) and A3 (Jalali non-regression: formatDate→Persian digits under fa,
// Latin under en) are proven by the provider/formatter unit tests in
// `src/shared/i18n/appLang.test.tsx` (run via `npm run test:unit`). An IN-SHELL Jalali e2e assertion
// needs an active session header (a client-formatted absolute date) — that surface is introduced in S3,
// so the in-shell Jalali regression case should be added there with a stable date `data-testid` + a
// deterministic active-session mock. S1 changed no date logic, so Jalali is unaffected.

type Lang = "fa" | "en";

/** Mocked auth payload with an explicit authenticated-app language (authPayload defaults to "en"). */
function payloadWithAppLang(appLanguage: Lang) {
  const base = authPayload();
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

/** Pre-seed the PUBLIC-surface UI language (localStorage) — to prove the authed tree overrides it. */
async function seedPublicLang(page: import("@playwright/test").Page, lang: Lang) {
  await page.addInitScript((l) => window.localStorage.setItem("engram-ui-lang", l as string), lang);
}

/**
 * Sign in via the Doctor dev persona (mocked dev-login → our payload) and wait until the authed shell
 * has mounted. The `.user-menu` anchor is STRUCTURAL (a CSS class), so it survives the chrome
 * translation that lands in S2+ — keeping this gating spec stable across the epic.
 *
 * The persona grid lives in the login view; reach it from the landing's login CTA. That CTA label is
 * translated (en "Log in" / fa "ورود") since one case seeds the public surface to fa — match both. The
 * "Doctor" persona button itself is hardcoded English (dev tooling), so it is a stable selector.
 */
async function devLoginToAuthedShell(page: import("@playwright/test").Page) {
  await page.goto("/");
  const doctor = page.getByRole("button", { name: "Doctor", exact: true });
  if (!(await doctor.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
}

test.describe("S1 i18n foundation — authed <html> dir/lang follows tenant.appLanguage", () => {
  // Warm the dev server's authed module graph once, so the first assertion below never races a
  // first-request vite dep-optimization full reload (which would drop the session and land back on the
  // public surface). Harmless against an already-warm server (e.g. PLAYWRIGHT_BASE_URL).
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await installAppMocks(page, payloadWithAppLang("fa"));
      await devLoginToAuthedShell(page);
    } catch {
      // best-effort warmup; the tests themselves are the real assertions
    } finally {
      await page.close();
    }
  });

  test("fa tenant ⇒ rtl/fa (even though the public surface was en)", async ({ page }) => {
    await seedPublicLang(page, "en");
    await installAppMocks(page, payloadWithAppLang("fa"));
    await devLoginToAuthedShell(page);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
  });

  test("en tenant ⇒ ltr/en (even though the public surface was fa)", async ({ page }) => {
    await seedPublicLang(page, "fa");
    await installAppMocks(page, payloadWithAppLang("en"));
    await devLoginToAuthedShell(page);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });

  test("leftover public fa does NOT leak into an en tenant (source of truth = tenant.appLanguage)", async ({ page }) => {
    // The Iran-first public Persian default must never bleed into an English clinic's authed app.
    await seedPublicLang(page, "fa");
    await installAppMocks(page, payloadWithAppLang("en"));
    await devLoginToAuthedShell(page);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });
});
