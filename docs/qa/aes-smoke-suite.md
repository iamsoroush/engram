# Memara (Aesthetics) — QA/QC Test Plan & Smoke Suite

> **Audience:** QA/QC testers. **No coding required** — everything here is done in a web browser.
> **Goal:** verify the most important workflows for the aesthetics product across **both tiers — Basic and Pro** —
> before each release. **Budget:** ~60–90 min for a full pass.
>
> This is the curated "does the product still work" plan. For exhaustive, per-feature scripts see
> [aes-frontend-scenarios.md](aes-frontend-scenarios.md) (Basic clinic app) and
> [aes-patient-pages-scenarios.md](aes-patient-pages-scenarios.md) (public patient pages).

---

## 0 · What you are testing (product primer)

**Memara** is a clinical "memory" app for **aesthetics clinics** (Botox, fillers, skin treatments).
During a visit, clinic staff **capture** notes, photos, and audio; the app files them by **patient** and
**visit**, so the clinic can later recall "what did we do last time".

There are **two product tiers** — the difference is the single most important thing to understand:

| | **Basic** | **Pro** |
|---|---|---|
| Core idea | **Recall** — fast capture + reliable retrieval | **Understanding** — AI on top of capture |
| AI? | **None.** Captures save instantly like notes. Audio is a plain **voice memo** (no transcript). No auto-summaries. | **Yes.** Audio is **transcribed**, photos get **AI captions**, notes get **cleaned up**, each visit gets a **structured report**, plus patient **Q&A**. |
| Mental model | Apple Notes for a clinic | A documentation assistant |

> ⚠️ **The #1 rule for testers:** In **Basic** there must be **no AI anywhere** — no "transcribing",
> no "processing/organizing", no sparkle (✨) icons, no auto-captions. Seeing any of those in Basic is a **bug**.
> In **Pro**, those AI features **should** appear. Many test cases below check exactly this contrast.

