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
  and a **private** layer (the therapist's reflections + the raw transcript/audio). Patient-facing payloads
  and exports draw *only* from the shareable plane. This is built into the model, not a settings toggle.
- **Risk/safety is first-class memory** — persistent, dated, clinician-confirmed, surfaced at the top of
  the brief. The one thing a clinician must never walk in not knowing.
- **Audio-first, narrative capture** — no template gate. Talk; the system writes the narrative and threads
  it into memory.

---

## 2. The feature set (the proposal for review)

Grouped by purpose. Build-status is a planning estimate (foundation §3): `(exists)` built today ·
`(new)` not built · `(modify)` built but needs therapy-shaping. "Engine" = shared Spine-A core we inherit.

### A. Memory spine — inherited engine, therapy-shaped
- **A1. Client memory** — longitudinal **summary + history**, therapy-shaped: *arc position*, *recurring
  themes*, *risk timeline*, *outcome trend*. Reuses the patient-memory artifact `(modify — therapy prompt-shaping)`.
- **A2. Capture-first sessions** — audio-first; note secondary; capture never requires picking a client `(modify)`.
- **A3. Transcription** `(exists — in therapy capability set)` · **A4. AI client matching + out-of-context** `(exists)`.
- **A5. Smart search over memory** — Persian-aware, multi-field `(modify)`.

### B. The session loop — the signature
- **B1. Pre-session brief** — *the front door.* One screen before the client walks in: **safety/risk → arc
  position → themes to revisit → since last time (incl. outcome trend) → today's prompt.** Built on A1 `(new)`.
- **B2. In/post-session capture** — audio-first, narrative, private-by-default; mid-session jots + a
  post-session dictation `(modify)`.
- **B3. Narrative session summary, two planes** — a **shareable** progress-note-shaped summary and a
  **private** reflections + transcript layer; risk surfaced and dated. Default narrative format is
  **DAP-leaning**, with a quiet format switch (DAP / SOAP / BIRP) `(new — structured synthesis behind narrative)`.

### C. The clinical thread — continuity
- **C1. Treatment thread** — a light **living plan**: focus areas / goals, memory-framed (not an insurance
  artifact); each summary references it; the brief shows "where we're heading" `(new)`.
- **C2. Themes & arc tracking** — recurring topics surfaced across sessions; part of synthesis `(new)`.
- **C3. Risk & safety** — clinician-confirmed flag (assisted detection), persistent + **dated**, with a
  **safety-plan** note attached; always top of the brief `(new)`.
- **C4. Measurement-based care** — *optional, trend-first.* Persian-localized PHQ-9 / GAD-7 etc., completed
  via the patient surface on a cadence, auto-scored, **trended**; the trend (not the form) feeds B1 `(new)`.
- **C5. Recall / ask-the-memory** — "what have we covered about her mother?" over the client's history `(new)`.

### D. Reach — intake & the patient surface
- **D1. Intake & consent workflow (receptionist)** — create client, capture **informed consent + limits of
  confidentiality + privacy notice**, first-visit context; consent state **gates** the patient surface `(new presentation; client model exists)`.
- **D2. Patient-facing surface (therapy payload)** — a **privacy-gated** payload on the shared primitive
  (foundation §4): intake forms, measures (C4), optional between-session check-in, and a **withheld-by-
  default** session summary the clinician must *explicitly release* `(new payload)`.

### E. Privacy — cross-cutting, structural
- **E1. Two visibility planes** — shareable vs. private, enforced on every surface, export, and patient
  payload `(new)`.
- **E2. Transcript/audio as most-private object** — derive-and-de-emphasize; retention controls; never on a
  shared payload `(new)`.

**Deliberately *not* in v1** (research §5): a 10-format note bazaar, built-in telehealth video, insurance/
billing, agency supervisor analytics (talk-ratio/empathy scoring). Add later; none is the wedge.

---

## 3. Personas & permissions (therapy-specific, under foundation §2)

| Persona | Can | Cannot | Therapy notes |
|---|---|---|---|
| **Therapist (clinician)** | Capture, read full memory incl. **private plane**, write/confirm risk, edit & **release** summaries, own the treatment thread | — | The only role that sees the private plane. |
| **Assistant** *(optional)* | Support documentation; read **shareable plane** | See private reflections/transcript; release to patient | Supervised practices only. |
| **Receptionist** | Create clients, capture **consent**, scheduling-adjacent context | See **any** clinical content (no summaries, no transcript, no risk detail) | Intake-only; the strongest privacy wall in Spine A. |
| **Patient (client)** | Via D2: complete intake/measures, optional check-in, read **only explicitly-released** summaries | See anything not released; see the private plane ever | Withheld-by-default. |

> **The receptionist wall is the therapy-specific sharpening of foundation §2.** In aesthetics a
> receptionist seeing visit context is benign; in therapy it is not. Reception creates the *container*
> (client + consent + appointment) and never sees clinical *content*. Capture-first still holds — the
> therapist can create-and-capture without reception.

---

## 4. User-journey maps

### 4.1 Therapist — the weekly loop (the core journey)

```
BEFORE (in the doorway, ~60s)
  Open client → PRE-SESSION BRIEF
    1 Safety/risk flag (if any) — dated, with safety-plan link        [top, unmissable]
    2 Arc position — "Session 7 · mid-phase, working on boundaries"
    3 Themes to revisit — recurring threads + open loops from last time
    4 Since last time — what changed; outcome trend (GAD-7 ▼4)
    5 Today's prompt — one suggested opening, dismissible
  → walks in oriented, no chart-digging

DURING
  Capture stays out of the way: optional mid-session audio jot / note.
  Default is presence, not typing. (Privacy: private-by-default.)

AFTER (post-session, ~2 min)
  Dictate a quick recap (audio-first) OR rely on session audio.
  → System drafts the NARRATIVE SUMMARY in two planes:
      • SHAREABLE (DAP-leaning): what happened, response, plan — releasable
      • PRIVATE: reflections, hypotheses, raw transcript — therapist-only
  Therapist reviews → edits → (optionally) RELEASES the shareable plane to the client.
  Risk, if present, is confirmed + dated here.
  → MEMORY UPDATES: summary, history, themes, arc, trend, treatment thread.
```

**First session with a new client** is a variant: no prior memory → the brief shows the **intake context**
(reason for referral, consent state, baseline measures) instead of an arc; capture + summary seed memory;
the therapist sets the initial **treatment thread**.

### 4.2 Receptionist — intake & the container

```
New client inquiry
  → Create client (name, contact, national ID) · duplicate guard
  → Send intake link (D2): demographics, presenting concern, history, baseline measures
  → Capture CONSENT: informed consent · limits of confidentiality · privacy notice
      (consent state is recorded on the client; it GATES the patient surface)
  → Schedule-adjacent context handed to the therapist's first-session brief
Ongoing: manage clients & appointments. NEVER sees summaries, transcripts, or risk.
```

### 4.3 Patient (client) — the narrow, privacy-gated surface

```
Onboarding: open intake link → complete forms + consent + baseline measures
Between sessions: complete measures on cadence (C4); optional light check-in
After a session: see a summary ONLY IF the therapist explicitly released it
  → default state is "nothing shared," by design (research §4.5, stigma context)
Everything is RTL/Persian-native; minimal, calm, no clinical jargon leaked.
```

---

## 5. Surface specs

Prototypes referenced are under `../../apps/frontend/design-prototypes/`. Visual language matches the
existing prototypes (Inter, the `--color-*` tokens, pill chips, `✨` provenance mark, RTL-on-Persian).
A therapy accent (calm teal/green) distinguishes the vertical from aesthetics blue without forking the system.

### 5.1 Pre-session brief — `therapy-pre-session-brief.html` (signature)

A single calm card opened from the client, designed to be *read in the doorway*. Sections, **ordered by
clinical urgency** (research §6):

1. **Safety banner** — only if a risk flag is active: severity + **date set** + *Safety plan* link +
   *who/when confirmed*. Tinted (amber/red), never dismissible while active. If no risk: a quiet
   "No active safety flags" reassurance.
2. **Arc position** — "Session 7 · mid-phase" + the treatment thread's current focus (C1).
3. **Themes to revisit** — 2–4 recurring threads / open loops, each tappable into history.
4. **Since last time** — what changed since the last session + an **outcome-trend** strip (C4) — a small
   sparkline + delta ("GAD-7 12 → 8 ▼4 over 4 weeks").
5. **Today's prompt** — one AI-suggested opening line, clearly labelled `✨ suggestion` and dismissible.

Provenance + states reuse `patient-memory-states.html`: `✨` marks synthesized content; while memory is
refreshing the brief shows the calm *Organizing memory* cue; if the AI is down it shows the **structural
fallback** (last summary + visit list) rather than nothing — **never an error, never empty**. The brief is
read-only synthesis; its primary action is **Start session** (→ 5.2).

### 5.2 In/post-session capture — `therapy-session.html`

Reuses the capture surface (`redesign-capture-surface.md`), therapy-shaped:

- **Capture bar:** **Audio** primary (audio-first), **Note** secondary, **Photo** rare (de-emphasized —
  therapy is not visual). A persistent `Capturing for: <client> · Today's session` cue.
- **Private-by-default banner:** every capture lands in the **private plane**; a calm line states
  "Captures are private to you until you release a summary." No patient sees raw captures, ever (E2).
- **Captures tab:** the chronological feed (transcript blocks, notes), with inline **Edit** on generated
  text, RTL-on-Persian. No before/after, no treatment-item extraction (aesthetics-only).
- **Matching** still runs (A4): assignment chips, out-of-context handling — identical mechanics, calmer copy.

### 5.3 Narrative session summary, two planes — `therapy-session.html` (Summary tab)

The therapy analogue of the aesthetics "Live report," restructured around the **two planes**:

- A **plane switch** in the card header: **Shareable | Private** (the therapy parallel of aesthetics'
  Captures | Live report). A small **format** control on the shareable plane (DAP default · SOAP · BIRP).
- **Shareable plane** — narrative, progress-note-shaped, **releasable**. DAP default sections:
  **Data** (what the client reported + observable) · **Assessment** (clinical impression, progress vs. the
  treatment thread, risk status) · **Plan** (next focus, homework, follow-up). Reads like prose, not a form.
- **Private plane** — the therapist's **reflections/hypotheses** + the **raw transcript** (most-private,
  collapsible, retention-controlled). Visually distinct (a private/lock accent); **never exportable to a
  patient payload**.
