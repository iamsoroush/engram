import { expect, test, type Page } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

// AES-1803 — the «بر اساس» draft provenance panel: a grounded draft names its sources (the strong
// template chip + patient-record/conversation chips); an ungrounded draft shows the honest
// general-knowledge caution chip, which is the state that deserves the hardest review.

function inboxWith(provenance: unknown) {
  return {
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
        urgent: false,
        urgentFlags: [],
        pendingQuestion: {
          messageId: "m1",
          question: "کی میتونم ورزش کنم؟",
          askedAt: "2026-07-10T10:00:00Z",
          suggestedReply: "تا ۲۴ ساعت از ورزش سنگین پرهیز کنید.",
          draftStatus: "ready",
          draftSource: "ai:test",
          draftProvenance: provenance,
          urgent: false,
          urgentFlags: [],
        },
        messages: [{ id: "m1", role: "patient", body: "کی میتونم ورزش کنم؟", status: "pending", inReplyToId: null, createdAt: "2026-07-10T10:00:00Z" }],
        visits: [],
        lastActivityAt: "2026-07-10T10:00:00Z",
      },
    ],
  };
}

async function openInbox(page: Page, provenance: unknown) {
  await useEnglish(page);
  await installAppMocks(page, authPayload({ role: "doctor", tier: "pro", appLanguage: "fa" }));
  await page.route("**/api/v1/patient-qa/inbox?**", (route) => route.fulfill({ contentType: "application/json", json: inboxWith(provenance) }));
  await page.route("**/api/v1/patient-qa/settings", (route) => route.fulfill({ contentType: "application/json", json: { routingMode: "ai_default" } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.goto("/#qa-inbox");
  await page.getByTestId("qa-inbox").waitFor();
}

test("a grounded draft names its sources: template + patient-record + conversation (fa)", async ({ page }) => {
  await openInbox(page, {
    grounded: true,
    kind: "template",
    exemplarId: "ex1",
    label: "ورزش بعد از بوتاکس",
    sources: [
      { type: "template", exemplarId: "ex1", label: "ورزش بعد از بوتاکس" },
      { type: "patient_aftercare" },
      { type: "conversation", text: "Q: قبلاً چی پرسیدم\nA: پاسخ قبلی دکتر" },
    ],
  });

  const panel = page.getByTestId("qa-draft-provenance");
  await expect(panel).toContainText("بر اساس");
  await expect(page.getByTestId("qa-provenance-template")).toContainText("الگوی کلینیک: ورزش بعد از بوتاکس");
  await expect(panel).toContainText("مراقبت پس از درمان بیمار");
  await expect(panel).toContainText("گفتگوی قبلی همین بیمار");
  // Not the general-knowledge state.
  await expect(page.getByTestId("qa-provenance-general")).toHaveCount(0);

  // The conversation chip carries its snippet — tapping it reveals the actual grounding text (AES-1803).
  await page.getByTestId("qa-provenance-conversation").click();
  await expect(panel).toContainText("پاسخ قبلی دکتر");
});

test("an ungrounded draft shows the general-knowledge caution chip (fa)", async ({ page }) => {
  await openInbox(page, { grounded: false, sources: [] });

  const general = page.getByTestId("qa-provenance-general");
  await expect(general).toBeVisible();
  await expect(general).toContainText("دانش عمومی — بدون منبع کلینیکی");
  await expect(page.getByTestId("qa-provenance-template")).toHaveCount(0);
});
