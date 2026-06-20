# Session patient-context + timeline round-trip

> The moment a patient is **determined** for the active session — by manual assignment **or** AI
> patient-matching — the clinician should immediately have the right prior context **at the session**,
> tier-appropriately, and be able to round-trip to the full patient timeline and back **without losing
> their place**. Today this is half-built (see Current state). Companion:
> [redesign-foundation.md](redesign-foundation.md), [redesign-aesthetics.md](redesign-aesthetics.md),
> [capture-intelligence-design.md](../ai_engine/capture-intelligence-design.md) (Job 4 powers the Pro side).

## Current state (the gap)

- **Basic:** a deterministic `LastVisitStrip` (AES-106) renders under the assignment — but only the prior
  visit's **concatenated typed note + ≤4 photo thumbs** + "Same as last time" + "View visit". It under-
  represents a visit (a visit is many captures) and shows only the *single* last visit.
- **Pro:** the strip is gated `!isPro` in `CaptureScreen.tsx` — so **Pro shows nothing** at the assignment
  point. The AI patient-memory exists only on the Memory screen, never surfaced at the session.
- **Round-trip:** "View visit" opens one visit in the Memory screen; returning to the in-progress capture
  session is manual (you lose your place). There's no "open the full timeline → come back to this visit".

## Principles

- **Capture-first is never blocked.** Context is a glanceable aid beside the capture flow, never a gate.
- **Glanceable first, depth on demand.** A compact card that answers "who is this / what happened last /
  what do I need to know" in ~3 seconds; the full timeline is one tap away.
- **Tier-aware:** Basic = *smart deterministic*; Pro = *intelligent (AI)* — genuinely more, not a reskin.
- **Round-trip without losing place:** session → full timeline → **back to this visit**, session intact.
- **Warnings over blocking; privacy-aware** (flags surfaced, internals stay internal).

## Trigger

Render/refresh the context surface whenever the session's `patientId` becomes known — **manual assign OR
AI match** — in **both tiers**. Clears if the patient is removed/reassigned.

---

## Basic context card (deterministic, "smart") — redesign

Replace the single-note strip with a **last-visit *digest* + cross-visit photo strip**. All deterministic,
zero AI.

- **Last visit digest** (not one note): the last session's **full** content, glanceable — all typed
  note(s), **all** its photos (thumbs + "+N"), and voice-memo count (playable). *Why:* a visit is many
  captures; one note hides most of what happened.
- **Recent-visits photo strip:** a compact before/after row **across the last N visits** (grouped by
  visit, recent prominent) for eyeball progress — the card-sized view of the AES-103 gallery. *Why:* "show
  progress at a glance" is the Basic value; one visit's photos isn't progress.
- **Deterministic key facts** (if present): patient-pinned notes/flags (allergies, preferences) surfaced
  at top; "Nth visit since <first-visit date>". *Why:* safety/recall facts shouldn't require a screen jump.
- **"Same as last time"** pre-fill (keep) + **"View full history →"** (the round-trip entry, below).

Backend: extend `get_last_visit` (or add `get_session_context`) to return the last session's full capture
set + a bounded **recent-visits media** list. Still zero AI.

---

## Pro context window (intelligent) — design

Pro has every prior capture, the structured **treatments[]** store, the synthesized reports, and AI. The
context window should be an **AI-assembled "everything you need to start this visit"** panel — proactive,
not just historical. Composed of these blocks (glanceable; expand for depth):

