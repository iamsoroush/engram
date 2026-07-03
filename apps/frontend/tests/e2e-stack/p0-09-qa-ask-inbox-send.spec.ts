import { expect, test } from "@playwright/test";
import { applyAuth, registerProClinic } from "./_stack";

// P0-9 — Q&A ask → inbox → deterministic draft → send (Pro). A patient asks a question on the public
// /qa/<token> page; it lands pending in the doctor's inbox with a deterministic fallback draft (no
// gateway); nothing auto-sends; the doctor approves + sends, and the reply becomes visible to the
// patient. (AES-402.)
test.describe("P0-9 Q&A ask → inbox → send", () => {
  test("public question lands pending with a fallback draft; doctor send makes it visible", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    const H = { Authorization: `Bearer ${token}` };

    const patient = await (await request.post("/api/v1/patients", { headers: H, data: { displayName: "Reply Patient" } })).json();
    const thread = await (await request.post("/api/v1/patient-qa/threads", { headers: H, data: { patientId: patient.id } })).json();
    const publicToken = String(thread.token);

    // The patient asks on the public page (no login — the token is the capability).
    const patientCtx = await browser.newContext();
    const patientPage = await patientCtx.newPage();
    await patientPage.goto(`/qa/${publicToken}`);
    const question = "Is the swelling normal after the filler?";
    await patientPage.getByLabel("Your question").fill(question);
    await patientPage.getByRole("button", { name: "Send question" }).click();
    // The question joins the patient's thread (awaiting a reply).
    await expect(patientPage.getByText(question)).toBeVisible();

    // The question lands pending in the inbox with a deterministic fallback draft — nothing auto-sends.
    let draft = "";
    await expect
      .poll(
        async () => {
          const inbox = await (await request.get("/api/v1/patient-qa/inbox?scope=all", { headers: H })).json();
          const pending = inbox.items?.[0]?.pendingQuestion;
          if (pending?.draftStatus === "ready" && pending?.suggestedReply) draft = String(pending.suggestedReply);
          return pending?.draftStatus ?? "none";
        },
        { timeout: 30_000 },
      )
      .toBe("ready");
    const publicBefore = await (await request.get(`/api/v1/qa/${publicToken}`)).json();
    expect(publicBefore.exchanges?.[0]?.reply).toBeFalsy(); // nothing sent yet

    // The doctor opens the inbox, sees the pending question + its draft, and sends it (doctor-verified).
    const staffCtx = await browser.newContext();
    await applyAuth(staffCtx, clinic.auth, { lang: "en" });
    const staff = await staffCtx.newPage();
    staff.on("dialog", (dialog) => void dialog.accept()); // accept the "send to patient?" confirm
    await staff.goto("/#qa-inbox");
    const inbox = staff.locator('[data-testid="qa-inbox"]');
    await expect(inbox).toBeVisible({ timeout: 30_000 });
    await inbox.getByRole("button", { name: "Clinic" }).click();
    await expect(inbox.getByText(question)).toBeVisible();
    await expect(inbox.locator(".qa-reply-input")).not.toHaveValue("");
    await inbox.getByRole("button", { name: "Send", exact: true }).click();

    // The reply is now visible to the patient on their private link. Reload-poll so the assertion is
    // robust against the send propagating just after the click returns.
    await expect
      .poll(
        async () => {
          await patientPage.goto(`/qa/${publicToken}`);
          return patientPage.getByText(/thanks for reaching out/i).count();
        },
        { timeout: 20_000 },
      )
      .toBeGreaterThan(0);

    await patientCtx.close();
    await staffCtx.close();
  });
});
