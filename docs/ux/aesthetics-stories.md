# Aesthetics — User-Story Inventory (build hand-off)

> Deliverable 3 of the aesthetics design track ([foundation §6](foundation.md)): the `AES-###`
> story-ID registry the docs and code cite. North-star: [foundation.md](foundation.md); the as-built
> surfaces are the system-state screen docs under [`screens/`](screens/).
>
> Every story is `As a <persona>, I want <goal>, so that <value>` + **acceptance** notes, tagged:
> **Tier** (`Basic` · `Pro` · `Both`) · **Persona** (Dr=doctor · As=assistant · Rc=receptionist ·
> Pt=patient) · **Build** (`exists` · `new` · `modify` — the original planning estimates, kept for
> the record). `⊕` marks a **candidate extension** beyond the agreed set, for human review (rationale
> + recommendation per extension: the **Decisions** block at the end); these are **proposals, not
> committed scope**.
>
> Traceability: each epic cites the agreed [foundation §3](foundation.md) Basic/Pro item it
> details.
>
> **Status:** **Basic, Both, and all committed Pro stories are built and merged to `main`** —
> Pro synthesis (AES-107/108), patient memory + matching (AES-207/208), out-of-context (AES-109), Q&A
> (AES-402/403), safety flags (AES-604/701), the unified report + verify surface, capture undo,
> multi-seat E9, and **AES-501/502** (the Pro **Lists** tab in Clinical Memory — deterministic lenses
> + an exact-match lot-recall cohort with the Q&A outreach handoff; as-built in
> [screens/patients.md](screens/patients.md)). Manual test scripts:
> [`../qa/aes-frontend-scenarios.md`](../qa/aes-frontend-scenarios.md) and
> [`../qa/aes-pro-smoke.md`](../qa/aes-pro-smoke.md). **Remaining committed scope:** **AES-705**
> (products/lots registry — still only implicit via extraction; 501/502 read raw extracted lots
> through a single ledger-builder aggregation point, the clean seam for the registry to layer on —
> canonical lots, expiry, per-product due-to-return precision — without reshaping responses).
> Candidate extensions (⊕) and the deferrals below remain proposals, not committed scope;
> **AES-703 was dropped** (see Decisions).

Legend in each story line: **`〔Tier · Persona · Build〕`**.

---

## E1 — Capture & active session
*Details [foundation §3 Basic 8 (zero-AI capture lifecycle), 3, 7](foundation.md) + [Pro 1, 2, 3, 7](foundation.md).*

### AES-101 — Instant, zero-AI capture (Basic lifecycle) 〔Basic · Dr/As · modify〕
As a **doctor**, I want note/photo/audio captured and saved **instantly, locally, with no AI job or
`processing` state**, so that capture feels like Apple Notes and works offline.
- **Acceptance:** Basic capture writes local-first, shows `Saved on this device`; **no** transcript /
  caption / report job, **no** `processing`/`Organizing` AI states. Audio is a **voice-memo** (playable,
  not transcribed). Matches the Basic surface in [screens/capture.md](screens/capture.md).
- **As built:** no persistent sync badges — not on the session header, not per capture. A single
  `Trying to sync` marker appears **only** while offline / the backend is unreachable; when
  connected, captures are badge-free.

### AES-102 — Audio-first Pro capture + enrichment 〔Pro · Dr/As · exists/modify〕
As a **doctor**, I want to **dictate** the visit and have audio transcribed, photos captioned, and notes
decorated, so that I document by talking.
- **Acceptance:** Pro primary capture = audio; `transcription` (exists), `image_caption` (modify — real
  today), `note_decoration` (modify). Generated text is inline-**editable** with edited-vs-AI attribution.
  RTL per the per-line script rule.

### AES-103 — Photo gallery, no tagging (Basic) 〔Basic · Dr/As · new〕
As a **doctor**, I want my photos filed to the patient and shown **well — grouped by visit, recent
visits prominent — with no tagging**, so that I see progress at a glance and compare by eye, without
camera-roll hunting or labeling work.
- **Acceptance:** photos filed to the patient, **not** the device camera roll; a per-patient gallery
  **grouped by visit** (≈last 4 prominent), photos in capture order; the returning-visit capture strip
  surfaces last visit's photos for eyeball comparison. **No Before/After/area tags, no app-built pairs,
  no slider** — that's Pro (AES-104). *Amends foundation §3 Basic 3: pairing → Pro (approved 2026-06-12).*

### AES-104 — AI captions + prepared before/after (Pro) 〔Pro · Dr · modify〕
As a **doctor**, I want photos **auto-captioned** and the **before/after pairs prepared for me** — area
detected, matched, aligned — so that the comparison builds itself.
- **Acceptance:** Pro captions the clinical image; detects area/angle; **intelligently assembles
  before/after pairs** with the **side-by-side + slider** compare (reversible); feeds the structured
  report's Before/after media + the curated share; powers "missing after-photo" (AES-501). Shown in
  Basic as the `✨ Try Pro` teaser on a photo (AES-803).

### AES-105 — Ghost-overlay capture alignment 〔Basic · Dr/As · new · ⊕〕
As a **doctor**, I want to optionally overlay a **previous photo** faintly while I shoot, so that
angle/framing/lighting match and the comparison is credible.
- **Acceptance:** deterministic, **optional** on-screen overlay of a prior photo (default: the patient's
  most recent shot; user can pick another) at low opacity during capture; **no Before/After taxonomy**,
  no AI. *Candidate extension (research §6 ADOPT) — adopt v1.*

### AES-106 — Last visit, one glance + "same as last time" pre-fill 〔Basic · Dr/As · new〕
As a **doctor**, with a returning patient I want **last visit's note + before/after surfaced at capture**
and a one-tap pre-fill of a new note from it, so that "what did we use last time" is answered by
retrieval and documentation is one edit, not a retype.
- **Acceptance:** for a returning patient the capture strip shows last visit's note + before/after (tap
  to open the visit); **"same as last time"** deterministically copies the prior typed note into a new
  editable note, marked "from last visit · DATE", never auto-saved without an edit/confirm. *This is
  Basic's substitute for structured treatment recall (no form — AES-108/203).*

