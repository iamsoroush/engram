import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks, installQaMocks } from "./_setup";

// EVALUATOR-owned gating spec — S6 (FINAL): the epic success bar.
// "No English chrome remains under fa anywhere in the authed AESTHETICS app." A cross-screen sweep
// asserts a denylist of unambiguous English CHROME strings is ABSENT under fa on every core screen
// (scan excludes [data-content] data + the intentional Latin tokens). Plus Q&A surface Persian +
// Persian-digit counts + en unregressed.

// Unambiguous English chrome (definitely translated, never data/config) — must NOT render under fa.
const ENGLISH_CHROME = [
  "Settings", "Profile", "Logout", "Cancel", "Delete", "Clinical report", "Sources", "Copy link",
  "Confirm dose", "Review", "Loading", "Searching", "All caught up", "No patients yet", "Needs input",
  "Add capture", "New session", "Add template", "Aftercare templates", "Capturing for", "Dose confirmed",
  "Fix at source", "Generating structured report", "Clinical Memory", "Patient history", "Send", "Dismiss",
  "Re-route", "Search patients", "Switch clinic", "Replay guide",
];

async function faLogin(page: import("@playwright/test").Page) {
  await installAppMocks(page, authPayload({ appLanguage: "fa", tier: "pro", role: "owner" }));
  await installQaMocks(page);
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
}

/** English chrome strings currently rendered OUTSIDE [data-content] (legit data is excluded). */
async function englishChromeOnScreen(page: import("@playwright/test").Page) {
  return page.evaluate((deny) => {
    const root = document.querySelector(".phone-shell") || document.body;
    const clone = root.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[data-content]").forEach((n) => n.remove());
    const text = clone.textContent || "";
    return deny.filter((w) => text.includes(w));
  }, ENGLISH_CHROME);
}

test.describe("S6 FINAL — no English chrome under fa across the authed aesthetics app", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try { await faLogin(page); } catch { /* warmup */ } finally { await page.close(); }
  });

  test("fa: active-session (capture/report) has no English chrome", async ({ page }) => {
    await faLogin(page);
    expect(await englishChromeOnScreen(page)).toEqual([]);
  });

  test("fa: Clinical Memory (today/patients/needs-input) has no English chrome", async ({ page }) => {
    await faLogin(page);
    await page.locator(".app-navigator button").nth(1).click();
    await page.getByRole("heading", { name: /حافظهٔ بالینی/ }).first().waitFor();
    expect(await englishChromeOnScreen(page)).toEqual([]);
    // walk the tabs
    for (const tab of ["بیماران", "نیازمند ورودی", "امروز"]) {
      await page.getByText(tab, { exact: true }).first().click().catch(() => {});
      expect(await englishChromeOnScreen(page)).toEqual([]);
    }
  });

  test("fa: Settings has no English chrome", async ({ page }) => {
    await faLogin(page);
    await page.locator(".user-menu summary").first().click();
    await page.locator(".user-menu-item").filter({ hasText: "تنظیمات" }).click();
    await page.getByRole("heading", { name: "تنظیمات" }).first().waitFor();
    expect(await englishChromeOnScreen(page)).toEqual([]);
  });

  test("fa: Q&A inbox (Pro) renders Persian chrome, no leak", async ({ page }) => {
    await faLogin(page);
    await page.goto("/#qa-inbox");
    await page.getByTestId("qa-inbox").waitFor({ timeout: 15000 });
    // patient name "Sara Karimi" + the question body are DATA (data-content) — excluded from the scan
    expect(await englishChromeOnScreen(page)).toEqual([]);
  });

  test("fa: interpolated counts render Persian digits (mixed-digit polish) — '۱ ثبت' not '1 ثبت'", async ({ page }) => {
    const ISO = "2026-06-20T08:30:00.000Z";
    const SESSION = { id: "s-1", status: "complete", patientId: "p-1", patientName: "Sara",
      capturedAt: ISO, items: [{ id: "c-1", type: "note", status: "processed", detail: "note", time: "08:30" }] };
    await installAppMocks(page, authPayload({ appLanguage: "fa", tier: "pro", role: "owner" }));
    await page.route("**/api/v1/sessions**", (r) => r.fulfill({ json: [SESSION] }));
    await page.addInitScript((sid) => window.localStorage.setItem("engram-active-workspace", JSON.stringify({
      schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
      activeSession: { id: sid, items: [] }, selectedSessionId: sid, assignmentSessionId: "",
      pendingCaptureKind: null, updatedAt: 1,
    })), SESSION.id);
    await page.goto("/");
    if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
      await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
    await page.getByRole("button", { name: "Doctor", exact: true }).click();
    const meta = page.getByTestId("session-meta").first();
    await meta.waitFor({ timeout: 15000 });
    // the capture count in the meta line must be a Persian digit, NOT Western ("۱ ثبت", not "1 ثبت")
    await expect(meta).toHaveText(/[۰-۹]\s*ثبت/);
    await expect(meta).not.toHaveText(/[0-9]\s*ثبت/);
  });

  test("en: a Pro app still renders English chrome (unregressed)", async ({ page }) => {
    await installAppMocks(page, authPayload({ appLanguage: "en", tier: "pro", role: "owner" }));
    await installQaMocks(page);
    await page.goto("/");
    if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
      await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
    await page.getByRole("button", { name: "Doctor", exact: true }).click();
    await page.locator(".user-menu summary").first().click();
    await expect(page.locator(".user-menu-item").filter({ hasText: "Settings" })).toBeVisible();
  });
});
