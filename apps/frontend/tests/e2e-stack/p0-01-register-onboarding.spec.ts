import { expect, test } from "@playwright/test";
import { pinLanguage, uniqueSuffix, expectShellReady, openAccountMenu } from "./_stack";

// P0-1 — Register → onboarding → shell (Basic). Drives the REAL self-serve sign-up form against the
// live backend (201, isolated Basic tenant + owner), then walks the first-run tour and asserts it is
// tier-accurate (Basic promises deterministic capture/organize, never the AI report), and that the app
// lands on the authed shell showing the new clinic.
test.describe("P0-1 register → onboarding → shell (Basic)", () => {
  test("a new founder self-serves a Basic clinic and gets the tier-accurate tour", async ({ page }) => {
    await pinLanguage(page, "en");
    const suffix = uniqueSuffix();
    const clinicName = `Founder Clinic ${suffix}`;
    const email = `founder-${suffix}@e2e.test`;

    await page.goto("/");
    await page.getByRole("button", { name: "Create your clinic" }).first().click();
    await page.locator('input[autocomplete="organization"]').fill(clinicName);
    await page.locator('input[autocomplete="name"]').fill("Dr. Founder");
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill("e2e-longenough-123");
    await page.getByRole("button", { name: "Create clinic" }).click();

    // First-run tour — tier-accurate Basic copy (deterministic capture/organize, NOT the AI report).
    await expect(page.getByText(/Welcome to Engram/)).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByText("Make your first capture").waitFor();
    await page.getByRole("button", { name: "I'll try later" }).click();
    await expect(page.getByText("Saved & organized")).toBeVisible();
    await expect(page.getByText("It organizes itself")).toHaveCount(0);
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Want AI on top?")).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("You're all set")).toBeVisible();

    // Finish the tour and confirm we land on the authed shell for the new clinic.
    await page.getByRole("button", { name: "Start capturing" }).click();
    await expectShellReady(page);
    await openAccountMenu(page);
    await expect(page.getByText(clinicName).first()).toBeVisible();
  });
});
