import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// Smart lists + lot/product recall (Pro; AES-501 / AES-502). Hermetic: the new deterministic
// endpoints are mocked. Covers the Pro Lists tab (rail counts → list rows → back), the lot-recall
// cohort + the trustworthy "similar lots (not included)" group, the Q&A outreach handoff button,
// Pro-gating (Basic has no Lists tab), and fa chrome with no English-chrome leak.

const ISO = "2026-06-25T08:30:00.000Z";
type Lang = "fa" | "en";

const COUNTS = { counts: { "seen-this-week": 2, "due-to-return": 1, "missing-after-photo": 1 }, dueToReturnWeeks: 12 };
const SEEN_ROWS = {
  key: "seen-this-week",
  rows: [
    { patientId: "p-sara", displayName: "Sara", visitAt: ISO, detail: "Dysport 20 u, forehead", identifyingContext: { phone: "0912 000" } },
    { patientId: "p-nima", displayName: "Nima", visitAt: ISO, detail: "Juvederm 1 cc, cheek" },
  ],
  total: 2,
  limit: 100,
  offset: 0,
  dueToReturnWeeks: 12,
};
const LEDGER = {
  lots: [{ lot: "D-4471", brand: "Dysport", product: "botox", patientCount: 2, visitCount: 3 }],
  products: [{ name: "Dysport", kind: "brand", patientCount: 2, visitCount: 3 }],
};
const RECALL = {
  kind: "lot",
  value: "D-4471",
  normalized: "D-4471",
  patientCount: 1,
  visitCount: 1,
  affected: [
    {
      patientId: "p-sara",
      displayName: "Sara",
      identifyingContext: { phone: "0912 000" },
      visits: [{ sessionId: "v-sara", visitAt: ISO, treatments: [{ lot: "D-4471", phrase: "Dysport 20 u, forehead" }] }],
    },
  ],
  similar: [{ lot: "D 4471", patientCount: 1, visitCount: 1 }],
};

function payload(appLanguage: Lang, tier: "pro" | "basic" = "pro") {
  const base = authPayload({ role: "owner", tier });
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

async function installSmartListMocks(page: Page, p: ReturnType<typeof payload>) {
  await page.route("**/api/v1/**", (r) => r.fulfill({ contentType: "application/json", json: {} }));
  await installAppMocks(page, p);
  // Branch smart-lists: the bare counts vs a specific list key.
  await page.route("**/api/v1/smart-lists**", (r) => {
    const path = new URL(r.request().url()).pathname;
    const match = path.match(/\/smart-lists\/([^/]+)$/);
    return r.fulfill({ contentType: "application/json", json: match ? { ...SEEN_ROWS, key: match[1] } : COUNTS });
  });
  await page.route("**/api/v1/lot-ledger**", (r) => r.fulfill({ contentType: "application/json", json: LEDGER }));
  await page.route("**/api/v1/lot-recall**", (r) => r.fulfill({ contentType: "application/json", json: RECALL }));
}

async function openMemory(page: Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
  await page.locator(".app-navigator button").nth(1).click(); // → Clinical Memory
  await page.getByRole("heading", { name: /Clinical Memory|حافظهٔ بالینی/ }).first().waitFor();
}

test.describe("Smart lists + lot recall (Pro; AES-501/502)", () => {
  test("Pro: Lists tab → rail counts → open a list → rows render", async ({ page }) => {
    await installSmartListMocks(page, payload("en"));
    await openMemory(page);
    await page.getByRole("tab", { name: "Lists" }).click();
    // The rail shows the three named lenses with live counts.
    await expect(page.getByText("Seen this week").first()).toBeVisible();
    await expect(page.getByText("Due to return").first()).toBeVisible();
    await expect(page.getByText("Missing after-photo").first()).toBeVisible();
    await expect(page.locator(".smart-list-count").first()).toHaveText("2");
    // Open "Seen this week" → patient rows (verbatim treatment detail is data).
    await page.locator(".smart-list-card").first().click();
    await expect(page.getByText("Sara").first()).toBeVisible();
    await expect(page.getByText("Dysport 20 u, forehead").first()).toBeVisible();
    // Back returns to the rail.
    await page.getByRole("button", { name: "Back to lists" }).click();
    await expect(page.getByText("Look up a lot or product")).toBeVisible();
  });

  test("Pro: lot recall → affected cohort, outreach handoff, similar-not-included", async ({ page }) => {
    await installSmartListMocks(page, payload("en"));
    await openMemory(page);
    await page.getByRole("tab", { name: "Lists" }).click();
    // A "recent in your data" chip runs the recall.
    await page.getByRole("button", { name: /D-4471/ }).first().click();
    await expect(page.getByText("Lot recall · D-4471")).toBeVisible();
    await expect(page.getByText("1 patient · 1 visit")).toBeVisible(); // singular forms, not "1 patients"
    await expect(page.getByText("Sara").first()).toBeVisible();
    // The outreach handoff to the existing patient channel (AES-402).
    await expect(page.getByRole("button", { name: /Open Q&A channel/ })).toBeVisible();
    // The safety rule: a same-core lot is surfaced separately, NOT folded into the affected list.
    await expect(page.getByText("Similar lots (not included)")).toBeVisible();
    await expect(page.getByRole("button", { name: /D 4471/ })).toBeVisible();
  });

  test("Pro: lookup is live (separator-insensitive) and re-focusing the search dismisses the result", async ({ page }) => {
    await installSmartListMocks(page, payload("en"));
    await openMemory(page);
    await page.getByRole("tab", { name: "Lists" }).click();
    const search = page.locator(".lot-lookup-search input");
    // Live, similar-match search: "d4471" (no hyphen) still surfaces the "D-4471" lot.
    await search.fill("d4471");
    await expect(page.getByRole("button", { name: /D-4471/ }).first()).toBeVisible();
    // Run a recall, then return to the search → the stale cohort card must clear (not linger).
    await search.fill("");
    await page.getByRole("button", { name: /D-4471/ }).first().click();
    await expect(page.locator(".recall-cohort")).toHaveCount(1);
    await search.click();
    await expect(page.locator(".recall-cohort")).toHaveCount(0);
  });

  test("Basic: no Lists tab (Pro-gated, legible upgrade)", async ({ page }) => {
    await installSmartListMocks(page, payload("en", "basic"));
    await openMemory(page);
    await expect(page.getByRole("tab", { name: "Patients" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Lists" })).toHaveCount(0);
  });

  test("fa: Lists chrome is Persian with no English-chrome leak", async ({ page }) => {
    await installSmartListMocks(page, payload("fa"));
    await openMemory(page);
    await page.getByRole("tab", { name: "فهرست‌ها" }).click();
    await expect(page.getByText("فهرست‌های هوشمند").first()).toBeVisible();
    await expect(page.getByText("جستجوی بچ یا محصول")).toBeVisible();
    // No English chrome outside verbatim clinical data ([data-content]).
    const leaks = await page.evaluate(() => {
      const root = document.querySelector(".smart-lists") || document.body;
      const clone = root.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("[data-content]").forEach((n) => n.remove());
      const text = clone.textContent || "";
      return ["Smart lists", "Seen this week", "Due to return", "Missing after-photo", "Look up a lot"].filter((w) => text.includes(w));
    });
    expect(leaks).toEqual([]);
  });
});
