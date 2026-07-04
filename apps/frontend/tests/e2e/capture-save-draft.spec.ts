import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// Increment-0 safety net (frontend-refactor plan §0): pin the capture → save-draft → session-appears
// path hermetically before the Sync/Store extraction moves saveDraft's optimistic `flushSync` (§6).
// The backend is mocked; we assert the OPTIMISTIC local write (session appears with the note) which is
// what the flushSync guarantees is visible before the async upload — independent of the upload result.

async function loginAsDoctor(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
}

test("writing a note optimistically creates a session with that capture", async ({ page }) => {
  await installAppMocks(page, authPayload({ role: "owner", tier: "basic" }));
  await loginAsDoctor(page);

  // Empty capture surface → the three big actions. Basic leads with "Note".
  await page.getByRole("button", { name: "Note" }).first().click();

  // The write-note sheet opens; type a distinctive note and save into the (new) visit.
  const noteText = "ZZ-characterization-note-42";
  await page.getByPlaceholder("Type the note now. Patient matching can wait.").fill(noteText);
  await page.getByRole("button", { name: "Save to visit" }).click();

  // The optimistic session must render the capture without waiting on the (mocked) upload.
  await expect(page.getByText(noteText).first()).toBeVisible({ timeout: 10000 });
});
