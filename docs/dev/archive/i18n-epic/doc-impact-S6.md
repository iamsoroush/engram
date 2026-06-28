# doc-impact — S6: cross-cutting tail + RTL polish (FINAL)

Branch `i18n/s6-tail` off main `8ba142c`. The "no English chrome remains under fa" gate for the
authed **aesthetics** app. +114 keys (catalog **1180 en / 1180 fa, matched**); guard live-scan
ratcheted 199→**155** (every remaining row audited below). tsc 0 · unit 10/10 · existing e2e 28/28.

## What S6 translated
- **Doctor-Q&A surface** — `DoctorQaInbox.tsx` (~70 keys: scope tabs, routing toggle, status badges,
  AI-draft reply box, Send/Dismiss/Re-route, confirms, toasts), `QaChannelButton.tsx`, and
  `useVoiceEdit.ts` (its 3 error strings now take a `t` translator — the hook's only consumer already
  has one). Patient names + message bodies stay DATA (`data-content`).
- **Missed aesthetics components** (never in a prior story's file list): `LastVisitStrip`, `MediaOverlay`,
  `TryProTeaser`, `VoiceMemoPlayer`, `CaptureBadges` ("Tap to edit"), `SharePatientSheet` preview
  aria-label. `SessionContextCard` was already fully translated (no new keys).
- **App.tsx offline/sync/storage toasts** — the long tail the guard can't see (TS string literals in
  `setToast`/`setSyncError`/`window.confirm`, not JSX): offline/transferred/upload-failed/saved-on-device/
  clear-cache confirm/export-queued/tier-switch/safety-flag, etc. All via `appT` (App renders above the
  provider). 19 keys.

## Mixed-digit policy (amendment 3 — surgically scoped)
`translate()` converts Western→Persian digits **only for numeric `t()` interpolation values** under fa
(`typeof raw === "number"`). Template literals and string vars are untouched, so:
- counts get Persian digits: `qa.visitCount {n:12}` → «۱۲ ویزیت»;
- **Latin tokens never corrupt**: tier "Pro"/"Basic" and "MVP v2" stay verbatim (passed as string vars
  or living in the template, never as numeric vars);
- DATA never converts: names, Jalali dates (already Persian via the formatter), file sizes, IDs (IDs/
  phone/dose are `data-content`, never numeric `t()` vars).
Unit-tested in `appLang.test.tsx` (numeric→fa digits; string/Latin untouched; en stays Western).

## RTL polish
Physical→logical in the newly-translated surfaces: `try-pro-teaser`/`try-pro-info-*` `text-align:left→start`,
`try-pro-go` `margin-left→margin-inline-start`, `media-overlay-close`/`try-pro-info-x` `right→inset-inline-end`;
qaInbox `text-align:left→start` (×2), the Q&A thread accent `border-left→border-inline-start` +
`padding` logicalized. Directional glyphs mirror under RTL via the established `scaleX(-1)` pattern:
`media-overlay-nav` chevrons (‹ ›) + the before→after `media-overlay-vs` arrow; the Try-Pro CTA arrow
points left in the fa string. `LastVisitStrip` already used logical props.

## Planner-visible EXCLUSIONS (amendment 2 — stated, not silent)
The epic's "no English chrome remains" claim is precisely scoped to **authed AESTHETICS app chrome**.
Deferred to their own future i18n passes (Evaluator signed off):
1. **`features/therapy/**`** (TherapyCaptureScreen + TherapyApp, ~69 baselined strings) — a SEPARATE,
   not-yet-shipped vertical. Translating now = churn + double-translation when therapy ships. **A fa
   therapy tenant still sees English therapy chrome** until the therapy i18n pass. Tracked.
2. **`features/patient-surface/**`** (PatientSharePage, PatientQaPage, ~28 strings) — PATIENT-facing
   pages that follow **shareLanguage/reportLanguage** (the patient's language), NOT the app UI language.
   Translating them via app-`t()` would be WRONG. Separate patient-facing i18n concern.
3. **Public surfaces** (landing/login/signup/onboarding, AuthGates dev-personas) — already bilingual via
   the public seam; non-goal here.
   - **One known sub-item:** `handlePasswordLogin`'s "Invalid email or password." (App.tsx) is hardcoded
     English and bypasses the public seam. It renders on the **login** screen (pre-auth, where `appT`
     resolves to en anyway), so it belongs to the public-seam i18n pass, not this epic. Flagged.
   - SharePreviewPane's "Your visit" fallback is share **content** (shareLanguage axis), inside
     `data-content` — out of app-chrome scope; belongs to the share/report-language work.

## Final guard-baseline AUDIT (amendment 4 — every remaining row justified)
Live scan = **155** strings / 36 files. By category:
- **106 in excluded surfaces** — therapy (69), patient-surface (28), auth public (8), landing (1). All
  out-of-scope per the exclusions above; NOT real authed-aesthetics chrome.
- **49 in in-scope files — ALL heuristic guard false-positives, ZERO real chrome.** The guard's
  `>...<` JSX-text heuristic mis-captures non-text fragments:
  - `"Promise"` / `"void | Promise"` / `"[] as Array"` (×~30) — TS generics/type-unions between `>` and `<`.
  - JSX ternary/expression fragments (×~19) — e.g. `") : freshness ? ("`, `") : member.isSelf ? ("`,
    `"recent.photos.length ? ("`, `"0 && remaining"` (from `quota > 0 && remaining < …`),
    `"captureTypeCounts[type] ? ("`. These are CODE between two JSX nodes, never rendered text.
  None is an untranslated user-facing string. (The guard stays a *ratchet*, not a zero-target; these
  noise rows are harmless and tightening the heuristic is out of scope.)

## Verification
tsc 0 · catalog 1180/1180 matched, no only-en/only-fa, no dups · all **1231** `t()`/`appT()` literal-key
refs resolve · en-preservation: every removed literal present verbatim in the en catalog · guard 0 new ·
unit 10/10 · existing i18n e2e 21/21 + account-menu/onboarding/landing 7/7.

## For the Evaluator's gating spec (`i18n-tail.spec.ts`)
- `tests/e2e/_setup.ts`: `authPayload({ appLanguage: "fa", tier: "pro" })` spawns the fa app; a
  **catch-all `**/api/v1/**` mock** is now registered first in `installAppMocks` (the 5c lesson —
  unmocked endpoints no longer 401→loop); `installQaMocks(page)` seeds one needs-approval conversation
  so the inbox renders full chrome.
- Reach the Q&A inbox via `#qa-inbox` (Pro-only); its root is `data-testid="qa-inbox"`. Scan chrome
  containers, exclude `[data-content]`, allowlist Latin `Engram/Pro/Basic/MVP v2`.
