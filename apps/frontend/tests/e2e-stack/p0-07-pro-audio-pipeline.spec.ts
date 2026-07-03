import { expect, test } from "@playwright/test";
import {
  applyAuth,
  assignSessionToNewPatient,
  FIXTURES,
  FIXTURE_AUDIO_INITIAL_TRANSCRIPT_MARKER,
  openSourcesDrawer,
  openTodaySession,
  registerProClinic,
  uploadCaptureApi,
  waitForCaptureText,
  waitForReportContains,
} from "./_stack";

// P0-7 — Pro fixture-audio pipeline (gateway-less). The fixture audio/photo are seeded through the real
// /captures API (the browser re-encodes audio and drops the fixture filename the AI engine keys on, so
// audio fixtures must go through the API — the backend + Celery transcription/caption jobs still run for
// real). The UI then shows the resolved transcript + caption in the Sources drawer, the report picks up
// the transcript, and a staff edit flips attribution from AI ✨ to "Edited by …". No LLM gateway.
test.describe("P0-7 Pro fixture-audio pipeline", () => {
  test("processing resolves to fixture transcript + caption, editable with AI-vs-edited attribution", async ({
    browser,
    request,
  }) => {
    const clinic = await registerProClinic(request, { lang: "en" });
    const token = clinic.auth.accessToken;

    const up = await uploadCaptureApi(request, token, { type: "audio", fixtureFile: FIXTURES.audioInitial, newSession: true });
    const sessionId = up.session.id;
    await waitForReportContains(request, token, sessionId, FIXTURE_AUDIO_INITIAL_TRANSCRIPT_MARKER, 30_000);
    await uploadCaptureApi(request, token, { type: "photo", fixtureFile: FIXTURES.photoPre, sessionId });
    await waitForCaptureText(request, token, sessionId, "Pre-correction image", 30_000);
    await assignSessionToNewPatient(request, token, sessionId, "Sara Nazari");

    const context = await browser.newContext();
    await applyAuth(context, clinic.auth, { lang: "en" });
    const page = await context.newPage();
    await openTodaySession(page);

    // The deterministic report carries the transcript content (synthesis disabled → baseline stands).
    await expect(page.getByTestId("report-body")).toContainText(FIXTURE_AUDIO_INITIAL_TRANSCRIPT_MARKER);

    await openSourcesDrawer(page);
    const audioCard = page.locator(".live-draft-capture.audio");
    const photoCard = page.locator(".live-draft-capture.photo");

    // Transcript == fixture text, with AI attribution while it is the machine transcript.
    await expect(audioCard).toContainText(FIXTURE_AUDIO_INITIAL_TRANSCRIPT_MARKER);
    await expect(audioCard.locator(".capture-ai-tag")).toBeVisible();
    // Fixture caption resolved (no gateway).
    await expect(photoCard).toContainText("Pre-correction image");

    // Transcript is editable; a staff edit flips attribution from AI ✨ to "Edited by …".
    const edited = "Follow-up cheek filler — reviewed and corrected by the clinician.";
    await audioCard.locator(".live-draft-preview-edit").first().click();
    await audioCard.locator(".capture-generated-editor textarea").fill(edited);
    await audioCard.locator(".capture-generated-save").click();
    await expect(audioCard).toContainText(edited);
    await expect(audioCard.getByText(/Edited by/)).toBeVisible();
    await expect(audioCard.locator(".capture-ai-tag")).toHaveCount(0);

    await context.close();
  });
});