- **Release control** — an explicit **Release to client** action on the shareable plane only; until pressed,
  the patient surface shows nothing for this session. A released summary shows a `Released <date>` badge;
  re-release after edits is explicit.
- **Risk capture** — a **Flag risk** affordance writes a dated C3 entry to memory + prompts a safety-plan
  note; risk status echoes into the shareable Assessment. Risk is **clinician-confirmed**, never auto-set.
- Same live/no-gate behavior as aesthetics (auto-derived **Complete** badge; no manual verify gate for the
  *report* — but **release is always an explicit, separate act**, because therapy sharing is consequential).

### 5.4 Longitudinal history — reuses `patient-memory-states.html`, therapy-shaped

The patient detail view, therapy sections: **Snapshot · Arc / Story so far · Recurring themes · Risk
timeline · Outcome trend · Recent sessions.** Same memory-refresh states and provenance. The treatment
thread (C1) sits here as an editable "Where we're heading" block.

### 5.5 Intake & patient surface — `therapy-intake-patient.html`

Two linked views on one shared primitive (foundation §4):

- **Receptionist intake** — create client (+ duplicate guard), send intake, and the **consent capture**
  block (informed consent · limits of confidentiality · privacy notice) with state recorded on the client.
  Reception sees **no clinical content** — the screen makes that wall visible.
