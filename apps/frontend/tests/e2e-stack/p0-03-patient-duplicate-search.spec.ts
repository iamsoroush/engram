import { expect, test } from "@playwright/test";
import { applyAuth, registerClinic, uniqueSuffix } from "./_stack";

// P0-3 — Patient create + duplicate guard + Persian search (Basic). Typing a name that matches an
// existing patient raises the amber duplicate guard, which warns but never blocks ("Create anyway").
// The deterministic, Persian-orthography-aware search then finds the record by a Persian query. Pure
// CRUD — no AI.
test.describe("P0-3 patient create + duplicate guard + Persian search", () => {
  test("duplicate guard warns without blocking; Persian search hits the record", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;
    // Distinct family name per run so parallel workers never collide, with a shared Persian given name.
    const family = `کریمی${uniqueSuffix()}`;
    const fullName = `سارا ${family}`;
    // Seed the first patient so the duplicate guard has something to match against.
    await request.post("/api/v1/patients", {
      headers: { Authorization: `Bearer ${token}` },
      data: { displayName: fullName },
    });

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();

    // Create a patient with the SAME name → the amber duplicate guard warns but never blocks.
    await page.goto("/#patients");
    await page.getByRole("tab", { name: "Patients" }).click();
    await page.getByRole("button", { name: "New patient" }).click();
    await page.getByPlaceholder("Patient name").fill(fullName);
    await expect(page.locator(".dup-guard")).toBeVisible();
    const save = page.locator(".patient-form-save");
    await expect(save).toHaveText("Create anyway");
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.locator(".dup-guard")).toHaveCount(0);

    // Persian-aware search finds the record, with a match-reason chip on the result.
    await page.goto("/#patients");
    await page.locator(".clinical-search input").fill("سارا");
    await expect(page.getByText("Deterministic, Persian-aware match")).toBeVisible();
    await expect(page.getByText(family).first()).toBeVisible();
    await expect(page.locator(".patient-memory-badge").first()).toBeVisible();

    await context.close();
  });
});
