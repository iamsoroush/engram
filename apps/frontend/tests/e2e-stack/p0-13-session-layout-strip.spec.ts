import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  FIXTURES,
  openTodaySession,
  registerProClinic,
  uploadCaptureApi,
  waitForReportContains,
} from "./_stack";

// P0-13 — Session-layout diet (the patient strip), gateway-less. A seeded capture builds the
// deterministic report; opening the visit shows the collapsed one-line **patient strip** above the
// report (identity + assignment state), and tapping it expands to the full stack (patient actions +
// context). Exercises AES-1301/1302 end-to-end without any AI — the strip is deterministic.
test.describe("P0-13 patient strip (layout diet)", () => {
  test("the report-has-content session shows a collapsed strip; a tap expands it", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForReportContains(request, token, sessionId, "Sara Nazari", 30_000);
    await assignSessionToNewPatient(request, token, sessionId, "Sara Nazari");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await openTodaySession(page);

    // The report has content → the strip opens COLLAPSED to one line, above the report, showing the
    // assigned patient by name and a "✓ assigned" state (identity is never hidden).
    const strip = page.locator(".patient-strip");
    await expect(strip).toBeVisible();
    await expect(strip).toHaveClass(/collapsed/);
    await expect(strip.locator(".patient-strip-identity")).toContainText("Sara Nazari");
    await expect(strip.locator(".patient-strip-state")).toContainText(/assigned/i);

    // The old standalone patient card is gone — identity lives only in the strip now.
    await expect(page.locator(".patient-context-card")).toHaveCount(0);

    // Tapping the identity expands the strip to the full stack: patient actions (Change / History).
    await strip.locator(".patient-strip-identity").click();
    await expect(strip).toHaveClass(/expanded/);
    await expect(strip.locator(".patient-strip-action")).toContainText([/History/i, /Change/i]);

    // The chevron re-collapses it (manual override).
    await strip.locator(".patient-strip-chevron").last().click();
    await expect(page.locator(".patient-strip")).toHaveClass(/collapsed/);

    await context.close();
  });
});
