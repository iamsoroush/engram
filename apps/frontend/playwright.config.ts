import { defineConfig, devices } from "@playwright/test";

// Default: Playwright starts the vite dev server at 5183 and specs mock the API. Set
// PLAYWRIGHT_BASE_URL to run against an already-running app (e.g. a worktree dev-stack) without
// starting a server — handy for isolated per-worktree stacks on non-default ports.
const externalBaseUrl = process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: "./tests",
  // The real-stack suite (tests/e2e-stack/) needs a live backend and runs under its own
  // playwright.stack.config.ts + the `e2e-stack` CI job — keep it out of the hermetic run.
  testIgnore: ["**/e2e-stack/**"],
  outputDir: "./test-results",
  reporter: [["list"], ["html", { open: "never" }]],
  webServer: externalBaseUrl
    ? undefined
    : {
        command: "npm run dev -- --host 127.0.0.1",
        url: "http://127.0.0.1:5183",
        reuseExistingServer: true,
        timeout: 120_000,
      },
  use: {
    baseURL: externalBaseUrl ?? "http://127.0.0.1:5183",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
});
