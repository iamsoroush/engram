# doc-impact — S5: settings / team / plan / patient-share

Branch `i18n/s5-account` off main `cc8be13`. `features/account/*` + `SharePatientSheet` +
the S5 App.tsx settings/auth toasts. +163 keys (catalog **1044 en / 1044 fa, matched**); guard 273→214.

## Amd 1 — share-sheet two-axis (proven structurally)

`SharePatientSheet`: the doctor's curation CHROME → app `t()`; the patient-facing SHARE CONTENT →
stays on `shareLanguage`:
- `summaryLabel`/`assessmentLabel` (the shared section labels) remain `fa = shareLanguage.startsWith("fa")`
  driven — **not** app-`t()`.
- `SharePreviewPane` ("what the patient sees") is wrapped `data-content data-testid="share-preview"`;
  its content (title, "For {name}", note, treatment lines, aftercare name/body, captions) stays data.
- **Oracle for your gate:** mock with `appLanguage` + `reportLanguage`/`shareLanguage` INDEPENDENT; app=fa
  ⇒ share CHROME Persian («هم‌رسانی با بیمار», toggles «افزودن خلاصهٔ ویزیت»…) while the share-preview
  content + section labels stay in the report language (English when shareLanguage=en). Scan chrome,
  exclude `[data-testid="share-preview"]`.

## Amd 2 — autonym language selectors (confirmed)

The App/Transcription/Report language pickers render OPTIONS as autonyms (`English` / `فارسی` /
`العربية`, each in its own script — NOT `t()`'d), so a user finds their language regardless of UI
language. The selector LABELs ("App language"/"Report language"/section headers) ARE translated.
Tier options stay Latin "Basic"/"Pro".

## Amd 3 — RTL mirror/CSS

Account/share physical-L/R→logical: `.share-aftercare-select`/`.share-note-input` margins,
`.share-preview-treatments` padding, and the **`.share-toggle` knob** (`left`→`inset-inline-start` on
the knob `span` + its `.on` position, so the toggle slides the mirrored way under RTL). No directional
text glyphs in this surface beyond toggles. (`.phone-shell` padding-left also went logical — identical
under LTR.)

## Amd 4 — DATA verbatim

Member names/emails, clinic name, share-preview patient name, dates, typed field values, aftercare
template names — all kept verbatim under `data-content` markers; the search/field inputs are never `t()`'d.

## Amd 5c — LIVE app-language switch: BLOCKED by a pre-existing auth loop (needs a decision)

**Implemented the chain:** `handleUpdateTenantSettings` + `updateTenantSettings` now carry `appLanguage`,
so the selector change commits `auth.tenant.appLanguage` → `AppLangProvider lang` changes → re-render.
Verified the handler computes + commits `fa` (`updated.appLanguage=fa`).

**But it doesn't apply live in the hermetic harness.** Diagnosis (via console-stack instrumentation,
since removed): a **pre-existing high-frequency `commitAuth(en)`** runs ~dozens/sec from login onward
(a `Promise.then` committing a stale-`en` auth object; top stack frame is a scheduled callback with no
app frame above it — the dev-persona/bootstrap/refresh path, NOT i18n code). After the settings handler
commits `fa`, this loop immediately re-commits `en`, so `auth.tenant.appLanguage` never settles on `fa`
and the provider stays en/ltr. `/me` is NOT re-fetched (ruled out). This is **not introduced by S5** —
it was an invisible no-op while the app was English-only; translating the app made it visible.

This likely is a **test-harness artifact** (50 `commitAuth`/sec would not survive unnoticed in
production), but it equally breaks a hermetic 5c test. Decision needed (see channel): investigate the
dev-persona/mock token as the trigger and adjust the gating mock; accept "language change persists across
reload"; or fix the auth-commit loop (a core-auth change — wants Planner/Evaluator sign-off).

Everything else in S5 (settings/team/plan/switch/share translation, autonyms, two-axis, RTL, App toasts)
is done + verified: tsc 0 · catalog 1044/1044 matched, all keys resolve · guard 0 · S1–S4 gating + existing
e2e 12/12 (sampled) green.
