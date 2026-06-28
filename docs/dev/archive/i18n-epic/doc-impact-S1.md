# doc-impact — S1: i18n foundation for the authenticated app

Branch `i18n/s1-foundation`. Foundation only — **no feature screen translated** beyond what the
public seam already covered. This note records mid-build decisions, deviations, and the tracked gaps
the Planner / later stories need (the Planner owns product-truth docs; this is the build-side record).

## What shipped

- **Authed-app language seam** (extends `shared/i18n`, did NOT fork a second seam):
  - `toLang(value)` — total/deterministic normalizer: `fa`/`fa-*` → fa; everything else (`en`, `ar`,
    null, garbage) → **en** (safe default; `ar` ships later).
  - `AppLangProvider` (React context) — provides `{ lang, t, dir }` from the tenant's app language and
    is the **sole authority** that writes `<html dir/lang>` on authed surfaces. Applies direction in an
    isomorphic **layout effect** (before paint) so it cleanly overrides any leftover public-surface
    direction with no flash. Calls `setAppLanguage(lang)` during render (before children) so the first
    authed paint already formats dates in the right calendar.
  - `useAppLang()` / `useT()` hooks — the API S2–S6 will consume to translate chrome.
- **App-root wiring** (`src/app/App.tsx`): all three authed branches (aesthetics `Shell`, `TherapyApp`,
  `PatientPreviewGate`) wrapped in `<AppLangProvider lang={toLang(auth.tenant.appLanguage)}>`. The
  render-time `setAppLanguage(...)` call at the top of `App()` was **removed** — the provider now owns
  that single source. Public/unauth surface is untouched (still `useUiLang` + `engram-ui-lang`).
- **Glossary** of canonical clinical terms in the catalog (`glossary.*`, fa/en) — see table below.
- **Dev guard** `npm run i18n:guard` (`scripts/check-i18n.mjs` + `scripts/i18n-baseline.json`).
- **A2/A3 unit tests** `npm run test:unit` (vitest added as a devDep + `vitest.config.ts`).

## Decisions / deviations

1. **`setAppLanguage` ownership moved into `AppLangProvider`** (was a render-time call in `App()`).
   Single source of truth for app language → date/Jalali + dir. Kept it as a render-time call (not an
   effect) inside the provider so the first authed render formats dates correctly (no Gregorian flash).
2. **One `<html>` authority per surface**: public = `useUiLang` (localStorage, default fa);
   authed = `AppLangProvider` (tenant.appLanguage). On login the provider's layout effect overrides the
   public direction in the same commit (verified: fa-public → en-tenant ⇒ ltr/en, no stale rtl).
3. **Guard = heuristic ratchet, scope `src/features/**/*.tsx`.** Baseline keyed on **(file +
   normalized string)** so a NEW literal in an already-baselined file still fails. Matches JSX **text
   nodes** + literal `placeholder`/`aria-label`/`title`/`alt` attributes; rejects code-ish fragments
   (assignments/statements/hooks) the `>…<` regex can splice out of TS generics. `--update` regenerates
   the baseline (later stories shrink it). Current baseline: **554 strings / 43 files**.
   - **Known limitation:** it does NOT catch **TS string literals** (e.g. `setToast("…")`, label
     helpers). Those are translated by hand per story and reviewed; the guard is a safety net for the
     common JSX-text leak, not an exhaustive parser. (Acceptable per the agreed contract.)
4. **A2 proven by a pure vitest provider test** (renders `<AppLangProvider>`→`useT()` via
   `react-dom/server`, asserts fa/en/`ar→en` fallback) — no shipped test-only DOM probe.
   **A3** proven by a formatter unit test (Persian/Jalali digits under fa) **and** the Evaluator's e2e.
5. **ENV:** the prescribed `scripts/dev-stack.sh up` could not start (running Docker env is the
   pre-rebrand `notari-*` stack; the post-rebrand script defaults to `engram-*`). Frontend-only epic →
   served the worktree via local Vite (`:5184`) proxying the canonical backend (`:8010`). Pre-existing
   rebrand drift, not an i18n change. (Also logged in `channel.md`.)

## Glossary — canonical clinical/UI terms (`glossary.*`)

