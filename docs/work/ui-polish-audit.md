# UI polish audit — visual/layout consistency (tablet + desktop)

**Fold destination(s):** as-built token/width/primitives description → `docs/frontend/overview.md`;
per-screen behavior changes → the matching `docs/ux/screens/*.md` (notably `insights.md`) and
`docs/ux/states.md` (empty states); any reversed styling decision → `docs/technical-decisions.md`.

**Status:** audit complete, fix plan proposed. Not built.

Owner-reported (from real tablet/desktop use): screens outside Visit/Memory render in a narrow
under-designed strip; the "←Back" pill reads as an afterthought; Insights uses mobile patterns on
wide viewports; the landing page reads dated; dropdowns/disclosures are "not from the same
universe." This doc grounds each observation in code and proposes a two-tier fix plan.

**Scope boundary:** the session/capture surface and PatientsHome are being redesigned by
[ux-epic-session-layout-diet.md](ux-epic-session-layout-diet.md) (and its sibling epics). This plan
targets **the other surfaces + shared primitives only**; §4 lists what is explicitly deferred.

All paths below are relative to `apps/frontend/src/` unless noted.

---

## 1. Findings

### F1 — Per-screen container widths: six different columns under one 820px topbar

The shell caps at 940px and the topbar at 820px, but each screen picks its own inner width, so on
a tablet (768–1024px) content jumps between column widths as you navigate — and the account pages
sit visibly narrower than the topbar above them:

| Surface | Selector | Width | Evidence |
| --- | --- | --- | --- |
| App shell | `.phone-shell` | `min(100%, 940px)` | `styles.css:8917` (final enforcement; earlier defs at 1710 → 760px, 5533 → 940px) |
| Topbar | `.topbar` | `min(100%, 820px)` | `styles.css:8924` |
| Visit (session) | `.session-workspace` | `min(100%, 820px)` | `styles.css:9163` |
| Clinical Memory | `.clinical-memory` | `min(100%, 820px)` | `styles.css:6907`, `9163` |
| Search | `.memory-home` | **uncapped** → fills the 940px shell | `styles.css:2191` (no width rule) |
| Q&A inbox | `.qa-inbox` | `max-width: 760px` + its own `padding: 16px` | `features/qa/qaInbox.css:3–14` |
| Settings / Profile / Team / Plan / Switch clinic / Insights | `.account-screen` | `min(100%, 720px)` | `styles.css:1971`; used by `features/account/AccountScreens.tsx:141,274`, `TeamScreen.tsx:95`, `PlanScreen.tsx:101`, `SwitchClinicScreen.tsx:42`, `features/insights/InsightsScreen.tsx:58` |
| Bottom capture bar | `.capture-pills` | `min(calc(100% - 36px), 800px)` | `styles.css:9674` — **misaligned 20px vs the 820px topbar/content** (earlier 820px defs at 6675, 6820, 8609 are overridden by the later 800px rule) |
| Legacy fixed rows | `.capture-actions`, `.app-version` | `min(100%, 760px)` | `styles.css:4003`, `4028` |
| Public landing | `.landing` | `max-width: 1080px` | `styles.css:11609` |

Compounding it: account pages hide the capture bar (`features/shell/Shell.tsx:45–46,199`), but the
shell keeps its capture-bar clearance `padding-bottom: max(150px, …)` (`styles.css:8919`) — dead
whitespace below short pages like Profile.

Breakpoints are equally scattered — **13 distinct pixel breakpoints** across the CSS
(430/520/560/600/620/640/680/720/760/860/900 in mixed max-/min-width forms; counted over
`styles.css` + feature CSS). There is no shared "two-column kicks in here" line.

### F2 — Back button: three competing patterns, none RTL-correct except one

