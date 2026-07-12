import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";
import type { APIRequestContext, Browser, BrowserContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";

// Real-stack e2e helpers: the frontend AND the backend/Celery/MinIO all run for real (compose stack),
// nothing is mocked. These helpers hit the backend through the app's own origin (the Vite dev-server
// proxies `/api/v1` → backend), so a single PLAYWRIGHT_BASE_URL drives both the browser and the API
// setup calls. The determinism seams (gateway-less fixtures, zero-AI Basic tier, dev auth) are enforced
// by docker-compose.e2e.yml. See docs/frontend/README.md "Testing".

const DEV_AUTH_STORAGE_KEY = "engram-dev-auth"; // mirrors src/shared/lib/config.ts
const UI_LANG_STORAGE_KEY = "engram-ui-lang"; // mirrors src/shared/i18n language persistence

export type Persona = "doctor" | "assistant" | "admin" | "patient-preview" | "therapist-b";
export type Tier = "basic" | "pro" | "therapy";
export type Lang = "en" | "fa";

/** Minimal shape of the backend AuthResponse (accessToken + profile). */
export type AuthResponse = {
  accessToken: string;
  refreshToken: string;
  user: Record<string, unknown>;
  tenant: Record<string, unknown> & { id: string; tier: string; appLanguage?: string };
  memberships: unknown[];
};

/** A registered clinic + the credentials to log back in through the UI if needed. */
export type Clinic = {
  auth: AuthResponse;
  email: string;
  password: string;
};

/** Run-unique token so parallel workers never collide on emails / patient names. */
export function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

async function readJson(res: import("@playwright/test").APIResponse, ctx: string): Promise<any> {
  if (!res.ok()) {
    throw new Error(`${ctx} failed: ${res.status()} ${res.statusText()} — ${await res.text()}`);
  }
  return res.json();
}

/**
 * Register a fresh, isolated Basic clinic + owner via the real `/auth/register` (no email
 * verification). `lang` sets the tenant appLanguage so the authed app chrome renders en or fa.
 */
export async function registerClinic(
  request: APIRequestContext,
  opts: { lang?: Lang; clinicName?: string; fullName?: string } = {},
): Promise<Clinic> {
  const suffix = uniqueSuffix();
  const email = `e2e-${suffix}@e2e.test`;
  const password = "e2e-longenough-123";
  const auth = (await readJson(
    await request.post("/api/v1/auth/register", {
      data: {
        clinicName: opts.clinicName ?? `E2E ${suffix}`,
        fullName: opts.fullName ?? "Dr. E2E",
        email,
        password,
        appLanguage: opts.lang ?? "en",
      },
    }),
    "register",
  )) as AuthResponse;
  return { auth, email, password };
}

/** Flip a clinic to Pro via the owner/admin plan endpoint (PATCH /clinic/plan). */
export async function setPlan(request: APIRequestContext, accessToken: string, tier: "basic" | "pro"): Promise<void> {
  await readJson(
    await request.patch("/api/v1/clinic/plan", {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { tier },
    }),
    `set plan ${tier}`,
  );
}

/** Register a fresh clinic already upgraded to Pro. */
export async function registerProClinic(request: APIRequestContext, opts: { lang?: Lang } = {}): Promise<Clinic> {
  const clinic = await registerClinic(request, opts);
  await setPlan(request, clinic.auth.accessToken, "pro");
  // Refresh the stored tenant so applyAuth seeds tier: "pro".
  (clinic.auth.tenant as Record<string, unknown>).tier = "pro";
  return clinic;
}

/** Owner/admin adds a clinic member with a temporary password. Returns the created member (incl. id). */
export async function addTeamMember(
  request: APIRequestContext,
  ownerToken: string,
  opts: { fullName: string; email: string; password: string; role: "doctor" | "assistant" | "admin" },
): Promise<{ id?: string; userId?: string } & Record<string, unknown>> {
  return readJson(
    await request.post("/api/v1/clinic/team", { headers: { Authorization: `Bearer ${ownerToken}` }, data: opts }),
    `add ${opts.role}`,
  );
}

/** Log in with email + password (existing member). */
export async function loginPassword(request: APIRequestContext, email: string, password: string): Promise<AuthResponse> {
  return (await readJson(await request.post("/api/v1/auth/login", { data: { email, password } }), "login")) as AuthResponse;
}

/** Dev-login a demo persona (shared demo tenants; gated on BACKEND_AUTH_MODE=dev). */
export async function devLogin(
  request: APIRequestContext,
  opts: { persona: Persona; tier: Tier },
): Promise<AuthResponse> {
  return (await readJson(
    await request.post("/api/v1/auth/dev-login", { data: { persona: opts.persona, tier: opts.tier } }),
    `dev-login ${opts.persona}/${opts.tier}`,
  )) as AuthResponse;
}

/**
 * Seed a browser context with a persisted auth profile so the app boots straight into the authed shell
 * (App bootstrap reads localStorage `engram-dev-auth` and re-issues an access token via /auth/refresh).
 * Must be called BEFORE the first navigation. Also pins the pre-auth UI language for stable chrome.
 */
export async function applyAuth(target: Page | BrowserContext, auth: AuthResponse, opts: { lang?: Lang } = {}): Promise<void> {
  const lang = opts.lang ?? (auth.tenant.appLanguage as Lang | undefined) ?? "en";
  const profile = JSON.stringify({
    refreshToken: auth.refreshToken,
    user: auth.user,
    tenant: auth.tenant,
    memberships: auth.memberships,
  });
  await target.addInitScript(
    ([key, value, langKey, langValue]) => {
      window.localStorage.setItem(key, value);
      window.localStorage.setItem(langKey, langValue);
    },
    [DEV_AUTH_STORAGE_KEY, profile, UI_LANG_STORAGE_KEY, lang] as const,
  );
}

/** Force the public/unauth surfaces to a language (they default to fa) for stable selectors. */
export async function pinLanguage(target: Page | BrowserContext, lang: Lang): Promise<void> {
  await target.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [UI_LANG_STORAGE_KEY, lang] as const,
  );
}

