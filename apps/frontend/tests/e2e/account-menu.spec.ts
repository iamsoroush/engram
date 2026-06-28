import { expect, test } from "@playwright/test";
import { authPayload, installAppMocks, useEnglish } from "./_setup";

async function signInPersona(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click(); // dev persona (mocked → our role)
  await page.locator(".user-menu summary").click();
}

test.describe("Account-menu role gating", () => {
  test("an owner sees Team + Plan", async ({ page }) => {
    await useEnglish(page);
    await installAppMocks(page, authPayload({ role: "owner" }));
    await signInPersona(page);
    await expect(page.getByRole("button", { name: "Team" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Plan" })).toBeVisible();
  });

  test("a doctor sees neither Team nor Plan", async ({ page }) => {
    await useEnglish(page);
    await installAppMocks(page, authPayload({ role: "doctor" }));
    await signInPersona(page);
    await expect(page.getByRole("button", { name: "Settings" })).toBeVisible(); // menu is open
    await expect(page.getByRole("button", { name: "Team" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Plan" })).toHaveCount(0);
  });

  test("a multi-clinic user sees Switch clinic", async ({ page }) => {
    await useEnglish(page);
    await installAppMocks(
      page,
      authPayload({
        role: "doctor",
        memberships: [
          { tenantId: "tenant-1", role: "doctor", tenantName: "E2E Clinic" },
          { tenantId: "tenant-2", role: "assistant", tenantName: "Second Clinic" },
        ],
      }),
    );
    await signInPersona(page);
    await expect(page.getByRole("button", { name: "Switch clinic" })).toBeVisible();
  });
});