1. **`.account-back`** — `<Button size="sm" variant="secondary">` with a literal `←` character.
   Rendered 5× with copy-pasted header markup: `AccountScreens.tsx:74–84` (local `AccountHeader`,
   not exported), `TeamScreen.tsx:97`, `PlanScreen.tsx:103`, `SwitchClinicScreen.tsx:44`,
   `InsightsScreen.tsx:60`. `btn-sm` is `min-height: 30px` (`styles.css:1235`) — under the 44px tap
   target. **No `[dir="rtl"]` rule exists for it** (the file has only 10 RTL rules total, listed at
   `styles.css:868,1966,6140,6969,10550,12261,12318`) and `←` is not a bidi-mirrored character —
   under fa the arrow points the wrong way.
2. **`.context-back-button`** — 34px min-height, SVG chevron (`styles.css:7708–7730`;
   `CaptureIcons.tsx:13` BackIcon). Used on the session surface (`CaptureScreen.tsx:342` — epic
   territory), on PatientTimeline (`features/memory/components/PatientTimeline.tsx:95,100`), and in
   therapy (`TherapyCaptureScreen.tsx:65`; `TherapyApp.tsx:289` uses a literal `‹`). Also no RTL
   mirror.
3. **`.smart-list-back`** — borderless text link whose chevron flips under RTL
   (`styles.css:12244–12263`, `SmartListsTab.tsx:141`). The only RTL-correct back affordance.

### F3 — Insights: the shared `Tabs` primitive is a stacked mobile pattern at every width

- `.tabs { display: grid; gap: 8px; }` with **no column template** (`styles.css:1476–1480`) →
  every `Tabs` render is a stack of full-width buttons. `Tabs` (`shared/ui/primitives.tsx:60–83`)
  is used **only** by Insights: the four section tabs (`InsightsScreen.tsx:78–80`) and the chart
  series toggle (`tabs.tsx:112–120`), which therefore stacks vertically inside the flex
  `.ins-card-head` beside the chart title.
- `.tab { text-align: left; }` (`styles.css:1485`) — physical property, wrong under RTL.
- `.tab-active` hardcodes `#2563eb` (`styles.css:1492–1496`) — a *different blue* from
  `--color-primary: #075eff` (see F6).
- Empty states are a bare muted paragraph: `.ins-empty` (`features/insights/insights.css:49–54`);
  `Heatmap` returns just that `<p>` when all-zero (`features/insights/charts.tsx:214`), `ColumnChart`
  likewise (`charts.tsx:123`), and a sparse series renders one lonely bar with no context. No
  min-height, no icon, no hint — cards collapse to different heights and look broken.
- KPI grid: 2-col, 4-col ≥560px (`insights.css:57–62,158–160`) — this part already behaves.

### F4 — Public landing: structurally sound, visually flat

`features/landing/LandingPage.tsx` + `styles.css:11601–11940`. It already has a hero grid
(two-column ≥860px, `styles.css:11923`), a token-built `AppPreview` phone mock (`LandingPage.tsx:38–68`),
steps/trust/plans sections. What makes it read dated:

- Every section is the same flat `display: grid; gap: 18px` (`.landing-section`,
  `styles.css:11758–11761`) on the same page background — no alternating rhythm, no section
  eyebrows, no anchoring visuals outside the hero.
- The preview mock is a tiny 300–320px "phone" with three skeleton lines — it under-sells the
  actual product (a live report surface).
- Trust items are plain text stanzas (`.landing-trust-item`, `styles.css:11826–11840`) — no icons,
  no card treatment.
- Plan cards are minimal; no social-proof placeholder section exists at all.
- Typography scale is fine (clamp-based) but there is no vertical rhythm between sections beyond a
  uniform `gap: clamp(36px, 6vw, 64px)` (`styles.css:11607`).

### F5 — Selects & disclosures: two dropdown species, five native-select stylings, four chevrons

**Selects.** The custom `SelectMenu` (`shared/ui/SelectMenu.tsx`, styled `styles.css:2042–2085`) is
used 7× (Settings languages + matching `AccountScreens.tsx:150–197`, Team roles
`TeamScreen.tsx:119,170`, Insights range `InsightsScreen.tsx:67`). Meanwhile native `<select>`
survives in 6 authed places, each styled differently:

