# Aesthetics — User-Journey Maps (Basic + Pro, all personas)

> Deliverable 2 of the aesthetics design track (foundation §6). Per **persona** × per **tier**,
> phased across a real clinic day. The companion deliverables: comparable-product research
> [aesthetics-research-brief.md](aesthetics-research-brief.md), the build hand-off
> [aesthetics-stories.md](aesthetics-stories.md), and the spec + prototypes
> [redesign-aesthetics.md](redesign-aesthetics.md). North-star:
> [redesign-foundation.md](redesign-foundation.md). Current UX seams reused here:
> [redesign-capture-surface.md](redesign-capture-surface.md), [screens/patients.md](screens/patients.md),
> [states.md](states.md).
>
> **The seam is the point.** Each journey marks, at every step, what is **deterministic (Basic)**
> vs **AI (Pro)** and where a **✨ Try Pro** teaser sits. Reading the Basic and Pro columns of one
> persona side-by-side *is* the tier boundary. Nothing in the agreed set
> ([foundation §3](redesign-foundation.md)) is dropped; proposed extensions are flagged
> `⊕ candidate` and collected in [redesign-aesthetics.md §10](redesign-aesthetics.md).

## How to read

- **Personas** ([foundation §2](redesign-foundation.md)): **Doctor** (captures, treats, owns clinical
  content) · **Assistant** (supports documentation) · **Receptionist** (intake; creates/manages
  patients; scheduling-adjacent). **Patient** is read / limited-write via the patient surface
  ([foundation §4](redesign-foundation.md)) — covered in the patient micro-journeys at the end.
- **Phases** of an aesthetics encounter: **Before** (arrival/intake) · **During** (in-chair capture +
  treatment) · **After** (close-out, share, aftercare) · **Between** (recall, follow-up, patient Q&A).
- `det` = deterministic/zero-AI (works offline, instant). `ai` = AI-derived (Pro). `✨` = a Try-Pro
  teaser shown *in Basic* — labelled, non-functional, a conversion lever
  ([foundation §1](redesign-foundation.md)).
- The capture-first invariant: **no journey blocks on reception.** A doctor can capture before a
  patient exists; assignment catches up ([design-principles §1](../design-principles.md)).

## Cast & surfaces (quick reference)

| Surface | Primary persona | Tier notes |
| --- | --- | --- |
| **Active Session** (capture) | Doctor, Assistant | Basic: note+photo primary, audio = voice memo. Pro: audio-first, transcription, structured report. |
| **Clinical Memory** (Today / Patients / Needs input) | All | Pro adds smart lists, AI memory/history, recall, flags, lot recall. |
| **Patient detail** (gallery · treatment history · flags) | Doctor, Assistant | Before/after gallery + visit history are Basic; AI history, recall, flags are Pro. |
| **Front desk** (a lens on Clinical Memory · Today) | Receptionist | Registration + duplicate guard (Basic); AI matching reduces manual assign (Pro). |
| **Patient surface** (clinic→patient channel) | Patient (+ Doctor/Assistant author) | Basic: shareable report + aftercare. Pro: post-session Q&A. |
| **Settings** (products & lots · aftercare · report template · flags) | Assistant/Admin | Lots, flags, report template are Pro; aftercare templates are Basic. |

---

# 1 · Doctor

The doctor is the center of gravity. In **Basic** the doctor gets a Notes-killer: instant capture,
visual-first before/after, a patient-centric file, and a professional artifact to hand the patient.
In **Pro** the doctor gets understanding: dictate and walk away, the structured report and recall
build themselves.

## 1.1 Doctor · Basic (deterministic Notes-killer)

