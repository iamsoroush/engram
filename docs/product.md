# Product

> Current product, top of funnel: what Engram is, who uses it, its shape, and the durable accepted
> behaviors. Strategy and sequencing live in [spines.md](spines.md); tier semantics in
> [spines.md](spines.md) §3; screen-level UX in [ux/overview.md](ux/overview.md); the capture→intent
> apply-semantics contract in [intelligence-layer.md](intelligence-layer.md).

## Purpose & promise

Engram is **capture-first clinical memory**. Clinicians document visits today across phone photos,
Apple Notes, voice memos, and messaging apps — fast in the moment, useless as memory. Engram keeps
capture that fast and turns it into organized, longitudinal patient memory.

The promise: **fast capture with progressively organized clinical memory.** Capture first, organize
later, review naturally during downtime — never block the clinician with rigid workflows.

## Users

- **Doctor / injector / therapist** — captures during visits, reviews generated session output,
  answers patient Q&A (Pro).
- **Owner** — the clinic's founding user from self-serve sign-up; a full superset of doctor + admin.
  Manages Team, Plan, and the Insights analytics panel.
- **Assistant** — captures, assigns patients, reviews session memory.
- **Admin** — read-oriented management (Team, Plan, Insights); no capture.
- **Patient** — not an account. Reached through public token links: a curated report + aftercare
  share page, and a Q&A page (Pro) where they ask questions and read doctor-verified replies.

## Product shape — verticals × tiers × surfaces

**Verticals** (editions of the same Spine-A core; see [spines.md](spines.md)):

- **Aesthetics** — the primary vertical, **live in production at engram.ir** with both tiers.
- **Therapy** — single plan; slice 1 built (note-first capture, two-plane session summary,
  federated private caseloads). Pre-session brief and intake/patient surface are later slices.
- **Dermatology** — next, after therapy's remaining slices.

**Tiers** — *Basic = recall (deterministic), Pro = understanding (AI)*. Aesthetics has Basic + Pro;
therapy is a single plan. Features gate on resolved **capabilities**, never on `tier` directly
([spines.md](spines.md) §3). The Pro AI layer: transcription, image captions, patient matching,
out-of-context detection, cross-visit synthesis (patient memory), live report synthesis, and
post-session patient Q&A. AI spend is metered per clinic with fair-use limits that pause background
enrichment at the budget — never capture ([business/ai-usage-limits.md](business/ai-usage-limits.md)).

**Surfaces:**

- **Staff app** — mobile-first, bilingual (fa/en) + RTL. Three primary screens: Active Session
  (capture + live report workspace), Clinical Memory (Today / Patients / Needs input — plus Lists
  with smart lists and lot recall on Pro), and Search. Pro adds a Q&A inbox. Account pages: Settings,
  Profile, Team, Plan, Insights (owner/admin).
- **Public patient surfaces** — separate token-link pages outside the staff shell, no login: the
  curated report/aftercare share and the patient Q&A thread (Pro). Revocable; a dead token shows one
  graceful "no longer available" screen.
- **Self-serve entry** — public landing → sign-up creates the clinic + founding owner and signs them
  straight in; a first-run onboarding tour follows.

## The core loop

1. **Capture first.** Audio, photo, or text in seconds — before any patient selection. Captures
   persist locally before upload; offline, capture keeps working and syncs later.
2. **AI organizes.** Transcription, captions, matching, and report synthesis run in the background.
   A deterministic report baseline is always current; synthesis quietly refines it. On Basic, the
   deterministic pipeline runs alone.
3. **Verify by exception.** Session completion is auto-derived — there is no manual verify gate.
   The Needs-input inbox surfaces only the items that genuinely require human judgment (patient
   assignment, out-of-context decisions, storage review).
4. **Patient timeline.** Everything lands in long-term patient memory: an AI-synthesized summary,
   the session timeline, and search — plus smart lists and exact-match lot recall (Pro).

## Core concepts

- **Patient** — the long-term memory container: synthesized history, session timeline, and
  needs-input indicators.
- **Session** (the vertical-typed Encounter) — the working object. It evolves continuously as
  captures arrive and AI processing updates the report; it stays accessible in every state.
- **Capture** — audio, photo, or text. Always immediate and lightweight.

## Accepted product behavior (durable)

- **Capture is never blocked** — not by patient selection, AI availability, network, or an exhausted
  AI budget.
- **Sessions remain reviewable and editable in all states.** States use assistant-like language,
  never job queues or backend failure labels.
- **Completion is derived, not gated.** Review reduces uncertainty by exception; nothing forces a
  verification step before the work counts.
- **Raw captures remain available** as expandable source material behind every AI output — trust
  through provenance.
- **Internal AI detail stays hidden** in normal use. When AI is unavailable, capture continues and
  organization catches up quietly.
- **UI chrome is bilingual (fa/en) + RTL-correct; clinical content follows the tenant's report
  language** — two independent axes.
- **Basic is genuinely AI-free** — a deterministic Notes-killer with standalone value, not a
  crippled Pro.