### AES-107 — Structured session report (Pro) 〔Pro · Dr · modify〕
As a **doctor**, I want my dictation + photos + notes turned into a **structured per-visit report**, so
that the record is consistent and the treatment specifics are captured.
- **Acceptance:** fixed v1 sections ([foundation §3 Pro 3](foundation.md)): Visit summary ·
  Concern/goals · Assessment · **Treatment performed** (per item: *area · product · brand · units/volume
  · lot #*) · Before/after media · Plan & follow-up · Aftercare given. Rebuilt deterministically-as-text
  but **AI-synthesized** content as captures land; auto-**Complete** badge; no Generate button, no verify
  gate. Out-of-context excluded.

### AES-108 — Treatment extraction into the structured report 〔Pro · Dr/As · modify〕
As a **doctor**, I want each treatment item *extracted from my dictation* as *area · product · brand ·
units/volume · lot*, so that "what we did" is queryable **without my filling a form**.
- **Acceptance:** **Pro only.** Auto-extracted from dictation into *Treatment performed* (AES-107) + the
  lot ledger (AES-705); feeds the treatment table (AES-203). **Basic does NOT capture structured
  treatment** — detail stays free-text (a note/voice memo); Basic answers "what did we use last time" by
  **retrieval** (AES-106/203), not entry. *Why:* a manual structured form would make Basic feel like a
  small EHR ([design-principles §2,§5](../design-principles.md)) — **decision 2026-06-11**.

### AES-109 — Out-of-context capture 〔Pro · Dr · exists〕
As a **doctor**, I want an off-topic capture (a phone call, a side comment) dimmed and excluded from the
report, never deleted, with one-tap **Mark relevant**, so that the report stays clean.
- **Acceptance:** as the generic build ([screens/capture.md](screens/capture.md)); Pro-only
  (report exclusion). Basic has no report synthesis to exclude from.

### AES-110 — Face-map injection visualization 〔Pro · Dr · new · ⊕〕
As a **doctor**, I want my **dictated** treatment rendered onto a **face diagram** I can glance at and
correct, so that where/what was injected is visual — **without filling a form**.
- **Acceptance:** *Candidate extension (research §6) — **derived visualization only.*** The face map is
  populated from the **extracted** *Treatment performed* sites (AES-108), a read-back the doctor taps
  **only to correct** — never a tap-to-enter capture gate (that would violate capture-first,
  [design-principles §1,§5](../design-principles.md)). **Later spike, not alpha** (decision 2026-06-11).

---

## E2 — Patient file, memory & search
*Details [foundation §3 Basic 2, 3, 4, 7](foundation.md) + [Pro 4](foundation.md).*

### AES-201 — Patient-centric automatic filing 〔Basic · All · modify〕
As a **doctor**, I want every capture filed under **patient → visit** automatically, so that the clinic's
real structure replaces a flat pile of notes.
- **Acceptance:** deterministic presentation of the existing patient/session/capture model; no AI
  needed to file. Patient detail shows visits grouped by time.

### AES-202 — Per-patient photo gallery, grouped by visit 〔Basic · Dr/As · new〕
As a **doctor**, I want a **per-patient gallery auto-grouped by visit**, so that I see the whole photo
history at a glance.
- **Acceptance:** deterministic grouping (recent visits prominent); photos in capture order; tap a photo
  → the visit. **No tags / pairs / slider** (that's Pro, AES-104). Photos never leave the patient file
  for the camera roll.

### AES-203 — Visit history & "what did we use last time" 〔Both · Dr/As · new〕
As a **doctor**, I want last visit's detail instantly findable, so that "what did we use last time" is
answerable **without structured data entry**.
- **Acceptance:** **Basic** = a **glanceable visit list**; each visit shows the doctor's own note +
  before/after — the answer lives in the free text they wrote, made instantly skimmable (**no structured
  table**). **Pro** = a longitudinal **treatment & lot table** (visit · area · product · units · lot)
  from extraction (AES-108), which also powers recall / lot-recall / smart-lists. Structure exists in
  Pro *because it's extracted*, never entered. The most-cited memory gap (research §3).

### AES-204 — Smart Persian search 〔Basic · All · modify〕
As a **receptionist**, I want **deterministic, Persian-orthography-aware, multi-field** search (name /
phone / national ID) that is **instant at scale**, so that I find the right record fast and don't create
a duplicate.
- **Acceptance:** folds Persian confusables/Arabic variants (reuse the existing patient-name
  normalization); multi-field; fast on large lists; **zero AI**.

### AES-205 — Duplicate-patient guard 〔Basic · Rc/As · new〕
As a **receptionist**, I want a warning when I'm about to create a patient who **looks like an existing
one**, so that one person doesn't split into several records.
- **Acceptance:** on create, deterministic near-match check (normalized name + national ID/phone) →
  shows likely existing matches with **Use existing / Create anyway**; never auto-merges.

### AES-206 — Deterministic patient memory (Basic) 〔Basic · Dr/As · exists〕
As a **doctor**, I want a **structural** patient recap (visit counts, dates, capture types, verbatim
typed notes) with **no ✨**, so that Basic memory is honest and never guesses.
- **Acceptance:** as [screens/patients.md](screens/patients.md) Basic memory — never paraphrases audio;
  audio visits read as a voice memo (`Voice memo · 2m 14s` — open the visit to play it; Basic has
  no transcription, AES-101). No AI.

### AES-207 — AI patient memory, history & recall (Pro) 〔Pro · Dr/As · exists/new〕
As a **doctor**, I want an **AI patient history** (Snapshot · Story so far · Worth remembering · Right
now) and to **recall** "what did I use last time", so that I walk in knowing the patient.
- **Acceptance:** cross-visit synthesis (exists); **recall** (new) answers from the structured
  *Treatment performed* data (area/product/units/lot); ✨ provenance per
  [screens/patients.md](screens/patients.md).

### AES-208 — AI patient matching 〔Pro · Dr/Rc · exists〕
As a **doctor**, I want visits **auto-matched / created / reassigned / suggested** to the right patient,
so that I never stop to assign.
- **Acceptance:** existing matching + partial-match resolution + strictness ([screens/capture.md](screens/capture.md) "Partial-match resolution").
  Basic uses deterministic assign (AES-301) instead.

---

## E3 — Assignment & reports
*Details [foundation §3 Basic 5, 6](foundation.md) + [Pro 3](foundation.md).*

### AES-301 — Capture-first, deterministic assign-later 〔Basic · All · modify〕
As a **doctor**, I want to capture **before** choosing a patient and get a **deterministic "Assign to …?"**
suggestion (from the open patient / recent context), so that capture never blocks and filing catches up.
- **Acceptance:** capture-first (exists); the Basic suggestion is **rule-based** (active/open patient,
  most-recent), **not AI**; one-tap assign; resolver offers Assign / Keep unassigned / Create new.

### AES-302 — Basic chronological report 〔Basic · Dr/As · modify〕
As a **doctor**, I want the visit rendered as a **clean chronological document** (clinic + patient header
from template/DB, notes + photos shown, honest timestamps, no synthesis), so that Basic produces a tidy
notebook that stands alone.
- **Acceptance:** as the Basic chronological report in [screens/capture.md](screens/capture.md); no AI chips.

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
*Details [foundation §4](foundation.md) + [§3 Basic 6, Pro 8](foundation.md). One
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

### AES-410 — Q&A knowledge library 〔Pro · Dr/As · new〕
As a **clinic**, I want a curated library of standard Q+A answers plus every doctor-approved reply
**indexed automatically**, so that the clinic's own guidance becomes reusable and the system gets
smarter with no manual work.
- **Acceptance:** a **Library** tab in the Q&A inbox — curated **templates** (create/edit/delete) +
  auto-indexed **sent replies** with a one-tap **exclude** (manage list); **Save as template** on any
  sent reply. Per-tenant (never crosses clinics). As-built:
  [screens/qa-inbox.md](screens/qa-inbox.md), [../backend/aes-pro-qa-api.md](../backend/aes-pro-qa-api.md).

### AES-411 — Retrieval-grounded reply drafting + provenance 〔Pro · Dr · new〕
As a **doctor**, I want the reply draft prepared **based on how our clinic answers similar questions**,
with a chip telling me what it's based on, so that drafts match our voice and I trust them.
- **Acceptance:** the backend retrieves the top library exemplars (hybrid lexical+embedding, per-tenant)
  into the `qa_draft` prompt; the patient's own context always wins, no dose/fact is copied across
  patients, and escalation + never-contradict-aftercare keep precedence over any exemplar; a doctor-only
  **provenance chip** (`based on: {template}` / `a previous reply`) opens the source. Eval-gated
  (`qa_draft_eval` — exemplar-followed / exemplar-overridden). *Extends AES-402.*

---

## E5 — Smart lists, filters & lot recall (Pro)
*Details [foundation §3 Pro 5, 6](foundation.md).*

### AES-501 — Smart lists / filters 〔Pro · Dr/As · new〕
As a **doctor**, I want lists like **seen this week · due for follow-up · on product X · missing
after-photo**, so that I can run the practice from the data.
- **Acceptance:** filters over the structured per-visit/treatment data; live counts; tap → the patients.
  Basic has none (legible upgrade).

### AES-502 — Lot/batch tracking + recall 〔Pro · Dr/As/Rc · new〕
As an **assistant**, I want to find **every patient who received a recalled lot**, so that we can act on
a product recall safely.
- **Acceptance:** lot ledger built from **extracted** lots (AES-108; no Basic lot data — Basic lot is
  free text in a note); a **recall lookup** returns affected patients/visits; surfaced for outreach (ties
  to AES-501 follow-up + E4 messaging). Real safety need (research §6; FDA counterfeit-Botox recalls).

### AES-503 — Lot/expiry scan 〔Pro · As · new · ⊕〕
As an **assistant**, I want to **scan a product box** (barcode/lot) at use, so that lot capture is
accurate and effortless.
- **Acceptance:** *Candidate extension.* Scan → lot/expiry onto the extracted treatment item + ledger.

---

## E6 — Front desk / reception
*Designs the receptionist persona inside aesthetics ([foundation §2](foundation.md)); a light
Today/arrivals lens, not a scheduler ([design-principles §2](../design-principles.md)).*

### AES-601 — Register a patient (one shared form) 〔Basic · Rc/As · modify〕
As a **receptionist**, I want to register a patient with **name required, rest fill-later**, so that
intake is fast and never blocks the room.
- **Acceptance:** reuses the shared `PatientForm`; name-only valid; duplicate guard (AES-205) on submit.

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
*Details [foundation §3 Pro 7](foundation.md) + supporting config.*

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
- **Acceptance:** fixed v1 ([foundation §3 Pro 3](foundation.md)); name + **Change** affordance
  in the report meta strip ([screens/capture.md](screens/capture.md)); user-uploadable is a
  future axis (shared with radiology/pathology).

---

## E8 — The upsell line (✨ Try Pro teasers)
*Details [foundation §3 Pro 9, §1](foundation.md). Lightweight AI appears in Basic **only** as a
clearly-labelled teaser — a conversion lever, never a Basic feature.*

**As built — one Try Pro per screen.** The per-capture teasers below were consolidated to a single
placement each: a **"Do more with Pro"** card at the foot of the Basic captures feed (one info box
covering transcription + caption/before-after pairing + the structured report — AES-802/803/801),
plus one teaser each on the Basic **report** (AES-801) and the **patient file** (AES-804). Tapping
any teaser opens a labelled info box — it never runs AI on Basic content. *Why:* repeating ✨ on
every capture read as upsell pressure; one consolidated explainer keeps Basic calm while still
selling Pro. The stories below still record *what each capability sells*.

### AES-801 — Teaser: structure this note 〔Basic · Dr/As · new〕
As a **Basic doctor**, I want to see what a **structured treatment report** would look like, so that the
value of Pro is concrete at the moment I'd use it.
- **Acceptance:** on the Basic chronological report, a labelled `✨ Try Pro — turn this into a structured
  treatment report` card → upgrade/preview; **never** silently structures Basic content. *(The most
  tempting cheap-LLM task is exactly the core Pro value — [foundation §1](foundation.md).)*

### AES-802 — Teaser: transcribe this dictation 〔Basic · Dr · new〕
As a **Basic doctor**, I want my voice-memo to offer `✨ Try Pro — transcribe & structure`, so that the
upsell sits exactly where audio stops being first-class.
- **Acceptance:** on a Basic audio card; labelled; non-functional preview/upgrade.

### AES-803 — Teaser: caption & prepare before/after 〔Basic · Dr/As · new〕
As a **Basic doctor**, I want `✨ Try Pro — caption & prepare before/after` on a photo, so that I see the
Pro upgrade (captions + assembled pairs + slider) in context.

### AES-804 — Teaser: recall & AI history 〔Basic · Dr · new〕
As a **Basic doctor**, on a returning patient I want `✨ recall — what product/units last time?` and an
AI-history teaser, so that the longitudinal-understanding upsell shows on every return.
- **Acceptance:** labelled teasers on the Basic patient file; tap → upgrade. Basic still shows the
  glanceable visit history + your own notes (AES-203) — the teaser sells the *synthesis + recall*, not
  the data.

---

## E9 — Multi-seat / multi-user
*Details [foundation §7](foundation.md). **Built** (finishes the Basic tier) — contracts in
[docs/backend/aes-basic-api.md](../backend/aes-basic-api.md) §E9.*

### AES-901 — Author attribution 〔Both · All · new〕
As **any clinician**, I want every capture/visit/note/photo to show **who created it and when**, so that in a multi-seat clinic it's clear who did what.
- **Acceptance:** "by <user> · time" on captures, visits, the patient timeline; from `created_by_user_id` (exists); deterministic.

### AES-902 — Session ownership 〔Both · All · new〕
As a **doctor**, I want the session I started **owned by me** and editable/curatable only by me by default, so that my record isn't changed under me.
- **Acceptance:** session owner = creator; edit/curate owner-only unless tenant policy (AES-905) grants more; others see it attributed/read-only; *contribute* follows policy.

### AES-903 — My "up next" worklist 〔Both · Dr · new〕
As a **doctor**, I want the patients reception lined up for me, and to start one with a tap (history + before/after first), so that I can work from my list — **without being forced to**.
- **Acceptance:** a "Today / up next" filtered to patients assigned to me; tap → patient → start session (assign-first); the capture footer **always** still starts a fresh session (capture-first never blocked). Soft list, not a calendar.

### AES-904 — "Mine vs Clinic" filter 〔Both · All · new〕
As a **doctor**, I want to filter Today / search / lists to my own work vs. the whole clinic, so that I focus without losing the shared base.
- **Acceptance:** deterministic toggle; sensible default (mine on Today, clinic on search).

### AES-905 — Configurable role permissions 〔Both · Admin · new〕
As an **admin**, I want to set what assistants and receptionists may do (**contribute / reassign / edit**), so that the product fits my clinic's real roles.
- **Acceptance:** per-role **presets** in Settings (contribute-only · +reassign · full); permissive default (contribute open · reassign = receptionist+owner · edit = owner); loosenable/tightenable; drives AES-902 + AES-906. Not a granular matrix.

### AES-906 — Policy-aware intent application 〔Pro · All · modify〕
As a **doctor**, I want a colleague's capture to **add** to my session, but a **reassign/edit they're not permitted** to become a **suggestion** for me rather than apply silently, so that permissions never block and never surprise.
- **Acceptance:** the intent gate applies append/reassign/edit **iff** the capturer's role is permitted (AES-905); else → **suggest-to-owner** (reuse `suggested_reassignment`); never blocks the capture. Pro (intents from transcription).

### E9 — as-built notes (deviations & additions beyond the plan, with rationale)

These were decided during build/review, not in the original AES-901..906 acceptance notes. Both tiers
unless stated. Backend contracts: [docs/backend/aes-basic-api.md](../backend/aes-basic-api.md) §E9.

- **No `receptionist` role — Assistant is the reception/intake seat.** The codebase models only
  `doctor`/`assistant`/`admin`; the design (§2/§7) names a receptionist but it was never added.
  *Why:* a new role means an enum migration + persona/seed/login wiring; deferred by decision. Assistant
  therefore carries the receptionist's permissive default (`assistant: reassign`, `doctor: contribute`).
  Adding a real receptionist later is the clean follow-up (slots into the same preset map + worklist roles).
- **Worklist is role-aware (creator vs. consumer), beyond AES-903's "soft list".** Reception
  (assistant/admin) **creates** line-ups *for a doctor* (the target picker lists doctors only, never
  self); doctors **consume** a read-only queue. *Why:* review feedback — doctors lining patients up for
  themselves / self-assigning was wrong; reception is the natural creator.
- **"Start visit" quick action** on a doctor's queue card → creates a session already assigned to the
  patient + marks the entry seen. *Why:* skip the patient-page → back → capture round-trip.
- **"Up next" recap popup** (replaces inline text): tapping a queued patient opens a sheet with
  tier-aware patient **history** (Pro AI sections / Basic structural recap, via the shared history
  block) + the prior visit's **before/after**, plus Start visit and "Open full timeline". *Why:* a
  glanceable recap before starting; "last visit note" was ambiguous (a visit has many notes), so we use
  the proper history brief. The box is **hidden entirely for a doctor with an empty queue**, and its
  description sits behind an ⓘ toggle — keep Today uncluttered.
- **Context-aware capture target.** While a patient's file is open in Clinical Memory, the footer
  captures **for that patient** (a new visit); the session is created only on the capture action, so
  merely viewing never changes the target, and leaving reverts to the active session. *Why:* "capture
  for who I'm looking at" without breaking capture-first.
- **Next-patient on the capture screen (AES-301 tie-in).** An unassigned active visit surfaces the
  doctor's next lined-up patient by name with **Assign this visit** (files it onto them + clears the
  entry) and **Start their visit**. *Why:* file a capture-first visit onto the queued patient without
  leaving capture.
- **Role-based default landing screen.** Reception (assistant) + admins land on **Clinical Memory**;
  doctors land on the **Session** workspace. *Why:* reception coordinates, doctors capture-first.
- **New primitives to support the above:** `worklist_entries` table + `GET /clinic/members` (the
  line-up store + clinician picker) and `POST /sessions` reused for "Start visit". *Why:* AES-903 needs
  a stored "lined up for" record + a directory; neither existed.
- **Attribution verified on both tiers** (it's deterministic, no AI): session/capture/timeline
  `createdBy`, shown as "by X". *Why:* confirm AES-901 is not Pro-gated.

---

## E10 — Close-the-day / unified attention (Both)
*One severity-tiered attention model that every "needs you" signal maps into — a backend **roll-up**
over existing sources (needs-input decisions, unconfirmed doses, detected safety, pending Q&A, the
Batch-1 candidate suggestions), rendered in place and aggregated into the Close-the-day sweep. **Built
and merged.** As-built: [screens/patients.md](screens/patients.md) "Attention Tab", [states.md](states.md)
"Attention model", backend `GET /api/v1/attention` (`app/services/attention.py`).*

### AES-1001 — Severity taxonomy + unified attention roll-up 〔Both · Dr/As/Rc · new〕
As **any clinician**, I want one place that says how much is open and how bad it is, so that "needs
you" is a single severity-tiered signal instead of four disconnected counts.
- **Acceptance:** every signal maps to exactly one tier — **S1** safety (shown, opt-out, **never
  counted**), **S2** confirm (doses + assignment decisions + inert-assignment conflict = the true "N
  to confirm"), **S3** suggested (name-correction / unassign / reassignment / recheck), **qa** messages
  (pending patient questions). **S4** notes never roll up. Backend `GET /attention?scope=mine|clinic`
  is a pure roll-up over the existing sources (no new clinical logic); the calendar-day boundary uses
  the client tz offset and carries prior-day items as an "earlier" group. Q&A is Pro-gated (Basic
  contributes no messages).

### AES-1002 — In-place severity language 〔Both · Dr/As · modify〕
As a **clinician**, I want each item to keep its colour/label at its source, so that the aggregate and
the in-session view never diverge. *(The verify-bar/safety-panel/suggestion-chip re-skin is shared
with the session layout-diet strip; the shared tier→colour map lives in `features/memory/attention.css`.)*

### AES-1003 — Unified Attention indicator 〔Both · All · new〕
As a **clinician**, I want one top-bar indicator (a severity-coloured bell) instead of separate
needs-input and Q&A badges, so that one glance answers "how much is open?".
- **Acceptance:** merges the old needs-input + Q&A badges; the count is confirm + messages, coloured
  by the highest open tier; a safety-only feed shows a bare red dot (shown, never counted).
  Surface-by-exception — it renders only when something is open; tapping it opens the sweep. The Q&A
  inbox stays reachable as a plain workspace icon (Library/routing/reply live only there).

### AES-1004 — Close-the-day sweep lens 〔Both · Dr · new〕
As a **doctor**, I want an end-of-day cross-session lens that clears what's open, resolve-in-place, so
that "before I leave, clear what's open" has a surface.
- **Acceptance:** the **Needs-input tab evolved into the Attention tab** — severity-ordered sections
  (Confirm · Safety to review · Messages · Suggested) + an **"Earlier, still open"** carry-over group;
  `N of M cleared` progress (never completion pressure); `Mine`/`Clinic` scope; a calm empty state
  (surface-by-exception). Each action opens the **same** resolver its item uses at its source (inline
  assign/choose, the visit in Active Session, or the Q&A inbox thread — the reply flow is never
  reimplemented). Never a completion gate.

### AES-1005 — Role & tier scoping 〔Both · Dr/As/Rc · new〕
As **reception**, I want the sweep to default to intake/assignment (`Clinic`), while a **doctor**
defaults to their own doses/safety/messages (`Mine`), so that each role sees their own attention.
- **Acceptance:** default scope by role (assistant/admin → `Clinic`, doctor/owner → `Mine`); Basic's
  ladder is naturally sparse (only deterministic S2 items) — a legible upgrade, never an empty Pro
  teaser.

### AES-1006 — Opt-in end-of-day nudge 〔Both · Dr · new〕
As a **doctor**, I want a quiet end-of-day reminder that items are still open, so that I remember to
clear them — **without being blocked**.
- **Acceptance:** a pure, **dismissible** prompt shown only in the late-afternoon window when items are
  open; per-day dismiss; never a gate or wall (never-block holds). *A persistent tenant/user opt-out
  setting is the clean follow-up.*

### AES-1007 — One attention count across the bell + Today chip 〔Both · Dr/As/Rc · modify〕
As **any clinician**, I want the top-bar bell and the Clinical-Memory "needs your input" chip to show
the **same** number, so that "how much needs me?" never disagrees with itself. *(Refines AES-1003.)*
- **Acceptance:** the hero chip is fed the same `attentionBadgeCount` (confirm + messages) the bell
  shows (App threads it down); **surface-by-exception** — the chip is hidden when the count is 0 (no
  "All caught up" pill). When the Today "Needs your input" preview is empty **but** the sweep still has
  open items (earlier days / messages), that section points to the sweep («See all N in Attention»)
  instead of claiming "all caught up", so the chip, the bell, and the section can never contradict.
  As-built: [screens/patients.md](screens/patients.md).

### AES-1008 — Per-visit grouping in the Close-the-day sweep 〔Both · Dr/As · modify〕
As a **doctor**, I want a visit with several open confirmations to appear as **one** grouped row
(«{patient} — N to confirm») rather than N sibling cards, so that a heavily-uncertain visit doesn't
flood the sweep and bury the other items. *(Refines AES-1004.)*
- **Acceptance:** within each sweep section (and the `Earlier, still open` group), confirm-tier (S2)
  items sharing a `sessionId` collapse into one grouped row leading with the patient name (or
  «This visit» when unassigned) + «N to confirm»; a lone confirmation and every non-confirm item stay
  as their normal detailed rows, in order; the group's single action opens the visit — the same
  per-source resolvers walk its confirmations in place (a **list-shape** change, not a new flow).
  Section counts and the `N of M cleared` progress still count individual items. As-built:
  [screens/patients.md](screens/patients.md).

---

## E11 — User-authored treatment overlay (Pro)
*Realises the deferred `edit` intent as a human-owned overlay (no AI). Data/contract layer + the editing
UI **built** (AES-1101–1105). Mechanics: [pipeline-versioning D2](../architecture/pipeline-versioning.md),
[backend/processing.md](../backend/processing.md); the edit surface: [capture.md](screens/capture.md) +
[session-review.md](screens/session-review.md).*

### AES-1101 — `treatment_overlay` contract + stable treatment keys 〔Pro · Dr · built〕
As a **doctor**, I want a corrected treatment field (a mis-heard dose, a wrong lot) to be a durable,
human-owned edit the AI can never silently overwrite, so that the record — and every projection built on
it — reflects the truth I typed.
- **Acceptance (DATA layer):** deterministic content-anchored `treatmentKey`
  (Unicode-general norm, `areaCode`-anchored, ordinal on collision); `treatment_overlay` as the fourth
  overlay class (folded at render/projection via `effective_treatments`, excluded from restore, preserved
  + re-bound across re-synthesis with a no-LLM `{aiValue, value}` reconcile diff); the overlaid value is
  authoritative for recall / lot-recall / smart lists / patient-memory (the lot-recall safety case); a
  carried-forward dose edit auto-satisfies the confirm blocker (Q4); owner-gated field-edit endpoints
  (`POST`/`DELETE /sessions/{id}/treatment-overlay`, field-edit only per Q2). Synthesis schema-v2 adds
  `areaCode`, `priorKey`, and a `lang` stamp; eval-gated (key-echo-stability case).

### AES-1102 — Inline field editing + provenance 〔Pro · Dr · built〕
A quiet **✎** on each treatment row opens a compact per-field editor (area · product · brand · quantity ·
lot); each changed field saves instantly as its own overlay entry — no synthesis, no AI budget. An edited
field flips to a human-owned presentation: an **`✎ Edited by you`** chip (vs the AI spark) and a
provenance subline that **preserves the AI/dictated value** (`AI Dose: ۲۰ واحد`). A human-confirmed field
clears its low-confidence / missing-lot uncertainty chip.

### AES-1103 — Synthesis-proof reconcile 〔Pro · Dr · built〕
The overlay wins on render, but a disagreement is **surfaced, never silent**: the AI value stays visible on
the provenance subline with one-tap **Use AI** (drops the overlay → the AI value returns); Keep-yours is
the default (do nothing). *Q3's provenance subline and §3.3's reconcile are unified into one never-silent
affordance because the backend ships a single `{aiValue, value}` pair (no edit-time vs post-synthesis
distinction).* A re-key/removed edit that can't re-bind parks as an **orphan review chip** (never lost;
re-binds when its row returns, or Discard).

### AES-1104 — Projection correctness (lot/recall safety) 〔Pro · built〕
Recall, lot-recall cohorts, smart lists, and patient-memory read the **overlaid** value (`effective_treatments`
fold) — a corrected lot reaches the recall cohort. (Shipped with AES-1101's data layer.)

### AES-1105 — Attribution + owner-default gating 〔Pro · Dr · built〕
Every edit is attributed (`Edited by you` vs `Edited by a colleague`); the ✎ shows only when the viewer may
edit (Pro, not read-only). Backend gates the write on the owner-class (`full`) preset. *(3-mode edit-policy
presets remain a fast-follow.)*

- **Deferred (⊕):** AES-1106 row add/remove · AES-1107 non-owner suggested correction.

---

## E13 — Session-screen layout diet (the patient strip)
*Collapses identity + context + verify state + safety into one sticky **patient strip** above the report,
so a phone above-the-fold becomes `[thin AI-usage bar] → [strip] → [report]` (nine zones → effectively
two). A shared Basic+Pro shell (Pro lights up more chips). Surface:
[capture.md](screens/capture.md) "Patient strip".*

### AES-1301 — Unified patient strip 〔Basic+Pro · Dr · built〕
One component absorbs the patient card + session-context digest + verify chip + safety chip, with a
collapsed one-line state (avatar · name · visit ordinal · assignment state · `⚠ N to confirm` · `🩹` ·
chevron) and an expanded full-stack state (patient actions + context + safety panel + AI-created-patient
verify). Basic lights up fewer chips (no verify/safety — those are Pro).

### AES-1302 — Auto-collapse state machine 〔Basic+Pro · Dr · built〕
Pre-capture expanded → report-has-content collapsed → unassigned keeps `Assign` prominent → undo-all
re-expands → historical collapsed. Manual override always wins. On **(re)assignment of a patient with
history** the strip auto-surfaces that history; collapse waits for report-has-content **and**
history-surfaced.

### AES-1303 — Resolver placement 〔Pro · Dr · built〕
Active patient conflicts stay in a **thin always-visible band above the report** (visible + resolvable in
place, never buried); the AI-created-patient verify panel moves into the strip expansion (reached by the
`⚠` chip). Never-block preserved: a blocker's chip is always visible.

### AES-1304 — Safety chip + high-risk pin 〔Pro · built〕
A red safety chip is always shown collapsed; a tenant **high-risk-clinic** setting
(`high_risk_clinic` + Settings toggle) pins the full safety panel open — never a chip — for clinics where
allergies/contraindications must always stay in view.

### AES-1305 — Tier variants 〔Basic+Pro · built〕
Basic and Pro share the strip shell; Pro simply lights up more chips (verify + safety). The AI layers are
absent in Basic, not teased.

- **Deferred (⊕):** AES-1306 responsive two-column strip-beside-report on tablet/landscape.

---

## E14 — Tier convergence (converge the shell, keep the primary surface tier-appropriate)
*Both tiers render a session with ONE tabless skeleton — patient strip → primary working surface →
secondary collapsible view → capture bar — but **what sits in "primary" differs by tier** because the
valuable artifact differs. Pro's primary is the synthesized **report** (raw captures demoted to the
**Sources** drawer); Basic's primary is the captures **feed** itself (the tidy chronological document
is the secondary **View as document** panel that flows into Share). The legacy Captures/Live-report
**tab switch is deleted in both tiers**; AI zones stay capability-gated (omitted, not disabled, in
Basic). Shares the layout-diet strip (E13) + the E8 consolidated teaser. As-built:
[screens/capture.md](screens/capture.md) "Surface by tier".*

### AES-1401 — Kill the tab switch; one shared skeleton 〔Basic+Pro · Dr · built〕
As **any clinician**, I want a session to render with the same interaction model on both tiers, so that
upgrading from Basic to Pro is a continuity, not a relearn.
- **Acceptance:** the Captures/Live-report tab switch is removed; both tiers render `patient strip →
  primary working surface → secondary collapsible view → capture bar`. The secondary is always a
  drawer/panel, never a co-equal tab (no "which tab am I on"). Layout unification is tier-independent;
  the AI features stay capability-gated on resolved capabilities.

### AES-1402 — Basic feed-first primary surface 〔Basic · Dr/As · new〕
As a **Basic doctor**, I want the captures feed to be the persistent primary surface, so that during
capture I always see what I just added and touch my own content directly — no drawer to open for daily
work.
- **Acceptance:** the captures feed (audio player / photo / note, with edit / rename / delete /
  source-preview) is the primary body; no auto-collapse-to-document (the feed always leads). *Why:*
  Basic's "report" is the same captures reformatted — zero new information — so burying them behind a
  drawer optimizes the rare upgrade over the daily Basic experience (owner round-2 correction).

### AES-1403 — Basic "View as document" / Share 〔Basic · Dr/As · new〕
As a **Basic doctor / assistant**, I want a tidy chronological notebook (AES-302) to review / print and
a curated Share (AES-303), so that the patient still leaves with a professional artifact — but it lives
where sharing lives, not as the star of the capture screen.
- **Acceptance:** a lightweight **`View as document`** header affordance on the capture screen opens the
  secondary document panel (the chronological notebook); the curated **Share** lives inside it (the two
  entry points are the capture-screen header affordance **and** the Share flow — owner decision 1).
  **"Live report" wording is retired in Basic** — the document is `View as document` / `Visit record`
  (owner decision 2).

### AES-1404 — Capability-gated AI-zone omission 〔Basic+Pro · Dr · built〕
As a **Basic doctor**, I want the shared shell to omit the Pro-only AI zones cleanly, so that Basic has
no empty bands and stays legibly zero-AI.
- **Acceptance:** the AI spark, synthesis/`Organizing` states, verify bar (`⚠ N to confirm`), safety
  panel, treatment table, freshness line, aftercare auto-include and report-feedback bar are **omitted
  (not disabled)** in Basic — every one gated on resolved capabilities (`isPro`). The single
  consolidated foot teaser (E8) stays.

### AES-1405 — Upgrade-continuity verification 〔Basic→Pro · Dr · built〕
As an **upgrading clinic**, I want Basic → Pro to change only what the AI adds, so that there is no
relearned interaction model.
- **Acceptance:** a QA scenario proves the skeleton is invariant across the upgrade — same patient
  strip, same secondary-drawer pattern, same capture bar, same nav; only the primary flips (feed →
  report), the raw feed slides into the Sources drawer, and the AI zones light up. Covered by the
  real-stack tier-surface spec (`p0-14-tier-convergence-shell.spec.ts`).

### AES-1406 — Align with the layout-diet strip + E8 teaser 〔Basic+Pro · built〕
As a **Basic doctor**, I want the shared strip (Basic variant) and one consolidated teaser, so that the
convergence reuses E13/E8 rather than duplicating them.
- **Acceptance:** both tiers share the [E13 patient strip](#e13--session-screen-layout-diet-the-patient-strip)
  (Basic lights up fewer chips — no verify/safety); the document's own Try-Pro is suppressed so the
  screen keeps exactly one **Do more with Pro** (E8), at the foot of the primary feed.

---

## E12 — Unified finder (app-wide retrieval)
*One patients-first finder overlay that replaces the old top-nav `/#search` local-substring screen
with the real Persian-aware patient search + Pro lot recall. Built + folded to the system-state doc:
[screens/finder.md](screens/finder.md) (entry points + launcher in [navigation.md](navigation.md)).*

### AES-1201 — Finder overlay (patients-first) 〔Both · All · new〕
As **any clinic user**, I want one app-wide finder I can open from anywhere, so that the box I reach
for first is the one that can actually find a patient — not a local-only filter.
- **Acceptance:** a mobile-first full-screen sheet floating over the current screen (capture bar stays
  underneath); grouped grains (patients / today's visits / Pro lot recall); a pre-query empty state
  (recent patients + today's visits + hint); one back-stack history level so hardware Back / Escape /
  the close control dismiss it; bilingual (fa/en + RTL) chrome, clinical content verbatim + bidi-isolated.

### AES-1202 — Finder patient + visit search 〔Both · All · new〕
As a **clinician / receptionist**, I want the finder to hit the real ranked patient search and my
loaded visits, so that a patient the client never loaded is findable by name, phone, or national ID.
- **Acceptance:** patients grain = debounced `GET /patients/search` (AES-204 deterministic,
  Persian-orthography-aware, ranked; match-reason shown); visits grain = the loaded sessions
  (today's + query substring); no-results offers a duplicate-guarded **Add a patient** hand-off (routes
  to the Patients tab's shared `RegisterPatientForm`). Composes existing endpoints — no new backend surface.

### AES-1203 — Lot/product recall grain (Pro) 〔Pro · Dr/As/Rc · new〕
As a **doctor / receptionist under recall stress**, I want to type a lot number into the finder and
get the affected cohort, so that recall-under-stress isn't three taps deep behind a Pro tab.
- **Acceptance:** a lot/product-shaped query surfaces a distinct **Recall lot {lot}** action above
  patient results; selecting runs the exact-match `GET /lot-recall`; the compact inline cohort cites
  each patient's verbatim treatment line(s), keeps near-misses in a separate **Similar lots (not
  included)** group (never folded in), and exposes the per-patient Q&A outreach handoff — the
  [Lists-tab](screens/patients.md) safety contract, verbatim. Absent on Basic (a legible upgrade).

### AES-1204 — Replace `/#search`; offline fallback 〔Both · All · new〕
As **any user**, I want the finder to be the top-level retrieval surface, so that the strong search
is prominent and the old local one still works offline.
- **Acceptance:** the old `SearchHome` local-substring screen is retired; `/#search` deep-links into
  the overlay over Clinical Memory and normalizes the hash to `#patients`; offline, backend grains are
  skipped and the query falls back to the preserved local substring over loaded sessions with the
  "patient search may be limited" note.

### AES-1205 — Launcher + entry points 〔Both · All · new〕
As a **desktop user**, I want a ⌘K launcher, and on mobile the existing magnifier, so that the finder
opens from anywhere without a keyboard dependency on mobile.
- **Acceptance:** the top-bar magnifier opens the overlay (all sizes); **⌘K / Ctrl-K** opens it on
  desktop (a nicety, not load-bearing). The finder is no longer a nav pill (no `aria-current`).
- **Deferred (within the band):** the `Mine`/`Clinic` scope toggle (AES-904 reuse — currently defaults
  to the whole-clinic base), add-a-patient name prefill, and "expand to finder" from the assignment sheets.

### AES-1206 — Global content search 〔Pro · Dr/As · new · ⊕〕
As a **doctor**, I want the finder to also search capture/report *content*, so that I can find a visit
by what was said, not just by patient/lot. **Deferred candidate** — backend global content search across
captures / extracted findings / report prose is a larger later migration; find-only in v1.

---

## E15 — UI expert-review refinements: screens, router & controls (2026-07)

*The accepted items from the 2026-07 UI expert review (trust/coherence/polish pass). This slice —
screens, router, and the public landing — covers the **screen/state** items; the capture/attention/shell
items land alongside it. Surfaces: [screens/insights.md](screens/insights.md),
[screens/qa-inbox.md](screens/qa-inbox.md), [states.md](states.md), [navigation.md](navigation.md).*

### AES-1501 — Role-guarded owner/admin routes + shared permission state 〔Both · Dr/As/Admin · new〕
As a **doctor**, when I reach an owner/admin page by a direct hash (deep link, bookmark, restored
screen), I want to land on my own workspace instead of a broken page, so that the boundary is honest and
calm.
- **Acceptance:** the clinic-management screens (`#insights` / `#team` / `#plan`) are route-guarded on
  the `canManageTeam` (owner/admin) capability — a non-owner hash-navigating to any of them redirects to
  `#patients` (the render also falls through, so no owner-only content flashes and no API call fires);
  an owner is never redirected. Any owner/admin API **403** maps to the shared **permission-denied**
  state (no retry — retrying can't grant access), reserving `try again` + a Retry button for genuinely
  retryable failures ([states.md](states.md) "Permission & retryable states"). Hermetic e2e pins the
  redirect for all three hashes + the owner non-redirect.

### AES-1502 — One control language (segmented control + select trigger) 〔Both · All · new〕
As a **clinic user**, I want the app's toggles and dropdowns to look like one system, so that the UI
reads as coherent rather than assembled from mismatched parts.
- **Acceptance:** a single segmented-control primitive (`Tabs`, `role="tab"` + `aria-selected`) and a
  single select-trigger (`SelectMenu`), matched in height/radius. Applied first on the **Q&A inbox**
  (Inbox|Library, Mine|Clinic → the segmented control; Routing → the select trigger) and **Insights**
  (sub-tabs + Activity series → the segmented control; range → the select trigger; the `Compare to
  previous` toggle aligned to the select height/radius). RTL-mirrored; bilingual chrome.

### AES-1503 — Q&A inbox teaching empty state 〔Pro · Dr/As · new〕
As a **doctor** with an empty Q&A inbox, I want to learn how a thread arrives and get a shortcut to
start one, so that a paid Pro feature isn't a dead end.
- **Acceptance:** the empty inbox shows the scope headline **plus** one teaching sentence (a thread
  starts when a patient asks from their Q&A link) **and** a **Share Q&A link** shortcut that opens the
  app-wide finder to pick a patient and open their Q&A channel. As-built:
  [screens/qa-inbox.md](screens/qa-inbox.md). *Extends AES-402.*

### AES-1504 — Landing hero mirrors the live capture bar 〔Basic · Pt · new〕
As a **prospect**, I want the landing mockup's capture bar to match the real first-run app, so that the
promise matches what I get.
- **Acceptance:** the landing in-product preview leads with **Record** (primary) then **Photo**, **Note**
  — the Pro capture-bar order (`CaptureActions`) — instead of the old Note-primary Note/Photo/Audio.

### AES-1505 — Dev usage-jump control reads as tooling 〔Pro · Dr · modify〕
As a **developer/tester**, I want the Settings AI-usage jump control to look like a clearly-badged dev
box, so that it never leaks a "broken" look into an otherwise coherent screen.
- **Acceptance:** the dev-only usage-state jumper (ships in dev builds only, `IS_DEV`) renders in a
  dashed, `Dev`-badged inset box with the percentages as small buttons — not four bare percentage links.

## E16 — Clinical Memory & top-bar UI-review refinements (2026-07)
*Accepted items from the 2026-07-10 UI expert review — trust/coherence + polish on the Clinical Memory
screen and the app top bar. The unified-count and sweep-grouping items from the same review live in
[E10](#e10--close-the-day--unified-attention-both) (AES-1007 / AES-1008).*

### AES-1601 — One shared timestamp formatter 〔Both · All · modify〕
As **any clinician**, I want every clock time in a card to use one convention, so that a visit card
never shows `Visit: … 17:43` directly above `Updated: 5:43 PM`.
- **Acceptance:** a single clock formatter (`shared/lib/datetime.formatTime`) drives the visit card's
  `Visit:` / `Updated:` lines, the patient-card "Latest visit", and the capture "updated" labels —
  **24-hour everywhere** (Persian digits under fa via the `fa-IR` locale, 24h under en). The `Visit:`
  line derives from the visit timestamp so its date localizes (`Today` → «امروز»). Decision: en clock =
  24h ([technical-decisions](../technical-decisions.md)).

### AES-1602 — Drop the marketing subtitle on Clinical Memory 〔Both · All · modify〕
As **any clinician**, I want the Clinical Memory heading to orient without a marketing sentence, so that
every phone visit isn't taxed a self-praising text row (it violated the calm-professional principle it
cited).
- **Acceptance:** the "Your calm, intelligent assistant…" subtitle is removed; the heading + attention
  chip + search already orient. If it must live somewhere, it belongs in onboarding.

### AES-1603 — Legible primary nav at every width 〔Both · All · modify〕
As a **new user**, I want the Visit/Memory nav pills identifiable at phone widths, so that two
near-abstract glyphs aren't the only cue.
- **Acceptance:** the `Visit` / `Memory` labels are kept at **all** widths (the action cluster is
  compacted on phones so the full Pro row — nav + search + Q&A + bell + avatar — still fits one line at
  390px), plus a **decisively stronger selected state** (full-primary ring + heavier weight) so the
  active pill reads even where a glyph would otherwise be icon-only.

### AES-1604 — Balanced top bar on tablet 〔Both · All · modify〕
As a **tablet user**, I want the top bar to read as intentional, so that the brand doesn't float
mid-bar with leftover space.
- **Acceptance:** the `Engram` wordmark is anchored to the inline-start (far-left; far-right under RTL)
  **before** the nav cluster, with the avatar pinned to the inline-end and the single flexible gap
  between them — no mid-bar float. Phones keep the two-row restack (brand on top).

---

## E17 — Report version history (Pro)
*Exposes the content-addressed `session_report_versions` store (pipeline-versioning) as a navigable
history UI, replacing the bare "Undo last capture" button with navigate → preview → restore. Built
(v1). Mechanics: [pipeline-versioning](../architecture/pipeline-versioning.md); surface:
[screens/capture.md](screens/capture.md) "Report history".*

### AES-1701 — Report version timeline 〔Pro · Dr/As · built〕
As a **doctor**, I want a quiet **History** affordance on the report card that opens a timeline of every
stored version — time, a trigger label (photo added / transcript edited / …), capture count, demoted
provenance — so that I can see how the report evolved instead of a one-way Undo.
- **Acceptance:** newest-first list from `GET /sessions/{id}/report-versions`; the current version tagged
  `Current`; Pro only (Basic has no synthesis chain). Trigger labels are **chrome** — the backend sends a
  structured `{kind, count?}`, the client localizes it (fa/en). Empty/1-version → calm empty state.

### AES-1702 — Read-only version preview (overlay-on-top) 〔Pro · Dr/As · built〕
As a **doctor**, I want to tap a version and see that report **read-only**, with a
`Viewing the version from HH:MM · Back to current` banner, so that I can inspect a past state without
changing anything.
- **Acceptance:** renders the version's artifacts through the same report presentation (`canEditTreatments`
  off); the **live user-state overlay** (rejected flags / dismissed aftercare / confirmed doses /
  treatment edits) is applied on top so a decision is never time-traveled away (pipeline-versioning D2).
  In-sheet preview (not time-travel-in-place) keeps the CaptureScreen mount to a single header affordance.

### AES-1703 — Revert-restore (owner-only) 〔Pro · Dr · built〕
As a **visit owner**, I want to **restore** the report to an earlier version, so that a later capture that
made the report worse can be rolled back — the richer face of undo.
- **Acceptance:** `POST /sessions/{id}/report-versions/{vid}/restore` returns the session to that version's
  capture set by de-effecting the captures added after it, reusing the **exact undo machinery** (P0-8
  semantics shared); **owner-only** (`can_remove_capture`), gated behind a confirmation naming how many
  captures are removed. Offered **only for versions reachable by removal** (subset of the current set); a
  non-linear version is **preview-only** with a calm note. `409` when unreachable. **No pipeline change.**

### AES-1704 — Quick undo stays 〔Pro · Dr · built〕
As a **doctor**, I want "Undo last capture" to remain the one-tap shortcut in the Sources drawer, so that
the common case stays instant while the timeline is its richer, multi-step face.
- **Acceptance:** the Sources-drawer Undo is unchanged (it is "restore the previous version", N=1, on the
  same `DELETE /captures/{id}` de-effect path).

- **Deferred (⊕, fast-follows):**
  AES-1705 **pin** (make a version authoritative without touching captures — the unused `pinned` column);
  AES-1706 **time-travel-in-place** preview; AES-1707 **field-level version diffs**; AES-1708 **D5
  GC/bounded-ring** (pipeline-versioning); restore under the 3-mode **edit-policy presets** (shared undo
  fast-follow); restore to **non-linear** (out-of-context / re-add) versions.

## E18 — Legible safety flags (owner testing, 2026-07)

Extends [AES-701](#aes-701--safety-flags-surfaced-each-visit-pro). Owner testing found the safety
panel legible only after reading a full dictated sentence; the flags must be glanceable and
impossible to miss. Screen: [capture.md — Safety panel + Patient strip](screens/capture.md). Eval-gated
(synthesis PROMPT_VERSION bump + `safety_flags_eval` label assertions).

### AES-1801 — Two-layer safety flag: legible label + evidence 〔Pro · Dr/As · built〕
As a **doctor**, I want each safety flag shown as a short normalized **label** (kind + substance) with the
clinician's verbatim sentence as expandable **evidence** and a tap-through to its source capture, so that
I read the fact at a glance yet can still verify the quote.
- **Acceptance:** synthesis emits a per-flag `label` (report language, native script, not a verbatim
  echo) alongside the unchanged verbatim `text`; the panel shows the label as primary, the verbatim
  sentence under `Show evidence`, and `sourceCaptureIds` as the report's `↗ source` citation; a
  pre-label flag falls back to the verbatim text as primary. The stable rejection/reconcile **key stays
  text-based** (a reworded label never shifts it). The label rides onto the patient store and the
  cross-visit surfaces (context card + timeline) as the glanceable primary.

### AES-1802 — Event-driven strip expansion + flag-count chip 〔Pro · Dr/As · built〕
As a **doctor**, I want the patient strip to open itself when a safety flag arrives or changes, and the
collapsed strip to carry a red **count** chip, so that a new flag is never missed and I always see how
many are on record.
- **Acceptance:** the strip auto-expands when the kept-flag set changes to a new, unacknowledged set (a
  patient with existing flags first assigned, a flag landing from synthesis/reconcile, a restore/undo);
  the clinician can collapse it and the same set is not re-expanded (**acknowledged-signature** in
  session UI state); the collapsed strip always shows a `🩹 N` chip when any flag exists. Reuses the
  high-risk-clinic pin-open machinery.

## Coverage check — every agreed feature is detailed

| [Foundation §3](foundation.md) item | Stories |
| --- | --- |
| Basic 1 — shared clinic workspace | (exists; underpins AES-201, E6) |
| Basic 2 — patient-centric filing | AES-201 |
| Basic 3 — visual-first gallery *(pairing → Pro, amended 06-12)* | AES-103, AES-202; AES-104 (Pro pairing) (+⊕ AES-105) |
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
Rationale + recommendation for each: the **Decisions** block below.

**Decisions (2026-06-11 & 06-12 reviews):** **Before/after — Basic presents** (a visit-grouped photo
gallery, **no tagging / pairs / slider**); **Pro prepares** (captions + assembled before/after pairs +
slider) — *amends foundation §3 Basic 3 (06-12)*. **No structured forms in Basic** — a Basic treatment/lot row is
**rejected** (Basic = free-text note + retrieval; structure is Pro-only, by extraction). **AES-703
consent — dropped** (a consent form a clinic wants on file is just a photo). **AES-404 delivery** —
copy-link / native-share / QR first; automated SMS/WhatsApp deferred. **AES-110 face-map** — a *derived*
visualization of dictated treatment only (never tap-to-enter), later spike. **AES-503 lot scan** — out
of MVP. **AES-704 pre-visit link** — agreed, deferred. **AES-105 ghost-overlay** — adopt v1 Basic,
reframed as an optional "align to a previous photo" aid.
