import * as Sentry from "@sentry/react";

/**
 * Initialize Sentry/GlitchTip error tracking for the SPA.
 *
 * No-op when `VITE_SENTRY_DSN` is empty (dev / unconfigured builds are unaffected). GlitchTip is
 * Sentry-API-compatible, so `@sentry/react` points at the GlitchTip DSN unchanged.
 *
 * PHI safety: `sendDefaultPii` is false and request/breadcrumb bodies are not attached, so no
 * patient/clinical data leaves the browser — only error names, stacks, and route URLs.
 */
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) {
    return;
  }

  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "development",
    // Never attach PII (IP, user identifiers) or request payloads to events.
    sendDefaultPii: false,
  });
}