| Phase | Step | What the doctor does | System (deterministic) | Seam / teaser |
| --- | --- | --- | --- | --- |
| **Before** | Pull up the patient | Opens patient from **smart search** (name / phone / national ID), Persian-orthography-aware, instant at scale | `det` fuzzy-but-deterministic Persian search; opens patient detail with the **before/after gallery** grouped by visit | A returning patient's prior photos are *right there* — the camera-roll problem is gone |
| | "Same as last time" | Glances at last visit's note/photos before starting | `det` patient file shows last visit verbatim; **"Same as last time"** offers to pre-fill a new note from the last one | `✨ recall — "what product/units last time?"` teaser (Pro extracts it structurally) |
| **During** | Start capturing | Taps **Note** or **Photo** (primary in Basic); **Audio** is a voice-memo (kept, not transcribed) | `det` capture saved **instantly, local-first**; assigned to the active session; **no AI job, no `processing` state** | Audio card shows `✨ Try Pro — transcribe & structure your dictation` |
| | Before photo | Takes the **before** photo; tags area (cheek/lips/forehead) and **Before** | `det` photo tagged `Before` + area; enters the gallery; **ghost-overlay** `⊕ candidate` helps frame | Manual before/after tag = Basic; *auto*-pairing-by-area = Pro |
| | Treat + after photo | Treats; takes the **after** photo, tags **After** | `det` after-photo auto-suggested to pair with the matching before (same area, same visit) | `✨ Try Pro — auto-caption these photos` |
| | Note the work | Types a short note ("بوتاکس پیشانی، ۲۰ واحد، lot X") | `det` saved verbatim as a typed note; **no extraction** | `✨ Try Pro — turn this into a structured treatment report` |
| **After** | Assign patient | Confirms the active patient (already open) — or, if captured first, a **deterministic "Assign to …?"** suggestion based on the open patient / recent context | `det` one-tap assign; **duplicate-patient guard** if creating new | Never blocks; assignment can lag capture |
| | Share with patient | Curates a few before/after + picks an **aftercare** template; **shares a read-only report** (link via SMS/WhatsApp `⊕ candidate channel`) | `det` curated report + **static aftercare** rendered from template/DB | The professional artifact Apple Notes can't make |
| **Between** | Recall on return | Next visit, reopens the file; reads last visit + gallery by hand | `det` chronological file + gallery | `✨ recall` teaser again — the upsell compounds on every returning patient |

**Basic report (close-out):** the Live report is a **clean chronological document** — clinic + patient
header (template/DB), then transcript-less notes + **photos shown**, honest timestamps, no synthesis,
no chips. A tidy notebook that stands on its own ([redesign-capture-surface.md](redesign-capture-surface.md) B2 Basic).

## 1.2 Doctor · Pro (understanding + upsell)

| Phase | Step | What the doctor does | System | Seam |
| --- | --- | --- | --- | --- |
| **Before** | Walk in knowing the patient | Opens the patient; reads the **AI patient history** (Snapshot · Story so far · Worth remembering · Right now) and any **flags** (allergy · consent · preference) | `ai` cross-visit synthesis; `ai` flags surfaced on the patient row at the top of the session | Pro turns the file into a brief; Basic showed facts, Pro shows understanding |
| | Recall | Asks "what did I use last time?" | `ai` **recall** answers from the structured *Treatment performed* data — area · product · brand · units · lot | The Basic teaser is now real |
| **During** | Dictate | **Audio-first**: dictates the visit naturally while treating; drops photos as before/after | `ai` **transcription** (native script, RTL-aware); `ai` **captions** photos; `ai` **before/after auto-paired** by area | Audio is first-class in Pro; secondary in Basic |
| | Out-of-context | A side-comment / phone call mid-session | `ai` **out-of-context** capture dimmed, excluded from the report, never deleted; one-tap **Mark relevant** | Same guard as the generic build |
| | Patient match | Says the patient's name, or it's inferred | `ai` **patient matching** — auto-match / create / reassign / suggest; partial matches resolve in-place ([capture-surface H4](redesign-capture-surface.md)) | Capture never waits on the match |
| **After** | Structured report builds itself | Glances at the **Live report** | `ai` **structured session report** (fixed v1: Visit summary · Concern/goals · Assessment · **Treatment performed** [area·product·brand·units·**lot**] · Before/after · Plan & follow-up · Aftercare); rebuilt as captures land; auto-**Complete** badge | The core Pro value; no Generate button, no verify gate |
| | Lot capture | Lot # spoken in the dictation (or scanned `⊕ candidate`) | `ai` lot extracted into *Treatment performed* + the clinic **lot/batch ledger** | Feeds recall + safety |
| | Share | Same shareable report + aftercare as Basic, now pre-filled from the structured report | `ai`-assembled, `det`-delivered | Patient surface is one primitive across tiers |
| **Between** | Patient Q&A | A patient messages ("is this swelling normal?") | `ai` drafts a reply from the doctor's **prior answers + this patient's context**; surfaces *"Patient X asks … Suggested reply … → Send / edit / dismiss"* | Doctor-verified before send; every exchange accrues to memory |
| | Smart lists | Reviews "due for follow-up", "missing after-photo", "on product X" | `ai` **smart lists / filters** over the structured data | Basic has none of these — the upgrade is legible |
| | Recall / safety sweep | A product lot is recalled | `ai` **lot recall** — every patient who received lot N | A safety capability only structure can give |

