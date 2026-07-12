import { expect, test } from "@playwright/test";
import { addTeamMember, applyAuth, expectShellReady, loginPassword, registerClinic, uniqueSuffix } from "./_stack";

// P0-10 — Reception worklist multi-seat (Basic). An assistant lines a patient up for a doctor; the
// doctor sees the queued patient and starts the visit — and the capture bar stays available throughout
// (the worklist never blocks fresh capture). Two real seats in one isolated clinic. (AES-903.)
test.describe("P0-10 reception worklist multi-seat", () => {
  test("assistant lines up a patient; the doctor sees it and starts the visit", async ({ browser, request }) => {
    const owner = await registerClinic(request, { lang: "en" });
    const ownerToken = owner.auth.accessToken;
    const suffix = uniqueSuffix();
    const password = "e2e-longenough-123";
    const docEmail = `doc-${suffix}@e2e.test`;
    const asstEmail = `asst-${suffix}@e2e.test`;
    await addTeamMember(request, ownerToken, { fullName: "Dr. Seat", email: docEmail, password, role: "doctor" });
    await addTeamMember(request, ownerToken, { fullName: "Ari Assistant", email: asstEmail, password, role: "assistant" });
    const docAuth = await loginPassword(request, docEmail, password);
    const asstAuth = await loginPassword(request, asstEmail, password);
    const docUserId = String((docAuth.user as any).id);

    // A patient to line up.
    const patientName = `Lineup ${suffix}`;
    const patient = await (await request.post("/api/v1/patients", { headers: { Authorization: `Bearer ${ownerToken}` }, data: { displayName: patientName } })).json();

    // Assistant lines the patient up for the doctor.
    const lineUp = await request.post("/api/v1/worklist", {
      headers: { Authorization: `Bearer ${asstAuth.accessToken}` },
      data: { patientId: patient.id, clinicianUserId: docUserId },
    });
    expect(lineUp.ok()).toBeTruthy();

    // Doctor seat: the queued patient appears in the worklist; starting the visit opens a capturable visit.
    const context = await browser.newContext();
    await applyAuth(context, docAuth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/#patients");
    await page.getByRole("tab", { name: "Recent" }).click();
    const worklist = page.locator(".worklist-section");
    await expect(worklist).toBeVisible({ timeout: 30_000 });
    await expect(worklist.getByText(patientName)).toBeVisible();

    await worklist.getByRole("button", { name: "Start visit" }).click();

    // The visit opens on the doctor's shell and the capture bar is available (never blocked).
    await expectShellReady(page);
    await expect(page.getByText(patientName).first()).toBeVisible();

    await context.close();
  });
});
