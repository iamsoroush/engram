import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

// #8: the Pro Q&A inbox empty state must teach (how a thread arrives) and offer a shortcut, not
// dead-end with "No conversations yet." With only installAppMocks the inbox mock resolves empty, so
// the teaching state renders.

test("Q&A inbox empty state teaches how a thread arrives + offers a Share Q&A link shortcut", async ({ page }) => {
  await useEnglish(page);
  await installAppMocks(page, authPayload({ role: "doctor", tier: "pro" }));

  await page.goto("/");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  // Click-nav (not goto): the icon renders only once capabilities resolve, so this can't race the route guard.
  await page.getByTestId("qa-nav-button").click();
  await page.getByTestId("qa-inbox").waitFor();

  // The teaching sentence (how a thread arrives) and the shortcut are both present.
  await expect(page.getByText("A thread starts here", { exact: false })).toBeVisible();
  const share = page.getByRole("button", { name: "Share Q&A link" });
  await expect(share).toBeVisible();

  // The shortcut opens the app-wide finder (pick a patient → open their Q&A channel).
  await share.click();
  await expect(page.locator(".finder-panel")).toBeVisible();
});
