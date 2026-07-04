# UX Epic — Unified finder

**Status:** design proposal for owner review. Not built. Do not fold into system-state until approved.

**Fold destination (when approved + built):** [`docs/ux/screens/search.md`](../ux/screens/search.md)
(rewrite Search → the finder — the current "local substring over loaded sessions" doc becomes the
finder spec), [`docs/ux/navigation.md`](../ux/navigation.md) (the finder entry points + keyboard
launcher), [`docs/ux/screens/patients.md`](../ux/screens/patients.md) (cross-link lot recall from
the finder), and a new `AES-12xx` band in [`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md).

> Priority **3 of 5**. Details the deferred backend-search "Known Gap" in
> [search.md](../ux/screens/search.md) and promotes the strong-but-buried
> [AES-204](../ux/aesthetics-stories.md) Persian patient search to the top-level surface.

---

## 1. Problem & evidence

The app has **three siloed retrieval surfaces**, and the most prominent one is the weakest:

| Surface | What it actually does | Strength |
| --- | --- | --- |
| **Top-nav Search** (`/#search`) | **local substring** filter over sessions **already loaded** in the client | weak — no backend, no patients not in memory |
| **Patients tab** (Clinical Memory) | the **real** search: backend, Persian-orthography-aware, paginated, at scale | strong — but **buried** two levels in |
| **Lists tab** (Pro) | lot/product **recall** cohort — the recall-under-stress tool | strong — but buried, and unknown to a stressed user |

**Grounded in code:**

- `SearchHome` (`features/memory/components/SearchHome.tsx`) filters the in-memory `sessions` prop:
  `[label, summary, patientName, reviewReason, …items].join(" ").toLowerCase().includes(query)`.
  **No `apiFetch`, no endpoint.** A patient the client hasn't loaded is invisible to the top-nav box.
- The real search is `searchPatientsSmart` → `GET /api/v1/patients/search` (AES-204: deterministic,
  Persian-aware, ranked). It is wired **only** to `PatientsHome` (`onSmartSearch`) and only fires on
  the Patients tab (`PatientsHome.tsx`, debounced 280 ms). The prominent Search box never calls it.
  (The assignment sheets use a *different, plainer* `searchPatients` → `GET /patients?query=`.)
- Lot recall is `LotLookup` / `RecallCohort` in `SmartListsTab.tsx`, backed by `GET /lot-ledger` +
  `GET /lot-recall`. It lives inside Clinical Memory → **Lists** (Pro), reachable only by tab.
- **No global omnibox, command palette, or keyboard launcher exists** — confirmed by grep for
  `cmd/ctrl/meta+k`, `omnibox`, `command palette`, `launcher`. Every `keydown` handler is local.

Net: the box a clinician reaches for first is the one that can't find a patient by name; the search
that *can* is hidden; and the one safety-grade lookup that matters under stress (a lot recall) is
three taps deep behind a tab a panicked user won't remember.

## 2. Design goal & principles

**One patients-first, app-wide finder**, reachable from anywhere, backed by the real search — plus the
Pro lot lookup promoted into it for recall-under-stress.

Principles ([design-principles.md](../design-principles.md)):

- **Lightweight, not a database browser** (§2) — a finder overlay, not a new heavy screen.
- **Patients-first** (§4) — the primary grain is the patient (the clinic's real object), not a
  session row.
- **Deterministic + instant** — patient search is zero-AI and fast at scale (AES-204); lot recall is
  **exact-match, safety-grade** (never fuzzy).
- **Bilingual + RTL** ([CLAUDE.md §5](../../CLAUDE.md)) — Persian-orthography folding is the whole
  point of the real search; mixed-direction names bidi-isolated.

## 3. The design

### 3.1 One finder overlay, reachable from anywhere

The top-bar Search affordance opens a **finder overlay** (an omnibox sheet), not a separate tab-screen.
It replaces the local `/#search` screen as the top-level retrieval surface; the old local-substring
behavior survives only as an **offline fallback** (see §5). The overlay pushes one history level
(reuse `shared/lib/backStack.ts`, [navigation.md](../ux/navigation.md)) so hardware Back closes it.

**Result grains, ranked:**

1. **Patients** (primary) — backed by `GET /patients/search`: name / phone / national ID,
   Persian-orthography-aware, ranked, paginated. A row opens the patient timeline. Duplicate-guard
   aware (surfaces "looks like an existing patient" for reception).
2. **Visits** — recent + matching sessions (today's active, by patient, by date). Opens the visit in
   historical review.
3. **Lot / product** (Pro) — a lot- or product-shaped query surfaces the **recall cohort** action
   (exact-match, from the lot ledger). This is the recall-under-stress promotion.
4. **Report / capture content** — deferred (backend global content search is future migration work,
   [search.md Known Gaps](../ux/screens/search.md)); noted, not in v1.

### 3.2 States

```text
┌ Finder ────────────────────────────────────────── Mine ▾ ┐
│ 🔎  Search patients, visits, or a lot number…            │
├──────────────────────────────────────────────────────────┤
│ (empty / pre-query)                                       │
│   Recent patients      Sara M. · Reza K. · Niloofar A.    │
│   Today's visits       Follow-up · 4:23 PM  …             │
└──────────────────────────────────────────────────────────┘
```

- **Empty (pre-query):** recent patients + today's visits + the hint copy. Offline: `You're offline —
  patient search may be limited` ([states.md](../ux/states.md)) over local results.
- **Typing (patient):** debounced backend patient search; grouped `Patients` results with
  name + identifying context; Persian folding applied server-side.
- **Lot-shaped query** (uppercase alphanumeric with hyphens/dots, matches the ledger): a distinct
  **`Recall lot D-4471 · N patients`** action appears above patient results. Exact-match only;
  near-misses go to a separate `Similar lots (not included)` group — reuse the safety-grade Lists
  contract verbatim (never silently merge a near-miss into a recall cohort).
- **No results:** `No patient matches “…”. Create patient? · Search visits instead.`
- **Scope** `Mine` / `Clinic` (reuse [AES-904](../ux/aesthetics-stories.md)); default **Clinic** on
  the finder (you search the whole base; AES-904 says "clinic on search").

### 3.3 Entry points

- **Mobile:** the existing top-bar search icon opens the overlay (replaces navigating to `/#search`).
- **Desktop:** a **⌘K / Ctrl-K** launcher opens the overlay from anywhere (find-only, not a command
  palette — see open questions). The icon shows the shortcut hint.
- **From context:** the assignment sheets keep their inline patient search, but can "expand to finder"
  to reach the full ranked search when the plain list isn't enough.

### 3.4 Copy (en, with fa notes)

| Surface | English | fa note |
| --- | --- | --- |
| Placeholder | `Search patients, visits, or a lot number…` | «جستجوی بیمار، ویزیت، یا شماره لات…» |
| Group heads | `Patients` · `Visits` · `Recall lot` · `Recent` | clinical nouns |
| Lot action | `Recall lot {lot} · {n} patients` | numbers tabular; lot stays LTR |
| Similar-lots | `Similar lots (not included)` | safety copy — never auto-merged |
| No results | `No patient matches “{q}”. Create patient?` | «بیماری با این مشخصات پیدا نشد» |
| Offline | `You're offline — patient search may be limited` | reuse the states.md string |

## 4. Tier & persona behaviour (per [foundation.md](../ux/foundation.md))

- **Basic:** patients + visits grains (deterministic, AES-204). **No lot/product grain** (Pro; the
  lot ledger is built from Pro extraction) — a legible upgrade, absent not teased.
- **Pro:** + the lot/product recall grain, with the outreach handoff (`Open channel` →
  [Q&A thread](../ux/screens/qa-inbox.md)) reachable from a recalled cohort, same as the Lists tab.
- **Reception / assistant:** patients-first is their core tool — find the record fast, avoid a
  duplicate (the finder surfaces the [AES-205](../ux/aesthetics-stories.md) duplicate guard as you
  type a new-looking name). Default their scope to `Clinic`.
- **Doctor / injector:** recall-under-stress lot lookup, and patient-by-name mid-visit without
  leaving capture (the finder overlays the capture screen; the capture bar stays the trust anchor
  underneath).

## 5. Edge cases

- **Offline / not-yet-loaded patients:** backend search is unavailable offline → fall back to the
  local substring over loaded sessions (today's `SearchHome` behavior, preserved) with the explicit
  "limited" note. Online, the finder always hits the backend so unloaded patients are findable.
- **Persian orthography:** confusables / Arabic-vs-Persian ye/kaf folding is server-side (AES-204
  normalization); mixed fa/en names bidi-isolated per-line so they don't scramble.
- **Lot exact-match safety:** never fuzzy; `D-4471 ≠ D4471`; similar lots in their own group;
  every recalled row cites its source (patient · visit · verbatim treatment line) — the Lists
  contract, unchanged.
- **Scale:** patient results are backend-paginated (`GET /patients/search` + `/patient-memory`);
  the overlay shows the top ranked N with "see all in Patients" spilling to the full tab.
- **Deep-link + Back:** a finder result → patient timeline / visit review / recall cohort each push
  a level; Back returns to the finder, then closes it (backStack batching).
- **Duplicate creation:** `Create patient?` from a no-results finder routes through the shared
  `PatientForm` **with** the duplicate guard — the finder must not become a duplicate factory.

## 6. Incremental build plan + AES-### candidates

Proposed as **candidate epic E12** (new band; not yet registered).

1. **AES-1201 — Finder overlay (patients-first).** The omnibox overlay, grouped grains, recent/empty
   state, `Mine`/`Clinic` scope, backStack integration — wired to `GET /patients/search`.
2. **AES-1202 — Finder backend search (patients + visits).** Promote `patients/search` to the finder;
   add a visit search (reuse `patient-memory` + session data). Global capture/report content search
   stays out of v1 (noted gap).
3. **AES-1203 — Lot/product recall grain (Pro).** Detect a lot/product query; surface the recall
   action; reuse `lot-ledger` / `lot-recall`, exact-match + similar-lots + source citations + the
   outreach handoff.
4. **AES-1204 — Replace `/#search`; offline fallback.** The finder becomes the top-level surface;
   local substring survives as the offline mode with the "limited" note.
5. **AES-1205 — Launcher + entry points.** Desktop ⌘K/Ctrl-K; mobile top-bar entry; "expand to
   finder" from assignment sheets.
6. **AES-1206 (⊕) — Global content search.** Backend search across captures / extracted findings /
   report prose (the [search.md](../ux/screens/search.md) future migration). Candidate — larger
   backend scope.

## Decisions & open questions

**Resolved (owner review, 2026-07-04):**

- **Replace `/#search`** with the finder overlay as the top-level surface (the route can still open
  the overlay for deep-links). Confirmed, conditional on the mobile experience — which is met: the
  finder is **mobile-first** (the existing top-bar search icon opens it as a full-screen sheet, the
  natural mobile pattern). ⌘K is a **desktop-only nicety** layered on top, not load-bearing, so the
  mobile experience does not depend on a keyboard launcher.

**Resolved (owner review, round 2 — 2026-07-04):**

- **Find-only in v1** (patients/visits/lots) — confirmed; actions/command-palette is v2.
- **Content search — deferred** to AES-1206 (report/capture prose search rides the later backend
  work; not a v1 must-have).
