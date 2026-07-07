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

// P1-2 — User-authored treatment overlay (AES-1102/1103), on the e2e-ai stack (mock gateway synthesis).
// A synthesized treatment row is edited inline via its ✎ per-field editor; the field flips to a
// human-owned "Edited by you" presentation with the AI value preserved (provenance/reconcile), the edit
// is durable across a re-open (a user-owned overlay synthesis can't overwrite), and Use-AI reverts it.
test.describe("P1-2 treatment overlay (inline field edit)", () => {
  test("editing a dose is human-owned, durable, and revertible to the AI value", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForSynthesisTreatments(request, token, sessionId, 60_000);
    await assignSessionToNewPatient(request, token, sessionId, "Overlay Patient");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await openTodaySession(page);

    const row = page.locator(".treatments-list .treatment-item").first();
    await expect(row).toBeVisible();

    // Open the per-field editor and correct the dose to a known value.
    await row.locator(".treatment-edit-btn").click();
    const editor = page.locator(".treatment-editor").first();
    await expect(editor).toBeVisible();
    const doseInput = editor.locator('input[aria-label="Dose"]');
    await doseInput.fill("99 units");
    await editor.getByRole("button", { name: /save/i }).click();

    // The field flips to human-owned: "Edited by you" + the new value, with the AI value preserved
    // as the provenance/reconcile subline and a one-tap Use-AI.
    const editedRow = page.locator(".treatment-item.edited").first();
    await expect(editedRow).toContainText("99 units");
    await expect(editedRow.locator(".treatment-edited-chip")).toContainText(/Edited by you/i);
    await expect(editedRow.locator(".treatment-provenance")).toBeVisible();
    await expect(editedRow.locator(".treatment-revert-btn")).toContainText(/Use AI/i);

    // Durable: re-opening the visit still shows the human value (the overlay is server-side, immune to
    // synthesis overwrite).
    await openTodaySession(page);
    await expect(page.locator(".treatment-item.edited").first()).toContainText("99 units");

    // Use-AI reverts: the human value + the edited chip drop, the AI value returns.
    await page.locator(".treatment-item.edited").first().locator(".treatment-revert-btn").click();
    await expect(page.locator(".treatment-item.edited")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.locator(".treatments-list")).not.toContainText("99 units");

    await context.close();
  });
});