| Block | What it shows | Source |
|---|---|---|
| **Brief / "story so far"** | ≤2-sentence who-they-are + journey + goals | **Job 4** patient-memory summary (line-up card) |
| **Since last visit** | what changed since the last visit; elapsed time | **Job 4** delta line |
| **Last-visit recap** | AI summary of the last session + what was done | last session's **synthesis** report summary + `treatments[]` |
| **Treatment recall** | "what we've used": product · dose · area · lot · interval, across visits | **deterministic query** over `extracted_metadata.treatments` (no new AI) |
| **Flags & safety** | allergies, consent, contraindications, preferences | **Job 4** memory flags (+ deterministic flags) |
| **Before/after hero** | the hero photo + a journey before/after | **Job 4** `heroCaptureId` + **Job 2** pairing |
| **Suggested focus / "due for"** | what this visit is likely about; treatments due (e.g. "botox 10 wks ago, usually 12") | **NEW** — see below |
| **Open items** | unconfirmed carried-forward dose, pending patient Q&A, missing consent | **deterministic** (needs-input / Q&A / flags) |

### AI jobs behind it
- **Backbone = Job 4 (patient memory, in flight on `pro-memory`).** Its summary + history + **line-up card
  projection** (story-so-far, since-last delta, flags, hero) already produce most of the window. **This
  feature surfaces Job-4 output at the session by `patientId`** — no new heavy job for these blocks.
- **Treatment recall = deterministic** queries over `treatments[]` — *not* an AI job.
- **NEW: a "session-context / suggested-focus" projection.** Mostly deterministic + light AI:
  - *due-for* = **deterministic**: compute intervals from `treatments[]` dates per product/area.
  - *suggested focus* = **light AI**: 1 line on what this visit is likely about, grounded in the last
    report's plan/follow-up + the trajectory (NOT a clinical recommendation — a memory aid).
  - *open items* = **deterministic** from existing needs-input / Q&A / flags.
  **Design decision (for the owner):** implement this as an **extension of Job 4's output** (add a
  `sessionContext` field to the memory projection) rather than a new job — it shares Job 4's context and
  triggers. Keep "suggested focus" explicitly a *memory aid, never a clinical directive* (safety/liability).

### Pro guardrails
- Read-triggered like Job 4 (no cost on un-opened patients); deterministic fallback (gateway-less Pro →
  show the deterministic Basic-style digest + treatment recall, never blank).
- Everything is **assistive + cited** (tap a claim → the source visit/capture); never authoritative.
- Vertical-agnostic via the domain descriptor (therapy/derma reuse the same window, different content).

---

## Timeline round-trip (both tiers)

- On the context card: **"View full history →"** opens the patient's **full timeline** (the existing
  `PatientTimeline`), entered *from* the session.
- The timeline shows a persistent **"← Back to this visit"** that **restores the in-progress capture
  session exactly** (active session, drafts, scroll). *Why:* the current "View visit" loses the session;
  a clinician mid-capture must be able to glance at history and return in one tap.
- Tapping any prior visit in the timeline opens it read-only; "back" still returns to the active session.

---

## Sequencing & dependencies

- **Now / independent (Basic slice):** redesign the Basic card (last-visit digest + recent-visits strip) +
  build the **round-trip** (works for both tiers) + **un-gate Pro** to at least show the deterministic
  digest (so Pro is never blank).
- **After `pro-memory` (Job 4) merges:** swap Pro's deterministic placeholder for the **intelligent
  window** (Job-4 line-up projection surfaced at the session).
- **The "session-context / suggested-focus" projection** is a small Job-4 extension — schedule with or
  right after Job 4.
- **Needs a UX pass** (card layout for both tiers + the round-trip affordance) — adjacent to, but distinct
  from, the Story-C *report* design (this is the *session/assignment* surface).

## Open questions (for the owner)

1. **Basic card depth** — last-visit digest + a recent-visits photo strip (this design), or also a compact
   deterministic "treatments-ish" recall from free-text (riskier without structure)?
2. **Pro "suggested focus" proactiveness** — a light "likely about / due-for" memory aid (this design), or
   keep Pro purely retrospective (no anticipation) to avoid any directive feel?
3. **New job vs Job-4 extension** for `sessionContext`/due-for — extend Job 4 (recommended) or a separate
   lightweight job?
4. **Round-trip scope** — full timeline only, or also inline "peek" expansions on the card before a full
   navigation?
