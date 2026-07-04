import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// Increment-4 offline characterization (frontend-refactor plan §4). Pins the observable offline→online
// path the Sync/Store extraction must preserve, end-to-end in a real browser: a capture made while the
// backend is unreachable saves + appears optimistically, and on reconnect the outbox drains and the
// offline-return receipt confirms the sync exactly once. The unit-level engine contract (queue/process/
// retry/self-heal) is pinned in src/app/outbox/outboxEngine.test.ts.

async function loginAsDoctor(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
}

test("captures made offline drain and confirm with the return receipt on reconnect", async ({ page, context }) => {
  await installAppMocks(page, authPayload({ role: "owner", tier: "basic" }));

  // Registered AFTER installAppMocks so it wins over the catch-all. The capture upload fails while the
  // backend is "down", and succeeds once reachable — the real fail→retry→drain path.
  let backendDown = false;
  await page.route("**/api/v1/captures**", async (route) => {
    if (backendDown) return route.abort();
    return route.fulfill({
      contentType: "application/json",
      json: {
        session: { id: "backend-sess-1", label: "Visit", status: "processing", items: [] },
        item: { id: "backend-cap-1", type: "note", status: "uploaded", detail: "" },
      },
    });
  });

  await loginAsDoctor(page);

  // Go offline, then capture a note: it must save + appear optimistically with no reachable backend.
  backendDown = true;
  await context.setOffline(true);
  await page.getByRole("button", { name: "Note" }).first().click();
  const noteText = "ZZ-offline-note-77";
  await page.getByPlaceholder("Type the note now. Patient matching can wait.").fill(noteText);
  await page.getByRole("button", { name: "Save to visit" }).click();
  await expect(page.getByText(noteText).first()).toBeVisible({ timeout: 10000 });

  // Reconnect: the browser online event resumes the outbox, the capture drains, and the return receipt
  // confirms the sync (it was queued while offline).
  backendDown = false;
  await context.setOffline(false);
  await expect(page.getByText(/now synced to your clinic memory/i)).toBeVisible({ timeout: 20000 });
});
