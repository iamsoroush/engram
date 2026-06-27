import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// EVALUATOR-owned gating spec — S2 (app shell / nav / account menu).
// Authored independently against the agreed contract surface + the catalog oracle.
//
// S2 is the FIRST story translating VISIBLE chrome, so this gates the core new promise:
//   Under fa the shell (nav + account menu + brand + tier) renders Persian with NO English chrome
//   leak EXCEPT the intentional Latin tokens [Engram (wordmark), Pro/Basic (tier)]; under en it is
//   unchanged; nav + account-menu navigation work in BOTH langs; the dropdown is RTL-aligned.
//
// Leak strategy: scan ONLY pure-chrome elements (.nav-label, .user-menu-item) for Latin letters — they
// hold no user data. Identity rows (displayName/tenant.name) are DATA and are excluded.

type Lang = "fa" | "en";

// Catalog oracle (exact values, messages.ts @ S2).
const FA = {
  navSession: "جلسه", navMemory: "حافظه",
  profile: "نمایه", settings: "تنظیمات", team: "تیم", plan: "پلن", logout: "خروج",
  roleOwner: "مالک",
};

function payloadWithAppLang(appLanguage: Lang) {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  const doctor = page.getByRole("button", { name: "Doctor", exact: true });
  if (!(await doctor.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
}

/** Latin-letter text inside pure-chrome elements, after allowlisting intentional Latin tokens. */
async function latinLeaks(page: import("@playwright/test").Page, selector: string) {
  return page.$$eval(selector, (els) =>
    els
      .map((e) => (e.textContent || "").trim())
      .filter((tx) => tx && /[A-Za-z]/.test(tx) && !/^(Engram|Pro|Basic)$/.test(tx)),
  );
}

test.describe("S2 shell — fa is Persian + RTL (no leak), en unchanged, nav works in both", () => {
  // Warm the authed module graph once so no test eats a first-load dep-optimization reload.
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await installAppMocks(page, payloadWithAppLang("fa"));
      await login(page);
    } catch {
      /* best-effort */
    } finally {
      await page.close();
    }
  });

  test("fa: shell chrome is Persian; no English leak except Latin tokens", async ({ page }) => {
    await installAppMocks(page, payloadWithAppLang("fa"));
    await login(page);
    // nav short-labels are Persian
    await expect(page.locator(".app-navigator")).toContainText(FA.navSession);
    await expect(page.locator(".app-navigator")).toContainText(FA.navMemory);
    // role label localized in the summary (owner ⇒ مالک)
    await expect(page.locator(".user-menu summary")).toContainText(FA.roleOwner);
    // open the dropdown
    await page.locator(".user-menu summary").first().click();
    for (const w of [FA.profile, FA.settings, FA.team, FA.plan, FA.logout]) {
      await expect(page.locator(".user-menu-item", { hasText: w })).toBeVisible();
    }
    // intentional Latin tokens stay Latin (and are bidi-isolated <bdi>)
    await expect(page.locator(".topbar-brand")).toHaveText("Engram");
    await expect(page.locator(".tier-pill")).toHaveText(/^(Pro|Basic)$/);
    // NO English chrome leak in pure-chrome elements
    expect(await latinLeaks(page, ".app-navigator .nav-label")).toEqual([]);
    expect(await latinLeaks(page, ".user-menu-item")).toEqual([]);
    // logout glyph is mirrored under rtl (directional exit arrow)
    const tf = await page.locator(".user-menu-item-danger svg").evaluate((el) => getComputedStyle(el).transform);
    expect(tf === "matrix(-1, 0, 0, 1, 0, 0)").toBeTruthy();
  });

  test("en: shell chrome is English (unregressed) and logout glyph not mirrored", async ({ page }) => {
    await installAppMocks(page, payloadWithAppLang("en"));
    await login(page);
    await expect(page.locator(".app-navigator")).toContainText("Session");
    await page.locator(".user-menu summary").first().click();
    for (const w of ["Profile", "Settings", "Team", "Plan", "Logout"]) {
      await expect(page.locator(".user-menu-item", { hasText: w })).toBeVisible();
    }
    const tf = await page.locator(".user-menu-item-danger svg").evaluate((el) => getComputedStyle(el).transform);
    expect(tf === "none" || tf === "matrix(1, 0, 0, 1, 0, 0)").toBeTruthy();
  });

  for (const lang of ["fa", "en"] as Lang[]) {
    test(`${lang}: nav (→Memory) + account-menu navigation work`, async ({ page }) => {
      await installAppMocks(page, payloadWithAppLang(lang));
      await login(page);
      // nav: clicking the 2nd nav button (Memory) marks it current
      const memoryNav = page.locator(".app-navigator button").nth(1);
      await memoryNav.click();
      await expect(memoryNav).toHaveAttribute("aria-current", "page");
      // account menu: open → click Settings → menu closes (navigation fired, goTo closes it)
      await page.locator(".user-menu summary").first().click();
      await expect(page.locator(".user-menu")).toHaveAttribute("open", "");
      await page.locator(".user-menu-item").filter({ hasText: lang === "fa" ? FA.settings : "Settings" }).click();
      await expect(page.locator(".user-menu")).not.toHaveAttribute("open", "");
    });
  }
});
