# doc-impact — S2: app shell, navigation & account menu

Branch `i18n/s2-shell` off main `d14ee56`. Scope = the frame component `src/features/shell/Shell.tsx`
+ its CSS. Every shell chrome string now goes through `t()`; the shell is RTL-correct under fa.

## What shipped

- **`Shell.tsx`** — all chrome via `t()`: nav (`nav.*`), search + Q&A-inbox aria/title, account menu
  (`menu.*`), role label (`role.*`), offline banner + "Saving on this device" (`shell.*`), version
  footer (`shell.version`). **Zero hardcoded UI literals remain** (Shell.tsx dropped out of the guard
  baseline: 554→541).
- **Intentional Latin tokens kept untranslated + bidi-isolated** (`<bdi>`): brand wordmark
  `t("brand.name")` = "Engram" (same in both catalogs), tier pill "Pro"/"Basic" (matches the public
  surface). Bidi isolation prevents reorder against adjacent Persian in the RTL topbar (principle 4).
- **`role.*` full enum** (en+fa): owner, admin, doctor, assistant, therapist-b, patient-preview, user.
  `roleLabel` falls back to the raw role only for an unknown value — every reachable role has a key, so
  fa never renders raw English. (patient-preview/therapist-b don't reach the aesthetics shell — that
  gate / the therapy app render separately — but the keys exist for completeness + reuse in S5/team.)

## Amendment 1 — shell CSS physical→logical sweep (every change)

All edits in `src/styles.css`. After S2, **zero physical L/R properties remain in the shell selectors**
(verified by scanning the shell line ranges 1573–2017, 3872–3884, 5305–5561).

| selector | before | after |
| --- | --- | --- |
| `.user-menu summary` | `padding: 4px 10px 4px 6px` | `padding-block: 4px; padding-inline: 6px 10px` |
| `.user-menu-panel` (block 1) | `right: 0` | `inset-inline-end: 0` |
| `.user-menu-panel` (block 2) | `right: 0` | `inset-inline-end: 0` |
| `.user-menu-item` | `text-align: left` | `text-align: start` |
| `.app-version` | `right: 0; … left: 0` | `inset-inline: 0` |
| `.app-navigator button` (≤620px) | `padding-left: 12px; padding-right: 12px` | `padding-inline: 12px` |
| `[dir="rtl"] .user-menu-item-danger svg` (NEW) | — | `transform: scaleX(-1)` (logout mirror) |

> Note: the topbar layout already mirrors correctly — `.topbar-inner` is a 3-col grid with
> `grid-column` placement + `.user-menu { justify-self: end }`, all of which flip under `dir=rtl`
> automatically. `.topbar-left`/`.user-menu-*`/menu items are flex+gap (no physical margins), so child
> order auto-reverses. The stylesheet has TWO shell blocks (~1573 and ~5383, a redesign appended over
> the old); both `.user-menu-panel right:0` were fixed.

## Amendment 2 — shell icon mirror table

| icon | shape | directional? | mirror under RTL? |
| --- | --- | --- | --- |
| ActiveSessionNavIcon | document/checklist | no | no |
| ClinicalMemoryNavIcon | folder + person | no | no |
| SearchNavIcon | magnifier | no (object; RTL convention keeps search un-mirrored) | no |
| QaInboxNavIcon | chat/inbox bubble | no | no |
| `.user-menu summary::after` | disclosure caret "v" | vertical (down) | no |
| ProfileMenuIcon | person | no | no |
| SettingsMenuIcon | gear | no | no |
| TeamMenuIcon | people | no | no |
| PlanMenuIcon | clipboard/card | no | no |
| SwitchClinicMenuIcon | two horizontal swap arrows | bidirectional (symmetric) | no (mirror is a no-op) |
| GuideMenuIcon | help "?" in circle | no (help-icon convention; not punctuation) | no |
| **LogoutMenuIcon** | door + exit arrow → | **yes (exit points "out")** | **yes — `scaleX(-1)`** |

Only the logout glyph is directional; it is mirrored under `[dir="rtl"]` so the exit arrow points
toward the inline-start edge.

## Translations (oracle for the gating spec)

| key | en | fa |
| --- | --- | --- |
| nav.activeSession / .short | Active Session / Session | جلسهٔ فعال / جلسه |
| nav.memory / .short | Clinical Memory / Memory | حافظهٔ بالینی / حافظه |
| nav.search | Search | جستجو |
| nav.qaInbox | Q&A inbox | صندوق پرسش‌وپاسخ |
| menu.profile / settings / team / plan | Profile / Settings / Team / Plan | نمایه / تنظیمات / تیم / پلن |
| menu.switchClinic / replayGuide / logout | Switch clinic / Replay guide / Logout | تغییر کلینیک / نمایش دوبارهٔ راهنما / خروج |
| role.owner / admin / doctor / assistant | Owner / Admin / Doctor / Assistant | مالک / مدیر / پزشک / دستیار |
| shell.offline | Offline · Captures are saved on this device | آفلاین · ثبت‌ها روی این دستگاه ذخیره می‌شوند |
| shell.savingOnDevice | Saving on this device | در حال ذخیره روی این دستگاه |

## Decisions / notes for the Planner

- **`پلن` (Plan)** — kept the loanword (common in Iranian SaaS); the Evaluator flagged طرح/اشتراک as
  alternatives. Deferred to the Planner's wording pass; trivially swappable (one catalog key).
- **`MVP v2` version footer** routed through `t("shell.version")` (same value both langs) so Shell has
  zero raw literals; it's a non-localized version token, not prose.
- The two-block shell CSS duplication (old + redesign) is pre-existing tech debt, not addressed here.
