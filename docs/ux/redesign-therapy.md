# Memara for Therapy — UX Design (greenfield)

> The therapy vertical of Memara (Spine A), designed **greenfield** — not aesthetics re-skinned.
> Grounded in [redesign-therapy-research.md](redesign-therapy-research.md); built on the shared
> foundation [redesign-foundation.md](redesign-foundation.md) and the capture/memory surfaces
> ([redesign-capture-surface.md](redesign-capture-surface.md), `patient-memory-states.html`).
> Status: **P2a design — pre-PMF, a later alpha** ([../spines.md](../spines.md) §4). Encounter label =
> **Session**. **Single plan** (no Basic/Pro). Prototypes: `../../apps/frontend/design-prototypes/therapy-*.html`.
>
> **Non-negotiables inherited from the foundation:** capture-first never blocks a role; the AI *is* the
> value (single tier); the patient-facing surface is one shared primitive (§4). **Added here, therapy-
> specific:** privacy is structural (two visibility planes), and risk/safety is a first-class element of
> memory.

---

## 1. Therapy in one screen

Aesthetics is *visual-first* (photos, before/after, treatment specifics). Therapy is **narrative-first
and longitudinal** — the value is *continuity of understanding across a relationship that unfolds over
months*. The clinician's hardest problem isn't writing the note; it's **walking into session N
remembering where session N−1 left off, what's been recurring, and what's unsafe to forget.**

So the product's center of gravity is **client memory**, and its front door is the **pre-session brief**.
Everything else — capture, summary, plan, measures — exists to *feed* memory and to *project* it back at
the moment of care. The note is a projection of memory, not the home.

Three structural commitments distinguish therapy from aesthetics:

