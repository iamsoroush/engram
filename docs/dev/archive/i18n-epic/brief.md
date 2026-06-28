# Epic: Persian-UI i18n (authenticated app) — brief

## Goal
When app language = **Persian (fa)**, the **entire authenticated app UI** renders in Persian, RTL-correct.
Today only **dates/Jalali**, **report CONTENT**, and the **public surfaces** (landing/login/sign-up/
onboarding) are bilingual — the **authenticated app is English-only**. Close that gap so an Iran-first
clinic gets a fully Persian, right-to-left experience end to end.

## Target user + behaviour
Iran-first aesthetics-clinic staff (doctor + reception) who think and work in Persian, on mobile, mid-
visit. They read Persian natively; English chrome ("Clinical report", "Confirm dose", "Sources") is
friction and a trust/adoption risk. They mix scripts naturally (Persian prose with Latin brand names,
Western/Persian digits, dose units).

## Scope
- Every **chrome string** in the authenticated app (labels, buttons, headings, statuses, toasts,
  empty/error/loading copy, account/settings/team/plan/share, capture+report+memory surfaces).
- **RTL correctness** under fa: `dir`, logical CSS, mixed-LTR safety (brands/numbers inside RTL),
  icon mirroring where directional.
- Drive off the **existing `shared/i18n` seam** (built for the public surfaces); extend it app-wide.

## Non-goals (do NOT touch)
- **Report/clinical CONTENT language** — that's the separate `reportLanguage` setting, already handled
  (and the synthesis/captions own it). Only translate **app chrome**, never clinical content.
- New features, redesigns, or behaviour changes — this is a translation + RTL pass, not a rework.
- The **public surfaces** (landing/login/onboarding) — already bilingual; only touch if a shared
  string/seam needs refactoring.
- Other languages (ar, etc.) — structure for it, but only fa + en ship now.

## Success bar
With app language = fa: no English chrome remains in the authenticated app; layout is RTL-correct (no
broken alignment, no LTR leakage except intentional Latin tokens); en is unregressed; every CORE journey
(`docs/ux/workflows/`) passes its e2e in both languages.
