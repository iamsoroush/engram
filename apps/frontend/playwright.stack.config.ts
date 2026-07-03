import { defineConfig, devices } from "@playwright/test";

// Real-stack e2e config (tests/e2e-stack/). Unlike the hermetic playwright.config.ts, these specs run
// the frontend AND the real backend/Celery/MinIO from the compose stack — no API mocking. The stack is
// external (brought up by `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --wait`),
// so there is no webServer here: point PLAYWRIGHT_BASE_URL at the running frontend. In CI that is
// http://localhost:5183 (compose default); locally an isolated stack may use a different port.
//
//   PLAYWRIGHT_BASE_URL=http://localhost:5183 npx playwright test --config playwright.stack.config.ts
//
// See docs/frontend/README.md "Testing" and the `e2e-stack` CI job in .github/workflows/ci.yml.
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5183";

export default defineConfig({
  testDir: "./tests/e2e-stack",
  outputDir: "./test-results-stack",
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report-stack" }]],
  // Fail fast with an actionable message if the stack isn't up.
  globalSetup: "./tests/e2e-stack/_global-setup.ts",
  // Real backend + async Celery pipeline: allow one retry to absorb transient timing, and give
  // auto-retrying assertions a generous ceiling (the gateway-less pipeline resolves in ~1-2s, but the
  // first cold request after boot can be slower).
  retries: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // Per-tenant isolation lets files run concurrently; tests within a file stay ordered (the demo-tenant
  // multi-persona specs rely on that). 3 workers matches the spec's 2-3 guidance.
  fullyParallel: false,
  workers: process.env.CI ? 3 : 2,
  use: {
    baseURL,
    trace: "retain-on-failure",
    // Auto-accept the mic prompt with a fake device so the audio capture dialog opens without a real
    // microphone (specs upload a fixture .wav rather than record live).
    launchOptions: {
      args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
    },
    // The gateway-less stack renders English or Persian chrome from tenant.appLanguage; specs pin the
    // language explicitly per tenant, so no global locale is forced here.
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
});
