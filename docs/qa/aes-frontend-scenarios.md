# Aesthetics-Basic clinic app — manual test scenarios

> A numbered, no-code script a non-developer can follow in the running app to verify every
> aesthetics-**Basic** clinic story. Each scenario lists the **story**, the **setup** (which login
> persona + tier, and any sample data to create first), the **steps** (where to navigate / what to
> click), and the **expected** result (tied to the story's acceptance criteria).
>
> Companion docs: stories [`../ux/aesthetics-stories.md`](../ux/aesthetics-stories.md) · spec
> [`../ux/redesign-aesthetics.md`](../ux/redesign-aesthetics.md) · backend contracts
> [`../backend/aes-basic-api.md`](../backend/aes-basic-api.md). Prototypes the screens match:
> `apps/frontend/design-prototypes/aesthetics-{capture,patient,report,frontdesk}.html`.

---

## 0 · Conventions, routes & how to sign in

**App URL.** The clinic app is a single-page app. In local dev it runs at the URL the dev stack
prints when it starts (`scripts/dev-stack.sh up` → e.g. `http://localhost:5183`, or a worktree's own
port such as `http://localhost:5184`). All screens below are reached **inside** that one app — there
is no separate page to type a URL for; you navigate with the on-screen controls. Where a screen has a
stable hash, it is given as `#…` (e.g. the app root + `#settings`).

**Top navigation (always visible).**
- **Session** (the capture screen) — the default screen, hash `#active-session`.
- **Memory** (Clinical Memory: Today · Patients · Needs input) — hash `#patients`.
- **Search** (the magnifier) — hash `#search`.
- **Avatar menu** (top right) → **Profile** (`#profile`), **Settings** (`#settings`), **Logout**.

**Sign in as the right persona + tier.** On the sign-in screen:
1. In the **Tier** switch, choose **Basic** (this is the whole point — everything below is the Basic
   experience).
2. Click a persona: **Doctor** (clinician) or **Assistant** (documentation) for clinical scenarios;
   either also acts as the **Receptionist** for the front-desk scenarios (reception lives inside
   Clinical Memory). Use **Admin** only where a scenario says so.
3. To switch tier/persona later: avatar menu → **Logout**, then sign in again.

**Sample data to create once (used across many scenarios).** Sign in as **Doctor · Basic**, then:
- Go to **Memory → Patients → New patient** and create **سارا نظری** (Sara) — National ID
  `0012345678`, phone `+989120000001`. (Type the name in Persian, or any name you like; the Persian
  name best shows the orthography-aware features.)
- Create a near-duplicate **سارا نظری‌فر** — National ID `0019887210`.
- Create **بابک احمدی** (Babak) — phone `+989120000003`.
- Create at least one **aftercare template** (Scenario 22) so the share sheet has something to attach.
- Where a scenario needs prior **visits/photos** for a patient, it says so in its own setup.

**The golden rule for Basic (test it everywhere).** Basic is **deterministic and AI-free**: you must
**never** see a ✨ sparkle on a Basic feature, a "Processing / Organizing / Transcribing" state, an
AI transcript, an AI caption, or an AI-written summary. The only ✨ allowed is on a clearly-labelled
**"✨ Try Pro"** teaser (violet), which is non-functional.

---

## E1 · Capture & active session

### 1. Note-first capture footer (AES-101) — *the tier shows in the footer order*
- **Story:** As a Basic doctor, capture is **note-first**; audio is a secondary **voice memo**.
- **Setup:** Doctor · **Basic**.
- **Steps:** Land on **Session** (`#active-session`). Look at the three buttons in the bottom footer.
- **Expected:** Left/primary button is **Note** (blue-filled) with a small **"memo"** sub-label; middle
  is **Photo**; right is **Audio** with a **"memo"** sub-label. (Sign out, sign in as **Pro**, and the
  order flips to **Record/Audio** first labelled "dictate" — proof the order encodes the tier.)

### 2. Instant, zero-AI note capture (AES-101)
- **Story:** A note is saved instantly, locally, with no AI job and no processing state.
- **Setup:** Doctor · Basic, on **Session**.
- **Steps:** Tap **Note**, type "Forehead Botox, 20u Dysport — lot on box. Recheck 2 weeks.", tap
  **Save to session**.
- **Expected:** The note appears immediately in the **Captures** feed with a timestamp. A toast says it
  saved on the device. **No** "Processing", **no** ✨, **no** "Organizing" appears. The note text shows
  as your own words (no AI "decorated text"). **Tap the note text** → it becomes an inline editable
  field (no separate "Edit" button); change it and tap away → it saves.

### 3. Audio is a voice memo — no transcript (AES-101 / AES-802 edge)
- **Story:** In Basic, audio is a playable **voice memo**; it is never transcribed.
- **Setup:** Doctor · Basic, on **Session**.
- **Steps:** Tap **Audio**, record a few seconds, tap **Stop & save** (or attach an audio file).
- **Expected:** The audio card shows a **compact play/pause + seek-bar + time** player. There is **no**
  transcript section, **no** "Transcribing audio" placeholder, and **no** persistent "saved" badge —
  sync state appears **only if there's a problem** (a "Syncing" / "Needs attention" marker by the
  title). On the **first** audio capture a small **"✨ Try Pro"** badge sits below the player (Scenario 6).

