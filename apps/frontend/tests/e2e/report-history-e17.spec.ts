import { expect, test, type Page, type Route } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// E17 report-history HARDENING (hermetic): the safety-loss guard (finding 1) on both restore and the
// Sources-drawer undo, plus the redo/forward-restore flow (finding 2). Backend mocked; the frontend
// (sheet + confirm + safety-loss list + removal guard) is real.

const FLAG_TEXT = "allergy to lidocaine"; // distinctive clinical content rendered verbatim in the guard

function proPayload(appLanguage: "en" | "fa" = "en") {
  const base = authPayload({ role: "owner", tier: "pro" });
  return { ...base, tenant: { ...base.tenant, appLanguage, reportLanguage: "en" } };
}

function liveSession(overrides: Record<string, unknown> = {}) {
  return {
    id: "s-e17",
    status: "complete",
    patientId: "p-1",
    patientName: "Test Patient",
    capturedAt: "2026-06-20T08:30:00.000Z",
    items: [
      { id: "c-1", type: "note", status: "processed", detail: "note one", time: "08:30" },
      { id: "c-2", type: "photo", status: "processed", caption: "a photo", time: "08:40" },
    ],
    reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: "CURRENTREPORT" }] }] },
    ...overrides,
  };
}

const json = (data: unknown) => (r: Route) => r.fulfill({ contentType: "application/json", json: data as object });

async function seedWorkspace(page: Page, sessionId: string) {
  await page.addInitScript((sid) => window.localStorage.setItem("engram-active-workspace", JSON.stringify({
    schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
    activeSession: { id: sid, items: [] }, selectedSessionId: sid,
    assignmentSessionId: "", pendingCaptureKind: null, updatedAt: 1,
  })), sessionId);
}

async function loginToReport(page: Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByTestId("report-section-title").first().waitFor({ timeout: 15000 });
}

