# AES smoke test suite — most important workflows

> **Curated regression smoke** for the **aesthetics** product (Basic + Pro). Run it before promoting a
> build and after each merge wave — it answers one question fast: *do the critical features and the main
> UX still work?* Budget ~30–45 min. This is intentionally a subset; for exhaustive per-story coverage
> see [aes-frontend-scenarios.md](aes-frontend-scenarios.md) (Basic clinic) and
> [aes-patient-pages-scenarios.md](aes-patient-pages-scenarios.md) (public patient pages).

## Setup

- **App:** http://localhost:5183 (local dev). Use Chrome.
- **Sign in:** on the login screen, first pick the **tier** on the switch (**Pro / Basic**), then click a
  **persona** (**Doctor / Assistant / Admin / Patient preview**). To change tier or persona, **log out**
  (top-right) and sign in again.
- **Demo tenants:** Basic = *Memara Demo Clinic (Basic)*, Pro = *Memara Demo Clinic* (both aesthetics).
- **Test data:** create fresh patients with a **unique name each run** — e.g. `ZZ Test <date> 01` — so
  you can find them and avoid clashing with existing data. **Do not delete** existing demo data.
- **Recording results:** mark each case ✅ pass / ❌ fail and add a note. File bugs by **case ID**.

**Legend** — Tier: Basic / Pro · Persona: **Dr** doctor · **As** assistant · **Ad** admin · **Pt** patient preview · ⭐ = critical / newly-merged, test carefully.

---

## 1 · Sign-in & shell

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| S1 | Basic·Dr, then Pro·Dr | Sign in Basic→Doctor; note the screen. Log out; sign in Pro→Doctor. | Both load to the capture / active-session screen with no errors; the header tenant name matches the tier picked. | |
| S2 | Basic·Dr | From the main screen, move through the app's primary nav (capture / Clinical Memory / Search) and back. | Each area opens without error; back returns to where you were. | |

## 2 · AES Basic — capture, zero-AI ⭐ (the core promise of Basic)

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B1 ⭐ | Basic·Dr | Type a text note and save it. | Saves **instantly** ("Saved on this device" or similar); shows in the session immediately. **No** "processing"/"Organizing"/✨ anywhere. | |
| B2 ⭐ | Basic·Dr | Add/take a photo. | Uploads, shows a thumbnail. **No** AI caption, **no** processing spinner. | |
| B3 ⭐ | Basic·Dr | Record an audio capture. | Saved as a **playable voice memo**; **no** transcript generated. | |

> **B1–B3 are the keystone.** Any transcript, AI caption, "processing", or ✨ in the Basic tenant is a **FAIL**.

## 3 · AES Basic — patients, search, assignment

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B4 | Basic·Dr/As | Create a new patient (unique name + phone). | Saved; appears in the patient list/search. | |
| B5 | Basic·Dr | Search by partial name, and by Persian text if you have it. | The patient is found; results are sensible. | |
| B6 | Basic·Dr | Try creating a second patient with the same name/phone. | A **possible-duplicate warning** appears before it's created. | |
| B7 ⭐ | Basic·Dr | Make a capture **without** choosing a patient, then assign it to B4's patient. | Capture starts **unassigned**; after assigning it's filed under that patient → visit. | |

## 4 · AES Basic — photos, last-visit recall, sharing

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B8 | Basic·Dr | Add photos on **two** separate visits for one patient; open the patient's gallery. | Photos **grouped by visit**, recent visits prominent. | |
| B9 | Basic·Dr | Start a new capture for that **returning** patient. | Last visit's note + photos surface; **"same as last time"** pre-fills a new **editable** note marked "from last visit" (not auto-saved). | |
| B10 ⭐ | Basic·Dr → no login | Curate a few items for a patient, create a **share link**, open it in a private/incognito window. Then **revoke** it. | Public page is **read-only**, shows **only the curated** items (no internal notes/raw data). After revoke, the link no longer opens. | |

