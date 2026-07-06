import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { authPayload, installAppMocks } from "./_setup";

// Unified finder (AES-1201..1205). Hermetic: the composed endpoints (patients/search, patient-memory,
// lot-ledger/lot-recall) are mocked. Covers the app-wide overlay opened from the top-bar search
// affordance, the patients-first backend search grain, the no-results duplicate-guarded hand-off, the
// Pro lot-recall grain + the safety "similar lots (not included)" group, Pro-gating (Basic has no lot
// grain), the `/#search` deep-link, and fa chrome (RTL, no English-chrome leak).

type Lang = "fa" | "en";

const RECENT = {
  items: [{ patientId: "p-recent", displayName: "Reza Ahmadi", metadataSentence: "Botox · 2 visits" }],
  limit: 6,
  offset: 0,
  total: 1,
};
const MATCH = {
  query: "sara",
  total: 1,
  items: [
    {
      id: "p-sara",
      displayName: "Sara Karimi",
      phone: "0912 111 2222",
      reason: "Deterministic, Persian-aware match",
      matchedOn: ["name"],
      score: 0.92,
    },
  ],
};
const EMPTY_SEARCH = { query: "zzz", total: 0, items: [] };
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
      displayName: "Sara Karimi",
      identifyingContext: { phone: "0912 111 2222" },
      visits: [{ sessionId: "v-sara", visitAt: "2026-06-25T08:30:00Z", treatments: [{ lot: "D-4471", phrase: "Dysport 20 u, forehead" }] }],
    },
  ],
  similar: [{ lot: "D 4471", patientCount: 1, visitCount: 1 }],
};

function payload(appLanguage: Lang, tier: "pro" | "basic" = "pro") {
  const base = authPayload({ role: "owner", tier });
  return { ...base, tenant: { ...base.tenant, appLanguage } };
}

async function installFinderMocks(page: Page, p: ReturnType<typeof payload>) {
  await installAppMocks(page, p);
  await page.route("**/api/v1/patient-memory**", (r) => r.fulfill({ contentType: "application/json", json: RECENT }));
  // Branch the ranked search by the `q` param so the no-results state is reachable deterministically.
  await page.route("**/api/v1/patients/search**", (r) => {
    const q = new URL(r.request().url()).searchParams.get("q") || "";
    return r.fulfill({ contentType: "application/json", json: /zzz/i.test(q) ? EMPTY_SEARCH : MATCH });
  });
  await page.route("**/api/v1/lot-ledger**", (r) => r.fulfill({ contentType: "application/json", json: LEDGER }));
  await page.route("**/api/v1/lot-recall**", (r) => r.fulfill({ contentType: "application/json", json: RECALL }));
}

async function login(page: Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.locator(".user-menu summary").first().waitFor();
}

async function openFinder(page: Page) {
  await login(page);
  // The finder button carries only `app-search-button` — the Pro Q&A button shares the class (+
  // `app-qa-button`), so exclude it to stay unambiguous across tiers.
  await page.locator(".app-search-button:not(.app-qa-button)").click();
  await expect(page.locator(".finder-panel")).toBeVisible();
}

test.describe("Unified finder (AES-1201..1205)", () => {
  test("en: top-bar opens the finder; recent patients + hint show pre-query", async ({ page }) => {
    await installFinderMocks(page, payload("en"));
    await openFinder(page);
    await expect(page.getByRole("dialog", { name: "Find" })).toBeVisible();
    await expect(page.getByText("Recent patients")).toBeVisible();
    await expect(page.getByText("Reza Ahmadi")).toBeVisible();
    await expect(page.getByText(/Search by name, phone, or national ID/)).toBeVisible();
  });

  test("en: typing hits the backend patient search; opening a result closes the finder", async ({ page }) => {
    await installFinderMocks(page, payload("en"));
    await openFinder(page);
    await page.locator(".finder-search input").fill("sara");
    await expect(page.getByText("Patients").first()).toBeVisible();
    const row = page.locator(".finder-row", { hasText: "Sara Karimi" }).first();
    await expect(row).toBeVisible();
    await expect(page.getByText("Deterministic, Persian-aware match")).toBeVisible();
    await row.click();
    await expect(page.locator(".finder-panel")).toHaveCount(0);
  });

  test("en: a query with no patient match offers the duplicate-guarded add-a-patient hand-off", async ({ page }) => {
    await installFinderMocks(page, payload("en"));
    await openFinder(page);
    await page.locator(".finder-search input").fill("zzz");
    await expect(page.locator('[data-testid="finder-no-results"]')).toBeVisible();
    await expect(page.getByRole("button", { name: "Add a patient" })).toBeVisible();
  });

  test("Pro: a lot-shaped query surfaces the recall action → cohort + similar-not-included", async ({ page }) => {
    await installFinderMocks(page, payload("en", "pro"));
    await openFinder(page);
    await page.locator(".finder-search input").fill("D-4471");
    // The recall action appears above patient results (safety-tinted); running it renders the cohort.
    const action = page.locator(".finder-lot-action", { hasText: "Recall lot D-4471" });
    await expect(action).toBeVisible();
    await action.click();
    await expect(page.locator('[data-testid="finder-recall"]')).toBeVisible();
    await expect(page.getByText("Dysport 20 u, forehead")).toBeVisible(); // verbatim source citation
    // The safety rule: a same-core lot is surfaced separately, never folded into the affected cohort.
    await expect(page.getByText("Similar lots (not included)")).toBeVisible();
    await expect(page.getByRole("button", { name: /D 4471/ })).toBeVisible();
  });

  test("Basic: no lot-recall grain (Pro-gated; a lot-shaped query shows no recall action)", async ({ page }) => {
    await installFinderMocks(page, payload("en", "basic"));
    await openFinder(page);
    await page.locator(".finder-search input").fill("D-4471");
    await expect(page.locator(".finder-lot-action")).toHaveCount(0);
  });

  test("`/#search` deep-links into the finder overlay and normalizes the hash", async ({ page }) => {
    await installFinderMocks(page, payload("en"));
    await login(page);
    await page.goto("/#search");
    await expect(page.locator(".finder-panel")).toBeVisible();
    await expect.poll(() => page.evaluate(() => window.location.hash)).toBe("#patients");
  });

  test("fa: Persian chrome, RTL document direction, and no English-chrome leak", async ({ page }) => {
    await installFinderMocks(page, payload("fa"));
    await openFinder(page);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByText("بیماران اخیر")).toBeVisible(); // finder.group.recent
    await expect(page.getByPlaceholder("جستجوی بیمار، ویزیت، یا شمارهٔ لات…")).toBeVisible();
    // No English chrome outside verbatim clinical data ([data-content]).
    const leaks = await page.evaluate(() => {
      const root = document.querySelector(".finder-panel") || document.body;
      const clone = root.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("[data-content]").forEach((n) => n.remove());
      const text = clone.textContent || "";
      return ["Find", "Recent patients", "Today's visits", "Recall lot", "Add a patient", "Searching"].filter((w) => text.includes(w));
    });
    expect(leaks).toEqual([]);
  });
});