### 4. Photo capture, filed to the patient (AES-103)
- **Story:** Photos are filed to the patient and shown — no tagging, no AI caption, shown whole.
- **Setup:** Doctor · Basic, on **Session**.
- **Steps:** Tap **Photo** → **Take photo** or **Choose**, pick an image, tap **Use photo**.
- **Expected:** The photo appears in the feed **shown whole (not cropped)**. There is **no** Before/After
  tag, **no** slider, **no** "Reading image" AI caption, and **no** explanatory caption text. On the
  **first** photo a small **"✨ Try Pro"** badge sits at the **bottom-left** of the photo (Scenario 6).
  Tap the photo to open it → a plain **"Caption"** free-text field (no "AI-generated caption", no
  processing/file metadata) you can fill in.

### 5. Ghost-overlay alignment aid (AES-105)
- **Story:** Optionally overlay the patient's previous photo faintly while shooting, so framing matches.
- **Setup:** Doctor · Basic. The active visit must be **assigned to a patient who has a prior photo**
  (assign the visit to Sara after seeding her a prior visit-with-photo — see Scenario 11 setup).
- **Steps:** Tap **Photo**. Above the photo area, tap the **"⊕ Align to last photo"** toggle.
- **Expected:** The toggle turns active ("Aligning to last photo") and the patient's previous photo
  appears **faintly overlaid** on the capture area as an alignment guide. Toggling again removes it. No
  Before/After labels, no AI.

### 6. The single "✨ Try Pro" upsell is labelled & non-functional (AES-801–804)
- **Story:** Lightweight AI shows in Basic only as a labelled, non-functional teaser — **one per screen**.
- **Setup:** Doctor · Basic, with a capture or two in the feed (Scenarios 2–4).
- **Steps:** Scroll to the **bottom of the Captures feed**. There are **no** ✨ badges on individual
  captures — instead there is **one** consolidated **"Do more with Pro"** card. Tap it.
- **Expected:** A single info box opens ("**Upgrade to Pro · Do more with Pro**") listing the Pro
  capture features as bullets (dictate & transcribe audio · auto-caption & pair before/after photos · a
  structured treatment report). It **never** runs AI; dismiss with the **× (top-right)**, **Got it**, or
  by **tapping the backdrop**. One contextual teaser also appears once on the Basic **report** (Scenario
  16) and the **patient file** (Scenario 13) — never per-capture.

### 7. Last visit, one glance + "same as last time" (AES-106)
- **Story:** For a returning patient, the prior visit's note + photos surface at capture, with a one-tap
  note pre-fill.
- **Setup:** Doctor · Basic. **Seed Sara a prior visit first** (see Scenario 11 setup), then start a
  **new** visit and assign it to **Sara** (via **Edit patient** on the patient card → search Sara →
  Select).
- **Steps:** With Sara assigned on the **Session** screen, look just under the patient card.
- **Expected:** A dashed **"Last visit · <date> — your note: "…"** strip appears, with the prior note,
  small thumbnails of last visit's photos labelled **"compare by eye"**, a **"View visit"** link, and a
  **"Same as last time"** button. Tap **View visit** → opens the prior visit. Tap **Same as last time**
  → the note composer opens **pre-filled** with the prior note and a hint **"Pre-filled from last
  visit — edit before saving."** (it is never auto-saved; you must edit/save it).