- **Two visibility planes on every session** (research §4): a **shareable** summary (progress-note-shaped)
  and a **private** layer (the therapist's reflections + the dictation transcript). Patient-facing payloads
  and exports draw *only* from the shareable plane. This is built into the model, not a settings toggle.
- **Risk/safety is first-class memory** — persistent, dated, clinician-confirmed, surfaced at the top of
  the brief. The one thing a clinician must never walk in not knowing.
- **Note-first, free-stream capture — *not* session recording, *nothing required*.** The therapist stays
  **present**; capture is a free stream of optional items — **typed notes in-session** (auto-decorated),
  **audio when alone** — that the system **continuously synthesizes**. The whole session is never recorded;
  nothing is forced — see §1.2.

### 1.1 Screen inventory (four surfaces)

| # | Surface | When | Role |
| --- | --- | --- | --- |
| 1 | **Pre-session brief** (§5.1) | before | the *distillation* — what you need to walk in |
| 2 | **Active session** (§5.2–5.3) | during/after | capture (notes + optional audio) + "Session so far" + the two-plane summary |
| 3 | **Past-session view** | anytime | a prior session's summary, read-only (surface 2 in read mode) |
| 4 | **Client memory / history** (§5.4) | anytime | the full *archive* — longitudinal summary + session timeline |

The **brief is the distillation; history is the archive.** The brief also carries a compact **arc strip**
(a mini-timeline) so the longitudinal context is present at the doorway without opening history (§5.1).

### 1.2 Capture model (the corrected core): a free stream, note-first, continuously synthesized

Capture is a **stream of optional captures** — the therapist just adds things; the system does the rest
(capture-first DNA, foundation §2). **Nothing is ever required** — not a recap, not a format, not a field.
The system **continuously synthesizes** a session summary from whatever exists (three terse notes → a
summary from three notes; add audio → richer). Capture types, by how they fit the *moment*:

- **Note (typed) — the in-session primary.** Mid-session the therapist is *with* the client; a discreet
  **typed note** is the natural tool (you can't narrate an audio jot aloud in the room without breaking it).
  Each note is **decorated** — the therapist types shorthand, the `note_decoration` capability cleans it
  into clinical prose, raw kept underneath + editable. *"bndry convo w mother — better than feared"* →
  *"Client reported the boundary conversation with her mother went better than she feared."*
- **Audio — secondary / after.** Natural when the therapist is *alone*: an optional **post-session recap**
  dictation, or a between-session voice jot. Never mid-session-primary, never required.
- **Photo — rare.** Therapy isn't visual.

*Why note-first + no full-session recording (cost + privacy):*

- **Cost.** ~24 min of session audio through a multimodal LLM is ≈40–50k input tokens **per session**; a
  short note is a tiny fraction, and a 1–2 min recap ≈3–4k. Note-first is the **cheapest** input there is.
- **Privacy.** A verbatim transcript of the client's most sensitive disclosures is the single worst object
  to store in a stigma-sensitive market. Notes and a therapist recap are **already filtered through clinical
  judgment** — their words, not the client's raw speech. (Mirrors Eleos's "ambient, not stored", research §3–4.)

**Two surfaces fall out of "continuous synthesis":** mid-session it's the **"Session so far"** panel — a
glanceable running synthesis that also tracks the **brief's threads as covered / open** (live agenda); after
session the *same* synthesis is the **two-plane summary** (§5.3). One synthesis, two temporal views.

**Ambient full-session capture is explicitly out of MVP** — a possible future, consent-gated, opt-in mode
for clinics that want it and accept the cost, never the default.

---

## 2. The feature set (the proposal for review)

Grouped by purpose. Build-status is a planning estimate (foundation §3): `(exists)` built today ·
`(new)` not built · `(modify)` built but needs therapy-shaping. "Engine" = shared Spine-A core we inherit.

### A. Memory spine — inherited engine, therapy-shaped

- **A1. Client memory** — longitudinal **summary + history**, therapy-shaped: *arc position*, *recurring
  themes*, *risk timeline*, *qualitative trajectory* (improving/stuck/worsening, derived from session
  memory — no formal instrument). Reuses the patient-memory artifact `(modify — therapy prompt-shaping)`.
- **A2. Capture-first sessions** — **note-first free stream** (§1.2); capture never requires picking
  a client; AI matching catches up, defaulting to the *scheduled* client `(modify)`.
- **A3. Transcription** (of jots/recap, not full sessions) `(exists)` · **note decoration** (shorthand →
  clinical prose) `(modify — mock today)` · **A4. AI client matching + out-of-context** `(exists)`.
- **A5. Smart search over memory** — Persian-aware, multi-field `(modify)`.

### B. The session loop — the signature

- **B1. Pre-session brief** — *the front door.* One screen before the client walks in: **arc strip
  (mini-timeline) → safety/risk → arc position → recurring themes → since last time → today's prompt.**
  Built on A1 `(new)`.
- **B2. Capture stream** — a free, **private-by-default** stream of optional captures: **note (typed,
  decorated) primary in-session**, **audio (recap/jot) secondary/after**, photo rare. **Nothing is required;**
  the system synthesizes from whatever's there (§1.2). `(modify)`
- **B2a. "Session so far"** — a glanceable, collapsible mid-session synthesis that also tracks the **brief's
  threads as covered / open** (live agenda). It is the two-plane synthesis (B3) viewed mid-session `(new)`.
- **B3. Narrative session summary, two planes** — the same synthesis after session: a **shareable**
  progress-note-shaped summary and a **private** reflections + audio-transcript layer; risk surfaced and
  dated. Default format **DAP-leaning**, with a quiet switch (DAP / SOAP / BIRP) `(new — structured synthesis behind narrative)`.

### C. The clinical thread — continuity

- **C1. Treatment thread** — a light **living plan**: focus areas / goals, memory-framed (not an insurance
  artifact); each summary references it; the brief shows "where we're heading" `(new)`.
- **C2. Themes & arc tracking** — recurring topics surfaced **across sessions**; part of synthesis `(new)`.
- **C3. Risk & safety** — clinician-confirmed flag (assisted detection), persistent + **dated**, with a
  **safety-plan** note attached; always top of the brief `(new)`.
- **C5. Recall / ask-the-memory** — "what have we covered about her mother?" over the client's history `(new)`.

### D. Reach — intake & the patient surface

- **D1. Intake & consent workflow (receptionist)** — create client, capture **informed consent + limits of
  confidentiality + privacy notice**, first-visit context; consent state **gates** the patient surface `(new presentation; client model exists)`.
- **D2. Patient-facing surface (therapy payload)** — a **privacy-gated** payload on the shared primitive
  (foundation §4): intake forms + consent, and a **withheld-by-default** session summary the clinician must
  *explicitly release*. (MVP scope; measures/check-ins are post-MVP — see below.) `(new payload)`.

### E. Privacy — cross-cutting, structural

- **E1. Two visibility planes** — shareable vs. private, enforced on every surface, export, and patient
  payload `(new)`.
- **E2. Dictation transcript as most-private object** — derive-and-de-emphasize; retention controls; never on
  a shared payload. (There is no full-session verbatim transcript to begin with — §1.2.) `(new)`.

### Post-MVP (designed-for, not built at launch)

- **C4. Measurement-based care** — Persian-localized PHQ-9 / GAD-7 on a cadence via the patient surface,
  auto-scored and trended into the brief. **Deferred:** it's a whole subsystem (instrument library +
  scoring + cadence + patient form UI + trend store), it depends on the heavier patient-surface build, and
  Persian validation/licensing is its own risk — disproportionate to a cash-pay market with no payer
  mandating outcomes. The brief's *qualitative* trajectory (A1) covers the core value for free until then.
