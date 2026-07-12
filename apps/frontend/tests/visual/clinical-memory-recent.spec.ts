import { expect, test } from "@playwright/test";

const now = new Date();
const todayDateLabel = "Today";
// Clock labels are 24h everywhere now (one shared formatter, #5) — these match their capturedAt
// timestamps (16:23, 14:15), which is how real session times render.
const todaySessionTime = "16:23";
const needsInputTime = "14:15";
const previousVisitDate = new Date(now);
previousVisitDate.setDate(now.getDate() - 42);
const previousVisitDateLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(previousVisitDate);

test.beforeEach(async ({ page }) => {
  // Catch-all FIRST (lowest Playwright priority — later routes win): any unmocked /api/v1/** call
  // returns an empty 200 instead of failing into offline/self-heal states. These specs predate
  // worklist/ai-usage/preview endpoints; without this, whichever unmocked fetch loses the race
  // flips the app state and a random test in this file times out (the exact flake _setup.ts:51
  // documents for the hermetic suite). Specific routes below override per-endpoint.
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const body = /\/(inbox|members|threads|treating-doctors|worklist)/.test(url) ? { items: [], total: 0 } : {};
    await route.fulfill({ contentType: "application/json", json: body });
  });

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

  // The goto("/#patients") after login is a full reload; bootstrap restores the user via /me.
  // Without this mock the catch-all answers {} and the app falls back to the landing page —
  // the source of the one-random-test-per-run timeout this file was known for.
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
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

