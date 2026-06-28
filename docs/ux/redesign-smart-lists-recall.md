# Smart lists & lot recall — design note (AES-501 / AES-502)

> The Pro **smart-lists + lot-recall** cluster — the last committed slice of the aesthetics build
> ([aesthetics-stories.md](aesthetics-stories.md) E5). Companion to the spec
> [redesign-aesthetics.md §5](redesign-aesthetics.md) (smart lists + lot recall "live in Clinical
> Memory: filters over the structured data, and a recall lookup that returns every patient on a
> recalled lot and hands off to the patient channel"). Self-checked against
> [design-principles.md](../design-principles.md) — see §6.
>
> **Scope:** AES-501 (smart lists / filters) + AES-502 (lot/batch tracking + recall). Both are
> **deterministic, zero-AI** — built entirely from data the Pro synthesis *already* extracts. No new
> AI job; the eval gate ([CLAUDE.md §4](../../CLAUDE.md)) does not apply. **AES-705** (products & lots
> registry) is **postponed** — built directly off extracted lot/product values, with a clean seam
> (§5).

## 1 · The idea: two siblings, one surface

Smart lists and lot recall are the same move — **a deterministic query over the structured data Pro
extracts, returning a list you can act on.** They differ only in intent:

- **Smart lists (AES-501)** answer *"who needs my attention?"* — run the practice from the data.
- **Lot recall (AES-502)** answers *"who got this batch?"* — a product-safety lookup.

They share the query substrate (extracted `treatments[]`, photo pairing, visit recency), the result
primitive (a patient/visit list), and the handoff (tap into a patient; for recall, hand a cohort to
the patient channel). So they are designed as **one surface: a Pro-only "Lists" tab in Clinical
Memory** — not a new screen, not a dashboard.

```
Clinical Memory
┌─────────────────────────────────────────────┐
│  Today   Patients   [ Lists ]   Needs input  │   ← Lists is the Pro upgrade (Basic: 3 tabs)
├─────────────────────────────────────────────┤
│  SMART LISTS                                  │
│   ┌──────────────┐ ┌──────────────┐          │
│   │ Seen this wk │ │ Due to return│          │   ← named lenses, live counts, one-line defn
│   │      12      │ │       5      │          │
│   └──────────────┘ └──────────────┘          │
│   ┌──────────────┐                           │
│   │ Missing      │                           │
│   │ after-photo 3│                           │
│   └──────────────┘                           │
│                                              │
│  LOOK UP A LOT OR PRODUCT                     │
│   [ 🔎 lot # or product…           ]          │   ← serves "on product X" (501) + recall (502)
│   recent in your data: D-4471 · Dysport (3)  │
└─────────────────────────────────────────────┘
```

*Why a tab, not filters on Patients:* the existing Patients filters (`recent/active/all`) are scope
toggles over one list. Smart lists are **distinct named lenses** with their own counts and grains
(some patient-, some visit-scoped), and lot recall wants a focused, safety-grade space. A tab keeps
each lens legible and gives recall room — without turning Patients into a query builder.

*Why Basic gets nothing here (not even a teaser):* the tab is simply absent in Basic — a clean,
legible upgrade ([redesign-aesthetics.md §1](redesign-aesthetics.md): "Basic has none (legible
upgrade)"). The Patients-file `✨` already sells recall/AI-history (AES-804); a second teaser would
add upsell pressure the build deliberately removed ([redesign-aesthetics.md §8](redesign-aesthetics.md)).

## 2 · The smart lists (AES-501)

A **small, curated** set of named lenses — never a configurable analytics dashboard
([design-principles §2](../design-principles.md)). Each list is a deterministic predicate with a
**crisp definition shown in the UI**, so the count is trustworthy and the clinic knows exactly what
it means.

| List | Grain | Definition (deterministic) | Source field |
| --- | --- | --- | --- |
| **Seen this week** | patient | a visit `captured_at` within the last 7 days | `Session.captured_at` |
| **Due to return** | patient | most-recent visit ≥ **12 weeks** ago (re-engagement) | `max(Session.captured_at)` |
| **Missing after-photo** | visit | a photo paired as `before` with no matching `after` | `Capture.metadata.photo_pairing` |

- **Seen this week** — the "what happened this week" glance. Patient rows, context line
  *"Visited Jun 25"*, newest first.
- **Due to return** — the honest, deterministic form of the brief's *"due for follow-up."* There is
  **no structured follow-up date** in the data (the report's *Plan & follow-up* is prose — see §5),
  so we do **not** parse prose or invent a date. Instead: patients whose last visit was **12+ weeks**
  ago — the re-engagement list a clinic actually runs. The threshold is **shown** (*"Last seen 14
  weeks ago"*) and is the AES-705 seam to per-product precision (§5). Longest-overdue first.
- **Missing after-photo** — close-the-loop on before/afters. **Visit**-grained (a patient may have
  several), context line *"Botox · forehead · before photo, no after yet."* Tap → the visit. Powered
  by the deterministic pairing already computed for the Pro report (AES-104).

"On product X" from the brief is **not** a fixed-count list (it's parameterized) — it's served by the
lookup (§3), which browses by product as well as lot.

## 3 · Lot & product lookup + recall (AES-502)

One search box, two grains: a **product** filter (AES-501 "on product X") and an exact **lot**
recall (AES-502). The safety capability — so the bar is *trustworthy and unambiguous*.

**Browse / suggest.** The box is backed by the **lot ledger**: the distinct lots and products in the
clinic's extracted data, each with its product/brand and patient/visit counts (*"D-4471 · Dysport ·
3 patients, 4 visits"*). No typing-from-memory; the clinic picks from what it actually used.

**Recall a lot — the cohort.** Selecting a lot (or searching one) returns **every patient who
received it**, grounded and verifiable:

```
⚠ Lot recall · D-4471
3 patients · 4 visits received this lot.

  Sara M.            ☎ 0912…        [ Open channel ]
    Apr 12 · Dysport, forehead, 20u   "…lot D-4471…"   → visit
  Nima R.            ☎ 0935…        [ Open channel ]
    Mar 3 · Dysport, glabella, 12u    "…D 4471…"        → visit
  …
  Similar lots (not included): D-4471-A (1)            ← never folded in
```

**Trustworthy & unambiguous — the rules:**

- **Exact match, normalized only for case + whitespace.** A recall must not over- or under-match. We
  fold case and collapse internal spaces (`D 4471` == `d-4471`? no — see below) but never fuzzy-match.
  *Decision:* normalize = uppercase + strip + collapse runs of spaces. Hyphens/dots are **kept**
  (`D-4471` ≠ `D4471`). Near-misses surface in a separate **"Similar lots (not included)"** group so
  staff can act on them deliberately — never silently merged into the affected list.
- **Every row cites its source** — patient + visit date + the verbatim treatment (area · product ·
  units) + the extracted `evidence` snippet — so staff can verify each inclusion against the record.
- **A clear count summary** up top (*"3 patients · 4 visits"*) so the scope is unmistakable.
- **Attention, not alarm** — amber treatment, calm copy; it's a marker, never a blocker
  ([design-principles §7](../design-principles.md)).

**Outreach handoff.** "Hand the affected list off to the existing patient channel"
([redesign-aesthetics.md §5](redesign-aesthetics.md)) = the **post-session Q&A channel** (AES-402) —
the only built clinic→patient channel. Per affected patient, **Open channel** opens (or reuses) their
tokenized Q&A thread and yields a link to send (reusing `QaChannelButton` / `onOpenQaChannel`). The
clinic also gets **Copy affected list** for its own outreach workflow. We do **not** fake a bulk
"Message all" blast: automated SMS/WhatsApp is deferred ([redesign-aesthetics.md §10](redesign-aesthetics.md),
AES-404), and sharing is an explicit, per-patient, outward-facing action
([design-principles §7](../design-principles.md), [redesign-aesthetics.md §9](redesign-aesthetics.md)).
The AES-404 bulk-delivery seam is noted in §5.

## 4 · Backend — deterministic, Pro-gated

All read-only, all gate on the `live_report_synthesis` capability (Pro) → 403 for Basic, all
tenant-scoped. New service module `app/services/smart_lists.py` (lists + ledger + recall), routes in
`main.py`.

| Endpoint | Returns |
| --- | --- |
| `GET /smart-lists` | `{ counts: { "seen-this-week": n, "due-to-return": n, "missing-after-photo": n } }` — the rail, one round-trip |
| `GET /smart-lists/{key}` | `{ key, rows: [SmartListRow], total }` — one list's rows (paginated) |
| `GET /lot-ledger` | `{ lots: [{ lot, product, brand, patientCount, visitCount }], products: [{ name, kind, patientCount, visitCount }] }` |
| `GET /lot-recall?lot=` *or* `?product=` | `{ kind, value, normalized, patientCount, visitCount, affected: [PatientCohortRow], similar: [{ lot, ... }] }` |

`SmartListRow = { patientId, displayName, identifyingContext?, contextLabel, sessionId?, visitAt? }`
— `sessionId` set for visit-grained lists (tap → visit), null for patient-grained (tap → patient).

The query substrate is **`Session.extracted_metadata["treatments"]`** (the live, current treatments —
written by the synthesis worker; the immutable `SessionReportVersion` snapshots are for undo/versioning,
not "current state"). Photo pairing reads `Capture.metadata["photo_pairing"]`. All confirmed in code
before building (§7 of the report).

## 5 · The AES-705 seam (registry layers on later)

AES-705 (products & lots registry in Settings) is postponed. 501/502 read raw extracted values, but
the seam is kept clean so a registry enriches without reshaping anything:

- **Single aggregation point.** All lot/product reading lives in `smart_lists.py`'s ledger builder.
  A registry adds one validation/enrichment pass there (canonical lot → known product, expiry,
  "unknown lot" flag) — the `/lot-ledger` and `/lot-recall` response shapes already carry
  `product`/`brand` next to `lot`, so enrichment only *adds* fields (`expiry`, `known`, `canonicalLot`).
- **Recall stays exact.** The registry would let recall offer "did you mean canonical lot X?" via the
  existing **similar lots** channel — still never auto-merging.
- **"Due to return" → precise.** A registry carrying per-product typical duration upgrades the single
  12-week recency threshold into per-product "treatment due to wear off" — same list key, better
  predicate.
- **Bulk outreach (AES-404).** The per-patient channel handoff is the seam for automated SMS/WhatsApp:
  the cohort + links are already assembled; a delivery integration consumes the same list.

## 6 · Self-check vs. design principles

1. **Capture first** — untouched; Lists is a memory surface, never blocks capture. ✓
2. **Lightweight, not a dashboard** — the explicit risk. Mitigated: a *small fixed set* of named
   lenses + one lookup; no charts, pivots, or custom-query builder; lot recall is a *lookup*, not a
   products-admin screen (that's AES-705). ✓
3. **Active session clear** — unaffected. ✓
4. **Organize around current work** — smart lists *are* "memory organized around the clinician's
   current work," the opposite of a raw nested patient/session dump. This principle backs the feature. ✓
5. **Minimize primary actions** — capture bar stays primary; Lists is a secondary tab. ✓
6. **Hide technical AI details** — counts/rows just appear; no job/extraction internals; deterministic,
   so no AI states. ✓
7. **Warnings over blocking** — recall is amber attention, never a blocker; outreach explicit, never
   forced. ✓
8. **Capture bar trust anchor** — unaffected. ✓

## 7 · Frontend shape

- `features/memory/components/SmartListsTab.tsx` — the Lists tab: the smart-list rail, a list's rows
  (reusing `PatientRow` / `VisitCard` / `EmptyClinicalState` from `MemoryCards`), and the lot/product
  lookup + recall cohort. Mounted in `PatientsHome` for Pro only.
- `services/api/client.ts` — `fetchSmartLists`, `fetchSmartList`, `fetchLotLedger`, `fetchLotRecall`;
  types in `domain/appTypes.ts`.
- Outreach reuses `onOpenQaChannel` + `QaChannelButton`.
- **Bilingual (fa/en) + RTL** for all chrome via `t()` ([CLAUDE.md §5](../../CLAUDE.md)); clinical
  content (treatment phrases, lot strings) is verbatim, not translated.

## 8 · Out of scope / gaps noted

- **AES-705** registry — postponed (seam in §5).
- **AES-503** lot/expiry scan, **AES-404** bulk SMS/WhatsApp — deferred candidates
  ([redesign-aesthetics.md §10](redesign-aesthetics.md)); seams noted.
- **No structured follow-up date** in the data — "Due to return" is recency-based by design (§2); a
  structured plan/follow-up field would be the precise upgrade (gap, not built here).
