# UX Epic — Tier convergence (converge the shell, keep the primary surface tier-appropriate)

**Status:** design proposal for owner review. Not built. Do not fold into system-state until approved.

**Fold destination (when approved + built):** [`docs/ux/screens/capture.md`](../ux/screens/capture.md)
("Surface by tier" — both tiers lose the tab switch and share one shell), possibly
[`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md) (AES-302 acceptance update), and a new
`AES-14xx` band there.

> Priority **5 of 5**. Shares the one-skeleton shell + patient strip with
> [session-layout-diet](ux-epic-session-layout-diet.md); the teaser placement is
> [E8](../ux/aesthetics-stories.md).
>
> **Revised after owner review (2026-07-04).** The original framing ("put Basic onto Pro's
> report-first layout") was **wrong** and is replaced below. *Why:* in Pro the report is a distinct,
> valuable synthesized artifact, so report-first earns its place; in **Basic the "report" is the same
> captures reformatted** — no new information — so making it primary forces the user to tunnel through
> a drawer to touch their own content, worst during capture. The right convergence is of the **shell
> (kill the legacy tab switch)**, not of the **primary surface**, which stays tier-appropriate.

---

## 1. Problem & evidence

Basic and Pro render a session with **two different interaction models**, and Basic's is a clunky
legacy one:

- **Basic** has a **Captures | Live-report tab switch** — two co-equal tabs the user toggles, one
  showing the raw feed, one showing a chronological document.
- **Pro** is a single report-first surface with the raw captures in a collapsible **Sources drawer**.

**Grounded in code** (`features/capture/components/CaptureScreen.tsx` + `LiveReport.tsx`):

- `const isPro = tier !== "basic"` → `const useUnifiedLayout = isPro`.
- **Basic** renders the tab switch (`{!useUnifiedLayout ? …}`): `capture.capturesTab` vs
  `capture.liveReportTab`, toggling `reportView` between `"draft"` and `"structured"`; the body
  swaps between the raw `captureFeed` and `LiveReportView`.
- **Pro** hides the tabs, always shows the report as the body, and puts captures in `.sources-drawer`
  (gated `useUnifiedLayout && captureCount > 0`) with one-tap undo-last.
- `BasicLiveReport` (`LiveReport.tsx`) maps `session.items` to chronological entries + a
  `TryProTeaser` — **no** treatments table, **no** Sources drawer.

Two problems, one real, one a mistaken fix:

1. **Real:** the tab switch is legacy cruft — a "which tab am I on" model no other screen uses, and a
   discontinuity from Pro (an upgrading clinic meets a different interaction model).
2. **Mistaken fix (the original epic):** "just adopt Pro's report-first for Basic." But **Basic's
   report is not a distinct artifact** — it is the captures + a header, chronological (AES-302). It
   carries no new information (zero AI, [foundation §1](../ux/foundation.md)). Making it primary buries
   the captures — the actual content the Basic user works with — behind a drawer they'd re-open every
   visit. Optimizing the rare upgrade moment over the daily Basic experience is the wrong trade,
   especially pre-PMF where most clinics are Basic.

## 2. Design goal

**Converge the *shell*, not the *primary surface*.** Kill the tab switch; give both tiers one
skeleton — **patient strip → a primary working surface → a secondary collapsible view → the capture
bar** — but let *what sits in "primary"* differ by tier, because the valuable artifact differs:

- **Pro:** primary = the **synthesized report** (a real AI artifact) · secondary = the **Sources**
  drawer (raw captures).
- **Basic:** primary = the **captures feed** (the content itself — seen and touched directly) ·
  secondary = a **Document / Share** view (the tidy chronological notebook, for review/print/share).

The Basic document isn't worthless — but its value is **outbound/at-share-time** (the "professional
artifact Apple Notes can't produce", AES-302/303/401), **not** the daily working surface. So it lives
where sharing lives (a *View as document / Share* affordance), not as the star of the capture screen.

This still delivers the convergence value: **no relearn on upgrade** (same skeleton, same drawer
pattern, same nav, same patient strip). What changes on upgrade is honest and desirable — the raw
captures move from primary → the Sources drawer, and a **new** synthesized report appears as primary:
*"your captures are still here; here's the AI report you're now paying for."* That's an upsell signal,
not a jarring migration.

## 3. The design

### 3.1 The shared skeleton (both tiers)

```text
[patient strip]              ← shared (Basic: simpler; Pro: + verify/safety chips — layout-diet epic)
[primary working surface]    ← Basic: the captures FEED   ·   Pro: the synthesized REPORT
[secondary collapsible view] ← Basic: “Document / Share”  ·   Pro: “Sources · N” (raw captures)
[Do more with Pro]           ← Basic only (E8 consolidated teaser, foot of the surface)
[capture bar]                ← shared, always the trust anchor
```

The **tab switch is deleted in both tiers.** The secondary is a drawer/affordance, never a co-equal
tab — so there is no "which tab am I on".

### 3.2 Basic — feed-first (the correction)

- The **captures feed is the persistent primary surface** — capture cards (audio player, photo, note)
  with their edit / rename / delete / source-preview affordances **directly reachable**, no drawer to
  open. During capture you always see what you just added.
- A **`View as document`** affordance (in the header or the share flow) opens the tidy chronological
  notebook (AES-302) for review / print, and flows into **Share** (AES-303 curated report). This is
  where the "report" concept lives in Basic — a review/outbound artifact, not the daily surface.
- No auto-collapse-to-document (that Pro behavior is wrong for Basic — the feed always leads).
- Absent, legibly: AI spark, synthesis/`Organizing` states, verify bar, safety panel, treatment
  table, freshness line — none apply to zero-AI Basic. The single foot teaser stays.

### 3.3 Pro — report-first (unchanged, correct)

Report primary + Sources drawer (raw captures, undo-last in header), auto-expanding while the report
is still building. Unchanged from today's Pro; the convergence just makes its *skeleton* the one
Basic also uses.

### 3.4 The upgrade moment

Basic → Pro ([Plan screen](../ux/navigation.md)) is a **continuity** event: same patient strip, same
secondary-drawer pattern, same capture bar, same nav. What changes: the primary flips from the feed to
the synthesized report; the raw feed slides into the Sources drawer; the AI spark + structured
sections + treatment table + verify/safety chips light up. **No layout migration, no relearned
interaction model** — the acceptance test for the epic.

### 3.5 Copy (en, with fa notes)

| Surface | English | fa note |
| --- | --- | --- |
| Basic secondary | `View as document` / `Share` | «نمایش به‌صورت سند» / «هم‌رسانی» |
| Pro secondary | `Sources · N` | «منابع» — same string as today |
| Undo | `Undo last capture` | «واگرد آخرین ثبت» |
| Basic audio entry | `Voice memo · 2m 14s · tap to play` | zero-AI: a playable memo, **never** "transcript" — see §5 |
| Teaser | `Do more with Pro` | «امکانات بیشتر با Pro» |

## 4. Tier & persona behaviour (per [foundation.md](../ux/foundation.md))

- **Basic doctor / assistant:** feed-first working surface + a document/share view; deterministic,
  offline-first, zero-AI — and the interaction model (primary surface + secondary drawer + strip +
  capture bar) is now the same one they'd meet on Pro.
- **Upgrading clinic:** zero relearning; the flip to report-first is an honest upsell signal.
- **Reception:** mostly in Clinical Memory; minimally affected.

## 5. Edge cases

- **Basic audio (resolved — 2026-07-04).** Basic is **zero-AI**
  ([foundation §1](../ux/foundation.md) + [AES-101](../ux/aesthetics-stories.md)), so audio is a
  **voice-memo, not transcribed**. The conflicting claim in
  [patients.md](../ux/screens/patients.md) ("Basic has transcription but no summarization") **and in
  AES-206** ("Transcript saved — open the visit") are **wrong** and are a system-state fix to sweep
  separately from this epic. The Basic feed renders audio as a playable memo (`Voice memo · 2m 14s`),
  never a transcript.
- **Empty state:** feed-first with capture-first guidance (already in
  [capture.md](../ux/screens/capture.md) states).
- **Offline:** Basic is local-first; the shell change is presentational and offline-safe.
- **Capability-gated zones:** the shared shell must omit the Pro-only zones cleanly in Basic (no empty
  bands) — dovetails with the [layout-diet](ux-epic-session-layout-diet.md) strip (Basic lights up
  fewer chips).
- **Historical review:** Basic historical visits use the same feed-first structure; the document view
  is reachable for review/share.

## 6. Incremental build plan + AES-### candidates

Proposed as **candidate epic E14** (new band; not yet registered).

1. **AES-1401 — Kill the tab switch; one shared skeleton.** Remove the Captures/Live-report tabs;
   render both tiers as `patient strip → primary surface → secondary collapsible view → capture bar`.
   Layout unification is tier-independent; the AI features stay capability-gated.
2. **AES-1402 — Basic feed-first surface.** The captures feed is the persistent primary (direct
   edit/play/delete); no drawer to open for daily work.
3. **AES-1403 — Basic `View as document` / Share.** The tidy chronological notebook (AES-302) becomes
   a review/print view flowing into the curated Share (AES-303) — the document's real home in Basic.
4. **AES-1404 — Capability-gated AI-zone omission.** Verify bar, safety panel, AI spark, freshness,
   treatment table omitted (not disabled) in Basic; the single foot teaser stays.
5. **AES-1405 — Upgrade-continuity verification.** A QA scenario proving Basic → Pro changes only what
   the AI adds (primary flips feed→report, feed → Sources), not the interaction model.
6. **AES-1406 — Align with the layout-diet strip + E8 teaser.** Share the patient strip (Basic
   variant) and the consolidated teaser placement.

## Decisions (owner review, round 2 — 2026-07-04)

1. **`View as document` in Basic — both entry points** (as recommended): a lightweight header
   affordance on the capture screen *and* the Share-flow entry.
2. **Retire "Live report" wording in Basic — YES**; use `Document` / `Visit record`.
3. **System-state cleanup — APPROVED:** fix the Basic-audio contradiction (patients.md + AES-206)
   independently of this epic (done in the same review pass that recorded these decisions).
