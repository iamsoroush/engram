import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  FIXTURES,
  openSourcesDrawer,
  openTodaySession,
  registerProClinic,
  uploadCaptureApi,
  waitForReportContains,
} from "./_stack";

// P0-8 — Capture undo (Pro). Two captures are seeded through the real API; deleting the newest via its
// Sources-drawer overflow menu reverts the deterministic report to its exact prior state (the procedure
// content drops out) while the earlier capture stays intact. Exercises the content-addressed report
// store + user-state overlay end-to-end, gateway-less.
test.describe("P0-8 capture undo", () => {
  test("deleting the newest capture reverts the report; earlier capture intact", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForReportContains(request, token, sessionId, "Sara Nazari", 30_000);
    await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioProcedure, sessionId });
    await waitForReportContains(request, token, sessionId, "hyaluronic acid", 30_000);
    await assignSessionToNewPatient(request, token, sessionId, "Sara Nazari");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    page.on("dialog", (dialog) => void dialog.accept()); // auto-accept the delete confirm
    await openTodaySession(page);
    await expect(page.getByTestId("report-body")).toContainText(/hyaluronic acid/i);
    await expect(page.getByTestId("report-body")).toContainText("Sara Nazari");

    await openSourcesDrawer(page);
    await expect(page.locator(".live-draft-capture")).toHaveCount(2);

    // Undo the newest capture via its overflow menu.
    const newest = page.locator(".live-draft-capture").last();
    await newest.locator(".live-draft-overflow").click();
    await newest.locator(".capture-item-menu button.danger").click();

    // Report reverts to the exact prior state: the procedure content is gone, the consult remains.
    await expect(page.locator(".live-draft-capture")).toHaveCount(1);
    await expect(page.getByTestId("report-body")).not.toContainText(/hyaluronic acid/i, { timeout: 30_000 });
    await expect(page.getByTestId("report-body")).toContainText("Sara Nazari");

    await context.close();
  });
});
