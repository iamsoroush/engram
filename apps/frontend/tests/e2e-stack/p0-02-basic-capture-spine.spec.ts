import { expect, test } from "@playwright/test";
import { applyAuth, expectShellReady, fixturePath, FIXTURES, registerClinic, uniqueSuffix } from "./_stack";

// P0-2 — Basic zero-AI capture spine. On Basic (zero AI capabilities), the three capture kinds are pure
// CRUD: a note saves instantly and stays editable, a photo files as a whole thumbnail with no caption or
// spinner, and audio is a plain voice memo with no transcript. No AI attribution chrome appears anywhere.
test.describe("P0-2 Basic zero-AI capture spine", () => {
  test("note is instant + editable, photo has no caption/spinner, audio is a plain voice memo", async ({
    browser,
    request,
  }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/");
    await expectShellReady(page);

    const actions = page.locator(".capture-pills-actions");

    // --- Note: instant + editable ---
    const noteText = `Consult notes ${uniqueSuffix()}`;
    await actions.locator(".capture-action-button", { hasText: "Note" }).click();
    await page.getByPlaceholder(/Type the note now/).fill(noteText);
    await page.getByRole("button", { name: "Save to visit" }).click();
    const note = page.locator(".basic-note-text", { hasText: noteText });
    await expect(note).toBeVisible(); // rendered instantly from the local-first outbox
    await expect(note).toHaveClass(/editable/); // tap-to-edit affordance (role=button)
    await expect(note).toHaveAttribute("role", "button");

    // --- Photo: whole thumbnail, no caption, no spinner ---
    await actions.locator(".capture-action-button", { hasText: "Photo" }).click();
    await page.getByLabel("Choose photo from library").setInputFiles(fixturePath(FIXTURES.photoPre));
    await page.getByRole("button", { name: "Use photo" }).click();
    await expect(page.locator(".live-draft-photo-basic img").first()).toBeVisible();

    // --- Audio: plain voice memo, no transcript ---
    await actions.locator(".capture-action-button", { hasText: "Audio" }).click();
    await page.getByLabel("Select audio file").setInputFiles(fixturePath(FIXTURES.audioInitial));
    await expect(page.locator(".voice-memo-player").first()).toBeVisible();

    // --- Zero AI chrome: no caption/transcript sections and no AI attribution anywhere in the feed ---
    await expect(page.locator(".capture-generated-section")).toHaveCount(0);
    await expect(page.locator(".capture-ai-tag")).toHaveCount(0);

    await context.close();
  });
});
