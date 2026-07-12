import { expect, test, type Page } from "@playwright/test";
import { authPayload, installAppMocks } from "../e2e/_setup";

// Screenshots for the three Memory-surface refinements (owner review), fa/en at 390 (phone) and 768
// (tablet):
//   1. Recent tab — time buckets (Active visit / Today), no header search bar.
//   2. Patients tab — the lighter local roster filter (search moved out of the header).
//   3. Attention sweep — a grouped visit card NAMES its target («Visit {name} · 16:23»), never "This visit".
//   4. Guided review — opening the grouped card enters the review state on the capture screen: a compact
//      progress banner ("N to confirm", next/prev) with the current confirmation highlighted in place.

const now = new Date();
function withToday(hour: number, minute: number) {
  const date = new Date(now);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
}
const VISIT_TS = withToday(16, 23);

type Lang = "fa" | "en";

// A capture on a session.
function capture(id: string, type: "audio" | "photo" | "note", hour: number, minute: number) {
  return { id, type, title: type, detail: `${type} detail`, time: `${hour}:${minute}`, status: "uploaded", capturedAt: withToday(hour, minute) };
}

// The active in-progress visit → "Active visit" bucket.
const ACTIVE_VISIT = {
  id: "s-active", label: "Follow-up visit", time: "16:23", dateLabel: "Today",
  createdAt: VISIT_TS, capturedAt: VISIT_TS, updatedAt: withToday(16, 31), status: "reopened",
  patientId: "patient-soroush", patientName: "Soroush", assignmentSource: "staff",
  items: [capture("c-a1", "photo", 16, 24), capture("c-a2", "audio", 16, 27)],
};
// An unassigned visit needing input → Today bucket (amber, "Assign patient").
const UNASSIGNED_VISIT = {
  id: "s-unassigned", label: "Unassigned visit", time: "14:15", dateLabel: "Today",
  createdAt: withToday(14, 15), capturedAt: withToday(14, 15), updatedAt: withToday(14, 20), status: "unassigned",
  items: [capture("c-u1", "photo", 14, 16), capture("c-u2", "note", 14, 18)],
};
// The visit with two carried-forward doses to confirm → the grouped attention card + the review target.
const REVIEW_GROUP_VISIT = {
  id: "s-review-group", label: "Follow-up visit", time: "16:23", dateLabel: "Today",
  createdAt: VISIT_TS, capturedAt: VISIT_TS, updatedAt: withToday(16, 33), status: "needs_review",
  patientId: "patient-soroush", patientName: "Soroush", assignmentSource: "ai_match",
  extractedMetadata: {
    treatments: [
      { area: "Lips", product: "Filler X", quantity: 1, unit: "ml", carriedForward: true, treatmentKey: "lips|filler-x" },
      { area: "Cheek", product: "Filler Y", quantity: 2, unit: "ml", carriedForward: true, treatmentKey: "cheek|filler-y" },
    ],
    treatment_review: [
      { category: "carried_forward", key: "Lips|Filler X", reason: "Carried forward from the previous visit — confirm the dose." },
      { category: "carried_forward", key: "Cheek|Filler Y", reason: "Carried forward from the previous visit — confirm the dose." },
    ],
  },
  items: [capture("c-r1", "photo", 16, 24), capture("c-r2", "audio", 16, 27)],
};

const ATTENTION = {
  scope: "mine",
  highestTier: "confirm",
  counts: { confirm: 2, suggested: 0, messages: 0, safety: 0, total: 2 },
  items: [
    { id: "g1", kind: "dose", tier: "S2", sessionId: "s-review-group", patientName: "Soroush", reason: "Confirm the carried-forward Lip filler dose.", sortTime: VISIT_TS, dayGroup: "today" },
    { id: "g2", kind: "dose", tier: "S2", sessionId: "s-review-group", patientName: "Soroush", reason: "Confirm the carried-forward Cheek filler dose.", sortTime: VISIT_TS, dayGroup: "today" },
  ],
};

async function installMocks(page: Page, lang: Lang) {
  const payload = authPayload({ role: "doctor", tier: "pro", appLanguage: lang });
  await installAppMocks(page, payload);
  const json = (data: unknown) => async (route: import("@playwright/test").Route) => route.fulfill({ contentType: "application/json", json: data as object });
  await page.route("**/api/v1/sessions**", json([ACTIVE_VISIT, UNASSIGNED_VISIT, REVIEW_GROUP_VISIT]));
  await page.route("**/api/v1/patients**", json([
    { id: "patient-soroush", displayName: "Soroush", lastVisit: VISIT_TS },
    { id: "patient-sara", displayName: "Sara", lastVisit: withToday(11, 30) },
  ]));
  await page.route("**/api/v1/attention**", json(ATTENTION));
}