### 8. Basic has no AI report states (AES-101 edge)
- **Story:** Basic never shows AI report processing.
- **Setup:** Doctor · Basic, with a few captures in a visit.
- **Steps:** On **Session**, switch the report card tab to **Live report**.
- **Expected:** The card's tier chip reads **BASIC**. The report is a **chronological** document (see
  Scenario 16). There is **no** "live / updating" spinner, **no** "Generating structured report", **no**
  ✨. (Sign in as Pro to contrast: Pro shows a synthesized report and an "updating" cue.)

---

## E2 · Patient file, memory & search

### 9. Smart, Persian-aware patient search (AES-204)
- **Story:** Deterministic, Persian-orthography-aware, multi-field search, instant.
- **Setup:** Doctor · Basic, with the sample patients created.
- **Steps:** **Memory → Patients**. In the search box type **سارا** (or part of any patient's
  name / phone / national ID).
- **Expected:** A line **"Deterministic, Persian-aware match · N results"** appears, then ranked
  patient rows. Each row shows the patient, a **match reason** ("Name starts with the query."), and a
  small **match chip** ("name prefix", "✓ national ID", "✓ phone", …). Results are ordered by match
  strength. Tap a row → opens that patient's file. (Searching a national ID or phone matches those
  fields too.)

### 10. Deterministic patient memory recap — no ✨ (AES-206)
- **Story:** A structural recap (visit counts/dates/capture types/your verbatim notes), no AI.
- **Setup:** Doctor · Basic. Open a patient with at least one visit (after Scenario 11 setup), or any
  patient.