| Usage | Styling | Evidence |
| --- | --- | --- |
| Role permissions (Settings!) | `.setting-row-control select` | `AccountScreens.tsx:53`, `styles.css:2031–2039` — sits in the same card stack as four SelectMenus |
| Worklist doctor picker | `.worklist-lineup-field select` (just `flex: 1`) | `features/memory/components/WorklistSection.tsx:304`, `styles.css:7607` |
| Q&A routing mode | `.qa-routing select` — references **undefined token `var(--border, #d8dde6)`** | `features/qa/DoctorQaInbox.tsx:175`, `qaInbox.css:97–104` |
| Share aftercare template | `.share-aftercare-select` | `features/aesthetics/SharePatientSheet.tsx:317`, `styles.css:10875,10900,11230` |
| Patient form sex | `.patient-form-field select` | `features/patient/PatientForm.tsx:83`, `styles.css:323–331` |
| Therapy risk level | unstyled | `features/therapy/components/TherapyCaptureScreen.tsx:241` |

All native ones keep the tiny UA caret; none share a class.

**Disclosures.** Four unrelated chevron treatments, three using raw text glyphs that do **not**
mirror under RTL (`▸` is not bidi-mirrored):

| Usage | Treatment | Tap target | Evidence |
| --- | --- | --- | --- |
| Sources drawer (session) | `▸`/`▾` in a 22px box, hardcoded `#e7eefb`/`#3b537e` | row is fine; chevron decorative | `CaptureScreen.tsx:629`, `styles.css:6338–6348` |
| "Show visit context" row (session) | text `▸` at 0.7rem | full-width row, OK | `SessionContextCard.tsx:70,126`, `styles.css:10430` |
| Q&A thread expand | SVG chevron, link-blue `#3753e6` text button, `padding: 2px 0` | **~20px tall** | `DoctorQaInbox.tsx:410,498`, `qaInbox.css:144–186` |
| Patient row chevron | 34px SVG box | decorative on a large row | `MemoryCards.tsx:90,159`, `styles.css:7153–7168` |
| SelectMenu caret | text `▾` at 0.66rem | inside 30px trigger | `SelectMenu.tsx:67`, `styles.css:2059` |

### F6 — Token divergence sweep ("not from the same universe" — quantified)

`styles.css:1–47` defines a real token system (colors, radii 8/10/12/pill, space scale, 5 text
sizes, 2 shadows). The rest of the file largely bypasses it:

- **960 hardcoded hex colors** in `styles.css` alone. Top offenders are literal copies of tokens:
  `#ffffff` ×85, `#075eff` ×48 (= `--color-primary`), `#080d2d` ×41 (= `--color-text`),
  `#dce6f2` ×39 (= `--color-border`).
- **Three-plus primary blues.** Tokens say `--color-primary: #075eff`, but the *core button*
  `.btn-default` and `.tab-active` use `#2563eb` (`styles.css:1214–1217,1492`); `qaInbox.css` uses
  its own `#3753e6` (×11) and `#2456d6`; `--color-primary-hover: #155eef` appears raw ×12. Primary
  actions literally aren't the same blue across screens.
- **Off-scale radii:** `7px` ×19, `6px` ×12, `14px` ×6, `9px` ×2 (vs tokens 8/10/12/999). The
  default `.btn` itself is `border-radius: 7px` (`styles.css:1201`) — off the token scale.
- **Font sizes:** 15+ distinct rem values between 0.66 and 0.95rem against 5 `--text-*` tokens;
  `qaInbox.css` uses raw px (`13px`, `13.5px` at `qaInbox.css:90,99,157`).
- **Shadows:** ~30 one-off `box-shadow` values vs 16 tokenized uses of `--shadow-card/float`.
- **Icon sizes:** SVG widths span 11–19px across 9 distinct values (`grep "width: 1[0-9]px"`),
  no icon-size token exists.
- **Focus states:** 41 `:focus-visible` rules exist, but **`.btn` — the shared button — has none**
  (nothing between `styles.css:1194–1250`; no `.btn:focus-visible` anywhere).
