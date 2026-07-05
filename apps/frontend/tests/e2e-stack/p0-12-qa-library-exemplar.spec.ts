import { expect, test } from "@playwright/test";
import { applyAuth, registerProClinic } from "./_stack";

// P0-12 — Q&A knowledge library + retrieval-grounded drafting (AES-410), gateway-less.
// A doctor curates a template in the Library tab; a patient then asks a matching question and the
// deterministic (gateway-less) draft is GROUNDED IN that template — the reply carries the template's
// guidance and the draft shows a "based on: <template>" provenance chip. Then the sent reply is
// auto-indexed into the library and can be excluded. Everything runs on the deterministicFallback
// path (no gateway), so the assertions are stable.
test.describe("P0-12 Q&A library + retrieval-grounded draft", () => {
  test("curated template grounds the gateway-less draft, shows provenance, auto-indexes + excludes", async ({
    browser,
    request,
  }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const H = { Authorization: `Bearer ${clinic.auth.accessToken}` };

    // A unique marker in the template answer proves the draft was grounded in THIS exemplar.
    const marker = `EXEMPLAR-${Date.now().toString(36).toUpperCase()}`;
    const templateAnswer = `Some swelling after filler is normal for a few days and usually settles. ${marker}`;

    // The doctor opens the Q&A inbox and switches to the Library tab.
    const staffCtx = await browser.newContext();
    await applyAuth(staffCtx, clinic.auth, { lang: "en" });
    const staff = await staffCtx.newPage();
    staff.on("dialog", (dialog) => void dialog.accept()); // accept send / delete confirms
    await staff.goto("/#qa-inbox");
    await expect(staff.locator('[data-testid="qa-inbox"]')).toBeVisible({ timeout: 30_000 });
    await staff.locator('[data-testid="qa-tab-library"]').click();
    const library = staff.locator('[data-testid="qa-library"]');
    await expect(library).toBeVisible();

    // Curate a template through the Library form (library CRUD via the real UI).
    await library.locator('[data-testid="qa-library-new"]').click();
    await staff.locator('[data-testid="qa-template-title"]').fill("Filler swelling");
    await staff.locator('[data-testid="qa-template-question"]').fill("Is swelling after filler normal?");
    await staff.locator('[data-testid="qa-template-answer"]').fill(templateAnswer);
    await staff.locator('[data-testid="qa-template-save"]').click();
    await expect(library.getByText(marker)).toBeVisible({ timeout: 15_000 });

    // A patient asks a MATCHING question (via the public API — the token is the capability).
    const patient = await (
      await request.post("/api/v1/patients", { headers: H, data: { displayName: "Exemplar Patient" } })
    ).json();
    const thread = await (
      await request.post("/api/v1/patient-qa/threads", { headers: H, data: { patientId: patient.id } })
    ).json();
    const publicToken = String(thread.token);
    await request.post(`/api/v1/qa/${publicToken}/ask`, { data: { question: "Is the swelling normal after my filler?" } });

    // The gateway-less draft lands ready, GROUNDED IN the template (carries the marker) with template
    // provenance — nothing auto-sends.
    let messageId = "";
    await expect
      .poll(
        async () => {
          const inbox = await (await request.get("/api/v1/patient-qa/inbox?scope=all", { headers: H })).json();
          const pending = inbox.items?.[0]?.pendingQuestion;
          if (pending?.draftStatus === "ready") messageId = String(pending.messageId);
          const grounded = Boolean(pending?.suggestedReply?.includes(marker));
          const provenance = pending?.draftProvenance?.kind === "template";
          return pending?.draftStatus === "ready" && grounded && provenance;
        },
        { timeout: 30_000 },
      )
      .toBe(true);

    // The provenance chip is visible in the inbox UI. The thread has no treating doctor (the
    // patient has no visits), so it lives under the CLINIC scope — the default "Mine" scope is
    // correctly empty (the API poll above used scope=all for the same reason).
    await staff.locator('[data-testid="qa-tab-inbox"]').click();
    const inbox = staff.locator('[data-testid="qa-inbox"]');
    await inbox.getByRole("button", { name: "Clinic" }).click();
    await expect(inbox.getByText("Exemplar Patient").first()).toBeVisible({ timeout: 15_000 });
    await expect(inbox.locator('[data-testid="qa-draft-provenance"]').first()).toBeVisible();

    // Approve + send the doctor-verified reply (the draft already carries the template guidance).
    await inbox.getByRole("button", { name: "Send", exact: true }).first().click();

    // The sent reply is auto-indexed into the clinic's knowledge base and appears in the Library.
    await expect
      .poll(
        async () => {
          const lib = await (await request.get("/api/v1/patient-qa/library", { headers: H })).json();
          return (lib.sentReplies ?? []).filter((r: { status: string }) => r.status === "active").length;
        },
        { timeout: 20_000 },
      )
      .toBeGreaterThan(0);

    // Excluding the auto-indexed reply evicts it from the index (the manage/exclude list).
    const lib = await (await request.get("/api/v1/patient-qa/library", { headers: H })).json();
    const indexed = (lib.sentReplies ?? []).find((r: { status: string }) => r.status === "active");
    expect(indexed).toBeTruthy();
    const excludeResp = await request.post(`/api/v1/patient-qa/library/${indexed.id}/status`, {
      headers: H,
      data: { status: "excluded" },
    });
    expect(excludeResp.ok()).toBeTruthy();
    const after = await (await request.get("/api/v1/patient-qa/library?status=excluded", { headers: H })).json();
    expect((after.sentReplies ?? []).some((r: { id: string }) => r.id === indexed.id)).toBe(true);

    await staffCtx.close();
  });
});
