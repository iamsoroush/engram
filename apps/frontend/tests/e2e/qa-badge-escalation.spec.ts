import { expect, test, type Page } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

// AES-1901 — the Q&A badge (a deliberate partial-revert of the E16 merge), the urgent toast on a
// newly-arrived red-flag question, and the urgent warning styling on the inbox row.

// The catch-all in installAppMocks is registered LAST and Playwright checks routes newest-first, so
// per-endpoint routes MUST be added AFTER installAppMocks to win. `setup` installs the base mocks; the
// caller then adds its specific routes before `login`.
async function setup(page: Page, appLanguage: "en" | "fa" = "en") {
  await useEnglish(page); // the login chrome stays English for stable selectors
  await installAppMocks(page, authPayload({ role: "doctor", tier: "pro", appLanguage }));
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
}

test("Q&A badge shows the pending count, and a newly-arrived urgent question escalates it + toasts", async ({ page }) => {
  await setup(page);
  // The summary drives the badge; a closure flag flips it to urgent so we can assert the ARRIVAL toast.
  let urgent = false;
  await page.route("**/api/v1/patient-qa/inbox/summary**", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: urgent
        ? { scope: "mine", pending: 1, urgent: 1, urgentThreads: [{ threadId: "t1", patientName: "Sara", flags: ["vision"] }] }
        : { scope: "mine", pending: 1, urgent: 0, urgentThreads: [] },
    }),
  );

  await login(page);

  // The badge shows the pending count, in the calm (non-urgent) tone.
  const badge = page.getByTestId("qa-pending-badge");
  await expect(badge).toHaveText("1");
  await expect(badge).not.toHaveClass(/tone-urgent/);

  // A red-flagged question arrives; the badge refetches on window focus (no 60s wait).
  urgent = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  // The badge escalates to the danger tone AND an in-app toast names the flag.
  await expect(badge).toHaveClass(/tone-urgent/);
  await expect(page.locator(".toast")).toContainText("vision changes");
});

test("an urgent thread renders the warning row + red-flag banner (fa)", async ({ page }) => {
  const inbox = {
    scope: "mine",
    total: 1,
    items: [
      {
        threadId: "t1",
        patientId: "p1",
        patientName: "سارا",
        assignedDoctor: { userId: "user-1", name: "Dr. E2E" },
        routingSource: "treating",
        treatingDoctorCount: 1,
        needsApproval: true,
        urgent: true,
        urgentFlags: ["vision"],
        pendingQuestion: {
          messageId: "m1",
          question: "پوستم سفید شده و تار می‌بینم",
          askedAt: "2026-07-10T10:00:00Z",
          suggestedReply: "",
          draftStatus: "pending",
          draftSource: null,
          draftProvenance: null,
          urgent: true,
          urgentFlags: ["vision"],
        },
        messages: [{ id: "m1", role: "patient", body: "پوستم سفید شده و تار می‌بینم", status: "pending", inReplyToId: null, createdAt: "2026-07-10T10:00:00Z" }],
        visits: [],
        lastActivityAt: "2026-07-10T10:00:00Z",
      },
    ],
  };
  await setup(page, "fa");
  await page.route("**/api/v1/patient-qa/inbox?**", (route) => route.fulfill({ contentType: "application/json", json: inbox }));
  await page.route("**/api/v1/patient-qa/settings", (route) => route.fulfill({ contentType: "application/json", json: { routingMode: "ai_default" } }));

  await login(page);
  // Click-nav (not goto): the icon renders only once capabilities resolve, so this can't race the route guard.
  await page.getByTestId("qa-nav-button").click();
  await page.getByTestId("qa-inbox").waitFor();

  // The urgent badge + red-flag banner both render, in Persian, naming the flag «تاری دید».
  await expect(page.getByTestId("qa-urgent-badge")).toHaveText("فوری");
  const banner = page.getByTestId("qa-urgent-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("تاری دید");
});
