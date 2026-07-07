# Finder (unified retrieval)

The one patients-first, app-wide retrieval surface. It replaces the old top-nav local-substring
search screen: online it hits the real, deterministic, Persian-orthography-aware patient search
(AES-204) plus the Pro lot recall (safety-grade, exact match); offline it falls back to a local
substring over the sessions already loaded on the device. Story band: **AES-1201..1206**
([aesthetics-stories §E12](../aesthetics-stories.md)).

## Surface

An **overlay**, not a screen — a mobile-first full-screen sheet that floats over whatever screen is
beneath (the capture bar stays the trust anchor underneath). It is not a route; it has no
`aria-current` nav pill.

## Entry points

- **Mobile / all sizes:** the top-bar **search affordance** (the magnifier icon) opens the overlay.
- **Desktop:** **⌘K / Ctrl-K** opens it from anywhere — a nicety layered on the mobile-first entry,
  not load-bearing (the mobile experience never depends on a keyboard launcher).
- **Deep-link:** `/#search` opens the overlay over the Clinical-Memory workspace and normalizes the
  hash to `#patients` (the retired search route survives only as this deep-link).
- **Dismissal:** hardware/browser **Back** (one history level via
  [`shared/lib/backStack`](../navigation.md#back-navigation-in-screen-levels)), the close control, or
  **Escape** (desktop).

## Result grains (ranked)

1. **Patients** (primary) — backed by `GET /patients/search`: name / phone / national ID,
   Persian-orthography-aware, ranked. A row shows the name + match reason + identifying context and
   opens the patient's timeline (Clinical Memory patient file). Because it is a real backend search, a
   patient the client never loaded is findable.
2. **Today's visits** — the pre-query grain: sessions captured today, from the already-loaded session
   list, so it renders instantly and works offline. A row opens the visit in historical review.
3. **Lot / product recall** (Pro) — a lot- or product-shaped query surfaces a distinct **Recall lot
   {lot}** action above the patient results. Selecting it runs the exact-match recall
   (`GET /lot-recall`) and renders a compact cohort inline: each affected patient cites its verbatim
   treatment line(s) (tap to open the visit), and near-miss lots sit in their own **Similar lots (not
   included)** group — never folded into the cohort (the safety contract, verbatim from the
   [Lists tab](patients.md)). The Q&A outreach handoff (Open channel) is reachable per patient. Absent
   on Basic (a legible upgrade, not teased). The recall grain composes the same `lot-ledger` /
   `lot-recall` endpoints the Lists tab uses.
4. **Report / capture content** — deferred (AES-1206): backend global content search across captures /
   extracted findings / report prose is later migration work, not in v1.

## States

- **Empty (pre-query):** Today's visits (local) + recent patients (`GET /patient-memory?filter=recent`)
  + a hint (search by name / phone / national ID, or a lot number for a recall).
- **Typing:** debounced (280 ms) backend patient search; grouped `Patients` results; Persian folding
  applied server-side.
- **No results:** `No patient matches "{q}".` with a duplicate-guarded **Add a patient** hand-off
  (routes to the Patients tab, which owns the shared `RegisterPatientForm` + duplicate guard — the
  finder never becomes a duplicate factory).
- **Offline:** the "patient search may be limited" note ([states.md](../states.md)); the backend
  grains are skipped and the query falls back to the local substring over loaded sessions (the
  preserved old top-nav Search behavior).

## Bilingual + RTL

All chrome routes through the `shared/i18n` `t()` seam (`finder.*` keys), fa + RTL; clinical CONTENT
(patient names, visit labels, verbatim treatment lines, lot strings) is rendered verbatim, never
translated, and bidi-isolated so mixed fa/en names don't scramble.

## v1 boundaries (deferred within the AES-12xx band)

- **`Mine` / `Clinic` scope** control (AES-904 reuse): the finder currently searches the whole clinic
  base (the `Clinic` default — "you search the whole base"); the explicit toggle is a fast-follow.
- **Add-a-patient prefill:** the hand-off navigates to the Patients tab; seeding the typed name into
  the create form is a nicety, deferred.
- **Global content search** (AES-1206) and **actions / command-palette** (v2): find-only in v1.
