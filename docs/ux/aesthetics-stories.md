# Aesthetics — User-Story Inventory (build hand-off)

> Deliverable 3 of the aesthetics design track ([foundation §6](redesign-foundation.md)). The hand-off
> to build. Companion docs: research [aesthetics-research-brief.md](aesthetics-research-brief.md),
> journeys [aesthetics-journeys.md](aesthetics-journeys.md), spec
> [redesign-aesthetics.md](redesign-aesthetics.md). North-star: [redesign-foundation.md](redesign-foundation.md).
>
> Every story is `As a <persona>, I want <goal>, so that <value>` + **acceptance** notes, tagged:
> **Tier** (`Basic` · `Pro` · `Both`) · **Persona** (Dr=doctor · As=assistant · Rc=receptionist ·
> Pt=patient) · **Build** (`exists` · `new` · `modify`, a planning estimate per
> [foundation §3](redesign-foundation.md) — confirm against the codebase at build time). `⊕` marks a
> **candidate extension** beyond the agreed set, for human review (see
> [redesign-aesthetics.md §10](redesign-aesthetics.md)); these are **proposals, not committed scope**.
>
> Traceability: each epic cites the agreed [foundation §3](redesign-foundation.md) Basic/Pro item it
> details. **Build order:** aesthetics-**Basic** first ([foundation §6](redesign-foundation.md)) — the
> `Basic` + `Both` stories are P1; `Pro` stories follow.

Legend in each story line: **`〔Tier · Persona · Build〕`**.

---

## E1 — Capture & active session
*Details [foundation §3 Basic 8 (zero-AI capture lifecycle), 3, 7](redesign-foundation.md) + [Pro 1, 2, 3, 7](redesign-foundation.md).*

### AES-101 — Instant, zero-AI capture (Basic lifecycle) 〔Basic · Dr/As · modify〕
As a **doctor**, I want note/photo/audio captured and saved **instantly, locally, with no AI job or
`processing` state**, so that capture feels like Apple Notes and works offline.
- **Acceptance:** Basic capture writes local-first, shows `Saved on this device`; **no** transcript /
  caption / report job, **no** `processing`/`Organizing` AI states. Audio is a **voice-memo** (playable,
  not transcribed). Matches [redesign-capture-surface.md](redesign-capture-surface.md) Basic.
- **Note:** today Basic still runs the AI pipeline — this is the core P1 re-gate ([foundation §3 Basic 8](redesign-foundation.md)).

### AES-102 — Audio-first Pro capture + enrichment 〔Pro · Dr/As · exists/modify〕
As a **doctor**, I want to **dictate** the visit and have audio transcribed, photos captioned, and notes
decorated, so that I document by talking.
- **Acceptance:** Pro primary capture = audio; `transcription` (exists), `image_caption` (modify — real
  today), `note_decoration` (modify). Generated text is inline-**editable** with edited-vs-AI attribution.
  RTL per the per-line script rule.

### AES-103 — Before/after photo pairing 〔Basic · Dr/As · new〕
As a **doctor**, I want to tag a photo **Before / After / During** and an **area** (e.g. forehead, cheek,
lips, jaw), and have the after auto-suggested to pair with the matching before, so that progress is
visible without camera-roll hunting.
- **Acceptance:** deterministic tag + manual/one-tap pair within a visit; pair renders **side-by-side
  + slider** compare; photos are filed to the patient, **not** the device camera roll. *AI auto-pairing
  by detected area is Pro (AES-104).*

### AES-104 — AI before/after auto-pairing + captions 〔Pro · Dr · modify〕
As a **doctor**, I want photos **auto-captioned and auto-paired by area** so that the gallery organizes
itself.
- **Acceptance:** Pro captions describe the clinical image; same-area before/after auto-paired; pairing
  is reversible. Shown in Basic as a `✨ Try Pro` teaser on a photo (AES-803).

