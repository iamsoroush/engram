import { test } from "@playwright/test";
import { authPayload, installAppMocks } from "../e2e/_setup";

// AES-1801/1802 screenshot capture — the two-layer safety flag (legible label + expandable evidence +
// source citation) and the event-driven strip, at a 390px phone width, in both app languages. Not a
// snapshot-assertion spec: it renders the real app against the hermetic mock harness and writes PNGs
// to test-results/ for owner review. Run against your OWN vite (PLAYWRIGHT_BASE_URL) — see the
// shared-port-trap note in playwright.config.ts.

type Lang = "fa" | "en";

// reportLanguage is fa so the clinical label + verbatim evidence render in Persian (the CONTENT axis),
// independent of the app-CHROME language under test.
function proPayload(appLanguage: Lang) {
  const base = authPayload({ role: "owner", tier: "pro", appLanguage });
  return { ...base, tenant: { ...base.tenant, appLanguage, reportLanguage: "fa" } };
}

// A settled Pro visit with a patient assigned, report content, and two detected safety flags — each
// with the normalized `label` (primary) + the verbatim clinician sentence (evidence) + a source capture.
function sessionWithFlags() {
  return {
    id: "s-safety",
    status: "complete",
    patientId: "p-1",
    patientName: "سارا نظری",
    assignmentSource: "manual",
    capturedAt: "2026-07-12T09:00:00.000Z",
    items: [{ id: "c-1", type: "audio", status: "processed", detail: "note", time: "09:00" }],
    reportModel: {
      sections: [{ id: "assessment", title: "ارزیابی", blocks: [{ type: "paragraph", text: "بیمار برای فیلر لب مراجعه کرد." }] }],
    },
    extractedMetadata: {
      safety_flags: [
        {
          kind: "allergy",
          label: "حساسیت به لیدوکائین",
          text: "بیمار گفت به لیدوکائین حساسیت داره و قبلاً واکنش پوستی داشته",
          sourceCaptureIds: ["c-1"],
        },
        {
          kind: "contraindication",
          label: "منع مصرف در بارداری",
          text: "بیمار باردار هست، فعلاً بوتاکس انجام نمی‌دیم",
          sourceCaptureIds: ["c-1"],
        },
      ],
    },
  };
}

async function installSafetyMocks(page: import("@playwright/test").Page, payload: ReturnType<typeof proPayload>) {
  await installAppMocks(page, payload);
  const session = sessionWithFlags();
  await page.route("**/api/v1/sessions**", (r) => r.fulfill({ contentType: "application/json", json: [session] }));
  await page.addInitScript((sid) => window.localStorage.setItem("engram-active-workspace", JSON.stringify({
    schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
    activeSession: { id: sid, items: [] }, selectedSessionId: sid,
    assignmentSessionId: "", pendingCaptureKind: null, updatedAt: 1,
  })), session.id);
}

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false)))
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
}

for (const lang of ["fa", "en"] as Lang[]) {
  test(`safety flags — legible label + evidence @ 390px (app=${lang})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installSafetyMocks(page, proPayload(lang));
    await login(page);

    // The strip renders; wait for the collapsed safety count chip (🩹 N) to be present.
    const chip = page.locator(".patient-strip-chip.safety");
    await chip.waitFor({ timeout: 15000 });
    await page.screenshot({ path: `test-results/safety-${lang}-1-collapsed-chip.png` });

    // Expand to the panel: the normalized labels lead as the legible primary.
    await chip.click();
    const panel = page.locator(".session-safety-panel");
    await panel.waitFor({ timeout: 10000 });
    await page.locator(".session-safety-primary").first().waitFor();
    await page.screenshot({ path: `test-results/safety-${lang}-2-panel-labels.png` });

    // Reveal the verbatim evidence beneath the first label.
    await page.locator(".session-safety-evidence-toggle").first().click();
    await page.locator(".session-safety-evidence").first().waitFor();
    await page.screenshot({ path: `test-results/safety-${lang}-3-evidence-open.png` });
  });
}
