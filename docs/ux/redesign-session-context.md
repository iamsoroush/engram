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
  at top; "Nth visit since the first visit". *Why:* safety/recall facts shouldn't require a screen jump.
- **"Same as last time"** pre-fill (keep) + **"View full history →"** (the round-trip entry, below).

Backend: extend `get_last_visit` (or add `get_session_context`) to return the last session's full capture
set + a bounded **recent-visits media** list. Still zero AI.

---

## Pro context window (intelligent) — design

Pro has every prior capture, the structured **treatments[]** store, the synthesized reports, the photos,
and AI. The context window should feel like **a great human clinic assistant's pre-visit brief** — one who
reads the whole record, **predicts what matters for THIS patient at THIS moment**, and surfaces just that —
warmly, scannably — so the visit starts informed and the doctor's flow is easier and more joyful. The
intelligence is in the **curation/prediction** (what's worth showing) and in **using everything, including
the photos** — never in clinical advice (see guardrail). The blocks below are the assistant's *palette*: it
**chooses, orders, and phrases what's salient** for each patient (it won't show all of them every time):

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
- **The pre-visit brief IS the centerpiece — a richer Job-4 synthesis** (`sessionContext` extension), not a
  due-for line. An *assistant-grade* pass that **predicts + curates**: the salient story, the most telling
  before/after, **visible progress read from the photos**, the patient's cadence (*due-for as a fact*), the
  doctor's own prior plan, and what needs attention — choosing what to show and how to phrase it. It may be
  **multimodal** (the Job-2 captions/pairing + a vision read of progress where it adds value). Deterministic
  pieces stay deterministic (due-for intervals, open items, treatment recall); the **curation + phrasing is
  the AI**. Implement as an **extension of Job 4** (shares its context + triggers). This is the heart of the
  Pro experience — careful prompt design + the same eval scrutiny as extraction.

### Safety flags (deterministic, cross-visit) — BUILT 2026-06-27

The **Flags & safety** block's `(+ deterministic flags)` is now real and **does not depend on Job 4**.
The Pro session synthesis emits a structured `safetyFlags: [{kind: allergy|contraindication|consent,
text, sourceCaptureIds}]` (grounded — only what a capture states, in the report language, never
invented). They are **opt-out** at capture (auto-kept; the clinician rejects a wrong one — see
[capture.md](screens/capture.md)); the **non-rejected** flags are projected onto a dedicated
`Patient.safety_flags` store (kept **out of** `patients.memory` so a Job-4 rebuild never wipes them).
This store is surfaced here — in the session-context card's flags slot at **every future visit** (via
`GET /patients/{id}/session-context` → `safetyFlags`) and on the patient timeline (`…/memory` →
`safetyFlags`). Fully deterministic: no AI job runs to surface them; Job 4's memory-card flags layer on
top when present. The clinical `text` is rendered verbatim (report language); only chrome is translated.

### Pro guardrails
- **Curate freely, never prescribe.** The assistant may decide what's relevant, predict what the doctor
  will want, narrate **visible progress from photos**, and surface the patient's own cadence + the doctor's
  own prior plans — but it must **never make a clinical recommendation** (no "you should", no suggested
  treatment/dose, no diagnosis, no "indicated/due" as a directive). The judgment is *what to surface*, not
  *what to do*; visual statements stay **observational** ("visible fullness up in the left cheek vs the Jan
  photo"), never diagnostic.
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
2. **Pro proactiveness — DECIDED: an assistant-grade pre-visit brief.** Be as smart as a great human clinic
   assistant at **predicting + curating what's valuable** from the whole record (incl. photos) and
   presenting it warmly — but **never make a clinical recommendation**. The judgment is *what to surface*,
   not *what to do*: due-for + visible progress are **facts/observations**, cited, never directives.
   Per-clinic suppressible.
3. **sessionContext/due-for — DECIDED: extend Job 4** (add a `sessionContext` field to the memory
   projection), not a separate job — it shares Job 4's context + triggers.
4. **Round-trip scope** — full timeline only, or also inline "peek" expansions on the card before a full
   navigation?
