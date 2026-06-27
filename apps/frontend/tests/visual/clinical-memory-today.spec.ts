import { expect, test } from "@playwright/test";

const now = new Date();
const todayDateLabel = "Today";
const todaySessionTime = "4:23 PM";
const needsInputTime = "2:15 PM";
const previousVisitDate = new Date(now);
previousVisitDate.setDate(now.getDate() - 42);
const previousVisitDateLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(previousVisitDate);

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/dev-login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        accessToken: "visual-access-token",
        refreshToken: "visual-refresh-token",
        user: {
          id: "doctor-visual",
          email: "doctor@example.test",
          displayName: "Doctor Demo",
          persona: "doctor",
        },
        tenant: {
          id: "tenant-visual",
          name: "Engram Visual Clinic",
        },
        memberships: [{ tenantId: "tenant-visual", role: "doctor" }],
      },
    });
  });

  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        accessToken: "visual-access-token-refreshed",
        refreshToken: "visual-refresh-token-refreshed",
      },
    });
  });

  await page.route("**/api/v1/sessions", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: [
        followUpVisit(),
        unassignedVisit(),
        uncertainMatchVisit(),
        aiVerifyVisit(),
        technicalFailureVisit(),
        updatedInitialConsultation(),
      ],
    });
  });

  await page.route("**/api/v1/patients?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: [
        { id: "patient-soroush", displayName: "Soroush", lastVisit: now.toISOString() },
        { id: "patient-sara", displayName: "Sara", lastVisit: previousVisitDate.toISOString() },
        { id: "patient-0", displayName: "Patient 0", lastVisit: previousVisitDate.toISOString() },
      ],
    });
  });

  await page.route("**/api/v1/sessions/session-unassigned/assign-patient", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        ...unassignedVisit(),
        patientId: "patient-soroush",
        patientName: "Soroush",
        assignmentSource: "staff",
        status: "organized",
        updatedAt: now.toISOString(),
      },
    });
  });

  await page.route("**/api/v1/sessions/session-uncertain-match/assign-patient", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        ...uncertainMatchVisit(),
        patientId: "patient-soroush",
        patientName: "Soroush",
        assignmentSource: "staff",
        status: "organized",
        reviewReason: "",
        updatedAt: now.toISOString(),
      },
    });
  });

  await page.route("**/api/v1/sessions/session-review-summary*", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        ...aiVerifyVisit(),
        status: "verified",
        reviewReason: "",
        extractedMetadata: { ai_patient_action: { needsVerification: false, status: "verified" } },
        updatedAt: now.toISOString(),
      },
    });
  });

  await page.route("**/api/v1/patient-memory?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [],
        limit: 50,
        offset: 0,
        total: 0,
      },
    });
  });
});

test("Clinical Memory Today renders session-first cards on desktop and mobile", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Doctor" }).click();
  await page.goto("/#patients");

  await expect(page.getByRole("heading", { name: "Clinical Memory" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Active session" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Follow-up visit" }).first()).toBeVisible();
  await expect(page.getByText("Patient:").first()).toBeVisible();
  await expect(page.getByText("Soroush").first()).toBeVisible();
  await expect(page.getByText("Session:").first()).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${todaySessionTime}`).first()).toBeVisible();
  await expect(page.getByText(/Updated:/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue visit", exact: true })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Needs your input" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Unassigned visit" })).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${needsInputTime}`)).toBeVisible();
  await expect(page.getByText(/Needs input since:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Assign patient", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open visit" })).toHaveCount(0);

  await expect(page.getByRole("heading", { name: "Updated today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Initial consultation" })).toBeVisible();
  await expect(page.getByText("Updated today · Patient assigned").first()).toBeVisible();

  await page.screenshot({ path: "test-results/clinical-memory-today-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Follow-up visit" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue visit", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/clinical-memory-today-mobile.png", fullPage: true });
});

test("Clinical Memory Patients renders memory-first cards with focused needs-input actions", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Doctor" }).click();
  await page.goto("/#patients");
  await page.getByRole("tab", { name: "Patients" }).click();

  await expect(page.getByRole("heading", { name: "Soroush" })).toBeVisible();
  await expect(page.getByText(/Latest visit: Today ·/).first()).toBeVisible();
  // The card badge reads the exact needs-input reason (here, an AI-created patient to verify).
  await expect(page.getByText("Needs input: verify patient")).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify patient", exact: true })).toBeVisible();
  // "Active session" is no longer shown on patient cards — live work lives in the Today tab.
  await expect(page.getByText(/active session/i)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sara" })).toBeVisible();
  await expect(page.getByText(new RegExp(`Latest visit: ${previousVisitDateLabel} ·`))).toBeVisible();
  await expect(page.getByRole("button", { name: /Open memory|View history/ })).toHaveCount(0);

  await page.screenshot({ path: "test-results/clinical-memory-patients-desktop.png", fullPage: true });
});

