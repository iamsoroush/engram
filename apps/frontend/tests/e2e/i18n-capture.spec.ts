import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// EVALUATOR-owned gating spec — S3 (capture/session + report chrome).
// The core gate is the TWO-AXIS SAFETY BOUNDARY: app-language CHROME → t(); report CONTENT (prose +
// REPORT_SECTION_TITLES_FA / localizedSectionTitle) → reportLanguage-driven, NEVER app t().
// Authored independently against the agreed contract + the catalog oracle + the Generator's documented
// mock (data-testids: report-section-title, report-body/[data-content], session-meta).

type Lang = "fa" | "en";
const TOKEN = "ZZQOLTOKEN42"; // distinctive CONTENT token — must render byte-identical regardless of app lang
const FA = {
  clinicalReport: "گزارش بالینی", sources: "منابع", capturesTab: "ثبت‌ها",
  assessmentFa: "ارزیابی", // REPORT_SECTION_TITLES_FA["assessment"] — appears ONLY when reportLanguage=fa
};

function payloadWith(appLanguage: Lang, reportLanguage: Lang) {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage, reportLanguage } };
}

function twoAxisSession() {
  return {
    id: "s-twoaxis", status: "complete", patientId: "p-1", patientName: "Test Patient",
    capturedAt: "2026-06-20T08:30:00.000Z",
    items: [{ id: "c-1", type: "note", status: "processed", detail: "note", time: "08:30" }],
    reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: TOKEN }] }] },
  };
}

async function installCaptureMocks(page: import("@playwright/test").Page, payload: ReturnType<typeof payloadWith>) {
  await installAppMocks(page, payload);
  const session = twoAxisSession();
  // override sessions AFTER installAppMocks (last-registered route wins in Playwright)
  await page.route("**/api/v1/sessions**", (r) => r.fulfill({ contentType: "application/json", json: [session] }));
  // CRUCIAL: seed the workspace so the session restores ACTIVE (else the report never renders)
  await page.addInitScript((sid) => window.localStorage.setItem("engram-active-workspace", JSON.stringify({
    schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
    activeSession: { id: sid, items: [] }, selectedSessionId: sid,
    assignmentSessionId: "", pendingCaptureKind: null, updatedAt: 1,
  })), session.id);
}

async function loginToReport(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByTestId("report-section-title").first().waitFor({ timeout: 15000 });
}

test.describe("S3 capture/report — TWO-AXIS safety boundary (chrome=app, content=reportLanguage)", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try { await installCaptureMocks(page, payloadWith("fa", "en")); await loginToReport(page); } catch { /* warmup */ } finally { await page.close(); }
  });

  test("SAFETY: app=fa + report=en ⇒ section title 'Assessment' (English, report-driven, NOT ارزیابی); chrome Persian", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("fa", "en"));
    await loginToReport(page);
    // CONTENT follows reportLanguage=en → English section title + verbatim token
    await expect(page.getByTestId("report-section-title").first()).toHaveText("Assessment");
    await expect(page.getByTestId("report-body").first()).toContainText(TOKEN);
    // the report-content Persian title must NOT appear (would mean titles wrongly went through app t())
    await expect(page.getByTestId("report-section-title").first()).not.toHaveText(FA.assessmentFa);
    // CHROME follows app=fa → Persian (coexists with the English content → proves the two axes)
    await expect(page.getByText(FA.clinicalReport).first()).toBeVisible();
  });

  test("app=fa + report=fa ⇒ section title 'ارزیابی'; content token verbatim", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("fa", "fa"));
    await loginToReport(page);
    await expect(page.getByTestId("report-section-title").first()).toHaveText(FA.assessmentFa);
    await expect(page.getByTestId("report-body").first()).toContainText(TOKEN);
  });

  test("app=en + report=en ⇒ 'Assessment' + English chrome", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("en", "en"));
    await loginToReport(page);
    await expect(page.getByTestId("report-section-title").first()).toHaveText("Assessment");
    await expect(page.getByText("Clinical report").first()).toBeVisible();
  });

  test("no-English-leak: chrome is Persian under fa (scan EXCLUDES [data-content])", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("fa", "en"));
    await loginToReport(page);
    // positive: key report/capture chrome is Persian
    await expect(page.getByText(FA.clinicalReport).first()).toBeVisible();
    await expect(page.getByText(FA.sources).first()).toBeVisible();
    // the only English on screen must live inside the CONTENT region — assert no English chrome word
    // leaks OUTSIDE [data-content]. We pull text of the report card EXCLUDING content nodes.
    const chromeLatin = await page.evaluate(() => {
      const root = document.querySelector(".phone-shell") || document.body;
      const clone = root.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("[data-content]").forEach((n) => n.remove()); // drop legit-English content
      const text = (clone.textContent || "");
      // allowlist: intentional Latin tokens + data (patient name) that legitimately appear in chrome rows
      const chromeWords = ["Clinical report", "Sources", "Captures", "Live report", "Share", "Review", "Confirm dose", "Assessment"];
      return chromeWords.filter((w) => text.includes(w));
    });
    expect(chromeLatin).toEqual([]);
  });

  test("A3 Jalali: session-meta shows Persian digits under fa, Latin under en", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("fa", "en"));
    await loginToReport(page);
    // Jalali date renders with Persian digits under fa (the A3 gate). NB: interpolated counts like
    // "1 ثبت" still use a Western digit — a minor mixed-digit craft gap flagged to the Generator/Planner,
    // not part of the A3 date gate.
    await expect(page.getByTestId("session-meta").first()).toHaveText(/[۰-۹]/);
  });

  test("A3 Jalali (en): session-meta shows Latin digits, no Persian", async ({ page }) => {
    await installCaptureMocks(page, payloadWith("en", "en"));
    await loginToReport(page);
    await expect(page.getByTestId("session-meta").first()).toHaveText(/[0-9]/);
    await expect(page.getByTestId("session-meta").first()).not.toHaveText(/[۰-۹]/);
  });
});