- **`qaInbox.css` is nearly token-free:** 6 `var()` references vs ~60 hex literals — a whole
  surface styled in its own palette.
- **13 distinct breakpoints** (F1) with no scale.

---

## 2. Fix plan — Tier 1: consistency pass (shared tokens/components; mechanical, low-risk)

Ordering note: T1.1 and T1.7 first (tokens), then components. Every item: verify under **fa + en,
RTL + LTR**, tablet (768/1024) and phone widths. No behavior changes; chrome strings stay on `t()`.

### T1.1 — One responsive width system
Add tokens `--content-max: 820px` (aligns with `.topbar`) and `--content-wide: 940px`; standardize
breakpoints on **640 / 768 / 1024** (new work uses these; existing queries migrate opportunistically).
Apply:
- `.account-screen` 720 → `var(--content-max)` (`styles.css:1971`).
- `.qa-inbox` 760 → `var(--content-max)`; drop its private side padding in favor of the shell's (`qaInbox.css:3–14`).
- `.memory-home` gets `width: min(100%, var(--content-max)); margin-inline: auto` (`styles.css:2191`).
- `.capture-pills` 800 → 820 (`styles.css:9674`); `.capture-actions`/`.app-version` 760 → 820 (`styles.css:4003,4028`).
- Reduce shell bottom padding on account screens (the capture bar is hidden there): a
  `data-screen`-scoped rule or a `.phone-shell--no-capture` class set by `Shell.tsx` (it already
  computes `isAccountScreen`).

**Accept:** on a 1024px viewport, Settings/Profile/Team/Plan/Insights/Q&A/Search content column is
exactly as wide as the topbar and the Visit/Memory column; bottom capture bar aligns flush with the
content column; no dead scroll-space below short account pages. Session/Memory pixel output
unchanged (both already 820).

### T1.2 — One back/header pattern (`ScreenHeader` + `BackButton` in `shared/ui`)
Extract `AccountHeader` (`AccountScreens.tsx:74–84`) into `shared/ui` as `ScreenHeader`
(`{ title, onBack, actions? }`): back button ≥44px min-height/width, SVG chevron (reuse the
`BackIcon` path) with `[dir="rtl"] { transform: scaleX(-1) }`, label from the existing `*.back`
i18n keys. Replace the five copy-pasted headers (`AccountScreens.tsx` ×2 via the local component,
`TeamScreen.tsx:95–101`, `PlanScreen.tsx:101–107`, `SwitchClinicScreen.tsx:42–48`,
`InsightsScreen.tsx:58–64`). Drop the `←` literals. Style `.context-back-button` and the new
button from the same CSS block so they visually match; fix `TherapyApp.tsx:289`'s `‹` literal to
the shared component when touched.

**Accept:** all six account/utility screens share one header; back arrow points toward the
inline-start edge in both fa and en; tap target ≥44px; `.account-back` CSS deleted.