- **Ambient full-session capture** — opt-in, consent-gated, for clinics that accept the cost (§1.2).

**Deliberately *not* in scope** (research §5): a 10-format note bazaar, built-in telehealth video, insurance/
billing, agency supervisor analytics (talk-ratio/empathy scoring). None is the wedge.

---

## 3. Personas & permissions (therapy-specific, under foundation §2)

| Persona | Can | Cannot | Therapy notes |
| --- | --- | --- | --- |
| **Therapist (clinician)** | Capture, read full memory incl. **private plane**, write/confirm risk, edit & **release** summaries, own the treatment thread | — | The only role that sees the private plane. |
| **Assistant** *(optional)* | Support documentation; read **shareable plane** | See private reflections/transcript; release to patient | Supervised practices only. |
| **Receptionist** | Create clients, capture **consent**, scheduling-adjacent context | See **any** clinical content (no summaries, no transcript, no risk detail) | Intake-only; the strongest privacy wall in Spine A. |
| **Patient (client)** | Via D2: complete **intake + consent**, read **only explicitly-released** summaries (measures/check-ins post-MVP) | See anything not released; see the private plane ever | Withheld-by-default. |

> **The receptionist wall is the therapy-specific sharpening of foundation §2.** In aesthetics a
> receptionist seeing visit context is benign; in therapy it is not. Reception creates the *container*
> (client + consent + appointment) and never sees clinical *content*. Capture-first still holds — the
> therapist can create-and-capture without reception.

---

## 4. User-journey maps

### 4.0 Entry points & assignment (capture is *never* gated by the brief)

There are **two ways into a session**, and capture-first (foundation §2) guarantees the second always works:

- **Planned path (common).** Therapy is scheduled, so the usual flow is *open client → brief → start
  session*. The brief is the recommended on-ramp — but it is an *on-ramp, not a gate*.
- **Capture-first path (invariant).** The therapist can **hit record / jot with no client selected** — a
  walk-in, a between-session phone call, or just starting to talk. **AI matching** assigns it afterward
  (A4, identical to aesthetics), **defaulting to the *scheduled* client** for that time-slot, so in practice
  capture-first is nearly frictionless here. Assignment is reversible; nothing blocks on it.

So assignment is **open from capture**; brief-then-session is the *common* path, never the *forced* one.

### 4.1 Therapist — the weekly loop (the core journey)