- **Steps:** **Memory → Patients →** tap the patient.
- **Expected:** A **"Patient history"** card shows a **structural** recap (e.g. "3 visits since … ·
  Recent visits: …"), with **no** ✨ sparkle anywhere on it. An audio-only visit reads as a voice memo,
  never a paraphrased transcript. (Sign in as Pro to contrast: Pro's history carries a ✨ and AI prose.)

### 11. Per-patient photo gallery, grouped by visit (AES-202)
- **Story:** The whole photo history at a glance, grouped by visit, recent first — no tags/pairs/slider.
- **Setup:** Doctor · Basic. **Seed a patient with photos across two visits first:** assign a captured
  visit (with 1–2 photos) to **Sara**, then start a **new** visit, add another photo, assign it to Sara
  too. *(If photo upload is unavailable in your environment, this section is empty — see the
  Environment note at the end.)*
- **Steps:** **Memory → Patients →** tap **Sara**.
- **Expected:** A **"Photo gallery — by visit"** card lists visit groups (most recent first), each
  headed by **"<date> · <visit title> · N photos"** with the photos in a row. There are **no**
  Before/After tags, **no** pair slider. A footer note reads: "No tagging — your photos, grouped by
  visit, recent first. You compare by eye; **Pro** labels & pairs them with a slider." Tapping a photo
  opens that visit.

### 12. Glanceable visit history (AES-203 Basic)
- **Story:** Each visit shows your own note + that visit's photos — the answer lives in your free text.
- **Setup:** Doctor · Basic, Sara opened (with a couple of visits).
- **Steps:** Scroll the patient file to the **visit timeline**.
- **Expected:** A skimmable list of visits, each with its date, your note summary, and capture chips.
  There is **no** structured Area/Product/Units/Lot table (that's a Pro feature).

### 13. "✨ Try Pro" file teaser — recall & AI history (AES-804)
- **Story:** On a Basic patient file, a labelled teaser sells the Pro synthesis + recall.
- **Setup:** Doctor · Basic, any patient opened.
- **Steps:** Look between the "Patient history" recap and the visit timeline.
- **Expected:** A violet **"✨ Try Pro — AI history & "what did we use last time?""** teaser with
  subtitle "Basic lists the facts. Pro synthesizes the story and recalls products / units / lot." and a
  "Try Pro →" affordance. Tapping it only reveals the "Pro feature" note — it never runs AI.

### 14. Duplicate-patient guard on create (AES-205) — *near-match edge*
- **Story:** A warning before creating a patient who looks like an existing one.
- **Setup:** Doctor · Basic, with **سارا نظری** (National ID `0012345678`) already created.
- **Steps:** **Memory → Patients → New patient**. In **Full name** type **سارا نظری**; in **National
  ID** type **0012345678**.
- **Expected:** An **amber "⚠ This looks like an existing patient"** block appears with the subtitle
  "N close matches — Persian-orthography aware…", and one or more candidate rows (name + reason such as
  "An existing patient already has this national ID.") each with a **"Use this"** button. The submit
  button changes to **"Create anyway"**. Tap **Use this** → it adopts the existing record and opens that
  patient (no duplicate is created). Tap **Create anyway** → it still creates the new patient (never
  blocks). *Edge:* type only a **fuzzy** name with no matching ID/phone → candidates may still list but
  the amber flag does **not** raise (a weak signal alone never warns).

---

## E3 · Reports & sharing

### 15. (covered above) Basic report tier chip — see Scenario 8.

### 16. Basic chronological report + "✨ Try Pro" teaser (AES-302 / AES-801)
- **Story:** A clean chronological document (clinic + patient header, notes + photos, honest
  timestamps, no synthesis), with the "structure this" teaser.
- **Setup:** Doctor · Basic, a visit with a note and a photo, assigned to a patient.
- **Steps:** On **Session**, switch the report card to the **Live report** tab.
- **Expected:** A document with a **Clinic Information** + **Patient Information** header, then each
  capture **in chronological order** with its honest timestamp (the note as your words, the photo
  shown). No AI synthesis, no ✨ chips, no "Treatment performed" table. At the end sits a violet
  **"✨ Try Pro — turn your notes into a structured treatment report"** teaser.

### 17. Curate & share a patient report (AES-303 / AES-403)
- **Story:** Curate which before/after + sections the patient sees; share a read-only link; internals
  withheld.
- **Setup:** Doctor/Assistant · Basic. Open a patient (ideally one with photos + a note). At least one
  **aftercare template** must exist (Scenario 22).
- **Steps:** **Memory → Patients →** open the patient → tap **Share with patient** (top of the file).
- **Expected:** A **"Share with patient"** sheet opens: an instruction "Pick what <name> sees. They get
  a read-only link — nothing else from the file.", an editable **Title**, toggles for each
  **before/after photo** (with an optional caption), a **Visit summary** toggle (seeded from your note),
  and an **Aftercare instructions** toggle with a **template dropdown**. A grey **"Always withheld: raw
  audio, internal notes, lot numbers, national ID, other visits."** line with a lock icon is always
  shown. Tap **Preview** → see exactly what the patient will see. Tap **Send link** → a confirmation
  appears (outward-facing action), then a **read-only link** is produced with **Copy link**, a delivery
  hint (SMS/WhatsApp/any channel), and a **Revoke access** action.

### 18. Sharing is explicit & revocable; internals never leak (AES-403 edge)
- **Story:** Sharing is an explicit action exposing only curated content, and is revocable.
- **Setup:** Continue from Scenario 17 after a link is created.
- **Steps:** In the created-share view, tap **Revoke access** and confirm.
- **Expected:** The status flips to **"Link revoked — the patient can no longer open it."** (The
  withheld items — lots, national ID, raw audio, other visits — were never part of the curated snapshot
  to begin with; the preview only ever showed the toggled photos, summary, and aftercare.)

### 19. Attach aftercare to the share (AES-304)
- **Story:** Templated aftercare instructions ride along on the shared report.
- **Setup:** As Scenario 17, with at least one aftercare template.
- **Steps:** In the share sheet, ensure **Aftercare instructions** is toggled **on** and pick a template
  from the dropdown. Tap **Preview**.
- **Expected:** The preview shows the aftercare template's title and body as the patient would read it.
  Choosing a different template updates the preview.

---

## E6 · Front desk / reception

### 20. Register a patient (AES-601) + duplicate guard (AES-205)
- **Story:** Register with name required, rest fill-later; the duplicate guard runs as you type.
- **Setup:** Receptionist role (sign in as **Assistant · Basic**, or **Doctor · Basic**).
- **Steps:** **Memory → Patients → New patient**. Type a brand-new name (e.g. "Test Patient One") and
  tap **Create patient**. Then repeat but type an existing name/ID (see Scenario 14).
- **Expected:** A name alone is enough to create (other fields optional). When the typed
  name/ID/phone matches an existing record, the amber duplicate guard appears (Scenario 14) and the
  button becomes **Create anyway**. The created patient opens in their file.

### 21. Today / arrivals board (AES-602)
- **Story:** A front-desk view of who's in and what needs a patient.
- **Setup:** Assistant/Doctor · Basic. Have at least one **active** visit and one **unassigned** visit
  (start a capture without assigning a patient).
- **Steps:** **Memory → Today**.
- **Expected:** The Today board shows the **Active session**, a **Needs your input** section (which
  surfaces the unassigned visit), and **Updated today**. The unassigned visit's card offers **Assign
  patient**. (This is the front-desk lens; it is not a calendar/scheduler.)

### 22. Attach an unassigned (doctor-captured) visit (AES-301 / AES-603) — *deterministic suggestion*
- **Story:** One-tap assign a visit the doctor captured before registration, with a deterministic
  "Assign to …?" suggestion.
- **Setup:** Doctor · Basic. Start a capture **without** assigning a patient (leave it "Unassigned
  visit"). Make sure a patient (e.g. Sara) exists and was recently seen/active.
- **Steps:** **Memory → Today** (or **Needs input**) → on the unassigned visit tap **Assign patient**.
- **Expected:** The assignment resolver opens. At the top, a **"Suggested — in chair now / recently
  seen"** block shows a patient with a **"deterministic"** chip and a short reason, plus an **Assign**
  button (the active/recent patient is suggested first — this is rule-based, **not** AI). Below is a
  **search** (name / phone / national ID), **Create new patient**, and **Keep unassigned**. Tap
  **Assign** on the suggestion → the visit is filed to that patient; nothing is assigned silently.

---

## E7 · Settings

### 23. Aftercare templates management (AES-702)
- **Story:** Manage per-procedure aftercare templates in Settings.
- **Setup:** Assistant/Admin · Basic.
- **Steps:** Avatar menu → **Settings** (`#settings`). Scroll to **Aftercare templates**. Tap **+ Add
  template**; fill **Name** ("Botox aftercare"), optional **Procedure type** ("botox"), and
  **Instructions** ("Stay upright for 4 hours…"); tap **Save template**. Then **Edit** and **Delete**
  one.
- **Expected:** The new template appears in the list with its name, a lowercase procedure-type chip,
  and the body. **Edit** opens an inline editor that saves changes; **Delete** confirms and removes it.
  These templates are the ones offered in the share sheet's aftercare dropdown (Scenario 19).

### 24. Plan card shows Basic + Aesthetics (sanity)
- **Story:** The tier and vertical are legible.
- **Setup:** Any persona · Basic.
- **Steps:** **Settings** → **Plan** card.
- **Expected:** **Tier** reads **Basic**; **Workspace** reads **Aesthetics**.

---

## Cross-cutting "Basic stays AI-free" checks (run opportunistically)

- **No ✨ on any Basic feature.** The only ✨ allowed is on a violet **"Try Pro"** teaser. If you see a
  sparkle anywhere else (memory recap, report, captures), that's a bug.
- **No processing/organizing states, and no badges when synced.** Saving a note/photo/audio shows
  **no** status when connected (it just syncs), and never "Processing"/"Organizing"/"Transcribing". The
  only sync indicator — **"Trying to sync"** (on the session header and the affected captures) — appears
  **only when offline / the backend is unreachable**.
- **Session header naming.** The active visit reads **"{patient}'s Nth session"** when assigned, or the
  session **date + time** when unassigned (not a raw "Session …" name, no "Complete" badge).
- **Audio never transcribed in Basic.** A compact voice-memo player, no transcript; transcription lives
  behind Try Pro only.
- **Teasers are non-functional.** Tapping a "Try Pro" teaser never runs AI on your content; it only
  reveals the "Pro feature — upgrade your plan" note.
- **Duplicate guard never auto-merges.** It only suggests; "Create anyway" always works.
- **Sharing is explicit and withholds internals.** A patient link only ever contains what you toggled
  on; lots, national ID, raw audio, and other visits are never included, and the link is revocable.

---

## Environment note (object storage)

Photo/audio/note **file** captures require the stack's object storage (MinIO). If a worktree dev stack
was provisioned with an object-storage access key that MinIO does not recognise, **uploading a
capture returns a 500** and the photo/audio-dependent scenarios (4, 5, 7, 11, 12, 16's photo row, and
the share sheet's before/after photos) cannot be exercised — the surfaces render their empty/structural
states correctly but stay photoless. The **patient-level** scenarios (smart search 9, recap 10,
teasers 6/13, duplicate guard 14/20, reception suggestion 22, settings 23–24, share-sheet structure
17–19) do **not** depend on object storage and can be run as written. To exercise the photo paths, run
against a stack whose MinIO bucket + access key are correctly provisioned (the canonical `engram`
stack, or a worktree stack with working object-storage credentials).