### T1.3 — `Tabs` primitive becomes a horizontal segmented control
Rework `.tabs` (`styles.css:1476–1497`): `display: inline-flex` in a bordered pill container
(matching `.top-nav`'s existing segmented look, `styles.css:5497–5523`), `overflow-x: auto` below
640px, `text-align: start`, active state on `--color-primary` tokens. Since `Tabs` is only used by
Insights, blast radius is two call sites.

**Accept:** Insights section tabs render as one horizontal segmented row at ≥640px and a
scrollable row below; series toggle no longer stacks; RTL order mirrors; no other screen changes.

### T1.4 — One Select treatment
Keep both species, but make them one visual system, preserving native semantics where it matters
(long lists, mobile pickers):
- Add a shared `.select` class (custom-styled native select: `appearance: none`, token border/radius,
  inline SVG caret via background-image with `[dir="rtl"]` position swap, ≥44px min-height) and a
  thin `Select` wrapper in `shared/ui/primitives.tsx`.
- Apply to the six native usages (F5 table); align `.select-menu-trigger` (`styles.css:2042`) to the
  same height/border/caret so SelectMenu and Select are visually identical closed.
- Convert the Settings role-permissions select (`AccountScreens.tsx:53`) to `SelectMenu` — it sits
  beside four SelectMenus in the same card.
- Fix the undefined `var(--border, #d8dde6)` in `qaInbox.css:102` → `var(--color-border)`.

**Accept:** every closed dropdown in the authed app has the same height, border, radius, caret
glyph and caret side (mirrored under RTL); a11y unchanged (native selects stay native).

### T1.5 — One `DisclosureRow` primitive
Add `DisclosureRow` to `shared/ui`: full-width row button, ≥44px min-height, 16px SVG chevron that
rotates 90° when open and mirrors under `[dir="rtl"]`, `aria-expanded`, token colors. Adopt now on
non-session surfaces: Q&A thread expand (`DoctorQaInbox.tsx:410`, replacing `.qa-expand-toggle`'s
20px target). Session-surface adopters (Sources drawer, visit-context row) are **deferred** — the
primitive is built now so the epic consumes it (§4).

**Accept:** disclosure rows outside the session surface share one component; chevron direction
correct in RTL; tap targets ≥44px.

### T1.6 — Icon-size tokens
Add `--icon-xs: 14px; --icon-sm: 16px; --icon-md: 18px; --icon-lg: 22px` and sweep the 9 distinct
11–19px SVG sizes onto them (nearest value; visual diff review per surface).

**Accept:** no raw px SVG width/height in rules touched by this pass; icons in the same context
(menu rows, buttons, chevrons) are the same size.

### T1.7 — Token reconciliation (colors, radii, focus)
- **One primary:** decide `#075eff` (`--color-primary`) as canonical; migrate `.btn-default`,
  `.tab-active` (`#2563eb`), and qaInbox's `#3753e6`/`#2456d6` onto tokens. This visibly changes
  primary buttons — flag in the PR with before/after screenshots.
- Mechanically replace exact-match hex copies of tokens (`#075eff`, `#080d2d`, `#dce6f2`,
  `#ffffff` on surfaces, etc.) with `var()` — scriptable, zero visual diff.
- Radii: `7px`/`6px` → `var(--radius-sm)`, `9px`/`10px` → `var(--radius-md)`, `14px` →
  `var(--radius-lg)` where the component family already uses that token (visual-diff reviewed).
- Add `.btn:focus-visible` (match the existing `box-shadow: 0 0 0 3px var(--color-primary-soft)`
  pattern from `.setting-text-input:focus`, `styles.css:2098`).
- Tokenize `qaInbox.css` (6 → full `var()` coverage; px font sizes → `--text-*`).

**Accept:** hardcoded hex count in `styles.css` drops by the ~250 exact-token duplicates; one
primary blue app-wide; keyboard focus visible on every `.btn`; eval/lint/build green.

---

## 3. Fix plan — Tier 2: screen redesigns

### T2.1 — Insights wide layout + empty states
Depends on T1.3.
- **Layout ≥768px:** cards flow in a 2-column grid inside the 820px column (`.stack` in the tab
  panels → `grid-template-columns: repeat(2, 1fr)` for the Donut/Heatmap/Needs cards; full-width
  for the activity chart). KPI grid stays 4-up ≥640.
- **Chart toggles:** series `Tabs` (post-T1.3 segmented) sits at the inline-end of `.ins-card-head`
  on one row; drops below the title under 640px (wrap already handles this).
- **Empty states:** a shared `.ins-placeholder` block — fixed min-height matching the chart it
  replaces (128px for ColumnChart, heatmap grid height), dashed `--color-border` frame, small icon
  + `insights.empty` label + a range hint ("try a longer range" key, new i18n pair). Apply in
  `charts.tsx` (`ColumnChart:123`, `Heatmap:214`, `BarList:96`) and `.ins-empty` call sites in
  `tabs.tsx`. Also: when a series has <3 nonzero buckets, keep the placeholder height so a single
  bar doesn't float in a void (min-height on `.ins-columns` already exists via `blockSize` — keep).
- Update `docs/ux/screens/insights.md` after build.

**Accept:** at 1024px, no full-width stacked buttons anywhere on Insights; every card has equal
visual weight when empty; all-empty Overview looks intentional (uniform placeholders); fa/RTL
mirrors; Basic-tier upsell unchanged.

### T2.2 — Settings two-column ≥768px
`.account-screen` becomes `grid-template-columns: repeat(2, minmax(0, 1fr))` at ≥768px with
`align-items: start`; the header, `AiUsageCard`, and `AftercareTemplatesSettings` (tall editor)
span both columns (`grid-column: 1 / -1`); the four small groups (Languages, Matching, Sharing,
Plan) flow into the two columns. Profile/Team/Plan/SwitchClinic get the same rule where they have
≥3 cards; single-card pages stay one column.

**Accept:** at 1024px Settings fills the 820px column with two balanced card columns and no dead
side whitespace; card order still reads top-to-bottom → start-to-end in both LTR and RTL; phone
layout unchanged.

### T2.3 — Landing modernization
Design direction ("credible medical SaaS, calm, product-forward"), component-level:
- **Hero:** keep the two-column grid; replace the 300px phone mock with a larger *tablet-frame*
  product shot — either a real localized screenshot pair (fa + en assets, swapped by lang) or an
  enriched token-built mock showing the actual report surface (treatments + safety chip), sized
  `min(520px, 100%)`. Add a soft radial/gradient backdrop behind the hero
  (`--color-primary-soft` wash) for depth.
- **Section rhythm:** alternate section backgrounds (page / surface-soft full-bleed bands), add a
  small eyebrow label per section (existing `.eyebrow` class, `styles.css`), tighten
  `.landing-section` gap onto a spacing scale (48/64/96 rhythm via clamp).
- **How-it-works:** number chips stay; add a connecting line/arrow between steps ≥860px (mirrors
  via logical properties).
- **Trust:** promote `.landing-trust-item`s to iconed cards (shield/lock/device icons from the
  existing stroke-icon style).
- **Plans:** equal-height cards, Pro card elevated (`--shadow-float`), per-feature check rows
  already exist; add a "fair-use AI included" footnote row sourcing copy keys only.
- **Social proof placeholder:** a quiet strip between Trust and Plans — "Used in Tehran clinics" +
  3 grayscale placeholder logos/initials chips, keyed for later real logos.
- All new strings through `t()`; fa/RTL parity checked; no marketing copy authored in this pass.

**Accept:** hero communicates the product visually at 1280px; sections have distinct rhythm;
lighthouse a11y unchanged; fa rendering reviewed side-by-side with en.

---

## 4. Explicitly deferred to ux-epic-session-layout-diet (and PatientsHome wave)

- **Session/capture surface polish**: the zone stack, `.context-back-button` placement on
  `CaptureScreen.tsx:342`, the Sources drawer disclosure (`CaptureScreen.tsx:629`,
  `.sources-drawer-chev`), the "Show visit context" collapsed row
  (`SessionContextCard.tsx:70,126`) — the epic redesigns these zones wholesale; it should **adopt
  the T1.5 `DisclosureRow` and T1.2 header pattern** rather than restyle in place.
- **PatientsHome / `clinical-tabs`** (`PatientsHome.tsx:608`, `styles.css:12555`) — being redesigned
  next wave; T1.3's segmented `Tabs` is available to it but no change is made here.
- Token-sweep (T1.7) *may* touch session-surface selectors mechanically (exact hex → var), since
  that is zero-visual-diff; anything visual there waits for the epic.

## 5. Suggested sequencing

1. T1.1 + T1.7 (tokens/widths — unblocks everything, mostly mechanical)
2. T1.2, T1.3, T1.4, T1.5, T1.6 (shared components; independent of each other, parallelizable)
3. T2.1 Insights → T2.2 Settings (small) → T2.3 Landing (largest, isolated public surface)

Close-the-loop per CLAUDE.md §3 when building: update `docs/ux/screens/insights.md`,
`docs/ux/states.md` (empty-state pattern), `docs/frontend/overview.md` (width/token system), and
delete this doc after folding.