- **Patient surface** — RTL/Persian, calm, minimal: intake forms, **measures** on cadence (C4) with a tiny
  trend the client can see, optional check-in, and a **released summaries** area that is **empty by default**
  ("Your therapist hasn't shared anything yet" — a deliberate, reassuring state, not a gap).

---

## 6. User-story inventory

`As a <persona>, I want <goal>, so that <value>.` Tagged **[persona]** and **build-status** (foundation §6).
Personas: **TH** therapist · **RC** receptionist · **PT** patient · **AS** assistant.

### Pre-session brief (B1) — the signature
- **[TH] (new)** As a therapist, I want a one-screen brief before the client walks in, so I walk in
  oriented without digging through past notes.
  *Accept:* opens in <1 tap from the client; ordered safety→arc→themes→since-last→prompt; readable in ~60s.
- **[TH] (new)** As a therapist, I want any active **safety/risk flag at the very top with its date**, so I
  never miss it.
  *Accept:* active flag is pinned, tinted, non-dismissible, shows date + confirmer + safety-plan link.
- **[TH] (new)** As a therapist, I want **themes/open loops from last time**, so I can pick up the thread.
  *Accept:* 2–4 recurring threads, each tappable into history; sourced from synthesis (`✨`).
- **[TH] (new)** As a therapist, I want **what changed since last time + the outcome trend**, so I gauge
  movement at a glance. *Accept:* since-last delta + measure sparkline (e.g. GAD-7 ▼4); absent if no measures.