```text
BEFORE (in the doorway, ~60s)
  Open client → PRE-SESSION BRIEF
    0 Arc strip — mini-timeline S1..S7, phase shading, risk markers, today  [longitudinal context]
    1 Safety/risk flag (if any) — dated, with safety-plan link              [top, unmissable]
    2 Arc position — "Session 7 · mid-phase, working on boundaries"
    3 Recurring themes — threads that span sessions + open loops
    4 Since last time — what changed; qualitative trajectory ("anxiety easing")
    5 Today's prompt — one suggested opening, dismissible
  → walks in oriented, no chart-digging

DURING (presence, not recording — nothing required)
  Discreet typed NOTES as needed → each auto-DECORATED (shorthand → clean prose).
  Glanceable "SESSION SO FAR" panel: a running synthesis + the brief's threads
  shown COVERED ✓ / OPEN ◦ — a live agenda. Audio jot only if natural. All private.

AFTER (optional, when alone)
  Optionally add a short audio RECAP — or just end; the summary is already built
  from the notes. If a brief thread was left uncovered, a GENTLE NUDGE offers
  "add a note / recap?" — dismissible, never blocking.
  → The continuous synthesis is the NARRATIVE SUMMARY in two planes:
      • SHAREABLE (DAP-leaning): what happened, response, plan — releasable
      • PRIVATE: reflections, hypotheses, any audio transcript — therapist-only
  Therapist reviews → edits → (optionally) RELEASES the shareable plane to the client.
  Risk, if present, is confirmed + dated here.
  → MEMORY UPDATES: summary, history, themes, arc, trajectory, treatment thread.
```

**First session with a new client** is a variant: no prior memory → the brief shows the **intake context**
(reason for referral, consent state) instead of an arc; the captures + summary seed memory; the therapist
sets the initial **treatment thread**.

### 4.2 Receptionist — intake & the container

```text
New client inquiry
  → Create client (name, contact, national ID) · duplicate guard
  → Send intake link (D2): demographics, presenting concern, history
  → Capture CONSENT: informed consent · limits of confidentiality · privacy notice
      (consent state is recorded on the client; it GATES the patient surface)
  → Schedule-adjacent context handed to the therapist's first-session brief
Ongoing: manage clients & appointments. NEVER sees summaries, transcripts, or risk.
```

### 4.3 Patient (client) — the narrow, privacy-gated surface

```text
Onboarding: open intake link → complete forms + consent
After a session: see a summary ONLY IF the therapist explicitly released it
  → default state is "nothing shared," by design (research §4.5, stigma context)
Between sessions (POST-MVP): complete measures on cadence (C4); optional light check-in
Everything is RTL/Persian-native; minimal, calm, no clinical jargon leaked.
```

---

## 5. Surface specs

Prototypes referenced are under `../../apps/frontend/design-prototypes/`. Visual language matches the
existing prototypes (Inter, the `--color-*` tokens, pill chips, `✨` provenance mark, RTL-on-Persian).
A therapy accent (calm teal/green) distinguishes the vertical from aesthetics blue without forking the system.

### 5.1 Pre-session brief — `therapy-pre-session-brief.html` (signature)

A single calm card opened from the client, designed to be *read in the doorway*. It opens with a
**longitudinal band** (the arc strip) so the brief isn't just "last session," then the urgency-ordered
sections (research §6):

0. **Arc strip (mini-timeline)** — a compact horizontal row of session nodes (S1…S7), **phase-shaded**
   (early / mid / consolidation), with **risk markers** on the sessions where a flag was set and **today**
   highlighted. Tap any node → that past session; tap the strip → full history (§5.4). *This is the fix for
   "the brief only sees N−1": the trajectory of the whole relationship is visible at a glance.*
1. **Safety banner** — only if a risk flag is active: severity + **date set** + *Safety plan* link +
   *who/when confirmed*. Tinted (amber/red), never dismissible while active. If no risk: a quiet
   "No active safety flags" reassurance.
