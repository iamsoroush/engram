import { expect, test } from "@playwright/test";

const now = new Date();
const todayDateLabel = "Today";
const todaySessionTime = "4:23 PM";
const needsInputTime = "2:15 PM";
const previousVisitDate = new Date(now);
previousVisitDate.setDate(now.getDate() - 42);

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
          name: "AesMem Visual Clinic",
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
      ],
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
  await expect(page.getByRole("heading", { name: "Follow-up visit" })).toBeVisible();
  await expect(page.getByText("Patient:").first()).toBeVisible();
  await expect(page.getByText("Soroush")).toBeVisible();
  await expect(page.getByText("Session:").first()).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${todaySessionTime}`)).toBeVisible();
  await expect(page.getByText(/Updated:/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Continue visit/ })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Needs your input" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Unassigned visit" })).toBeVisible();
  await expect(page.getByText(`${todayDateLabel} · ${needsInputTime}`)).toBeVisible();
  await expect(page.getByText(/Needs input since:/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Assign patient/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open visit" }).first()).toBeVisible();

  await expect(page.getByRole("heading", { name: "Updated today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Initial consultation" })).toBeVisible();
  await expect(page.getByText("Updated today · Patient assigned").first()).toBeVisible();

  await page.screenshot({ path: "test-results/clinical-memory-today-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Follow-up visit" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Continue visit/ })).toBeVisible();
  await page.screenshot({ path: "test-results/clinical-memory-today-mobile.png", fullPage: true });
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