## 5 · AES Basic — multi-seat (E9) ⭐ newly merged

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B11 ⭐ | Basic·Dr | Make a capture; check the author label. | Shows **"by <user> · time"** on captures/visits. | |
| B12 ⭐ | Basic·As, then Dr | **Assistant:** register a patient and line them up for a doctor (Today / "up next"). **Doctor:** see the "up next" worklist, tap a patient → history → start a session. Then start a **brand-new** capture **without** using the worklist. | Doctor sees lined-up patients; **the worklist never blocks starting a fresh capture**; assistant lands on the Memory screen. | |
| B13 | Basic·Dr | Toggle **"Mine" vs "Clinic"** on Today / lists. | "Mine" = only your items; "Clinic" = everyone's. | |
| B14 ⭐ | Basic·Dr, then Ad | As a **non-owner**, open someone else's session and try to **edit** → expect blocked (you can contribute, not edit theirs). As **Admin**: Settings → role permissions → change a preset (e.g. allow assistants to edit) → re-test. | Default blocks non-owner edits; after the admin change, behavior follows the new preset. | |

## 6 · AES Pro — capture & AI enrichment ⭐

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| P1 ⭐ | Pro·Dr | Dictate an **audio** capture. | Audio is **transcribed** (brief processing/✨, then a transcript); transcript is **editable** with edited-vs-AI attribution. | |
| P2 | Pro·Dr | Add a photo. | An **AI caption** is generated for the clinical image. | |
| P3 | Pro·Dr | Type a rough note. | It's **decorated/cleaned** by AI (with attribution), still editable. | |

> **P1–P3 confirm Pro DOES have the AI layer** — the deliberate opposite of B1–B3.

## 7 · AES Pro — structured report ⭐

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| P4 ⭐ | Pro·Dr | In a Pro session, dictate a visit **including a treatment with specifics** (e.g. "1 ml of [brand] filler to the cheeks, lot 1234"). Open the session report. | Report has the fixed sections — Visit summary · Concern/goals · Assessment · **Treatment performed** (area · product · brand · units/volume · lot #) · Before/after · Plan & follow-up · Aftercare — and the specifics you dictated land in **Treatment performed**. Builds as captures land (no "Generate" button). | |
| P5 | Pro·Dr | Make an obviously **off-topic** capture (e.g. dictate an unrelated phone call). | It's **dimmed and excluded** from the report (not deleted); **"Mark relevant"** re-includes it. | |

## 8 · AES Pro — patient Q&A (AES-402) ⭐ newly merged

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| P6 ⭐ | Pro·Pt | As **Patient preview** (or via the patient share surface), submit a question to the clinic. | Question is accepted; the patient sees it in their thread. | |
| P7 ⭐ | Pro·Dr | Open the **Q&A inbox** → find the question with a **suggested AI-drafted reply**. Edit it (try the **voice edit** if present), then send. | Draft is present and sensible; doctor must **approve before it sends**; after sending, the reply shows in the patient's thread. | |
| P8 | Pro·Dr/Pt | Confirm the question routed to the **treating doctor** by default; try a **manual re-route** to another provider. As the patient, confirm you see **only your own** thread. | Routing default + re-route work; **no leakage** of other patients or clinic internals. | |

## 9 · Cross-cutting smoke

| ID | Tier·Persona | Steps | Expected | Result |
|----|----|----|----|----|
| X1 ⭐ | Basic·Dr | Re-confirm there is **nowhere** in the Basic tenant a transcript, AI caption, "processing", or ✨. | Basic is entirely AI-free (regression guard — the merges must not have leaked AI into Basic). | |
| X2 | Basic·Dr | After creating captures/patients, **reload** the page. | Data persists; **no capture stuck in "trying to sync"**. | |
| X3 | Basic·Dr | Enter a **Persian** note. | Renders right-to-left correctly. | |

---

## Reporting bugs

For each ❌, record: **case ID**, tier + persona, what you did, what you **expected**, what **happened**, and a screenshot.
Severity:
- **Blocker** — a core flow is broken: B1–B3, B7, B10, B12, P1, P4, P6, P7, X1.
- **Major** — an important feature is wrong but has a workaround.
- **Minor** — cosmetic / edge case.
