import { expect, test } from "@playwright/test";
import { applyAuth, assignSessionToNewPatient, FIXTURES, registerClinic, uploadCaptureApi, uniqueSuffix } from "./_stack";

// P0-4 — Capture unassigned → assign later (Basic). A capture taken without a patient lands in "Needs
// input"; its resolver offers a deterministic suggestion (the recently-seen patient, rule-based — no AI)
// which, once accepted, files the visit onto that patient. (AES-301.)
test.describe("P0-4 capture unassigned → assign later", () => {
  test("Needs-input resolver offers a deterministic suggestion that files the visit", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    const suffix = uniqueSuffix();
    const recentName = `Recent Sara ${suffix}`;

    // A recently-seen patient (assigned visit) — the deterministic suggestion source.
    const recent = await uploadCaptureApi(request, token, { type: "photo", fixtureFile: FIXTURES.photoPre, newSession: true });
    await assignSessionToNewPatient(request, token, recent.session.id, recentName);

    // A fresh capture with no patient → it will need input.
    await uploadCaptureApi(request, token, { type: "photo", fixtureFile: FIXTURES.photoPost, newSession: true });

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/#patients");
    // The Needs-input tab is now the Attention sweep (Track A close-the-day); the unassigned
    // visit surfaces as an "Assign patient" item whose action opens the resolver directly.
    await page.getByRole("tab", { name: "Attention" }).click();
    await page.getByRole("button", { name: "Assign patient" }).first().click();
    const resolver = page.getByRole("dialog", { name: "Assign patient" });
    await expect(resolver).toBeVisible();

    // The resolver surfaces the deterministic, recently-seen patient as the top suggestion.
    await expect(resolver.getByText(/Suggested/).first()).toBeVisible();
    await expect(resolver.getByText(recentName).first()).toBeVisible();

    // Its "Assign" action files the visit; the resolver closes and the patient's visit is in view.
    await resolver.getByRole("button", { name: "Assign", exact: true }).first().click();
    await expect(resolver).toHaveCount(0);
    await expect(page.getByText(recentName).first()).toBeVisible();

    await context.close();
  });
});
