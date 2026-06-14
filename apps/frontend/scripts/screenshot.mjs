// Reusable screenshot helper for agents/devs.
//
// WHY: `npx playwright install chromium` downloads from the Playwright CDN, which is BLOCKED in our
// sandbox/CI (you'll see "Download failure code=1"). The fix is to drive the **system Google
// Chrome** via Playwright's `channel: "chrome"` — no browser download needed. `playwright-core` is
// already available (bundled by the `@playwright/test` devDependency), so once `npm install` has run
// in apps/frontend this works with zero extra setup.
//
// USAGE:
//   node apps/frontend/scripts/screenshot.mjs <url> <outPng> [viewport]
//   viewport: "mobile" (390x844, default) | "desktop" (1280x900) | "WxH"
// Example:
//   node apps/frontend/scripts/screenshot.mjs http://localhost:5187 /tmp/app.png mobile
//
// For multi-step flows (login → click → screenshot), copy this file and add page.* steps; the only
// thing that matters for the sandbox is `chromium.launch({ channel: "chrome" })`.

import { chromium } from "playwright-core";

const [url, out, viewportArg = "mobile"] = process.argv.slice(2);
if (!url || !out) {
  console.error("usage: node screenshot.mjs <url> <outPng> [mobile|desktop|WxH]");
  process.exit(1);
}

const presets = { mobile: { width: 390, height: 844, isMobile: true }, desktop: { width: 1280, height: 900, isMobile: false } };
let viewport = presets[viewportArg];
if (!viewport) {
  const [w, h] = viewportArg.split("x").map(Number);
  viewport = { width: w || 390, height: h || 844, isMobile: (w || 390) < 700 };
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const ctx = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 2,
    isMobile: viewport.isMobile,
    hasTouch: viewport.isMobile,
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: out, fullPage: true });
  console.log("wrote", out);
} finally {
  await browser.close();
}
