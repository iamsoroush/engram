import { expect, test, type Page } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// E14 report version-history (AES-14xx) — hermetic flow: open History → timeline → read-only preview →
// owner-only revert. The backend is mocked; the frontend (button + sheet + preview + restore) is real.

const OLD_TOKEN = "OLDVERSIONTOKEN42"; // distinctive content in the previewed older version

function proPayload(appLanguage: "en" | "fa" = "en") {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage, reportLanguage: "en" } };
}

function liveSession() {
  return {
    id: "s-history",
    status: "complete",
    patientId: "p-1",
    patientName: "Test Patient",
    capturedAt: "2026-06-20T08:30:00.000Z",
    items: [
      { id: "c-1", type: "note", status: "processed", detail: "note one", time: "08:30" },
      { id: "c-2", type: "photo", status: "processed", caption: "a photo", time: "08:40" },
    ],
    reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: "CURRENTREPORT" }] }] },
  };
}

const versionsList = {
  versions: [
    {
      id: "vNew", captureSetHash: "h2", captureCount: 2, captureIds: ["c-1", "c-2"],
      generatedAt: "2026-06-20T10:00:00Z", createdAt: "2026-06-20T10:00:00Z", generatedBy: "ai-engine",
      isCurrent: true, restorable: false, trigger: { kind: "photo_added" },
    },
    {
      id: "vOld", captureSetHash: "h1", captureCount: 1, captureIds: ["c-1"],
      generatedAt: "2026-06-20T09:00:00Z", createdAt: "2026-06-20T09:00:00Z", generatedBy: "ai-engine",
      isCurrent: false, restorable: true, trigger: { kind: "first_report" },
    },
  ],
};

const oldVersionDetail = {
  version: {
    id: "vOld", captureSetHash: "h1", captureCount: 1, captureIds: ["c-1"],
    generatedAt: "2026-06-20T09:00:00Z", createdAt: "2026-06-20T09:00:00Z", generatedBy: "ai-engine",
    isCurrent: false, restorable: true,
  },
  report: {
    summary: "old summary", generatedSummary: null, generatedReport: "old body",
    reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: OLD_TOKEN }] }] },
    reportTemplateKey: null, extractedMetadata: {},
  },
};

async function installHistoryMocks(page: Page, appLanguage: "en" | "fa" = "en") {
  const payload = proPayload(appLanguage);
  await installAppMocks(page, payload);
  const json = (data: unknown) => (r: import("@playwright/test").Route) => r.fulfill({ contentType: "application/json", json: data as object });
  const session = liveSession();
  // Registered AFTER installAppMocks so they win (last-registered route wins in Playwright).
  await page.route("**/api/v1/sessions**", json([session]));
  await page.route("**/api/v1/sessions/s-history", json(session));
  await page.route("**/api/v1/sessions/s-history/captures", json(session.items));
  await page.route("**/api/v1/sessions/s-history/report-versions", json(versionsList));
  await page.route("**/api/v1/sessions/s-history/report-versions/*", json(oldVersionDetail));
  await page.route("**/api/v1/sessions/s-history/report-versions/*/restore", json({ session: { ...session, items: [session.items[0]] } }));
  // Seed the workspace so the session restores ACTIVE and the Pro report card renders.
  await page.addInitScript((sid) => window.localStorage.setItem("engram-active-workspace", JSON.stringify({
    schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
    activeSession: { id: sid, items: [] }, selectedSessionId: sid,
    assignmentSessionId: "", pendingCaptureKind: null, updatedAt: 1,
  })), session.id);
}

async function loginToReport(page: Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByTestId("report-section-title").first().waitFor({ timeout: 15000 });
}

test.describe("E14 report version history", () => {
  test("navigate the timeline, preview an older version, and restore it (owner)", async ({ page }) => {
    await installHistoryMocks(page, "en");
    await loginToReport(page);

    // Open History from the report-card header.
    await page.locator(".report-history-button").click();
    await expect(page.getByText("Report history").first()).toBeVisible();

    // Timeline: both versions, newest tagged Current, trigger labels localized.
    const rows = page.locator(".report-history-row");
    await expect(rows).toHaveCount(2);
    await expect(page.locator(".report-history-row-trigger", { hasText: "Photo added" })).toBeVisible();
    await expect(page.locator(".report-history-row-trigger", { hasText: "First report" })).toBeVisible();
    await expect(page.locator(".report-history-row").filter({ hasText: "Photo added" }).getByText("Current")).toBeVisible();

    // Preview the older (restorable) version → banner + its distinctive content.
    await page.locator(".report-history-row").filter({ hasText: "First report" }).click();
    await expect(page.locator(".report-history-banner-label")).toContainText("Viewing the version from");
    await expect(page.locator(".report-history-preview-body")).toContainText(OLD_TOKEN);

    // Restore (owner) → confirmation naming the removed captures → confirm.
    await page.getByRole("button", { name: "Restore this version" }).click();
    await expect(page.locator(".report-history-confirm-title")).toHaveText("Restore this version?");
    await expect(page.locator(".report-history-confirm-removal")).toContainText("1");
    await page.locator(".report-history-confirm-actions").getByRole("button", { name: "Restore", exact: true }).click();

    // Sheet closes and a calm toast confirms the restore.
    await expect(page.getByText("Report restored to an earlier version.")).toBeVisible();
    await expect(page.getByText("Report history")).toHaveCount(0);
  });

  test("History affordance and sheet chrome are Persian under fa", async ({ page }) => {
    await installHistoryMocks(page, "fa");
    await loginToReport(page);
    await expect(page.locator(".report-history-button")).toHaveAttribute("aria-label", "تاریخچه");
    await page.locator(".report-history-button").click();
    await expect(page.getByText("تاریخچهٔ گزارش").first()).toBeVisible();
    await expect(page.locator(".report-history-row-trigger", { hasText: "عکس افزوده شد" })).toBeVisible();
  });
});