2. **Arc position** — "Session 7 · mid-phase" + the treatment thread's current focus (C1).
3. **Recurring themes** — 2–4 threads that **span sessions** (+ open loops), each tappable into history —
   not just last-session topics.
4. **Since last time** — what changed since the last session + a **qualitative trajectory** chip
   ("anxiety easing" / "holding" / "harder week"), **derived from session memory — no formal instrument**.
   (When MBC ships post-MVP, a measured sparkline can sit here; the qualitative read carries v1.)
5. **Today's prompt** — one AI-suggested opening line, clearly labelled `✨ suggestion` and dismissible.

Provenance + states reuse `patient-memory-states.html`: `✨` marks synthesized content; while memory is
refreshing the brief shows the calm *Organizing memory* cue; if the AI is down it shows the **structural
fallback** (last summary + visit list) rather than nothing — **never an error, never empty**. The brief is
read-only synthesis; its primary action is **Start session** (→ 5.2).

### 5.2 In/post-session capture — `therapy-session.html`

A **free capture stream, note-first, continuously synthesized** (§1.2). Nothing is required.

- **Capture bar (note-first):** **Note** primary (a discreet typed jot — the in-session tool), **Audio**
  secondary (recap/voice jot, natural when alone), **Photo** faint. A persistent
  `Capturing for: <client> · Session N` cue, and a private-by-default line. **No "record the session"
  affordance.**
- **Decorated notes:** the therapist types **shorthand**; each note shows the **`✨ decorated`** clinical
  prose with the **raw text kept underneath + inline Edit** (the `note_decoration` capability). Low effort
  in, clean text out — and the cheapest possible input.
- **"Session so far" panel** (B2a) — a collapsible strip at the top of the Captures tab: a one-line
  **running synthesis** (`✨`) + the **brief's threads as chips, covered ✓ / open ◦** (a live agenda the
  therapist can glance at without leaving presence). It's the two-plane synthesis (§5.3) viewed mid-session.
- **Gentle nudge, never a block:** if a brief thread is left **open** at session end (or the session looks
  thin), a dismissible nudge offers *"Job ambivalence was on the brief but not captured — add a note or a
  quick recap?"* The therapist can always ignore it; nothing is enforced.
- **Private-by-default:** every capture lands in the **private plane**; no patient sees raw captures, ever (E2).
- **Matching** still runs (A4): assignment chips, out-of-context handling. Capture is **never gated by the
  brief** (§4.0); matching defaults to the scheduled client. RTL-on-Persian; no before/after (aesthetics-only).

### 5.3 Narrative session summary, two planes — `therapy-session.html` (Summary tab)

The therapy analogue of the aesthetics "Live report," restructured around the **two planes**:

- A **plane switch** in the card header: **Shareable | Private** (the therapy parallel of aesthetics'
  Captures | Live report). A small **format** control on the shareable plane (DAP default · SOAP · BIRP).
- **Shareable plane** — narrative, progress-note-shaped, **releasable**. DAP default sections:
  **Data** (what the client reported + observable) · **Assessment** (clinical impression, progress vs. the
  treatment thread, risk status) · **Plan** (next focus, homework, follow-up). Reads like prose, not a form.
- **Private plane** — the therapist's **reflections/hypotheses** + **any audio transcript** (a recap/jot, if
  the therapist recorded one; many sessions are notes-only and have none) — most-private, collapsible,
  retention-controlled. There is **no whole-session verbatim transcript** (§1.2). Visually distinct
  (private/lock accent); **never exportable to a patient payload**.
- **Release control** — an explicit **Release to client** action on the shareable plane only; until pressed,
  the patient surface shows nothing for this session. A released summary shows a `Released <date>` badge;
  re-release after edits is explicit.
- **Risk capture** — a **Flag risk** affordance writes a dated C3 entry to memory + prompts a safety-plan
  note; risk status echoes into the shareable Assessment. Risk is **clinician-confirmed**, never auto-set.
