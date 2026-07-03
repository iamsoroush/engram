import { expect, test } from "@playwright/test";
import { applyAuth, expectShellReady, registerClinic, registerProClinic } from "./_stack";

// P0-6 — Tier-gating matrix (both tiers). Basic has no Lists tab and the Pro-only APIs return 403;
// Pro exposes the Lists tab and the audio-first capture footer. Exercises the real capability gate
// (apps/backend/app/services/capabilities.py) end-to-end, both in the UI and at the API contract.
test.describe("P0-6 tier-gating matrix", () => {
  test("Basic: no Lists tab; smart-lists / insights / patient-qa APIs are 403", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();

    await page.goto("/#patients");
    await expect(page.getByRole("tab", { name: "Patients" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Lists" })).toHaveCount(0);

    const headers = { Authorization: `Bearer ${clinic.auth.accessToken}` };
    expect((await request.get("/api/v1/smart-lists", { headers })).status()).toBe(403);
    expect((await request.get("/api/v1/insights/treatments", { headers })).status()).toBe(403);
    expect((await request.get("/api/v1/patient-qa/inbox", { headers })).status()).toBe(403);

    await context.close();
  });

  test("Pro: Lists tab present and an audio-first capture footer", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();

    await page.goto("/");
    await expectShellReady(page);
    // Audio-first: the first (primary) capture action is Record/dictate, not Note.
    const firstAction = page.locator(".capture-pills-actions .capture-action-button").first();
    await expect(firstAction).toContainText("Record");

    await page.goto("/#patients");
    await expect(page.getByRole("tab", { name: "Lists" })).toBeVisible();

    const headers = { Authorization: `Bearer ${clinic.auth.accessToken}` };
    expect((await request.get("/api/v1/smart-lists", { headers })).status()).toBe(200);
    expect((await request.get("/api/v1/patient-qa/inbox", { headers })).status()).toBe(200);

    await context.close();
  });
});
