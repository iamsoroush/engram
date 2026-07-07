import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import { applyAuth, registerClinic } from "./_stack";

// P0-13 — Close-the-day / unified attention (AES-1004). Seeded "needs you" items surface in the
// Attention tab of Clinical Memory: today's true "N to confirm" bucket into the severity-ordered
// Confirm section, and an item left open from a prior calendar day lands in the "Earlier, still open"
// carry-over group (nothing decays silently when the day rolls over). Deterministic on Basic — an
// unassigned visit is the zero-AI S2 signal; cross-tier severity ordering (S1<S2<qa<S3) is exhaustively
// covered by the pure unit test (src/features/memory/components/attentionModel.test.ts).

/** Seed a bare unassigned visit at a given capture time → a deterministic S2 "assign patient" item. */
async function seedUnassignedVisit(request: APIRequestContext, token: string, capturedAtIso: string): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post("/api/v1/sessions", { headers, data: { capturedAt: capturedAtIso } });
  if (!created.ok()) throw new Error(`create session failed: ${created.status()} ${await created.text()}`);
  const session = (await created.json()) as { id: string };
  // Flip to the unassigned state so the roll-up surfaces it as an "assign patient" attention item.
  const patched = await request.patch(`/api/v1/sessions/${session.id}`, { headers, data: { status: "unassigned" } });
  if (!patched.ok()) throw new Error(`set unassigned failed: ${patched.status()} ${await patched.text()}`);
  return session.id;
}

test.describe("P0-13 close-the-day attention sweep", () => {
  test("seeded items appear in Attention, severity-sectioned, with the Earlier carry-over group", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    const now = new Date();
    // ~36h back is safely a prior calendar day in any client timezone offset the app sends.
    const priorDay = new Date(now.getTime() - 36 * 60 * 60 * 1000);

    await seedUnassignedVisit(request, token, now.toISOString());
    await seedUnassignedVisit(request, token, now.toISOString());
    await seedUnassignedVisit(request, token, priorDay.toISOString());

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/#patients");
    await page.getByRole("tab", { name: "Attention" }).click();

    // Progress reassures over the full open set (never completion pressure): "0 of 3 cleared".
    await expect(page.locator(".attention-progress")).toContainText("3", { timeout: 30_000 });

    // Today's two unassigned visits bucket into the Confirm (S2) section.
    const confirm = page.locator(".attention-section", {
      has: page.getByRole("heading", { name: "Confirm", exact: true }),
    });
    await expect(confirm).toBeVisible();
    await expect(confirm.locator(".attention-card")).toHaveCount(2);

    // The prior-day item lands in its own "Earlier, still open" carry-over group.
    const earlier = page.locator(".attention-section", {
      has: page.getByRole("heading", { name: "Earlier, still open", exact: true }),
    });
    await expect(earlier).toBeVisible();
    await expect(earlier.locator(".attention-card")).toHaveCount(1);

    // Ordering: today's severity sections sit above the Earlier carry-over group in the DOM.
    const sections = page.locator(".attention-section");
    await expect(sections).toHaveCount(2);
    await expect(sections.first().locator(".attention-section-head")).toContainText("Confirm");
    await expect(sections.last().locator(".attention-section-head")).toContainText("Earlier");

    await context.close();
  });
});