| key | en | fa |
| --- | --- | --- |
| visit | Visit | ویزیت |
| session | Session | جلسه |
| capture | Capture | ثبت |
| report | Report | گزارش |
| summary | Summary | خلاصه |
| patient | Patient | بیمار |
| treatment | Treatment | درمان |
| dose | Dose | دوز |
| aftercare | Aftercare | مراقبت‌های پس از درمان |
| sources | Sources | منابع |
| note | Note | یادداشت |
| photo | Photo | عکس |
| audio | Audio | صدا |

Reuse these exact words when composing chrome strings; don't coin per-screen synonyms.

## Tracked gap — App.tsx authed chrome (amendment 5)

`src/app/App.tsx` is out of the `src/features/**` guard scope and its chrome is **TS string literals**
(toasts, sync/offline copy, a few screen titles/labels) that the JSX-text guard does not see — so they
will leak English under fa until translated. Enumerated below → owning story. **Convention for later
stories:** when you leave a known-untranslated literal in place, tag it `// i18n(S<n>): <reason>` so it
is greppable and doesn't silently fall through the ratchet.

**→ S2 (shell / nav / screen titles):** `"Clinical Memory"` (L2016), `"Needs input"` (L2013),
`"Patient history"` (L2009).

**→ S3 (capture / report flow chrome + its toasts):** `"Current capture destination"` (L2035),
`"Add the next capture to this session."` (L2047), `"Unassigned visit"` (L2414) + the
`captureContextLabel` template (`"Capturing for: … · Today's visit"` / `"… · new visit"`),
`"New session ready."` (L963), `"Could not start the visit."` (L988),
`"Generating structured report"` (L1064), `"Background AI is organizing the latest captures."` (L1065),
`"Structured report is generating."` (L1096), `"Capture renamed."` (L1184), `"Caption updated."` /
`"Transcript updated."` (L1252), `"Capture deleted."` (L1289),
`"Capture deleted. The live report is updating."` (L1307),
`"Marked relevant. The live report is updating."` (L1324), `"Dose confirmed."` (L1342),
`"Could not confirm the dose. Try again."` (L1344), `"Could not update aftercare. Try again."` (L1370),
`"Session title updated."` (L1141), `"Could not update title."` (L1164),
`"Could not load captures for this session."` (L1953).

**→ S4 (memory / patients / timeline toasts):** `"Visit unassigned."` (L1463),
`"That patient record is no longer available …"` (L1440), `"AI-created patient verified."` (L1605),
`"Patient details updated."` (L1627), `"Patient created."` (L1635), `"Could not create patient."`
(L1638), `"Summary added to patient memory"` (L1692), `"Note updated."` (L1791).

**→ S5 (settings / team / plan / auth toasts):** `"Role permissions updated."` (L1891),
`"Patient-matching preference updated."` (L1893), `"Language preferences updated."` (L1894),
`"Could not update role permissions."` (L1899), `"Could not update matching preference."` (L1901),
`"Could not update language preferences."` (L1902), `"Could not sign in with that persona."` (L1812),
`"Invalid email or password."` (L1823).

**→ S6 (cross-cutting: offline / sync / storage / generic errors + confirm dialogs):**
`"Offline · Captures are saved on this device."` (L485), `"Sync failed"` (L750),
`"Some local changes need retry"` (L752), `"Capture safely transferred."` (L824),
`"Capture upload failed"` (L852), `"Saved on this device. I'll organize it when connection returns."`
(L854), `"Audio conversion failed."` / `"Device storage failed."` (L898), `"Saved on device."` (L903),
`"Saved. I'll organize it when available."` (L1107), `"Title saved on this device."` (L1160),
`"No queued captures to export."` (L405), `"Could not export queued captures."` (L412),
`"Clear captures saved only on this device? This cannot be undone."` (L1025),
`"Local pending captures cleared."` (L1037). (`"No auth session"` L249 is an internal throw, not UI.)

> The guard's `src/features/**` scope should be **extended to `src/app/App.tsx`** once these literals
> move into the seam (or a later story can add a TS-string-literal matcher). Until then this list is the
> system of record for App.tsx leakage.