/**
 * Open an authed browser context for a fresh clinic (Basic or Pro), seeded so the app boots signed in.
 * Returns the context/page plus the clinic (auth token usable for `request`-based API setup).
 */
export async function openClinicContext(
  browser: Browser,
  request: APIRequestContext,
  opts: { tier?: "basic" | "pro"; lang?: Lang } = {},
): Promise<{ context: BrowserContext; page: Page; clinic: Clinic }> {
  const lang = opts.lang ?? "en";
  const clinic = opts.tier === "pro" ? await registerProClinic(request, { lang }) : await registerClinic(request, { lang });
  const context = await browser.newContext();
  await applyAuth(context, clinic.auth, { lang });
  const page = await context.newPage();
  return { context, page, clinic };
}

/** Wait for the authed staff shell to be interactive (capture bar present). */
export async function expectShellReady(page: Page): Promise<void> {
  await expect(page.locator('[data-onboarding="capture-bar"], .capture-pills-actions').first()).toBeVisible({
    timeout: 30_000,
  });
}

/** Open the top-right account menu (`.user-menu summary`). */
export async function openAccountMenu(page: Page): Promise<void> {
  const summary = page.locator(".user-menu summary").first();
  await summary.waitFor({ state: "visible", timeout: 30_000 });
  await summary.click();
}

// ---- Fixture media assets (filenames are load-bearing: they trigger the AI-engine's canned,
// gateway-less transcripts/captions — see apps/ai_engine/ai_engine/processing.py). ----

const FIXTURE_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

export const FIXTURES = {
  audioInitial: "audio_01_initial_consultation.wav",
  audioProcedure: "audio_02_procedure_note.wav",
  photoPre: "photo_01_pre_correction_left_cheek.jpg",
  photoPost: "photo_02_post_correction_left_cheek.jpg",
} as const;

/** The canned transcript the AI engine returns for the initial-consultation fixture audio. */
export const FIXTURE_AUDIO_INITIAL_TRANSCRIPT_MARKER = "Sara Nazari";

export function fixturePath(name: string): string {
  return path.join(FIXTURE_DIR, name);
}

// ---- API-seeded captures.
// The browser normalizes/renames audio uploads (audio-<ts>.wav), which drops the fixture filename the
// AI engine keys on — so gateway-less audio fixtures must be seeded via the real /captures API, which
// preserves original_filename. (Photos/notes keep their filename and can also go through the UI.) The
// backend + Celery pipeline are still exercised for real; only the browser's audio re-encode is bypassed.

const MIME_BY_TYPE: Record<string, string> = { audio: "audio/wav", photo: "image/jpeg" };

