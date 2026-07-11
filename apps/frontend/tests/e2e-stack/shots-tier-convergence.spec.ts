import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  expectShellReady,
  FIXTURES,
  fixturePath,
  registerClinic,
  registerProClinic,
  uniqueSuffix,
  uploadCaptureApi,
  waitForReportContains,
} from "./_stack";

// Screenshot harness for the tier-convergence epic (NOT a gate — run explicitly by filename). Captures
// the Basic feed-first surface + "View as document" panel and the Pro report-first surface + Sources
// drawer, in both languages at 390 and 768. Output → SHOTS_DIR. Uses language-agnostic (index/class)
// selectors so the same flow drives fa without Persian string coupling.
const SHOTS_DIR = process.env.SHOTS_DIR || "/tmp/tc-shots";
const WIDTHS = [390, 768] as const;
const LANGS = ["en", "fa"] as const;

async function shot(page: import("@playwright/test").Page, name: string) {
  await page.screenshot({ path: `${SHOTS_DIR}/${name}.png`, fullPage: true });
}

// Language-agnostic "open the seeded Today visit" (the shared openTodaySession clicks the English
// "Today" tab, which doesn't exist under fa). Today is always the first tab in the memory tablist.
async function openTodayAny(page: import("@playwright/test").Page) {
  await page.goto("/#patients");
  await page.locator('.clinical-tabs [role="tab"]').first().click();
  await page.locator(".clinical-memory .visit-card, .clinical-memory .clinical-row-selectable").first().click();
  await expect(page.getByTestId("report-body")).toBeVisible({ timeout: 30_000 });
}

// Drive the Pro Sources drawer to an explicit open/closed state (it persists across viewport changes).
async function setSourcesDrawer(page: import("@playwright/test").Page, open: boolean) {
  const summary = page.locator(".sources-drawer-summary").first();
  const expanded = (await summary.getAttribute("aria-expanded")) === "true";
  if (expanded !== open) await summary.click();
}

test.describe("tier-convergence screenshots", () => {
  for (const lang of LANGS) {
    test(`Basic feed-first + View-as-document (${lang})`, async ({ browser, request }) => {
      const clinic = await registerClinic(request, { lang });
      const context = await browser.newContext();
      await applyAuth(context, clinic.auth, { lang });
      const page = await context.newPage();
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/");
      await expectShellReady(page);

      // Seed the feed: a note + a photo (index-based buttons: Basic order = Note, Photo, Audio).
      const noteText = `${lang === "fa" ? "درمان بوتاکس پیشانی" : "Botox to the forehead, 20 units"} ${uniqueSuffix()}`;
      await page.locator(".capture-pills-actions .capture-action-button").nth(0).click();
      await page.locator(".sheet-stack textarea").fill(noteText);
      await page.locator("button.note-primary").click();
      await expect(page.locator(".basic-note-text", { hasText: noteText })).toBeVisible();

      await page.locator(".capture-pills-actions .capture-action-button").nth(1).click();
      await page.locator("input.visually-hidden-file").last().setInputFiles(fixturePath(FIXTURES.photoPre));
      await page.locator("button.add-photo-primary").click();
      await expect(page.locator(".live-draft-photo-basic img").first()).toBeVisible();

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
        await page.waitForTimeout(250);
        await shot(page, `basic-${lang}-${width}-feed`);
        // Open the secondary "View as document" panel and capture it.
        await page.locator(".report-doc-button").click();
        await expect(page.locator(".document-panel")).toBeVisible();
        await shot(page, `basic-${lang}-${width}-document`);
        await page.locator(".document-panel-close").click();
      }

      await context.close();
    });

    test(`Pro report-first + Sources drawer (${lang})`, async ({ browser, request }) => {
      const clinic = await registerProClinic(request, { lang });
      const token = clinic.auth.accessToken;
      const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
      const sessionId = up.session.id;
      await waitForReportContains(request, token, sessionId, "Sara Nazari", 30_000);
      await assignSessionToNewPatient(request, token, sessionId, "Sara Nazari");

      const context = await browser.newContext();
      await applyAuth(context, clinic.auth, { lang });
      const page = await context.newPage();
      await page.setViewportSize({ width: 390, height: 844 });
      await openTodayAny(page);

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
        await page.waitForTimeout(250);
        // Report primary, Sources collapsed (the demoted raw captures live behind the drawer).
        await setSourcesDrawer(page, false);
        await shot(page, `pro-${lang}-${width}-report`);
        // Reveal the Sources drawer (raw captures) for a second frame.
        await setSourcesDrawer(page, true);
        await expect(page.locator(".live-draft-capture").first()).toBeVisible();
        await shot(page, `pro-${lang}-${width}-sources`);
      }

      await context.close();
    });
  }
});