async function login(page: Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByRole("button", { name: /Memory|حافظه/ }).first().click();
  await page.getByRole("heading", { name: /Clinical Memory|حافظهٔ بالینی/ }).first().waitFor();
}

const RECENT_TAB = { fa: "اخیر", en: "Recent" } as const;
const PATIENTS_TAB = { fa: "بیماران", en: "Patients" } as const;
const ATTENTION_TAB = { fa: "توجه لازم", en: "Attention" } as const;
const REVIEW_ACTION = { fa: "بازبینی", en: "Review" } as const;
const NEXT_ACTION = { fa: "بعدی", en: "Next" } as const;
// The shared 24h clock renders Persian digits under fa (fa-IR locale), Latin under en.
const VISIT_TIME = { fa: "۱۶:۲۳", en: "16:23" } as const;

// The Patients-tab filter stays Persian-orthography-aware (AES-204): a cross-script query the plain
// roster substring can't match still surfaces the patient via the smart search, appended to the list.
test("Patients filter: Persian-aware — «sara» finds «سارا»", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 });
  await installMocks(page, "en");
  // Roster substring returns nothing for the Latin query; smart search transliterates and finds her.
  const json = (data: unknown) => async (route: import("@playwright/test").Route) => route.fulfill({ contentType: "application/json", json: data as object });
  await page.route("**/api/v1/patient-memory**", json({ items: [], limit: 50, offset: 0, total: 0 }));
  await page.route("**/api/v1/patients/search**", json({
    items: [{ id: "p-sara", displayName: "سارا", matchedOn: ["name_fuzzy"], reason: "Matched سارا · you typed sara", lastVisit: VISIT_TS }],
  }));
  await login(page);
  await page.getByRole("tab", { name: "Patients" }).click();
  await page.locator(".patients-filter input").fill("sara");
  await expect(page.getByRole("heading", { name: "سارا" })).toBeVisible({ timeout: 8000 });
  await page.screenshot({ path: "test-results/memref-patients-persian-search.png", fullPage: true });
});

for (const lang of ["en", "fa"] as Lang[]) {
  for (const width of [390, 768]) {
    test(`memory refinements — ${lang} @ ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await installMocks(page, lang);
      await login(page);
      const tag = `${lang}-${width}`;

      // The page never scrolls horizontally (the top bar fits at every phone width — the account
      // control collapses to an avatar-only button on phones so the Pro action row stays one line).
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);

      // 1. Recent tab (default) — time buckets, no header search bar.
      await expect(page.getByRole("tab", { name: RECENT_TAB[lang] })).toHaveAttribute("aria-selected", "true");
      await page.screenshot({ path: `test-results/memref-recent-${tag}.png`, fullPage: true });

      // 2. Patients tab — the lighter local roster filter.
      await page.getByRole("tab", { name: PATIENTS_TAB[lang] }).click();
      await expect(page.locator(".patients-filter input")).toBeVisible();
      await page.screenshot({ path: `test-results/memref-patients-${tag}.png`, fullPage: true });

      // 3. Attention sweep — the grouped card names its target (patient + time), never "This visit".
      await page.getByRole("tab", { name: ATTENTION_TAB[lang] }).click();
      const groupCard = page.locator(".attention-card-group");
      await expect(groupCard).toBeVisible();
      await expect(groupCard).toContainText("Soroush");
      await expect(groupCard).toContainText(VISIT_TIME[lang]);
      await page.screenshot({ path: `test-results/memref-attention-group-${tag}.png`, fullPage: true });

      // 4. Guided review — open the grouped card → the review banner walks its confirmations in place.
      await groupCard.getByRole("button", { name: REVIEW_ACTION[lang] }).click();
      const banner = page.locator(".attention-review-banner");
      await expect(banner).toBeVisible();
      await expect(banner).toContainText(lang === "fa" ? "۲ مورد برای تأیید" : "2 to confirm");
      // The current confirmation (the first dose row) is highlighted in place.
      await expect(page.locator("[data-review-focus]")).toHaveCount(1);
      await expect(page.locator("[data-confirm-id='dose:Lips|Filler X'][data-review-focus]")).toHaveCount(1);
      await page.screenshot({ path: `test-results/memref-review-banner-${tag}.png` });

      // Next moves the highlight to the second confirmation in place (walking the visit's items).
      await banner.getByRole("button", { name: NEXT_ACTION[lang] }).click();
      await expect(page.locator("[data-confirm-id='dose:Cheek|Filler Y'][data-review-focus]")).toHaveCount(1);
      await expect(page.locator("[data-review-focus]")).toHaveCount(1);
    });
  }
}
