import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

// AES-1902 — the Library makes the QUESTION the primary, required field (the retrieval signal), and
// shows one quiet notice when semantic (embedding) matching is off so the degradation isn't silent.

test("Library shows the semantic-off notice and requires the question field", async ({ page }) => {
  await useEnglish(page);
  await installAppMocks(page, authPayload({ role: "doctor", tier: "pro" }));
  await page.route("**/api/v1/patient-qa/library**", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: { templates: [], sentReplies: [], counts: { templates: 0, sentRepliesActive: 0, sentRepliesExcluded: 0 }, semanticSearch: false },
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  // Click-nav (not goto): the icon renders only once capabilities resolve, so this can't race the route guard.
  await page.getByTestId("qa-nav-button").click();
  await page.getByTestId("qa-inbox").waitFor();
  await page.getByTestId("qa-tab-library").click();

  // The quiet "semantic matching is off" notice is visible.
  await expect(page.getByTestId("qa-semantic-off")).toBeVisible();

  // Open the new-template form: the question field is present and primary.
  await page.getByTestId("qa-library-new").click();
  await expect(page.getByTestId("qa-template-question")).toBeVisible();

  // Filling only the answer (no question) is blocked — the question is required now.
  await page.getByTestId("qa-template-answer").fill("Up to 24 hours");
  await page.getByTestId("qa-template-save").click();
  await expect(page.getByText("Add the patient’s question", { exact: false })).toBeVisible();
});