- Same live/no-gate behavior as aesthetics (auto-derived **Complete** badge; no manual verify gate for the
  *report* — but **release is always an explicit, separate act**, because therapy sharing is consequential).

### 5.4 Longitudinal history — reuses `patient-memory-states.html`, therapy-shaped

The patient detail view, therapy sections: **Snapshot · Arc / Story so far · Recurring themes · Risk
timeline · Qualitative trajectory · Recent sessions** (the full session timeline the brief's arc strip
distills). Same memory-refresh states and provenance. The treatment thread (C1) sits here as an editable
"Where we're heading" block. *(A measured outcome trend slots in here once MBC ships — §2 Post-MVP.)*

### 5.5 Intake & patient surface — `therapy-intake-patient.html`

Two linked views on one shared primitive (foundation §4):

- **Receptionist intake** — create client (+ duplicate guard), send intake, and the **consent capture**
  block (informed consent · limits of confidentiality · privacy notice) with state recorded on the client.
  Reception sees **no clinical content** — the screen makes that wall visible.
- **Patient surface (MVP)** — RTL/Persian, calm, minimal: **intake forms + consent**, and a **released
  summaries** area that is **empty by default** ("Your therapist hasn't shared anything yet" — a deliberate,
  reassuring state, not a gap). *(Measures-on-cadence + between-session check-in are the post-MVP additions
  here, slotting into the same surface — §2 Post-MVP.)*

---

## 6. User-story inventory

`As a <persona>, I want <goal>, so that <value>.` Tagged **[persona]** and **build-status** (foundation §6).
Personas: **TH** therapist · **RC** receptionist · **PT** patient · **AS** assistant.

### Pre-session brief (B1) — the signature

- **[TH] (new)** As a therapist, I want a one-screen brief before the client walks in, so I walk in
  oriented without digging through past notes.
  *Accept:* opens in <1 tap from the client; ordered arc-strip→safety→arc→themes→since-last→prompt; readable in ~60s.
- **[TH] (new)** As a therapist, I want a **compact arc strip (mini-timeline) of all sessions** in the brief,
  so I see the whole trajectory, not just last session. *Accept:* nodes S1…N, phase-shaded, risk-marked, today
  highlighted; node → past session, strip → full history.
- **[TH] (new)** As a therapist, I want any active **safety/risk flag at the very top with its date**, so I
  never miss it.
  *Accept:* active flag is pinned, tinted, non-dismissible, shows date + confirmer + safety-plan link.
- **[TH] (new)** As a therapist, I want **recurring themes that span sessions** (+ open loops), so I pick up
  the thread. *Accept:* 2–4 cross-session threads, each tappable into history; sourced from synthesis (`✨`).
- **[TH] (new)** As a therapist, I want **what changed since last time + a qualitative trajectory**, so I
  gauge movement at a glance. *Accept:* since-last summary + a trajectory chip ("easing"/"holding"/"harder")
  derived from memory — no formal instrument required.
- **[TH] (new)** As a therapist, I want the brief to **degrade gracefully when AI is down**, so it's never
  blank. *Accept:* structural fallback (last summary + session list + the durable safety flag), no error state.

### Capture & summary (B2/B3, E1/E2)

- **[TH] (modify)** As a therapist, I want to **capture with discreet typed notes (auto-decorated) plus
  optional audio — never a whole-session recording, and never forced**, so it's present, cheap, and private
  (§1.2). *Accept:* Note primary / Audio secondary; notes decorated (raw kept + editable); no
  continuous-record control; the system synthesizes from whatever's captured.
- **[TH] (new)** As a therapist, I want a **"Session so far" panel that tracks the brief's threads as
  covered / open**, so I see my agenda live without leaving presence. *Accept:* collapsible; running
  synthesis (`✨`); per-thread covered ✓ / open ◦; a left-open thread earns a dismissible nudge, never a block.
- **[TH] (modify)** As a therapist, I want **capture that never makes me pick a client first**, so it never
  interrupts presence. *Accept:* one tap to record unassigned; matching catches up, defaulting to the
  scheduled client; works offline; **never gated by the brief** (§4.0).
