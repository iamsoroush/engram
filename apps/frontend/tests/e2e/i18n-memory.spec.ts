import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// EVALUATOR-owned gating spec — S4 (Clinical Memory / patients / timeline).
// No reportLanguage two-axis here; the boundary is CHROME (→t()) vs patient DATA (verbatim).
// Gates: fa chrome Persian + RTL with NO English-chrome leak (scan EXCLUDES [data-content]); patient
// DATA verbatim ("Sara" stays "Sara") + Jalali dates; en unchanged; CORE journey works in both langs.

type Lang = "fa" | "en";
const FA = { today: "امروز", patients: "بیماران", needsInput: "نیازمند ورودی" };
const ISO = "2026-06-20T08:30:00.000Z";
const SARA = { id: "p-sara", displayName: "Sara", lastVisit: ISO };
// A visit assigned to Sara so the memory-first Patients tab renders a card for her.
const SARA_VISIT = {
  id: "v-sara", label: "Follow-up visit", time: "08:30", dateLabel: "Jun 20",
  createdAt: ISO, capturedAt: ISO, updatedAt: ISO, status: "organized",
  patientId: "p-sara", patientName: "Sara", assignmentSource: "staff",
  items: [{ id: "c-1", type: "note", title: "Note", detail: "Note detail", time: "08:30", status: "uploaded", capturedAt: ISO }],
};

function payload(appLanguage: Lang) {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

async function installMemoryMocks(page: import("@playwright/test").Page, p: ReturnType<typeof payload>) {
  // catch-all FIRST (lowest precedence) so no unmocked /api/v1 call leaks to the real backend (401)
  await page.route("**/api/v1/**", (r) => r.fulfill({ contentType: "application/json", json: {} }));
  await installAppMocks(page, p);
  await page.route("**/api/v1/sessions**", (r) => r.fulfill({ contentType: "application/json", json: [SARA_VISIT] }));
  await page.route("**/api/v1/patients**", (r) => r.fulfill({ contentType: "application/json", json: [SARA] }));
}

async function openMemory(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
  await page.locator(".app-navigator button").nth(1).click(); // → Clinical Memory
  await page.getByRole("heading", { name: /Clinical Memory|حافظهٔ بالینی/ }).first().waitFor();
}

/** English chrome words that must NOT appear OUTSIDE [data-content] under fa. */
async function chromeLeaks(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const root = document.querySelector(".phone-shell") || document.body;
    const clone = root.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[data-content]").forEach((n) => n.remove()); // drop legit-English patient data
    const text = clone.textContent || "";
    const words = ["Today", "Patients", "Needs input", "Clinical Memory", "All caught up", "No patients", "Search patients", "Loading", "Searching"];
    return words.filter((w) => text.includes(w));
  });
}

test.describe("S4 Clinical Memory — fa Persian + RTL, data verbatim, en unchanged, core journey", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try { await installMemoryMocks(page, payload("fa")); await openMemory(page); } catch { /* warmup */ } finally { await page.close(); }
  });

  test("fa: memory tabs are Persian; no English chrome leak (scan excludes [data-content])", async ({ page }) => {
    await installMemoryMocks(page, payload("fa"));
    await openMemory(page);
    await expect(page.getByText(FA.today).first()).toBeVisible();
    await expect(page.getByText(FA.patients).first()).toBeVisible();
    await expect(page.getByText(FA.needsInput).first()).toBeVisible();
    expect(await chromeLeaks(page)).toEqual([]);
  });

  test("fa: patient DATA verbatim ('Sara' stays Sara) + Jalali date", async ({ page }) => {
    await installMemoryMocks(page, payload("fa"));
    await openMemory(page);
    await page.getByRole("tab", { name: FA.patients }).click().catch(async () => { await page.getByText(FA.patients).first().click(); });
    await expect(page.getByText("Sara").first()).toBeVisible(); // name NOT translated (data)
    // a client-formatted patient date renders Jalali (Persian digits) somewhere on the patients view
    await expect(page.locator("body")).toContainText(/[۰-۹]/);
  });

  test("en: tabs are English (unregressed)", async ({ page }) => {
    await installMemoryMocks(page, payload("en"));
    await openMemory(page);
    await expect(page.getByText("Today").first()).toBeVisible();
    await expect(page.getByText("Patients").first()).toBeVisible();
    await expect(page.getByText("Needs input").first()).toBeVisible();
  });

  for (const lang of ["fa", "en"] as Lang[]) {
    test(`${lang}: CORE journey — Clinical Memory → Patients tab → open patient timeline`, async ({ page }) => {
      await installMemoryMocks(page, payload(lang));
      await openMemory(page);
      await page.getByText(lang === "fa" ? FA.patients : "Patients").first().click();
      await expect(page.getByText("Sara").first()).toBeVisible();
      await page.getByText("Sara").first().click();
      // reached a patient view (timeline) — the patient name renders as a heading; chrome localized
      await expect(page.getByRole("heading", { name: "Sara" }).first()).toBeVisible({ timeout: 10000 });
    });
  }
});
