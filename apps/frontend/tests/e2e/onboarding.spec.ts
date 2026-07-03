import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

test.describe("First-run onboarding", () => {
  test("a new Basic founder gets the tier-accurate tour (no AI claims)", async ({ page }) => {
    await useEnglish(page);
    await installAppMocks(page, authPayload({ tier: "basic", role: "owner", userId: "founder-1" }));
    await page.goto("/");
    await page.getByRole("button", { name: "Create your clinic" }).first().click();
    await page.locator('input[autocomplete="organization"]').fill("New Clinic");
    await page.locator('input[autocomplete="name"]').fill("Dr. New");
    await page.locator('input[type="email"]').fill("new@e2e.test");
    await page.locator('input[type="password"]').fill("longenough");
    await page.getByRole("button", { name: "Create clinic" }).click();

    await expect(page.getByText(/Welcome to Engram/)).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByText("Make your first capture").waitFor();
    await page.getByRole("button", { name: "I'll try later" }).click();
    // Basic = deterministic capture/organize — must NOT promise the AI report.
    await expect(page.getByText("Saved & organized")).toBeVisible();
    await expect(page.getByText("It organizes itself")).toHaveCount(0);
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Want AI on top?")).toBeVisible();
  });

  test("onboarding is suppressed on an ordinary login", async ({ page }) => {
    await useEnglish(page);
    await installAppMocks(page, authPayload({ role: "owner" }));
    await page.goto("/");
    await page.getByRole("button", { name: "Log in" }).click();
    await page.locator('input[type="email"]').fill("owner@e2e.test");
    await page.locator('input[type="password"]').fill("longenough");
    await page.getByRole("button", { name: "Sign in" }).click();
    // The app shell loads; no first-run overlay for a returning user.
    await expect(page.getByRole("button", { name: /New visit/ })).toBeVisible();
    await expect(page.getByText(/Welcome to Engram/)).toHaveCount(0);
  });
});
