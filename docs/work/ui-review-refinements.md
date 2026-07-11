# UI expert review — refinement proposals (2026-07-10)

Process doc (create → decide → fold accepted items into stories/system-state → delete). Review ran
against the main dev stack (`en` chrome demo tenant, Pro doctor persona) at 390×844 and 768×1024;
screenshots under the session scratchpad (`ui-review/`). Items are **proposals** — the owner picks
what becomes an AES-### story.

> **Shipped (2026-07-11).** Items **#1, #2, #5, #7, #9, #10** are built + folded into stories +
> system-state docs: #1 → AES-1007, #2 → AES-1008 (both under
> [aesthetics-stories.md](../ux/aesthetics-stories.md) E10); #5/#7/#9/#10 → AES-1401–1404 (E14). See
> [screens/patients.md](../ux/screens/patients.md), [states.md](../ux/states.md) (Time Labels +
> Attention model), and [technical-decisions.md](../technical-decisions.md). **Still open:** #3, #4,
> #6, #8, #11, #12. Delete this doc once those are decided/shipped too.

## P1 — trust & coherence (recommend doing first)

1. **Unify the "needs me" numbers.** Within two screens a doctor sees three counts that never
   reconcile: the top-bar bell says `9+`, the Today chip says `3 need your input`, the Attention
   sweep says `0 of 12 cleared` — and the Today section below the chip says "All caught up.
   Nothing needs your input right now." For a product whose promise is *calm*, unexplained
   disagreeing counters are the fastest trust leak. Proposal: one Attention count (the sweep's),
   surfaced identically in the bell and the chip; scope labels («۳ مورد در همین صفحه») only where a
   filtered subset is genuinely shown; kill the chip when its section says "all caught up".
2. **Group Attention items per visit.** One seeded visit produced six sibling
   "Confirm treatment · سورنا معاضد" cards with overlapping asks (type? area? dose? brand/lot?).
   They flood the sweep and bury the two Verify-patient items. Proposal: group by visit —
   «سورنا معاضد — ۶ تأیید لازم» with one resolver that walks the visit's open confirmations
   (the sweep already opens per-source resolvers, so this is a list-shape change, not a flow change).
   Pipeline twin: teach synthesis to merge near-duplicate uncertainties (one entry per distinct
   unknown per treatment) — tracked with the prompt work, not the UI.
3. **`#insights` for a non-owner role: wrong guard, wrong state.** The account menu hides Insights
   for plain doctors, but direct `#insights` navigation renders the full screen, the API 403s, and
   the user sees "Could not load insights. Please try again." (with no retry affordance, and
   retrying can never help a 403). Proposal: route-guard owner/admin pages (redirect to `#patients`),
   and map 403 to the shared permission state from `docs/ux/states.md`, reserving "try again" +
   a Retry button for retryable failures.

## P2 — polish with real payoff

4. **One control language.** Side by side today: two top-bar pill styles, `Inbox|Library` and
   `Mine|Clinic` solid segments, a labelled `Routing` select, Insights' `This month ▾` select next
   to a `Compare to previous` outline pill. Proposal: a single segmented-control component and a
   single select trigger style (same height, radius, chevron), applied on Q&A inbox + Insights
   first. This is the "dropdowns not from the same universe" issue.
5. **Time format consistency.** The visit card renders `Visit: Jul 8 · 17:43` directly above
   `Updated: 5:43 PM` — one clock, two conventions. Pick per-locale (fa → ۲۴h Persian digits,
   en → one of the two) and route every timestamp through the same formatter.
6. **Empty-visit meta line.** A just-created visit reads `Created now · 0 captures · Updated
   recently` — three fragments, two of them redundant and jointly self-contradictory. Proposal:
   collapse to `Created just now`; add fragments only when they diverge.
7. **Drop the marketing subtitle on Clinical Memory.** "Your calm, intelligent assistant for
   capturing and organizing what matters most." costs a text row on every phone visit and praises
   rather than informs (violates the calm-professional principle it cites). The heading + chip +
   search already orient. Move the sentence to onboarding if it must live somewhere.
8. **QA-inbox empty state should teach.** "No conversations yet routed to you." is a dead end for a
   Pro feature the clinic pays for. Proposal: one sentence + action — how a thread arrives (patient
   asks via their share/Q&A link) and a "Share Q&A link" shortcut on a patient.

## P3 — smaller notes

9. **Icon-only nav pills at 390px** (Visit/Memory show labels only ≥~700px): the selected tint is
   subtle and the two glyphs are near-abstract for new users. Cheapest fix: keep labels at all
   widths (they fit at 390 with the current pill paddings), or strengthen the selected state.
10. **Tablet top-bar balance:** the `Engram` wordmark floats mid-bar after the bell, then a long
    gap to the avatar. Consider brand far-left before the pills (classic anchor) or centered with
    symmetric clusters; today it reads as leftover space.
11. **Landing hero mockup vs app truth:** the mockup highlights **Note** as primary and orders
    Note/Photo/Audio; the app's primary is **Record** (Record/Photo/Note). Align the mockup so the
    first-run app matches the promise.
12. **Dev-only "JUMP USAGE STATE" block** in Settings renders as four bare percentage links; style
    as small buttons inside a clearly dev-badged box (it already ships only in dev builds, but it
    visually leaks "broken" into an otherwise coherent screen).

## Verified non-issues

- **Capture-bar occlusion:** full-page screenshots show the fixed bar painted mid-list, but a live
  viewport scrolled to the bottom clears the bar with ample padding on Today/Attention/patient
  file — no defect (screenshot artifact).
- Note dialog copy ("Type the note now. Patient matching can wait.") and the finder's
  match-reason line ("Name starts with the query.") are genuinely good — keep.
- Landing page structure (capture-first hero, honest placeholder-pricing banner, AI-is-opt-in
  card) reads current, not dated.
