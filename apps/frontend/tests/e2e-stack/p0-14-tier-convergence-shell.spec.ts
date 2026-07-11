import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  expectShellReady,
  FIXTURES,
  openTodaySession,
  registerClinic,
  registerProClinic,
  uniqueSuffix,
  uploadCaptureApi,
  waitForReportContains,
} from "./_stack";

// P0-14 — Tier convergence (AES-1401..1406). Both tiers render a session with ONE tabless skeleton
// (patient strip → primary working surface → secondary collapsible view → capture bar); only what
// sits in "primary" differs. This is the upgrade-continuity gate (AES-1405): Basic → Pro must change
// only what the AI adds — the interaction model (no tabs, a strip, a secondary drawer, the capture
// bar) is invariant; the primary flips feed → report and the raw feed slides into the Sources drawer.
test.describe("P0-14 tier-convergence shell", () => {
  test("Basic: feed is primary, no tab switch, secondary is the 'View as document' panel", async ({ browser, request }) => {
    const clinic = await registerClinic(request, { lang: "en" });
    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await page.goto("/");
    await expectShellReady(page);

    // Capture a note into the active visit (feed-first surface, Basic).
    const noteText = `Convergence note ${uniqueSuffix()}`;
    await page.locator(".capture-pills-actions .capture-action-button", { hasText: "Note" }).click();
    await page.getByPlaceholder(/Type the note now/).fill(noteText);
    await page.getByRole("button", { name: "Save to visit" }).click();

    // --- Shared skeleton: the patient strip + the capture bar (converged with Pro) ---
    await expect(page.locator(".patient-strip")).toBeVisible();
    await expect(page.locator(".capture-pills-actions")).toBeVisible();

    // --- No legacy Captures/Live-report tab switch on either tier (AES-1401) ---
    await expect(page.locator(".report-view-switch")).toHaveCount(0);

    // --- PRIMARY = the captures FEED itself (AES-1402): the note is directly reachable, not behind a
    //     drawer, and it is NOT rendered inside the collapsed document panel yet.
    const note = page.locator(".basic-note-text", { hasText: noteText });
    await expect(note).toBeVisible();
    await expect(page.locator(".document-panel")).toHaveCount(0);
    // Pro's Sources drawer is absent on Basic (the feed IS the surface, not a demoted drawer).
    await expect(page.locator(".sources-drawer")).toHaveCount(0);
    // Exactly one consolidated "Do more with Pro" teaser, at the foot of the feed (E8 / AES-1406).
    await expect(page.locator(".capture-feed-teaser")).toHaveCount(1);

    // --- SECONDARY = the opt-in "View as document" panel (AES-1403). Tapping the header affordance
    //     reveals the tidy chronological notebook; the same note reformats into the document body.
    const docButton = page.locator(".report-doc-button");
    await expect(docButton).toBeVisible();
    await expect(docButton).toContainText("View as document");
    await docButton.click();
    const docPanel = page.locator(".document-panel");
    await expect(docPanel).toBeVisible();
    await expect(docPanel.getByTestId("report-body")).toContainText(noteText);
    // One Try-Pro per screen: the document's own teaser is suppressed (the feed teaser is the one).
    await expect(docPanel.locator(".report-teaser")).toHaveCount(0);

    // Zero-AI: no AI spark / synthesis chrome anywhere (AES-1404 — omitted, not disabled).
    await expect(page.locator(".report-ai-mark")).toHaveCount(0);

    await context.close();
  });

  test("Pro: report is primary, no tab switch, secondary is the Sources drawer", async ({ browser, request }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForReportContains(request, token, sessionId, "Sara Nazari", 30_000);
    await assignSessionToNewPatient(request, token, sessionId, "Sara Nazari");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await openTodaySession(page); // waits for the report body (the Pro primary)

    // --- Shared skeleton: identical to Basic (patient strip + capture bar), no tab switch ---
    await expect(page.locator(".patient-strip")).toBeVisible();
    await expect(page.locator(".capture-pills-actions")).toBeVisible();
    await expect(page.locator(".report-view-switch")).toHaveCount(0);

    // --- PRIMARY = the synthesized report (the AI artifact) ---
    await expect(page.getByTestId("report-body")).toContainText("Sara Nazari");

    // --- SECONDARY = the Sources drawer (raw captures demoted). Basic's "View as document" affordance
    //     is absent on Pro — the flip is honest: feed → Sources, document → report.
    await expect(page.locator(".sources-drawer")).toBeVisible();
    await expect(page.locator(".report-doc-button")).toHaveCount(0);

    await context.close();
  });
});