test.describe("E17 report-history hardening", () => {
  test("restore names the safety flags it would drop (finding 1)", async ({ page }) => {
    await installAppMocks(page, proPayload("en"));
    const session = liveSession();
    await seedWorkspace(page, session.id);
    await page.route("**/api/v1/sessions**", json([session]));
    await page.route("**/api/v1/sessions/s-e17", json(session));
    await page.route("**/api/v1/sessions/s-e17/captures", json(session.items));
    await page.route("**/api/v1/sessions/s-e17/report-versions", json({
      versions: [
        { id: "vNew", captureSetHash: "h2", captureCount: 2, captureIds: ["c-1", "c-2"], generatedAt: "2026-06-20T10:00:00Z", createdAt: "2026-06-20T10:00:00Z", generatedBy: "ai-engine", isCurrent: true, restorable: false, trigger: { kind: "photo_added" } },
        { id: "vOld", captureSetHash: "h1", captureCount: 1, captureIds: ["c-1"], generatedAt: "2026-06-20T09:00:00Z", createdAt: "2026-06-20T09:00:00Z", generatedBy: "ai-engine", isCurrent: false, restorable: true, trigger: { kind: "first_report" } },
      ],
    }));
    await page.route("**/api/v1/sessions/s-e17/report-versions/*", json({
      version: { id: "vOld", captureSetHash: "h1", captureCount: 1, captureIds: ["c-1"], generatedAt: "2026-06-20T09:00:00Z", createdAt: "2026-06-20T09:00:00Z", generatedBy: "ai-engine", isCurrent: false, restorable: true },
      report: { summary: "old", generatedSummary: null, generatedReport: "old body", reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: "OLDBODY" }] }] }, reportTemplateKey: null, extractedMetadata: {} },
      restoreImpact: { reachable: true, restorable: true, removedCaptureCount: 1, restoredCaptureCount: 0, safetyLoss: [{ key: "allergy|lidocaine", kind: "allergy", text: FLAG_TEXT, alsoRemovedFromPatient: true }] },
    }));
    await page.route("**/api/v1/sessions/s-e17/report-versions/*/restore", json({ session: { ...session, items: [session.items[0]] } }));
    await loginToReport(page);

    await page.locator(".report-history-button").click();
    await page.locator(".report-history-row").filter({ hasText: "First report" }).click();
    await page.getByRole("button", { name: "Restore this version" }).click();
    // The safety-loss guard lists the flag verbatim + the patient-file scope note.
    const guard = page.locator(".report-history-safety-loss");
    await expect(guard).toBeVisible();
    await expect(guard).toContainText(FLAG_TEXT);
    await expect(guard).toContainText("Also removed from the patient file");
    // Confirm goes through.
    await page.locator(".report-history-confirm-actions").getByRole("button", { name: "Restore", exact: true }).click();
    await expect(page.getByText("Report restored to an earlier version.")).toBeVisible();
  });

  test("a forward version is restorable and restoring it re-effects captures (redo, finding 2)", async ({ page }) => {
    await installAppMocks(page, proPayload("en"));
    const session = liveSession({ items: [{ id: "c-1", type: "note", status: "processed", detail: "note one", time: "08:30" }] });
    await seedWorkspace(page, session.id);
    let restoreCalled = false;
    await page.route("**/api/v1/sessions**", json([session]));
    await page.route("**/api/v1/sessions/s-e17", json(session));
    await page.route("**/api/v1/sessions/s-e17/captures", json(session.items));
    await page.route("**/api/v1/sessions/s-e17/report-versions", json({
      versions: [
        // Session currently sits at the OLDER version; the newer one is a reachable FORWARD (redo) target.
        { id: "vFwd", captureSetHash: "h2", captureCount: 2, captureIds: ["c-1", "c-2"], generatedAt: "2026-06-20T10:00:00Z", createdAt: "2026-06-20T10:00:00Z", generatedBy: "ai-engine", isCurrent: false, restorable: true, trigger: { kind: "photo_added" } },
        { id: "vCur", captureSetHash: "h1", captureCount: 1, captureIds: ["c-1"], generatedAt: "2026-06-20T09:00:00Z", createdAt: "2026-06-20T09:00:00Z", generatedBy: "ai-engine", isCurrent: true, restorable: false, trigger: { kind: "first_report" } },
      ],
    }));
    await page.route("**/api/v1/sessions/s-e17/report-versions/*", json({
      version: { id: "vFwd", captureSetHash: "h2", captureCount: 2, captureIds: ["c-1", "c-2"], generatedAt: "2026-06-20T10:00:00Z", createdAt: "2026-06-20T10:00:00Z", generatedBy: "ai-engine", isCurrent: false, restorable: true },
      report: { summary: "fwd", generatedSummary: null, generatedReport: "forward body", reportModel: { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: "FORWARDBODY" }] }] }, reportTemplateKey: null, extractedMetadata: {} },
      restoreImpact: { reachable: true, restorable: true, removedCaptureCount: 0, restoredCaptureCount: 1, safetyLoss: [] },
    }));
    await page.route("**/api/v1/sessions/s-e17/report-versions/*/restore", (r) => { restoreCalled = true; return json({ session })(r); });
    await loginToReport(page);

    await page.locator(".report-history-button").click();
    await page.locator(".report-history-row").filter({ hasText: "Photo added" }).click();
    await page.getByRole("button", { name: "Restore this version" }).click();
    // Redo confirm names the re-effected captures, not a removal.
    await expect(page.locator(".report-history-confirm-restored")).toContainText("1");
    await page.locator(".report-history-confirm-actions").getByRole("button", { name: "Restore", exact: true }).click();
    await expect.poll(() => restoreCalled).toBe(true);
  });

  test("Sources-drawer undo warns before dropping a safety flag (finding 1, undo path)", async ({ page }) => {
    await installAppMocks(page, proPayload("en"));
    const session = liveSession();
    await seedWorkspace(page, session.id);
    let deleteCalled = false;
    await page.route("**/api/v1/sessions**", json([session]));
    await page.route("**/api/v1/sessions/s-e17", json(session));
    await page.route("**/api/v1/sessions/s-e17/captures", json(session.items));
    await page.route("**/api/v1/sessions/s-e17/report-versions", json({ versions: [] }));
    // The removal-impact pre-flight returns a safety flag the undo would drop.
    await page.route("**/api/v1/captures/*/removal-impact", json({ safetyLoss: [{ key: "allergy|lidocaine", kind: "allergy", text: FLAG_TEXT, alsoRemovedFromPatient: false }] }));
    await page.route("**/api/v1/captures/*", (r) => { if (r.request().method() === "DELETE") { deleteCalled = true; return json({ session })(r); } return r.fallback(); });
    await loginToReport(page);

    await page.locator(".sources-drawer-undo").click();
    // The removal guard names the flag + the "stays on the patient file" scope; delete hasn't fired yet.
    const guard = page.locator(".report-history-safety-loss");
    await expect(guard).toBeVisible();
    await expect(guard).toContainText(FLAG_TEXT);
    await expect(guard).toContainText("Stays on the patient file");
    expect(deleteCalled).toBe(false);
    // Confirm → the de-effecting delete fires.
    await page.getByRole("button", { name: "Remove anyway" }).click();
    await expect.poll(() => deleteCalled).toBe(true);
  });

  test("undo with no safety loss deletes immediately — no guard dialog (P0-8 path preserved)", async ({ page }) => {
    await installAppMocks(page, proPayload("en"));
    const session = liveSession();
    await seedWorkspace(page, session.id);
    let deleteCalled = false;
    await page.route("**/api/v1/sessions**", json([session]));
    await page.route("**/api/v1/sessions/s-e17", json(session));
    await page.route("**/api/v1/sessions/s-e17/captures", json(session.items));
    await page.route("**/api/v1/sessions/s-e17/report-versions", json({ versions: [] }));
    // No safety flag would be dropped → the guard must NOT interrupt (the common, one-tap undo case).
    await page.route("**/api/v1/captures/*/removal-impact", json({ safetyLoss: [] }));
    await page.route("**/api/v1/captures/*", (r) => { if (r.request().method() === "DELETE") { deleteCalled = true; return json({ session })(r); } return r.fallback(); });
    await loginToReport(page);

    await page.locator(".sources-drawer-undo").click();
    await expect.poll(() => deleteCalled).toBe(true);
    await expect(page.locator(".report-history-safety-loss")).toHaveCount(0);
  });
});
