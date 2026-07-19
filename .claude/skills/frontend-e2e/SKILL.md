---
name: frontend-e2e
description: Run the frontend Playwright suites correctly — hermetic vs real-stack, the worktree shared-port trap, AI-spec compose overlays. Use whenever running or writing e2e tests, especially from a git worktree.
---

# Frontend e2e — hermetic and real-stack

Two suites live in `apps/frontend`: the hermetic mocked-API suite (`playwright.config.ts`) and the
real-stack suite (`playwright.stack.config.ts`).

## Hermetic suite (`npm run test:e2e`, mocked API)

- `playwright.config.ts` starts vite on fixed port **5183** with `reuseExistingServer: true`. In a
  git worktree, if any other checkout is already serving 5183, your tests **silently attach to that
  checkout's code** and pass/fail against the wrong build.
- Before trusting worktree results: start your own dev server and point the suite at it with
  `PLAYWRIGHT_BASE_URL=http://127.0.0.1:<your-port> npm run test:e2e` — or verify nothing else owns
  5183 first.
- Dev-login state is in-memory: navigate by **clicking through the UI**. A fresh `page.goto()` or
  hash jump drops auth and you end up testing the login screen.

## Real-stack suite (`playwright.stack.config.ts`)

- P0 specs (no AI): layer `docker-compose.e2e.yml` (gateway-less).
- P1 AI specs: layer `docker-compose.e2e-ai.yml` (mock gateway). Without the overlay, AI specs call
  the real external gateway — slow failures when it's down, real spend when it's up.
- `scripts/dev-stack.sh up` does **not** layer these overlays; add them explicitly when running
  stack specs from a worktree.
