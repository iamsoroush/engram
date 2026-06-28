# Persian-UI i18n — backlog (ordered, vertical, independently shippable)

Each story = translate ALL chrome for its surface(s) **+** RTL-correctness **+** no en regression **+**
an e2e (the touched CORE journey) green in BOTH languages. Build top-down; merge each before the next.

> Foundations first (S1) because every later story depends on the seam + RTL provider. Then the app
> frame (S2), then surfaces by traffic (S3 capture/report = highest, then memory, then admin), then the
> cross-cutting tail + RTL polish (S6).

---

## S1 — i18n foundation for the authenticated app
Extend the existing `shared/i18n` seam (built for landing/login/onboarding) to cover the authed app:
a complete `t()` + `useT()` over fa/en catalogs, an app-language→`dir` (rtl/ltr) provider at the app
root, and a **glossary** of canonical clinical terms. Add a dev guard (lint/test) that flags hardcoded
user-facing strings in `src/features/**` so later stories can't silently leak English.
**AC:** switching app language flips `t()` output + document/`app` `dir`; Jalali dates already work and
stay; the guard fails on a planted hardcoded string; en unchanged. No screen translated yet beyond what
the seam already covered.

## S2 — App shell, navigation & account menu
The frame everything renders inside: top bar, bottom/tab nav, screen titles, the account/profile menu,
language/tier labels, sign-out. Full RTL of the shell (nav order, chevrons, menu alignment).
**AC:** with fa, the entire shell chrome is Persian + RTL; nav + account menu work; en unchanged; e2e:
log in → navigate the main tabs, asserted in fa and en.

## S3 — Capture / session screen + report chrome (highest traffic)
The core working surface: capture bar (Record/Photo/Note), session header + status, the **verify bar**
("N to confirm"/Review), patient-context card, **verify region** (patient-conflict panel, AI-created-
patient), the **Clinical report** card chrome (title, freshness/"Updating", section *titles* already
localize via reportLanguage — leave those), Sources drawer, aftercare add/remove, inline dose-confirm,
"Fix at source". Translate CHROME only — never the report's clinical prose/treatment content.
**AC:** with fa, all capture/report chrome is Persian + RTL, clinical content untouched; capture →
report → confirm flow works; e2e: capture a note → see report → confirm a dose, in fa and en.

## S4 — Clinical Memory, patients & timeline
Memory tabs (Today / Patients / Needs input), needs-input cards + badges, patient list, **patient
timeline**, search + smart-search result chrome, empty states.
**AC:** with fa, all memory/patient/timeline chrome is Persian + RTL; search + needs-input navigation
work; e2e: open Clinical Memory → search a patient → open timeline, in fa and en.

## S5 — Settings, team, plan & patient-share chrome
Account utility surfaces: settings (incl. the language/tier selectors themselves), **Team**, **Plan**,
and the **patient-share sheet** chrome (toggles, labels, preview chrome — NOT the shared clinical
content, which follows reportLanguage).
**AC:** with fa, all of these are Persian + RTL; changing settings/plan/team works; share sheet chrome
Persian while shared content still follows reportLanguage; e2e: open settings → change app language →
open the share sheet, in fa and en.

## S6 — Cross-cutting states + RTL polish pass
The long tail: loading/error/empty/offline/permission copy, toasts, confirm dialogs, a11y labels,
placeholders across the app — then a dedicated **RTL polish sweep** (alignment, mixed-LTR tokens,
directional-icon mirroring, no clipped/overflowing Persian) screen by screen.
**AC:** no untranslated English chrome remains under fa anywhere in the authed app (incl. toasts/errors/
empty/offline); RTL is clean on every screen; en unregressed; full CORE e2e suite green in fa and en.