---

# 2 · Assistant

The assistant **supports documentation**: captures on the doctor's behalf, keeps photos and the
patient file tidy, prepares the shareable artifact, and clears the small decisions. In Basic that's
manual-but-fast; in Pro the assistant becomes a *verifier* of AI output rather than a typist.

## 2.1 Assistant · Basic

| Phase | Step | Assistant does | System (det) | Seam |
| --- | --- | --- | --- | --- |
| **During** | Capture on behalf | Stands in the room, takes before/after photos, types the doctor's spoken notes | `det` instant capture into the active session; before/after tagging + pairing | Audio voice-memo captures the doctor verbatim for later typing; `✨ Try Pro — transcribe it` |
| **After** | Organize | Assigns the visit to the right patient; pairs any stray photos; tidies the gallery | `det` assign + **duplicate guard**; gallery grouped by visit | Capture-first: organizing is a *later* pass, not a gate |
| | Prepare the share | Curates the before/after set, picks the aftercare template, sends the report | `det` curated report + aftercare | The assistant owns the patient-facing polish |
| **Between** | Keep the file clean | Adds phone/DOB/national ID to thin records; merges obvious duplicates via the guard | `det` patient edit; `det` duplicate guard | Front-desk-adjacent housekeeping |

## 2.2 Assistant · Pro

| Phase | Step | Assistant does | System | Seam |
| --- | --- | --- | --- | --- |
| **After** | Verify, don't type | Skims the **AI-structured report**; fixes a transcript/caption inline; confirms extracted *Treatment performed* fields (esp. **lot**) | `ai` report + extraction; `det` inline **Edit** with edited-vs-AI attribution feeding the report | The job shifts from authoring to checking |
| | Resolve matches | Clears **Needs input**: choose-patient, verify AI-created patient | `ai` candidates; `det` confirm (never auto-merges) | Same needs-input contract as today ([states.md](states.md)) |
| **Between** | Triage Q&A | First-pass on the **patient Q&A** queue: routes clinical ones to the doctor with the AI draft attached, handles logistics | `ai` drafts; doctor verifies clinical replies | Assistant filters; doctor approves clinical content |
| | Keep lots current | Logs new product lots/expiry into **Products & lots** | `ai` recall depends on this ledger | Data quality work that powers safety |

---

# 3 · Receptionist (front desk)

Designed *inside* aesthetics ([foundation §2](redesign-foundation.md)): intake here means **registering
walk-ins and returning patients, guarding against duplicates, and getting the right patient attached to
the right chair** — without ever blocking the doctor. Memara is **not** a booking/billing system
([design-principles §2](../design-principles.md)); the front desk is a light **Today / arrivals** lens
plus registration, not a scheduler. The receptionist's screens are Clinical Memory's **Today** tab and
the **assignment resolver**, framed for the desk.

## 3.1 Receptionist · Basic

| Phase | Step | Receptionist does | System (det) | Seam |
| --- | --- | --- | --- | --- |
| **Before** | Returning patient arrives | Searches name/phone/national ID | `det` **smart Persian search**, instant at scale | The desk's most-used action; Notes search can't do this |
| | New patient | Registers: name (required), national ID/phone/DOB (fill-later) | `det` create via the **one shared patient form**; **duplicate-patient guard** warns on a near-match before creating | Stops the silent duplicate-record problem at the source |
| | Mark "here today" | Adds the patient to **Today** as an arrival / opens a visit context for the doctor | `det` Today card; capture destination ready | Scheduling-*adjacent*, not a calendar |
| **During** | Doctor captured first | Doctor already recording before reg is done; an **unassigned visit** appears in Today/Needs input | `det` capture-first — **never blocked**; a **deterministic "Assign to …?"** suggests the just-registered patient | The non-blocking handoff, made concrete |
| **After** | Attach the visit | One-tap **assign** the unassigned visit to the registered patient | `det` assignment resolver (Assign / Keep unassigned / Create new) | Reception closes the loop the doctor left open |
| | Hand the patient their report | Sends the curated report + aftercare link as the patient leaves | `det` share | Front desk owns delivery |