- **[TH] (new)** As a therapist, I want the brief to **degrade gracefully when AI is down**, so it's never
  blank. *Accept:* structural fallback (last summary + session list), no error state.

### Capture & summary (B2/B3, E1/E2)
- **[TH] (modify)** As a therapist, I want **audio-first capture that never asks me to pick a client first**,
  so capture never interrupts presence. *Accept:* one tap to record; matching catches up; works offline.
- **[TH] (new)** As a therapist, I want **everything I capture to be private by default**, so nothing reaches
  a client without my act. *Accept:* captures land in the private plane; a banner states it; no payload reads them.
- **[TH] (new)** As a therapist, I want the summary in **two planes — shareable and private**, so I keep my
  process notes separate from what I might share. *Accept:* plane switch; private plane holds reflections +
  transcript; export/patient payload draw only from shareable. *(research §4.1)*
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

### Measurement-based care (C4)
- **[TH] (new)** As a therapist, I want to **send a measure (PHQ-9/GAD-7) on a cadence and see it trended**,
  so I track outcomes without manual scoring. *Accept:* Persian-localized; auto-scored; trend feeds the brief; fully optional.
- **[PT] (new)** As a client, I want to **complete measures on my phone in Persian**, so it's quick and
  private. *Accept:* RTL; mobile; results visible to me as a simple trend if my therapist enables it.

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

```
                         ┌───────────────────────── SESSION ─────────────────────────┐
   raw audio / transcript│   PRIVATE PLANE                    SHAREABLE PLANE         │
   (most-private, E2) ───┼─► reflections, hypotheses,  ─────► narrative summary       │
                         │   verbatim content                 (DAP/SOAP/BIRP)         │
                         └───────────────┬────────────────────────────┬──────────────┘
                                         │ therapist-only              │ therapist edits
                                         ▼                             ▼ + explicit RELEASE
                                   (never exported)            patient surface / export
   who sees what:
     Therapist  → both planes      Assistant → shareable only      Receptionist → neither (container only)
     Patient    → only RELEASED shareable summaries
```

Invariants: a patient payload or export **never** reads the private plane or raw transcript; **release is
always an explicit therapist act**; **risk flags are clinician-confirmed and dated**; consent state gates
the patient surface. These mirror the HIPAA psychotherapy-note rule **by construction** (research §4.1).

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

- `therapy-pre-session-brief.html` — the signature surface (§5.1), incl. risk banner, arc, themes, trend, prompt, and AI-down fallback.
- `therapy-session.html` — capture (audio-first, private-by-default) + the two-plane narrative summary with the Release control (§5.2–5.3).
- `therapy-intake-patient.html` — receptionist intake/consent (the privacy wall) + the privacy-gated patient surface (§5.5).

## 10. Open questions (for human review)

1. **Treatment thread depth** — full goals/objectives/interventions, or just "current focus" for v1? (Proposed: current focus + light goals.)
2. **MBC instruments at launch** — PHQ-9 + GAD-7 only, or a small library? Persian validation/licensing to confirm.
3. **Assistant persona** — include at v1, or therapist+receptionist only? (Proposed: design the wall now, ship AS later.)
4. **Risk detection assist** — how forward-leaning should AI be in *suggesting* a risk flag vs. staying silent until the clinician raises it? (Proposed: gentle suggestion, clinician-confirmed.)
5. **Session audio retention** — default retention window for the most-private raw audio/transcript (E2).