/** Upload a capture through the real API with the fixture filename preserved. Returns { session, item }. */
export async function uploadCaptureApi(
  request: APIRequestContext,
  accessToken: string,
  opts: { type: "audio" | "photo"; fixtureFile: string; sessionId?: string; newSession?: boolean; detail?: string },
): Promise<{ session: { id: string } & Record<string, unknown>; item: Record<string, unknown> }> {
  const multipart: Record<string, string | { name: string; mimeType: string; buffer: Buffer }> = {
    capture_type: opts.type,
    client_capture_id: `${uniqueSuffix()}-${uniqueSuffix()}`,
    detail: opts.detail ?? "",
    file: { name: opts.fixtureFile, mimeType: MIME_BY_TYPE[opts.type], buffer: fs.readFileSync(fixturePath(opts.fixtureFile)) },
  };
  if (opts.sessionId) multipart.session_id = opts.sessionId;
  if (opts.newSession) multipart.new_session = "true";
  return readJson(
    await request.post("/api/v1/captures", { headers: { Authorization: `Bearer ${accessToken}` }, multipart }),
    `upload ${opts.type} capture`,
  );
}

async function pollSession(request: APIRequestContext, accessToken: string, sessionId: string): Promise<any> {
  return readJson(
    await request.get(`/api/v1/sessions/${sessionId}`, { headers: { Authorization: `Bearer ${accessToken}` } }),
    "get session",
  );
}

/** Poll the session's deterministic report until it contains `marker` (the fixture pipeline resolved). */
export async function waitForReportContains(
  request: APIRequestContext,
  accessToken: string,
  sessionId: string,
  marker: string,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    const session = await pollSession(request, accessToken, sessionId);
    last = String(session.generatedReport ?? "");
    if (last.includes(marker)) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`report did not contain ${JSON.stringify(marker)} within ${timeoutMs}ms; last report: ${last.slice(0, 200)}`);
}

/** Poll a session until the Pro synthesis has produced a structured report with treatments (P1). */
export async function waitForSynthesisTreatments(
  request: APIRequestContext,
  accessToken: string,
  sessionId: string,
  timeoutMs = 60_000,
): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    const session = await pollSession(request, accessToken, sessionId);
    const treatments = session.extractedMetadata?.treatments ?? session.report?.treatments ?? [];
    last = `report=${session.report?.status} treatments=${Array.isArray(treatments) ? treatments.length : "?"}`;
    if (Array.isArray(treatments) && treatments.length > 0) return session;
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new Error(`synthesis did not produce treatments within ${timeoutMs}ms; last: ${last}`);
}

/** Create a patient via the API and assign a session to it (so the session shows as a Recent card). */
export async function assignSessionToNewPatient(
  request: APIRequestContext,
  accessToken: string,
  sessionId: string,
  displayName: string,
): Promise<{ id: string }> {
  const headers = { Authorization: `Bearer ${accessToken}` };
  const patient = await readJson(await request.post("/api/v1/patients", { headers, data: { displayName } }), "create patient");
  await readJson(
    await request.post(`/api/v1/sessions/${sessionId}/assign-patient`, {
      headers,
      data: { patientId: patient.id, source: "staff", reason: "e2e" },
    }),
    "assign patient",
  );
  return patient;
}

/** Open an API-seeded session from Clinical Memory → Recent (the Pro report + Sources drawer render). */
export async function openTodaySession(page: Page): Promise<void> {
  await page.goto("/#patients");
  await page.getByRole("tab", { name: "Recent" }).click();
  await page.locator(".clinical-memory .visit-card, .clinical-memory .clinical-row-selectable").first().click();
  await expect(page.getByTestId("report-body")).toBeVisible({ timeout: 30_000 });
}

/** Open the Pro "Sources" drawer that holds the per-capture transcript/caption cards. */
export async function openSourcesDrawer(page: Page): Promise<void> {
  await page.locator("button", { hasText: /Sources/i }).first().click();
  await expect(page.locator(".live-draft-capture").first()).toBeVisible({ timeout: 15_000 });
}

/** Poll a session's captures until one carries a caption/transcript containing `marker`. */
export async function waitForCaptureText(
  request: APIRequestContext,
  accessToken: string,
  sessionId: string,
  marker: string,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const caps = await readJson(
      await request.get(`/api/v1/sessions/${sessionId}/captures`, { headers: { Authorization: `Bearer ${accessToken}` } }),
      "get captures",
    );
    const list: any[] = Array.isArray(caps) ? caps : caps.items ?? [];
    const blob = JSON.stringify(list.map((c) => c.metadata ?? {}));
    if (blob.includes(marker)) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no capture carried ${JSON.stringify(marker)} within ${timeoutMs}ms`);
}
