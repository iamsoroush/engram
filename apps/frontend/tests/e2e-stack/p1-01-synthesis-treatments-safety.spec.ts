import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  FIXTURES,
  openTodaySession,
  registerProClinic,
  uploadCaptureApi,
  waitForSynthesisTreatments,
} from "./_stack";

// P1-1 — Pro synthesis via the mock LLM gateway (structured treatments + safety flags). Requires the
// e2e-ai stack (docker-compose.e2e-ai.yml: mock gateway + BACKEND_REPORT_SYNTHESIS_ENABLED=true). A
// seeded fixture audio drives the real synthesis job, which the mock answers with a canned structured
// report; the UI renders a treatments table and surfaces a safety flag that the clinician can reject —
// and the rejection persists. (B2.1 / B6.x.) The mock payload mirrors the AI-engine synthesis fixtures.
test.describe("P1-1 Pro synthesis (treatments table + safety flag)", () => {
  test("synthesis renders a structured treatments table and a rejectable safety flag", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForSynthesisTreatments(request, token, sessionId, 60_000);
    await assignSessionToNewPatient(request, token, sessionId, "Synth Patient");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await openTodaySession(page);

    // Structured treatments table (from the synthesized report).
    const treatment = page.locator(".treatments-list .treatment-item").first();
    await expect(treatment).toBeVisible();
    await expect(treatment).toContainText(/left cheek/i);

    // Safety is never buried: the collapsed patient strip shows a red safety chip; tapping it expands
    // the strip and reveals the full safety panel (session-layout-diet — it's no longer a standalone
    // zone above the report).
    const safetyChip = page.locator(".patient-strip-chip.safety");
    await expect(safetyChip).toBeVisible();
    await safetyChip.click();
    const safety = page.locator(".session-safety-panel");
    await expect(safety).toBeVisible();
    const flag = safety.locator(".session-safety-flag.safety-allergy");
    await expect(flag).toContainText("lidocaine sensitivity");

    // The clinician can reject it, and the rejection persists across re-opening the visit.
    await flag.locator(".session-safety-remove").click();
    await expect(page.locator(".session-safety-flag.safety-allergy")).toHaveCount(0);
    await openTodaySession(page); // navigate away and re-open the visit
    await expect(page.locator(".session-safety-flag.safety-allergy")).toHaveCount(0);

    await context.close();
  });
});