### Glossary
- **Capture** — one item: a typed note, a photo, or an audio recording.
- **Session / Visit** — one patient encounter; contains the captures from that visit.
- **Patient** — the person being treated.
- **Worklist / "Up next"** — patients a receptionist/assistant has lined up for a doctor.
- **Share** — a read-only link a patient opens (no login) to see their curated photos/report.
- **Persona (role)** — Doctor, Assistant, Admin (clinic staff), or Patient (the patient's own view).

---

## 1 · Environment & access

- **App URL:** `http://localhost:5183` (local test build). Use **Google Chrome**.
- **Signing in (no password):** on the login screen, first pick the **tier** on the switch — **Pro / Basic** —
  then click a **persona** button (**Doctor / Assistant / Admin / Patient preview**). To change tier or
  persona, **log out** (top-right menu) and sign in again.
- **Demo clinics:** Basic = *"Memara Demo Clinic (Basic)"*, Pro = *"Memara Demo Clinic"*. Confirm the clinic
  name in the header matches the tier you picked.
- **Test data hygiene:** when a case says "create a patient", use a **unique, findable name each run** —
  e.g. `ZZ Test 2026-06-13 01`. **Do not delete** existing demo data.

---

## 2 · How to run & record results

1. Work **top to bottom within a section** (later cases sometimes reuse data from earlier ones).
2. For every case, mark the **Result** column: **✅ Pass** or **❌ Fail**, and add a short note.
3. On a **failure**, capture a **screenshot** and record the steps in the bug template below.
4. Fill in the **sign-off sheet** (section 6) at the end.

**Bug report template**
```
Case ID:           (e.g. B7)
Tier / Persona:    (e.g. Basic / Doctor)
What I did:        (the steps)
Expected:          (from the case)
Actually happened: (what you saw)
Severity:          Blocker / Major / Minor
Screenshot:        (attach)
```
**Severity guide** — **Blocker:** a core flow is broken (IDs marked ⭐). **Major:** an important feature is
wrong but has a workaround. **Minor:** cosmetic / rare edge case.

---

# PART A · BASIC TIER

*Sign in with tier = **Basic**. Persona noted per case (Dr = Doctor, As = Assistant, Ad = Admin).*

## A1 · Sign-in & navigation
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A1.1 | Dr | Sign in Basic → Doctor. | App loads to the capture / active-session screen, no errors; header shows *"Memara Demo Clinic (Basic)"*. | |
| A1.2 | Dr | Move through the main navigation (capture / Clinical Memory / Search) and back. | Each area opens without error; back returns you to where you were. | |

## A2 · Instant, zero-AI capture ⭐ (the heart of Basic)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A2.1 ⭐ | Dr | Type a text note and save. | Saves **instantly** ("Saved on this device" or similar); appears in the visit immediately. **No** "processing"/"organizing"/✨. | |
| A2.2 ⭐ | Dr | Add or take a photo. | Uploads, shows a thumbnail. **No** AI caption, **no** processing spinner. | |
| A2.3 ⭐ | Dr | Record an audio capture. | Saved as a **playable voice memo**. **No** transcript is produced. | |

## A3 · Patients, search, assignment
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A3.1 | Dr/As | Create a new patient (unique name + phone). | Saved; appears in the patient list/search. | |
| A3.2 | Dr | Search by partial name (and Persian text if available). | The patient is found; results are sensible. | |
| A3.3 | Dr | Try to create a second patient with the same name/phone. | A **possible-duplicate warning** appears before it's created. | |
| A3.4 ⭐ | Dr | Make a capture **without** picking a patient, then assign it to A3.1's patient. | Capture starts **unassigned**; after assigning, it's filed under that patient → visit. | |

## A4 · Photos, last-visit recall, sharing
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A4.1 | Dr | Add photos on **two separate visits** for one patient; open the patient's gallery. | Photos **grouped by visit**, recent visits prominent. | |
| A4.2 | Dr | Start a new capture for that **returning** patient. | Last visit's note + photos surface; **"same as last time"** pre-fills a new **editable** note marked "from last visit" (not auto-saved). | |
| A4.3 ⭐ | Dr → no login | Curate a few items for a patient, create a **share link**, open it in a private/incognito window. Then **revoke** it. | Public page is **read-only**, shows **only the curated** items (no internal notes/raw data). After revoke, the link no longer opens. | |

## A5 · Multi-seat (multiple staff in one clinic) ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A5.1 ⭐ | Dr | Make a capture; check the author label. | Shows **"by &lt;user&gt; · time"** on captures/visits. | |
| A5.2 ⭐ | As, then Dr | **Assistant:** register a patient and line them up for a doctor ("up next"). **Doctor:** see the "up next" worklist, tap a patient → history → start a session. Then start a **brand-new** capture **without** using the worklist. | Doctor sees lined-up patients; **the worklist never blocks starting a fresh capture**; assistant lands on the Memory screen. | |
| A5.3 | Dr | Toggle **"Mine" vs "Clinic"** on Today / lists. | "Mine" = only your items; "Clinic" = everyone's. | |
| A5.4 ⭐ | Dr, then Ad | As a **non-owner**, open someone else's session and try to **edit** → expect blocked (you can contribute, not edit theirs). As **Admin:** Settings → role permissions → change a preset (e.g. allow assistants to edit) → re-test. | Default blocks non-owner edits; after the admin change, behavior follows the new preset. | |

## A6 · Basic cross-cutting
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A6.1 ⭐ | Dr | Re-check the whole Basic clinic: is there **anywhere** a transcript, AI caption, "processing", or ✨? | **No** — Basic is entirely AI-free. | |
| A6.2 | Dr | After creating captures/patients, **reload** the page. | Data persists; **no capture stuck in "trying to sync"**. | |
| A6.3 | Dr | Enter a **Persian** note. | Renders right-to-left correctly. | |

---

# PART B · PRO TIER

*Sign in with tier = **Pro** (clinic *"Memara Demo Clinic"*). Pro is a superset of Basic.*

> ⚠️ **About AI in this test environment.** The AI engine currently runs **placeholder processors** for
> some tasks: photo **captions** and note **"decoration"** return fixed stand-in text (e.g.
> *"Caption placeholder…"*), and audio **transcription** uses a configured gateway (it may return a real
> transcript, or an "unavailable" state if the gateway can't be reached). So for Pro cases, **verify the
> *flow*, not the AI wording**: a job runs, a result appears in the right place, it stays **editable**, and
> the report **assembles** — the placeholder text itself is expected, not a bug. Check with your build owner
> which AI tasks are "real" in the build you're handed.

## B1 · Capture **with** AI enrichment ⭐ (the opposite of Basic A2)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B1.1 ⭐ | Dr | Dictate an **audio** capture. | Audio is **transcribed** (a brief processing/✨ state, then a transcript). The transcript is **editable** and shows edited-vs-AI attribution. | |
| B1.2 | Dr | Add a photo. | An **AI caption** is generated for the clinical image. | |
| B1.3 | Dr | Type a rough note. | It's **cleaned/decorated** by AI (with attribution), still editable. | |

## B2 · Structured visit report ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B2.1 ⭐ | Dr | In a Pro visit, dictate treatment **specifics** (e.g. *"1 ml of [brand] filler to the cheeks, lot 1234"*). Open the visit report. | Report has fixed sections — Visit summary · Concern/goals · Assessment · **Treatment performed** (area · product · brand · units/volume · lot #) · Before/after · Plan & follow-up · Aftercare — and your dictated specifics land in **Treatment performed**. Builds automatically as captures land (no "Generate" button). | |
| B2.2 | Dr | Make an obviously **off-topic** capture (e.g. an unrelated phone call). | It's **dimmed and excluded** from the report (not deleted); **"Mark relevant"** re-includes it. | |

## B3 · Patient Q&A ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B3.1 ⭐ | Patient preview | As the **patient**, submit a question to the clinic. | Question is accepted; the patient sees it in their thread. | |
| B3.2 ⭐ | Dr | Open the **Q&A inbox** → find the question with a **suggested AI-drafted reply**. Edit it (try the **voice edit** if present), then send. | Draft is present and sensible; the doctor must **approve before it sends**; after sending, the reply shows in the patient's thread. | |
| B3.3 | Dr / Patient | Confirm the question routed to the **treating doctor** by default; try a **manual re-route**. As the patient, confirm you see **only your own** thread. | Routing default + re-route work; **no leakage** of other patients or clinic internals. | |

## B4 · Shared features on Pro (spot-check)
*These behaviors are the same engine as Basic; confirm they still work with AI present.*
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B4.1 | Dr | Create + search a patient; assign an unassigned capture (as A3.1–A3.4). | Same correct behavior as Basic. | |
| B4.2 | Dr → no login | Curate + share to a patient; open the read-only link. | Read-only, curated-only, as A4.3. | |
| B4.3 | As/Dr/Ad | Reception worklist, attribution, mine-vs-clinic, role permissions (as A5). | Same correct behavior as Basic. | |

---

## 5 · Quick regression checklist (the must-pass set)
If you only have 15 minutes, run exactly these — a fail here blocks the release:
- **A2.1–A2.3** Basic captures are instant and **AI-free**.
- **A3.4** assign-later files correctly.
- **A4.3** share is read-only & curated-only.
- **A5.2 / A5.4** worklist never blocks capture; non-owner can't edit by default.
- **A6.1** no AI anywhere in Basic.
- **B1.1** Pro audio transcribes.
- **B2.1** Pro structured report builds with treatment specifics.
- **B3.1 / B3.2** patient Q&A: ask → doctor inbox → AI draft → send.

---

## 6 · Sign-off sheet

| Field | Value |
|---|---|
| Build / version tested | |
| Tester name | |
| Date | |
| Browser / OS | |
| Basic cases: pass / fail | / |
| Pro cases: pass / fail | / |
| Blockers found | |
| Overall verdict | ☐ Ship  ☐ Ship with known issues  ☐ Do not ship |
