# Taking screenshots of the running app (agents + devs)

`npx playwright install chromium` **does not work in our sandbox/CI** — the Playwright browser CDN
is blocked, so the download fails with `Download failure code=1`. Do **not** rely on it.

**Use the system Google Chrome instead**, via Playwright's `channel: "chrome"`. No browser download
is needed, and `playwright-core` is already bundled by the `@playwright/test` devDependency.

## One-off screenshot

```sh
# from the repo root, with the app running (scripts/dev-stack.sh up prints the URL):
node apps/frontend/scripts/screenshot.mjs http://localhost:<appPort> /tmp/app.png mobile
```

The helper opens a mobile viewport (390×844) by default; pass `desktop` or `WxH` for other sizes.

## Multi-step flows (login → click → screenshot)

Copy `apps/frontend/scripts/screenshot.mjs` and add `page.*` steps. The only thing that matters for
the sandbox is launching with the system Chrome:

```js
import { chromium } from "playwright-core";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
await page.goto("http://localhost:<appPort>", { waitUntil: "networkidle" });
await page.getByRole("radio", { name: "Therapy" }).click();          // dev-login tier
await page.getByRole("button", { name: /Therapist \(Dr\. Demo\)/ }).click();
await page.screenshot({ path: "/tmp/clients.png", fullPage: true });
await browser.close();
```

## If `playwright-core` isn't installed on the host

It's a dependency of `@playwright/test` (a frontend devDependency), so `npm install` in
`apps/frontend` provides it. If you're outside that workspace, `npm i playwright-core` into a scratch
dir works — only the npm registry is needed (not the browser CDN).

## Requirements

- Google Chrome installed (`/Applications/Google Chrome.app` on macOS). `channel: "chrome"` uses it
  directly. `channel: "msedge"` works the same way if only Edge is present.
