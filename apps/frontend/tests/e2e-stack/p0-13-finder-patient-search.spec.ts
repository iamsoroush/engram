import { expect, test } from "@playwright/test";
import { applyAuth, registerClinic, uniqueSuffix } from "./_stack";

// P0-13 — Unified finder: Persian patient search (AES-1201/1204). The top-bar search affordance opens
// the app-wide finder overlay (replacing the old `/#search` local-substring screen); typing a Persian
// query hits the REAL, deterministic, Persian-orthography-aware backend search (AES-204) — so a patient
// the client never loaded is findable by name. Deterministic, gateway-less (no AI). The exact-match lot
// grain is unit-covered (features/finder/finderModel.test.ts) + rides the Pro synthesis stack, so it is
// not duplicated here (the P0 fixture pipeline yields no lot to recall).
test.describe("P0-13 unified finder — Persian patient search", () => {
  test("the top-bar finder opens an overlay and Persian search finds an unloaded patient", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    // Distinct family name per run so parallel workers never collide, with a Persian given name.
    const family = `رضایی${uniqueSuffix()}`;
    const fullName = `سارا ${family}`;
    await request.post("/api/v1/patients", {
      headers: { Authorization: `Bearer ${token}` },
      data: { displayName: fullName },
    });

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/#patients");

    // Open the finder from the top-bar search affordance (mobile-first full-screen sheet).
    await page.locator(".app-search-button").click();
    const finder = page.locator(".finder-panel");
    await expect(finder).toBeVisible();

    // Persian-aware backend search finds the record by a Persian query. The row is grouped under the
    // deterministic "Patients" head; the server's per-match reason line varies by match type (e.g.
    // "Name starts with the query."), so assert the record itself, not a specific reason string.
    await finder.locator(".finder-search input").fill("سارا");
    await expect(finder.getByText("Patients", { exact: true })).toBeVisible();
    const result = page.locator(".finder-row", { hasText: family }).first();
    await expect(result).toBeVisible();

    // Selecting the result opens the patient's file (Clinical Memory) and closes the finder.
    await result.click();
    await expect(page.locator(".finder-panel")).toHaveCount(0);
    await expect(page.getByText(family).first()).toBeVisible();

    await context.close();
  });

  test("`/#search` deep-links into the finder overlay and normalizes the hash", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();

    await page.goto("/#search");
    await expect(page.locator(".finder-panel")).toBeVisible();
    // The retired search screen normalizes to the Clinical-Memory workspace behind the overlay.
    await expect.poll(() => page.evaluate(() => window.location.hash)).toBe("#patients");

    await context.close();
  });
});
