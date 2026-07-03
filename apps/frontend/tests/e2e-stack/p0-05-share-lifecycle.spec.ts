import { expect, test } from "@playwright/test";
import { FIXTURES, registerClinic, uploadCaptureApi, uniqueSuffix } from "./_stack";

// P0-5 — Share lifecycle + withholding (Basic). A curated public share renders read-only clinical
// content but withholds internal data (national ID, internal notes, lot numbers). Revoking it makes the
// public page indistinguishable from a bogus token ("no longer available"), and the raw capture file
// endpoint stays behind auth (401). The public surface needs no login — the token is the capability.
test.describe("P0-5 share lifecycle + withholding", () => {
  test("curated public share withholds internals; revoke ≡ bogus; raw capture needs auth", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    const H = { Authorization: `Bearer ${token}` };
    const nationalId = `194${uniqueSuffix()}`.slice(0, 10);

    // Patient (with a national ID that must never leak) + a session with one capture.
    const patient = await (await request.post("/api/v1/patients", { headers: H, data: { displayName: "Share Patient", nationalId } })).json();
    const up = await uploadCaptureApi(request, token, { type: "photo", fixtureFile: FIXTURES.photoPre, newSession: true });
    const sessionId = up.session.id;
    const captureFileEndpoint = String((up.item as any).fileEndpoint);
    await request.post(`/api/v1/sessions/${sessionId}/assign-patient`, { headers: H, data: { patientId: patient.id, source: "staff", reason: "e2e" } });

    // Curated share: one aftercare-style section, treatments withheld.
    const share = await (
      await request.post("/api/v1/patient-shares", {
        headers: H,
        data: {
          patientId: patient.id,
          sessionId,
          title: "Your visit",
          sections: [{ label: "Aftercare", body: "Rest and avoid heavy exercise for 24 hours." }],
          includeTreatments: false,
        },
      })
    ).json();
    const shareToken = String(share.token);

    // Public curated page renders read-only content, withholding the national ID.
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`/share/${shareToken}`);
    await expect(page.locator(".ps-shell")).toBeVisible();
    await expect(page.getByText("Rest and avoid heavy exercise for 24 hours.")).toBeVisible();
    await expect(page.getByText(nationalId)).toHaveCount(0);
    await expect(page.getByText(/national id/i)).toHaveCount(0);

    // Revoke → the public page becomes indistinguishable from a bogus token.
    await request.post(`/api/v1/patient-shares/${share.id}/revoke`, { headers: H });
    await page.goto(`/share/${shareToken}`);
    await expect(page.getByText("This link is no longer available")).toBeVisible();
    await page.goto(`/share/bogus-${uniqueSuffix()}`);
    await expect(page.getByText("This link is no longer available")).toBeVisible();

    // The raw capture file endpoint stays behind auth (no token in the URL → 401).
    const unauth = await request.get(captureFileEndpoint);
    expect(unauth.status()).toBe(401);

    await context.close();
  });
});