test("Clinical Memory Recent renders time-bucketed cards (Active visit / Today), no header search bar", async ({ page }) => {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  // Navigate via the UI, not goto("/#patients") — a full reload races the app's
  // restore-last-screen bootstrap against the URL hash and randomly lands on Active visit.
  await page.getByRole("button", { name: "Memory" }).click();

  await expect(page.getByRole("heading", { name: "Clinical Memory" })).toBeVisible();
  // The default tab is now "Recent"; the always-visible header search bar was retired (the Patients
  // tab owns a lighter roster filter, deep search is the top-bar finder).
  await expect(page.getByRole("tab", { name: "Recent" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Search patients by name, phone, or ID...")).toHaveCount(0);

  // Bucket: Active visit (the in-progress follow-up).
  await expect(page.getByRole("heading", { name: "Active visit" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Follow-up visit" }).first()).toBeVisible();
  await expect(page.getByText("Patient:").first()).toBeVisible();
  await expect(page.getByText("Soroush").first()).toBeVisible();
  await expect(page.getByText("Visit:").first()).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${todaySessionTime}`).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue visit", exact: true })).toBeVisible();

  // Bucket: Today — needs-input visits stay actionable inline (amber + focused action); a settled
  // assigned visit sits alongside them. The old "Needs your input" / "Updated today" sections are gone.
  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Needs your input" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Updated today" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Unassigned visit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Assign patient", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open visit" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Initial consultation" })).toBeVisible();
  await expect(page.getByText("Updated today · Patient assigned").first()).toBeVisible();

  await page.screenshot({ path: "test-results/clinical-memory-recent-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Follow-up visit" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue visit", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/clinical-memory-recent-mobile.png", fullPage: true });
});

test("Clinical Memory Patients renders memory-first cards with focused needs-input actions", async ({ page }) => {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  // Navigate via the UI, not goto("/#patients") — a full reload races the app's
  // restore-last-screen bootstrap against the URL hash and randomly lands on Active visit.
  await page.getByRole("button", { name: "Memory" }).click();
  await page.getByRole("tab", { name: "Patients" }).click();

  await expect(page.getByRole("heading", { name: "Soroush" })).toBeVisible();
  await expect(page.getByText(/Latest visit: Today ·/).first()).toBeVisible();
  // The card badge reads the exact needs-input reason (here, an AI-created patient to verify).
  await expect(page.getByText("Needs input: verify patient")).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify patient", exact: true })).toBeVisible();
  // The active-visit surface is no longer shown on patient cards — live work lives in the Today tab.
  await expect(page.getByText(/active (session|visit)/i)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sara" })).toBeVisible();
  await expect(page.getByText(new RegExp(`Latest visit: ${previousVisitDateLabel} ·`))).toBeVisible();
  await expect(page.getByRole("button", { name: /Open memory|View history/ })).toHaveCount(0);

  await page.screenshot({ path: "test-results/clinical-memory-patients-desktop.png", fullPage: true });
});

// The Attention tab is the backend-fed Close-the-day sweep (AES-1001) — items come from the
// /attention roll-up, not client-derived from the session list. This is the hermetic render check
// of the sweep's severity-tiered rows; the full resolver flow against a real backend is
// p0-13-attention-sweep.spec.ts.
const ATTENTION_ITEMS = [
  { id: "a-assign", kind: "assign-patient", tier: "S2", sessionId: "session-unassigned", reason: "3 captures saved. I could not confidently attach this visit to a patient.", sortTime: now.toISOString(), dayGroup: "today" },
  { id: "a-choose", kind: "resolve-conflict", tier: "S2", sessionId: "session-uncertain-match", reason: "This visit may belong to Soroush or Sara. Please choose the correct patient.", sortTime: now.toISOString(), dayGroup: "today" },
  { id: "a-verify", kind: "verify", tier: "S2", sessionId: "session-ai-verify", patientName: "Sara", reason: "AI created this patient — confirm it's correct.", sortTime: now.toISOString(), dayGroup: "today" },
];

test("Clinical Memory Attention renders the severity-tiered sweep", async ({ page }) => {
  await page.route("**/api/v1/attention**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { scope: "mine", highestTier: "S2", counts: { confirm: 0, suggested: 3, messages: 0, safety: 0, total: 3 }, items: ATTENTION_ITEMS },
    });
  });
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByRole("button", { name: "Memory" }).click();
  await page.getByRole("tab", { name: "Attention" }).click();

  await expect(page.getByText("Unassigned visit").first()).toBeVisible();
  await expect(page.getByText("This visit may belong to Soroush or Sara. Please choose the correct patient.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Assign patient", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose patient", exact: true })).toBeVisible();

  await expect(page.getByText("Patient conflict").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify patient", exact: true })).toBeVisible();
  await expect(page.getByText("Summary ready for confirmation")).toHaveCount(0);

  await page.screenshot({ path: "test-results/clinical-memory-attention-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Choose patient", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/clinical-memory-attention-mobile.png", fullPage: true });
});

test("Assign patient opens a focused resolver and updates memory state", async ({ page }) => {
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  // Navigate via the UI, not goto("/#patients") — a full reload races the app's
  // restore-last-screen bootstrap against the URL hash and randomly lands on Active visit.
  await page.getByRole("button", { name: "Memory" }).click();

  await page.getByRole("button", { name: "Assign patient", exact: true }).click();
  const resolver = page.getByRole("dialog", { name: "Assign patient" });
  await expect(resolver).toBeVisible();
  await expect(resolver.getByText("Unassigned visit")).toBeVisible();
  await expect(resolver.getByText(`Visit: ${todayDateLabel} · ${needsInputTime}`)).toBeVisible();
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
  await page.route("**/api/v1/attention**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { scope: "mine", highestTier: "S2", counts: { confirm: 0, suggested: 1, messages: 0, safety: 0, total: 1 }, items: [ATTENTION_ITEMS[1]] },
    });
  });
  await page.goto("/");
  if (!(await page.getByRole("button", { name: "Doctor", exact: true }).isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^(Log in|ورود)$/ }).first().click();
  }
  await page.getByRole("button", { name: "Doctor", exact: true }).click();
  await page.getByRole("button", { name: "Memory" }).click();
  await page.getByRole("tab", { name: "Attention" }).click();

  await page.getByRole("button", { name: "Choose patient", exact: true }).click();
  const resolver = page.getByRole("dialog", { name: "Choose patient" });
  await expect(resolver).toBeVisible();
  await expect(resolver.getByText("This visit may belong to more than one patient. Choose the correct patient.")).toBeVisible();
  await expect(resolver.getByText(`Visit: ${todayDateLabel} · ${todaySessionTime}`)).toBeVisible();
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
    time: "12:45",
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
    time: "11:30",
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