### AES-105 — Ghost-overlay capture alignment 〔Basic · Dr/As · new · ⊕〕
As a **doctor**, I want the prior baseline photo faintly overlaid while I shoot the "after", so that
angle/framing/lighting match and the comparison is credible.
- **Acceptance:** deterministic on-screen overlay of the paired before image at low opacity during
  capture; no AI. *Candidate extension (research §6 ADOPT).*

### AES-106 — "Same as last time" pre-fill 〔Basic · Dr/As · new〕
As a **doctor**, I want to start a new note pre-filled from this patient's **last visit** note, so that
returning-patient documentation is one edit, not a retype.
- **Acceptance:** deterministic copy of the prior visit's typed note into a new editable note; clearly
  marked "from last visit · DATE"; never auto-saved without an edit/confirm. *Extends naturally to the
  treatment line.*

### AES-107 — Structured session report (Pro) 〔Pro · Dr · modify〕
As a **doctor**, I want my dictation + photos + notes turned into a **structured per-visit report**, so
that the record is consistent and the treatment specifics are captured.
- **Acceptance:** fixed v1 sections ([foundation §3 Pro 3](redesign-foundation.md)): Visit summary ·
  Concern/goals · Assessment · **Treatment performed** (per item: *area · product · brand · units/volume
  · lot #*) · Before/after media · Plan & follow-up · Aftercare given. Rebuilt deterministically-as-text
  but **AI-synthesized** content as captures land; auto-**Complete** badge; no Generate button, no verify
  gate. Out-of-context excluded.

### AES-108 — Treatment-line capture & extraction 〔Both · Dr/As · new/modify〕
As a **doctor**, I want each treatment item recorded as *area · product · brand · units/volume · lot*,
so that "what we did" is queryable.
- **Acceptance:** **Basic** — a lightweight **deterministic structured treatment row** the doctor/assistant
  fills (or leaves blank), stored on the visit (research §6 ADAPT: structured lot/product/units even in
  Basic). **Pro** — the same fields **auto-extracted** from dictation into *Treatment performed*. Both
  feed the patient's treatment history (AES-203).

### AES-109 — Out-of-context capture 〔Pro · Dr · exists〕
As a **doctor**, I want an off-topic capture (a phone call, a side comment) dimmed and excluded from the
report, never deleted, with one-tap **Mark relevant**, so that the report stays clean.
- **Acceptance:** as the generic build ([capture-surface](redesign-capture-surface.md)); Pro-only
  (report exclusion). Basic has no report synthesis to exclude from.

### AES-110 — Face-map injection logging 〔Pro · Dr · new · ⊕〕
As a **doctor**, I want to tap a **face diagram** to log each injection site with product/units/lot, so
that the treatment log is structured and recall-ready.
- **Acceptance:** tap-to-place sites on a face map → rows in *Treatment performed*. *Candidate extension
  (research §6). A deterministic Basic version = manual area tag only; the diagram + per-site rollup is
  the Pro hook.*

---

## E2 — Patient file, memory & search
*Details [foundation §3 Basic 2, 3, 4, 7](redesign-foundation.md) + [Pro 4](redesign-foundation.md).*

### AES-201 — Patient-centric automatic filing 〔Basic · All · modify〕
As a **doctor**, I want every capture filed under **patient → visit** automatically, so that the clinic's
real structure replaces a flat pile of notes.
- **Acceptance:** deterministic presentation of the existing patient/session/capture model; no AI
  needed to file. Patient detail shows visits grouped by time.

### AES-202 — Before/after gallery, grouped by visit 〔Basic · Dr/As · new〕
As a **doctor**, I want a **per-patient gallery auto-grouped by visit** with before/after pairs, so that
I see the whole aesthetic history at a glance.
- **Acceptance:** deterministic grouping; pairs show side-by-side/slider; tap a pair → the visit. Photos
  never leave the patient file for the camera roll.

### AES-203 — Treatment & lot history (per patient) 〔Both · Dr/As · new〕
As a **doctor**, I want a **longitudinal treatment log** — each visit's area/product/brand/units/lot —
on the patient, so that "what did we do last time" is always answerable.
- **Acceptance:** **Basic** = deterministic table from the captured treatment rows (AES-108).
  **Pro** = same, populated by extraction + summarized in memory. The most-cited memory gap (research §3).

### AES-204 — Smart Persian search 〔Basic · All · modify〕
As a **receptionist**, I want **deterministic, Persian-orthography-aware, multi-field** search (name /
phone / national ID) that is **instant at scale**, so that I find the right record fast and don't create
a duplicate.
- **Acceptance:** folds Persian confusables/Arabic variants (reuse existing normalization,
  [intelligence-layer-stories H1](../intelligence-layer-stories.md)); multi-field; fast on large lists;
  **zero AI**.

### AES-205 — Duplicate-patient guard 〔Basic · Rc/As · new〕
As a **receptionist**, I want a warning when I'm about to create a patient who **looks like an existing
one**, so that one person doesn't split into several records.
- **Acceptance:** on create, deterministic near-match check (normalized name + national ID/phone) →
  shows likely existing matches with **Use existing / Create anyway**; never auto-merges.

### AES-206 — Deterministic patient memory (Basic) 〔Basic · Dr/As · exists〕
As a **doctor**, I want a **structural** patient recap (visit counts, dates, capture types, verbatim
typed notes) with **no ✨**, so that Basic memory is honest and never guesses.
- **Acceptance:** as [screens/patients.md](screens/patients.md) Basic memory — never paraphrases audio;
  audio visits read "Transcript saved — open the visit." No AI.

### AES-207 — AI patient memory, history & recall (Pro) 〔Pro · Dr/As · exists/new〕
As a **doctor**, I want an **AI patient history** (Snapshot · Story so far · Worth remembering · Right
now) and to **recall** "what did I use last time", so that I walk in knowing the patient.
- **Acceptance:** cross-visit synthesis (exists); **recall** (new) answers from the structured
  *Treatment performed* data (area/product/units/lot); ✨ provenance per
  [screens/patients.md](screens/patients.md).

### AES-208 — AI patient matching 〔Pro · Dr/Rc · exists〕
As a **doctor**, I want visits **auto-matched / created / reassigned / suggested** to the right patient,
so that I never stop to assign.
- **Acceptance:** existing matching + partial-match resolution + strictness ([capture-surface](redesign-capture-surface.md)).
  Basic uses deterministic assign (AES-301) instead.

---

## E3 — Assignment & reports
*Details [foundation §3 Basic 5, 6](redesign-foundation.md) + [Pro 3](redesign-foundation.md).*

### AES-301 — Capture-first, deterministic assign-later 〔Basic · All · modify〕
As a **doctor**, I want to capture **before** choosing a patient and get a **deterministic "Assign to …?"**
suggestion (from the open patient / recent context), so that capture never blocks and filing catches up.
- **Acceptance:** capture-first (exists); the Basic suggestion is **rule-based** (active/open patient,
  most-recent), **not AI**; one-tap assign; resolver offers Assign / Keep unassigned / Create new.

### AES-302 — Basic chronological report 〔Basic · Dr/As · modify〕
As a **doctor**, I want the visit rendered as a **clean chronological document** (clinic + patient header
from template/DB, notes + photos shown, honest timestamps, no synthesis), so that Basic produces a tidy
notebook that stands alone.
- **Acceptance:** as [redesign-capture-surface.md](redesign-capture-surface.md) B2 Basic; no AI chips.

### AES-303 — Shareable curated patient report 〔Basic · Dr/As · new〕
As an **assistant**, I want to **curate** a few before/after + the visit into a **read-only patient
report** I can share, so that the patient leaves with a professional artifact.
- **Acceptance:** staff selects which media/sections are included; renders to the patient surface (E4);
  **Pro** pre-fills it from the structured report. Sharing is explicit; internals withheld (AES-403).

### AES-304 — Static aftercare instructions 〔Basic · Dr/As · new〕
As a **doctor**, I want to attach **templated aftercare instructions** to the shared report, so that the
patient has correct, consistent guidance.
- **Acceptance:** deterministic templates (per procedure type), editable per send; rendered read-only on
  the patient surface; managed in Settings (AES-702).

---

## E4 — Patient surface (the shared clinic→patient channel)
*Details [foundation §4](redesign-foundation.md) + [§3 Basic 6, Pro 8](redesign-foundation.md). One
primitive, two payloads; designed as a contract (access · delivery · consent · shared-vs-withheld).*

### AES-401 — Patient receives the report + aftercare (Basic payload) 〔Basic · Pt · new〕
As a **patient**, I want a **read-only** link to my before/after + aftercare, so that I can re-read my
care guidance anytime.
- **Acceptance:** tokenized link (delivery channel SMS/WhatsApp — see AES-404 ⊕); read-only; shows only
  curated content; revocable. No login friction beyond the link.

### AES-402 — Post-session patient Q&A (Pro payload) 〔Pro · Pt/Dr · new〕
As a **patient**, I want to **ask a question** between visits and get a verified answer, so that I'm not
lost in WhatsApp.
As a **doctor**, I want the system to **draft a reply** from my prior answers + this patient's context
and let me **Send / edit / dismiss**, so that the question deluge becomes a fast, in-context, verified
channel.
- **Acceptance:** patient→clinic question composer; clinic **Q&A queue** shows *"Patient X asks … ·
  Suggested reply … · Send / edit / dismiss"*; doctor approves before send; every exchange is captured
  into patient memory.

### AES-403 — Sharing & withholding contract 〔Both · Dr/As/Pt · new〕
As a **clinic**, I want sharing to be an **explicit action** that exposes only curated content and is
**revocable**, so that clinical internals (raw captures, notes, lots) never leak.
- **Acceptance:** explicit "Share" gesture; per-share preview of what the patient sees; revoke access;
  raw captures/notes/lots withheld by default. The same contract serves therapy/derm later.

### AES-404 — Delivery channel 〔Both · Rc/As · new · ⊕〕
As a **receptionist**, I want to deliver the link by **SMS / WhatsApp**, so that it reaches the patient
on the channel they use.
- **Acceptance:** *Candidate — channel decision.* Iranian clinics lean on WhatsApp/SMS; the surface is
  channel-agnostic (a tokenized link), the channel is a delivery integration to confirm with the human.

---

## E5 — Smart lists, filters & lot recall (Pro)
*Details [foundation §3 Pro 5, 6](redesign-foundation.md).*

### AES-501 — Smart lists / filters 〔Pro · Dr/As · new〕
As a **doctor**, I want lists like **seen this week · due for follow-up · on product X · missing
after-photo**, so that I can run the practice from the data.
- **Acceptance:** filters over the structured per-visit/treatment data; live counts; tap → the patients.
  Basic has none (legible upgrade).

### AES-502 — Lot/batch tracking + recall 〔Pro · Dr/As/Rc · new〕
As an **assistant**, I want to find **every patient who received a recalled lot**, so that we can act on
a product recall safely.
- **Acceptance:** lot ledger built from extracted/entered lots (AES-108); a **recall lookup** returns
  affected patients/visits; surfaced for outreach (ties to AES-501 follow-up + E4 messaging). Real safety
  need (research §6; FDA counterfeit-Botox recalls).

### AES-503 — Lot/expiry scan 〔Pro · As · new · ⊕〕
As an **assistant**, I want to **scan a product box** (barcode/lot) at use, so that lot capture is
accurate and effortless.
- **Acceptance:** *Candidate extension.* Scan → lot/expiry onto the treatment row + ledger.

---

## E6 — Front desk / reception
*Designs the receptionist persona inside aesthetics ([foundation §2](redesign-foundation.md)); a light
Today/arrivals lens, not a scheduler ([design-principles §2](../design-principles.md)).*

### AES-601 — Register a patient (one shared form) 〔Basic · Rc/As · modify〕
As a **receptionist**, I want to register a patient with **name required, rest fill-later**, so that
intake is fast and never blocks the room.
- **Acceptance:** reuses the shared `PatientForm` ([intelligence-layer-stories Epic F](../intelligence-layer-stories.md));
  name-only valid; duplicate guard (AES-205) on submit.

### AES-602 — Today / arrivals board 〔Basic · Rc · modify〕
As a **receptionist**, I want a **Today** view of arrivals / active visits, so that I can see who's in and
attach them to the right chair.
- **Acceptance:** a front-desk framing of Clinical Memory **Today** ([screens/patients.md](screens/patients.md));
  shows active + unassigned visits; scheduling-*adjacent*, not a calendar.

### AES-603 — Attach an unassigned (doctor-captured) visit 〔Basic · Rc · modify〕
As a **receptionist**, I want to **one-tap assign** a visit the doctor captured before registration to
the patient I just registered, so that the capture-first handoff closes cleanly.
- **Acceptance:** unassigned visit appears in Today/Needs input; resolver assigns to the registered
  patient (deterministic suggestion, AES-301). **Pro:** most visits auto-match (AES-208), so only
  ambiguous ones reach the desk.

### AES-604 — Flags & consent at check-in (Pro) 〔Pro · Rc · new〕
As a **receptionist**, I want **allergy · consent · preference flags** surfaced when a patient checks in,
so that the room is ready and consent isn't missed.
- **Acceptance:** flags (AES-701) shown on the arrival card; consent status visible. *Consent capture
  itself is AES-703 ⊕.*

---

## E7 — Flags, settings & configuration
*Details [foundation §3 Pro 7](redesign-foundation.md) + supporting config.*

### AES-701 — Safety flags surfaced each visit (Pro) 〔Pro · Dr/As · new〕
As a **doctor**, I want **allergy · consent · preference** flags surfaced on the patient at every visit,
so that I never miss a safety-critical fact.
- **Acceptance:** flags live on the patient; shown on the capture patient-row + patient detail + check-in
  (AES-604); set by staff and/or derived (Pro). Quiet but prominent; not blocking.

### AES-702 — Aftercare templates 〔Basic · As/Admin · new〕
As an **assistant**, I want to manage **aftercare instruction templates** per procedure, so that sends are
correct and consistent.
- **Acceptance:** deterministic templates in Settings; selectable + editable per send (AES-304).

### AES-703 — Lightweight consent capture 〔Both · Rc/As · new · ⊕〕
As a **receptionist**, I want to **attach/store a signed consent** (photo or e-sign) on the patient/visit,
so that consent is on file.
- **Acceptance:** *Candidate extension — legally sensitive; flag.* Attach/store + a consent **flag**
  (AES-701); **not** a full legal e-forms engine (research §5 concession). ⊕ pre-visit consent link
  (AES-704).

### AES-704 — Pre-visit consent/questionnaire link 〔Pro · Rc · new · ⊕〕
As a **receptionist**, I want to send a **pre-visit questionnaire/consent link** auto-attached to the
session, so that in-clinic friction drops.
- **Acceptance:** *Candidate extension.* Reuses the patient surface (E4) inbound; result attaches to the
  visit + sets the consent flag.

### AES-705 — Products & lots registry 〔Pro · As/Admin · new〕
As an **assistant**, I want to maintain the clinic's **products & lots** (brand, lot, expiry), so that
extraction/recall/expiry work.
- **Acceptance:** Settings registry feeding AES-108 extraction validation + AES-502 recall +
  AES-503 ⊕ scan.

### AES-706 — Report template (Pro) 〔Pro · Admin · modify〕
As an **admin**, I want the structured report to use the **fixed aesthetic default template** now and be
**uploadable later**, so that the report is consistent today and customizable when needed.
- **Acceptance:** fixed v1 ([foundation §3 Pro 3](redesign-foundation.md)); name + **Change** affordance
  in the report meta strip ([capture-surface B2](redesign-capture-surface.md)); user-uploadable is a
  future axis (shared with radiology/pathology).

---

## E8 — The upsell line (✨ Try Pro teasers)
*Details [foundation §3 Pro 9, §1](redesign-foundation.md). Lightweight AI appears in Basic **only** as a
clearly-labelled teaser — a conversion lever, never a Basic feature.*

### AES-801 — Teaser: structure this note 〔Basic · Dr/As · new〕
As a **Basic doctor**, I want to see what a **structured treatment report** would look like, so that the
value of Pro is concrete at the moment I'd use it.
- **Acceptance:** on the Basic chronological report, a labelled `✨ Try Pro — turn this into a structured
  treatment report` card → upgrade/preview; **never** silently structures Basic content. *(The most
  tempting cheap-LLM task is exactly the core Pro value — [foundation §1](redesign-foundation.md).)*

### AES-802 — Teaser: transcribe this dictation 〔Basic · Dr · new〕
As a **Basic doctor**, I want my voice-memo to offer `✨ Try Pro — transcribe & structure`, so that the
upsell sits exactly where audio stops being first-class.
- **Acceptance:** on a Basic audio card; labelled; non-functional preview/upgrade.

### AES-803 — Teaser: caption & auto-pair photos 〔Basic · Dr/As · new〕
As a **Basic doctor**, I want `✨ Try Pro — auto-caption & pair before/after` on a photo, so that I see
the Pro gallery upgrade in context.

### AES-804 — Teaser: recall & AI history 〔Basic · Dr · new〕
As a **Basic doctor**, on a returning patient I want `✨ recall — what product/units last time?` and an
AI-history teaser, so that the longitudinal-understanding upsell shows on every return.
- **Acceptance:** labelled teasers on the Basic patient file; tap → upgrade. Basic still shows the
  deterministic treatment log (AES-203) — the teaser sells the *synthesis*, not the data.

---

## Coverage check — every agreed feature is detailed

| [Foundation §3](redesign-foundation.md) item | Stories |
| --- | --- |
| Basic 1 — shared clinic workspace | (exists; underpins AES-201, E6) |
| Basic 2 — patient-centric filing | AES-201 |
| Basic 3 — before/after pairing + gallery | AES-103, AES-202 (+⊕ AES-105) |
| Basic 4 — smart search | AES-204 |
| Basic 5 — capture-first / deterministic assign-later | AES-301 |
| Basic 6 — shareable report + aftercare | AES-303, AES-304, AES-401 |
| Basic 7 — "same as last time" + duplicate guard | AES-106, AES-205 |
| Basic 8 — zero-AI capture lifecycle | AES-101 |
| Pro 1 — enrichment (transcription/caption/decoration) | AES-102, AES-104 |
| Pro 2 — AI matching + out-of-context | AES-208, AES-109 |
| Pro 3 — structured session report | AES-107, AES-108, AES-706 |
| Pro 4 — cross-visit synthesis + recall | AES-207 |
| Pro 5 — smart lists / filters | AES-501 |
| Pro 6 — lot/batch tracking + recall | AES-502 (+⊕ AES-503) |
| Pro 7 — flags / safety | AES-701, AES-604 |
| Pro 8 — post-session patient Q&A | AES-402 |
| Pro 9 — ✨ Try Pro teasers | AES-801–804 |
| §4 — patient-surface contract | AES-401, AES-402, AES-403 (+⊕ AES-404) |

**Candidate extensions (⊕, for human review):** AES-105 ghost-overlay · AES-110 face-map ·
AES-404 SMS/WhatsApp delivery · AES-503 lot scan · AES-703 consent capture · AES-704 pre-visit link.
Rationale + recommendation for each: [redesign-aesthetics.md §10](redesign-aesthetics.md).