- **[TH] (new)** As a therapist, I want **everything I capture to be private by default**, so nothing reaches
  a client without my act. *Accept:* captures land in the private plane; a banner states it; no payload reads them.
- **[TH] (new)** As a therapist, I want the summary in **two planes — shareable and private**, so I keep my
  process notes separate from what I might share. *Accept:* plane switch; private plane holds reflections +
  the *recap* transcript; export/patient payload draw only from shareable. *(research §4.1)*
- **[TH] (new)** As a therapist, I want to **choose the note format** (DAP/SOAP/BIRP), so it fits how I
  document. *Accept:* DAP default; switch re-projects the same content; no data loss.
- **[TH] (new)** As a therapist, I want to **explicitly release** a summary to the client, so sharing is
  always deliberate. *Accept:* nothing is patient-visible until Release; `Released <date>` badge; re-release explicit.
- **[TH] (new)** As a therapist, I want to **flag risk with a date and a safety-plan note**, so risk is
  durable, dated memory. *Accept:* clinician-confirmed (never auto-set); writes a dated C3 entry; echoes into Assessment + the next brief.
- **[TH] (exists)** As a therapist, I want **transcription + AI matching** as today, so the engine value carries over.

### Continuity (C1/C2/C5, A1/A5)

- **[TH] (new)** As a therapist, I want a **light living treatment thread (focus/goals)**, so each session
  connects to where we're heading. *Accept:* editable focus on history; referenced by each summary + brief; memory-framed, not an insurance form.
- **[TH] (new)** As a therapist, I want **recurring themes surfaced across sessions**, so I see patterns I'd
  otherwise lose. *Accept:* themes derive from synthesis; tappable to source sessions.
- **[TH] (new)** As a therapist, I want to **ask the client's memory a question** ("what have we covered
  about her mother?"), so recall is instant. *Accept:* answers cite the sessions they draw from.
- **[TH] (modify)** As a therapist, I want **Persian-aware search** across my clients & memory, so I find
  people and threads fast.

### Measurement-based care (C4) — *post-MVP*

- **[TH] (later)** As a therapist, I want to **send a measure (PHQ-9/GAD-7) on a cadence and see it trended**,
  so I track outcomes without manual scoring. *Accept:* Persian-localized; auto-scored; trend feeds the brief; fully optional.
- **[PT] (later)** As a client, I want to **complete measures on my phone in Persian**, so it's quick and
  private. *Accept:* RTL; mobile; results visible to me as a simple trend if my therapist enables it.

> Deferred from MVP (§2 Post-MVP): a whole subsystem, dependent on the heavier patient surface, with Persian
> validation/licensing risk — disproportionate to the wedge. The brief's qualitative trajectory covers the
> core value until then.

### Intake & reception (D1)

- **[RC] (new)** As a receptionist, I want to **create a client and capture consent (incl. limits of
  confidentiality)**, so the clinical container is ready and compliant. *Accept:* duplicate guard; consent state recorded; gates the patient surface.
- **[RC] (new)** As a receptionist, I want to **manage clients/appointments without seeing any clinical
  content**, so client privacy is protected by design. *Accept:* no summaries/transcripts/risk visible to RC — the wall is enforced + visible.
- **[TH] (modify)** As a therapist, I want to **create-and-capture a client myself without waiting on
  reception**, so capture-first never blocks (foundation §2). *Accept:* therapist-created client; reception/consent catches up.

### Patient surface (D2, foundation §4)

- **[PT] (new)** As a client, I want to **complete intake and consent before my first session**, so the
  first session starts on the work. *Accept:* RTL packet; consent recorded; flows to the therapist's first-session brief.
- **[PT] (new)** As a client, I want to **see only what my therapist has explicitly shared**, so I'm never
  exposed to raw notes. *Accept:* released summaries only; default empty state is reassuring, not a gap.
