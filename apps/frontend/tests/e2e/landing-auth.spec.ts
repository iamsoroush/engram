import { expect, test } from "@playwright/test";
import { useEnglish } from "./_setup";

test.describe("Landing + sign-up", () => {
  test("landing shows the marketing sections and toggles to Persian RTL", async ({ page }) => {
    await useEnglish(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "How it works" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Built for clinics you can trust" })).toBeVisible();
    await expect(page.getByText("Placeholder — pricing not final.")).toBeVisible();
    // Basic leads; Pro is the upgrade lane (honest about the AI-tier split).
    await expect(page.getByRole("heading", { name: "Basic" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Pro" })).toBeVisible();

    // The toggle's accessible name is its aria-label ("Switch language"), not the visible text.
    await page.getByRole("button", { name: "Switch language" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "چطور کار می‌کند" })).toBeVisible();
  });

  test("sign-up surfaces a distinct invalid-email error (400) vs the generic case", async ({ page }) => {
    await useEnglish(page);
    await page.route("**/api/v1/auth/register", async (route) =>
      route.fulfill({ status: 400, contentType: "application/json", json: { detail: "Enter a valid email address" } }),
    );
    await page.goto("/");
    await page.getByRole("button", { name: "Create your clinic" }).first().click();
    await page.locator('input[autocomplete="organization"]').fill("Clinic");
    await page.locator('input[autocomplete="name"]').fill("Dr. Test");
    await page.locator('input[type="email"]').fill("weird@bad");
    await page.locator('input[type="password"]').fill("longenough");
    await page.getByRole("button", { name: "Create clinic" }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  });
});
