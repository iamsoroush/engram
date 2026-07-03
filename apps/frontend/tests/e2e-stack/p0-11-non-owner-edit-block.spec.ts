import { expect, test } from "@playwright/test";
import { addTeamMember, applyAuth, assignSessionToNewPatient, FIXTURES, loginPassword, registerClinic, uploadCaptureApi, uniqueSuffix } from "./_stack";

// P0-11 — Non-owner edit block (Basic). The permissive default gives a non-owner peer (doctor) the
// `contribute` floor: they can append captures but not edit a colleague's. Editing another user's
// capture returns a predictable 403, and the visit workspace shows a read-only banner. (AES-902/905.)
test.describe("P0-11 non-owner edit block", () => {
  test("a contribute-level peer cannot edit another user's capture (403 + read-only banner)", async ({ browser, request }) => {
    const owner = await registerClinic(request, { lang: "en" });
    const ownerToken = owner.auth.accessToken;

    // Owner creates a capture and assigns the visit to a patient (so it's a Today card).
    const up = await uploadCaptureApi(request, ownerToken, { type: "photo", fixtureFile: FIXTURES.photoPre, newSession: true });
    const captureId = String((up.item as any).id);
    const sessionId = up.session.id;
    await assignSessionToNewPatient(request, ownerToken, sessionId, "Owner Patient");

    // Add a doctor peer and sign them in.
    const docEmail = `doc-${uniqueSuffix()}@e2e.test`;
    const docPassword = "e2e-longenough-123";
    await addTeamMember(request, ownerToken, { fullName: "Dr. Peer", email: docEmail, password: docPassword, role: "doctor" });
    const docAuth = await loginPassword(request, docEmail, docPassword);

    // The peer cannot remove the owner's capture — a predictable, owner-only 403.
    const del = await request.delete(`/api/v1/captures/${captureId}`, {
      headers: { Authorization: `Bearer ${docAuth.accessToken}` },
    });
    expect(del.status()).toBe(403);

    // In the UI, the peer sees the visit read-only.
    const context = await browser.newContext();
    await applyAuth(context, docAuth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/#patients");
    await page.getByRole("tab", { name: "Today" }).click();
    await page.locator(".clinical-memory .visit-card, .clinical-memory .clinical-row-selectable").first().click();
    await expect(page.locator(".session-readonly-banner")).toBeVisible({ timeout: 30_000 });

    await context.close();
  });
});