## 3.2 Receptionist · Pro

| Phase | Step | Receptionist does | System | Seam |
| --- | --- | --- | --- | --- |
| **Before** | Check-in surfaces flags | Opens the arrival | `ai` **flags** (allergy · **consent** status · preference) shown at check-in | Reception sees consent/allergy *before* the patient sits down |
| **During** | Fewer manual assigns | Doctor dictates the name; the visit **auto-matches** | `ai` patient matching attaches most visits automatically; only ambiguous ones reach the desk as **choose-patient** | Pro shrinks the receptionist's assign workload |
| | Verify AI-created | A walk-in the doctor created by voice lands **flagged verify** | `ai` create; `det` **Verify patient** fills/confirms identity | Reception is the natural verifier of identity |
| **Between** | Follow-up outreach | Works the **"due for follow-up"** smart list to message patients | `ai` smart list | A retention tool Basic doesn't have |

---

# 4 · One visit, three personas (the capture-first seam, concretely)

A single real visit, Pro tenant, showing the non-blocking handoff the whole product is built to protect:

1. **13:37 — Doctor** taps **Audio** and starts dictating while greeting the patient. The capture is
   saved on the device *instantly*; the visit is **unassigned**. *(No one waited for the front desk.)*
2. **13:38 — Receptionist** is still registering this walk-in (`det` form + duplicate guard). The
   doctor is already two photos in.
3. **13:39 — AI** transcribes the dictation, hears the patient's name, and **auto-matches** it to the
   record reception just created → the visit attaches itself. The doctor never touched assignment.
4. **13:52 — Assistant** skims the **structured report**, confirms the **lot** on the filler, fixes one
   caption inline.
5. **13:55 — Doctor** taps **Share**; the curated before/after + aftercare goes to the patient's phone.
6. **Next day — Patient** messages "lip feels firm, normal?"; the **doctor** approves the AI-drafted
   reply in two taps.

In **Basic**, the same visit runs deterministically: the doctor captures note+photo, reception
one-tap-assigns the unassigned visit to the registered patient, the assistant curates the share. The
handoff is identical — only the *understanding* layer (transcription, structure, auto-match, Q&A
drafting) is absent, each marked by a `✨ Try Pro` teaser at the exact moment it would have helped.

---

# 5 · Patient micro-journeys (the patient surface — [foundation §4](redesign-foundation.md))

The patient is **read / limited-write** through one shared clinic→patient channel, consumed by two
payloads. Designed as a **contract** (access · delivery · consent · what's shared vs withheld), not
per-tier buttons.

## 5.1 Patient · Basic payload — shareable report + aftercare (read-only)

1. Patient gets a link (SMS/WhatsApp `⊕ candidate channel`) as they leave.
2. Opens a **read-only** page: the clinic-curated **before/after**, the **aftercare instructions**, and
   safe contact info. No login friction beyond a tokenized link; **only curated content is shared** —
   raw captures, internal notes, lots are **withheld**.
3. Re-opens it days later to re-read aftercare. *(Deterministic; nothing AI.)*

## 5.2 Patient · Pro payload — post-session Q&A (limited-write)

1. Same channel gains a **question composer**: "is this swelling normal?"
2. The question lands in the clinic's **Q&A queue**; the doctor approves the AI-drafted, context-aware
   reply; the patient sees the verified answer in-thread.
3. The exchange is **captured into the patient's memory** — the next visit's history knows it happened.
   *(The unmanaged WhatsApp deluge becomes a fast, in-context, verified channel.)*

**Consent & withholding contract (both payloads):** sharing is an explicit clinic action; the patient
sees only what was curated; the channel is revocable; clinical internals never leak. This is the same
primitive therapy/derm will reuse — built once.