test("Clinical Memory Needs input renders a decision-first inbox", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Doctor" }).click();
  await page.goto("/#patients");
  await page.getByRole("tab", { name: "Needs input" }).click();

  await expect(page.getByText("A few things need your judgment to keep memory accurate and useful.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Unassigned visit" })).toBeVisible();
  await expect(page.getByText("Session:").first()).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${needsInputTime}`)).toBeVisible();
  await expect(page.getByText("Needs input since:").first()).toBeVisible();
  await expect(page.getByText("2 photos")).toBeVisible();
  await expect(page.getByText("1 audio").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Assign patient", exact: true })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Patient match uncertain" })).toBeVisible();
  await expect(page.getByText("This visit may belong to Soroush or Sara. Please choose the correct patient.")).toBeVisible();
  await expect(page.getByText("Needs input since:").nth(1)).toBeVisible();
  await expect(page.getByText("Soroush").first()).toBeVisible();
  await expect(page.getByText("Sara").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose patient", exact: true })).toBeVisible();

  // Routine summary confirmation is no longer a needs-input item; an AI-created patient awaiting
  // verification is. Its focused action opens the visit (where the verify panel lives).
  await expect(page.getByRole("heading", { name: "Verify AI-created patient" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify patient", exact: true })).toBeVisible();
  await expect(page.getByText("Summary ready for confirmation")).toHaveCount(0);
  await expect(page.getByText("AI failed")).toHaveCount(0);
  await expect(page.getByText(/retry transcription/i)).toHaveCount(0);

  await page.screenshot({ path: "test-results/clinical-memory-needs-input-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Patient match uncertain" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose patient", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/clinical-memory-needs-input-mobile.png", fullPage: true });
});

test("Assign patient opens a focused resolver and updates memory state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Doctor" }).click();
  await page.goto("/#patients");

  await page.getByRole("button", { name: "Assign patient", exact: true }).click();
  const resolver = page.getByRole("dialog", { name: "Assign patient" });
  await expect(resolver).toBeVisible();
  await expect(resolver.getByText("Unassigned visit")).toBeVisible();
  await expect(resolver.getByText(`Session: ${todayDateLabel} · ${needsInputTime}`)).toBeVisible();
  await expect(resolver.getByText("Captures: 2 photos, 1 audio")).toBeVisible();
  await expect(resolver.getByPlaceholder("Search patient")).toBeVisible();
  await expect(resolver.getByText("Soroush")).toBeVisible();
  await expect(resolver.getByText("Sara")).toBeVisible();
  await expect(resolver.getByText("Patient 0")).toBeVisible();

  await resolver.getByRole("button", { name: /Soroush/ }).first().click();
  await expect(resolver.getByRole("button", { name: "Assign to Soroush" })).toBeEnabled();
  await resolver.getByRole("button", { name: "Assign to Soroush" }).click();

  await expect(resolver).toHaveCount(0);
  await expect(page.getByText("Visit assigned to Soroush.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Unassigned visit" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Initial consultation" })).toBeVisible();
});

test("Choose patient resolves an uncertain patient match without opening the visit", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Doctor" }).click();
  await page.goto("/#patients");
  await page.getByRole("tab", { name: "Needs input" }).click();

  await page.getByRole("button", { name: "Choose patient", exact: true }).click();
  const resolver = page.getByRole("dialog", { name: "Choose patient" });
  await expect(resolver).toBeVisible();
  await expect(resolver.getByText("This visit may belong to more than one patient. Choose the correct patient.")).toBeVisible();
  await expect(resolver.getByText(`Session: ${todayDateLabel} · ${todaySessionTime}`)).toBeVisible();
  await expect(resolver.getByText("Captures: 1 note")).toBeVisible();
  await expect(resolver.getByRole("button", { name: /Soroush/ })).toBeVisible();
  await expect(resolver.getByRole("button", { name: /Sara/ })).toBeVisible();
  await expect(resolver.getByPlaceholder("Search another patient")).toBeVisible();
  await expect(resolver.getByRole("button", { name: "Create new patient" })).toBeDisabled();
  await expect(resolver.getByRole("button", { name: "Keep unassigned" })).toBeVisible();

  await resolver.getByRole("button", { name: /Sara/ }).click();
  await expect(resolver.getByRole("button", { name: "Confirm patient" })).toBeEnabled();
  await resolver.getByPlaceholder("Search another patient").fill("Patient 0");
  await expect(resolver.getByRole("button", { name: /Patient 0/ })).toBeVisible();
  await resolver.getByPlaceholder("Search another patient").fill("New Patient");
  await expect(resolver.getByRole("button", { name: "Create new patient" })).toBeEnabled();

  await resolver.getByRole("button", { name: /Soroush/ }).first().click();
  await resolver.getByRole("button", { name: "Confirm patient" }).click();

  await expect(resolver).toHaveCount(0);
  await expect(page.getByText("Patient confirmed")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Patient match uncertain" })).toHaveCount(0);
  await expect(page).toHaveURL(/#patients$/);
});

function followUpVisit() {
  return {
    id: "session-follow-up",
    label: "Follow-up visit",
    time: todaySessionTime,
    dateLabel: todayDateLabel,
    createdAt: withTodayTime(16, 23),
    capturedAt: withTodayTime(16, 23),
    updatedAt: withTodayTime(16, 31),
    duration: "8 min",
    summary: "Follow-up visit captures are saved.",
    status: "reopened",
    patientId: "patient-soroush",
    patientName: "Soroush",
    assignmentSource: "staff",
    items: [
      capture("capture-photo-1", "photo", "Photo 1", 16, 24),
      capture("capture-photo-2", "photo", "Photo 2", 16, 25),
      capture("capture-photo-3", "photo", "Photo 3", 16, 26),
      capture("capture-audio-1", "audio", "Audio note", 16, 27),
      capture("capture-note-1", "note", "Written note", 16, 28),
    ],
  };
}

function uncertainMatchVisit() {
  return {
    id: "session-uncertain-match",
    label: "Possible patient match",
    time: todaySessionTime,
    dateLabel: todayDateLabel,
    createdAt: withTodayTime(16, 23),
    capturedAt: withTodayTime(16, 23),
    updatedAt: withTodayTime(16, 29),
    duration: "6 min",
    summary: "Possible patient match needs confirmation.",
    status: "needs_review",
    reviewReason: "Patient match uncertain",
    extractedMetadata: {
      patient_match: {
        status: "possible_match",
        candidates: [{ display_name: "Soroush" }, { display_name: "Sara" }],
      },
    },
    items: [
      capture("capture-match-note-1", "note", "Written note", 16, 24),
    ],
  };
}

function aiVerifyVisit() {
  // An AI-created patient awaiting staff verification: assigned (so the visit is processed) but the
  // patient identity is unconfirmed → the `verify` needs-input category.
  return {
    id: "session-review-summary",
    label: "Follow-up visit",
    time: todaySessionTime,
    dateLabel: todayDateLabel,
    createdAt: withTodayTime(16, 23),
    capturedAt: withTodayTime(16, 23),
    updatedAt: withTodayTime(16, 32),
    duration: "9 min",
    summary: "Follow-up visit focused on headache patterns, sleep quality, and next steps. Photos and an audio note were captured.",
    status: "needs_review",
    reviewReason: "Verify AI-created patient",
    patientId: "patient-soroush",
    patientName: "Soroush",
    assignmentSource: "ai_created",
    extractedMetadata: {
      ai_patient_action: { needsVerification: true, status: "needs_verification" },
    },
    items: [
      capture("capture-review-photo-1", "photo", "Photo 1", 16, 24),
      capture("capture-review-photo-2", "photo", "Photo 2", 16, 25),
      capture("capture-review-photo-3", "photo", "Photo 3", 16, 26),
      capture("capture-review-audio-1", "audio", "Audio note", 16, 27),
      capture("capture-review-note-1", "note", "Written note", 16, 28),
    ],
  };
}

function technicalFailureVisit() {
  return {
    id: "session-technical-failure",
    label: "AI failed",
    time: "12:45 PM",
    dateLabel: todayDateLabel,
    createdAt: withTodayTime(12, 45),
    capturedAt: withTodayTime(12, 45),
    updatedAt: withTodayTime(12, 51),
    duration: "4 min",
    summary: "AI failed and should not appear in Needs input.",
    status: "needs_review",
    reviewReason: "AI failed retry transcription",
    items: [
      capture("capture-failed-audio-1", "audio", "Audio note", 12, 46),
    ],
  };
}

function unassignedVisit() {
  return {
    id: "session-unassigned",
    label: "Unassigned visit",
    time: needsInputTime,
    dateLabel: todayDateLabel,
    createdAt: withTodayTime(14, 15),
    capturedAt: withTodayTime(14, 15),
    updatedAt: withTodayTime(14, 20),
    duration: "5 min",
    summary: "Unassigned captures are saved.",
    status: "unassigned",
    items: [
      capture("capture-unassigned-photo-1", "photo", "Photo 1", 14, 16),
      capture("capture-unassigned-photo-2", "photo", "Photo 2", 14, 17),
      capture("capture-unassigned-audio-1", "audio", "Audio note", 14, 18),
    ],
  };
}

function updatedInitialConsultation() {
  return {
    id: "session-initial-consultation",
    label: "Initial consultation",
    time: "11:30 AM",
    dateLabel: "Apr 18",
    createdAt: previousVisitDate.toISOString(),
    capturedAt: previousVisitDate.toISOString(),
    updatedAt: withTodayTime(11, 44),
    duration: "18 min",
    summary: "Initial consultation was updated today.",
    status: "organized",
    patientId: "patient-sara",
    patientName: "Sara",
    assignmentSource: "staff",
    items: [
      capture("capture-sara-photo-1", "photo", "Photo 1", 11, 35),
      capture("capture-sara-photo-2", "photo", "Photo 2", 11, 36),
      capture("capture-sara-note-1", "note", "Written note", 11, 37),
    ],
  };
}

function capture(id: string, type: "audio" | "photo" | "note", title: string, hour: number, minute: number) {
  return {
    id,
    type,
    title,
    detail: `${title} detail`,
    time: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
    sourceName: "Visual test",
    status: "uploaded",
    capturedAt: withTodayTime(hour, minute),
  };
}

function withTodayTime(hour: number, minute: number) {
  const date = new Date(now);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
}