- **[AS] (new)** As an assistant, I want to **help with documentation but not see private reflections or
  release to clients**, so supervision boundaries hold. *Accept:* AS sees shareable plane only; no release; no private plane.

---

## 7. Privacy model (the structural spine) — E1/E2

```text
   capture stream (NOT the session): ┌──────────────────── SESSION ────────────────────┐
   • typed NOTES (decorated)         │   PRIVATE PLANE                 SHAREABLE PLANE  │
   • optional AUDIO (recap/jot) ─────┼─► reflections, hypotheses, ───► narrative summary│
   (audio transcript, if any, =      │   audio transcript (if any)     (DAP/SOAP/BIRP)  │
    most-private, E2 — no full        └───────────┬──────────────────────────┬───────────┘
    session verbatim)                            │ therapist-only           │ therapist edits
                                                  ▼                          ▼ + explicit RELEASE
                                            (never exported)        patient surface / export
   who sees what:
     Therapist  → both planes      Assistant → shareable only      Receptionist → neither (container only)
     Patient    → only RELEASED shareable summaries
```

Invariants: there is **no whole-session verbatim transcript** to begin with (§1.2); a patient payload or
export **never** reads the private plane or any audio transcript; **release is always an explicit therapist
act**; **risk flags are clinician-confirmed and dated**; consent state gates the patient surface. These
mirror the HIPAA psychotherapy-note rule **by construction** (research §4.1).

---

## 8. States & copy

Reuse [states.md](states.md) + the memory-refresh states in `patient-memory-states.html`. Therapy-specific:

- **Empty patient surface** (default) → *"Your therapist hasn't shared anything yet."* — reassurance, not a gap.
- **No active risk** → *"No active safety flags."* — present and calm, so its absence is informative.
- **AI down** → brief/summary fall back to structural memory; **no error, ever** (foundation behavior).
- **Private-by-default** → the capture/summary surfaces always state the privacy posture in plain words.
- All Persian content is RTL-native; assistant language follows the user's setting (en/fa).

---

## 9. Prototypes

- `therapy-pre-session-brief.html` — the signature surface (§5.1): arc strip, risk banner, arc position,
  recurring themes, qualitative trajectory, prompt, and the AI-down fallback.
- `therapy-session.html` — **note-first capture stream** (decorated notes, the "Session so far"
  thread-coverage panel, optional audio, private-by-default) plus the two-plane narrative summary with the
  Release control (§5.2–5.3).
- `therapy-intake-patient.html` — receptionist intake/consent (the privacy wall) + the privacy-gated patient
  surface (§5.5).

## 10. Open questions (for human review)

1. **Treatment thread depth** — full goals/objectives/interventions, or just "current focus" for v1? (Proposed: current focus + light goals.)
2. **Nudge sensitivity** — *nothing is required*; the system only nudges when something looks missing (a brief thread left open, a thin session). How eager should that nudge be, and on which signals? (Proposed: quiet, end-of-session, brief-thread-driven, always dismissible.)
3. **Assistant persona** — include at v1, or therapist+receptionist only? (Proposed: design the wall now, ship AS later.)
4. **Risk detection assist** — how forward-leaning should AI be in *suggesting* a risk flag vs. staying silent until the clinician raises it? (Proposed: gentle suggestion, clinician-confirmed.)
5. **Audio retention window** — when a therapist *does* record audio (recap/jot), how long do we keep the raw audio + verbatim transcript (the most-private object, E2) before auto-deleting and keeping only the derived summary? (Proposed: short default, e.g. 30–90 days, configurable; many sessions are notes-only with no audio at all.)
6. **Ambient full capture (post-MVP)** — do we ever offer opt-in whole-session capture given the cost/privacy cost (§1.2), or stay note/dictation-only? (Proposed: revisit only on real demand from a design partner.)
7. **MBC at launch (post-MVP)** — when MBC lands, PHQ-9 + GAD-7 only or a small library? Persian validation/licensing to confirm.
