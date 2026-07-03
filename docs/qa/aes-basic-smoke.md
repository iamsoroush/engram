# Engram (Aesthetics) — **Basic tier** QA/QC Smoke Suite

> **Audience:** QA/QC testers. **No coding required** — everything is done in a web browser.
> **Goal:** verify the most important **Basic-tier** workflows before each release. **Budget:** ~30 min.
> Pro tier has its own suite: [aes-pro-smoke.md](aes-pro-smoke.md). Exhaustive per-feature scripts:
> [aes-frontend-scenarios.md](aes-frontend-scenarios.md), [aes-patient-pages-scenarios.md](aes-patient-pages-scenarios.md).

## 0 · What you are testing
**Engram** is a clinical "memory" app for **aesthetics clinics** (Botox, fillers, skin treatments). Staff
**capture** notes, photos, and audio during a visit; the app files them by **patient** and **visit**.

**Basic** = **recall**: fast capture + reliable retrieval, with **NO AI**. Captures save instantly like
notes; audio is a plain **voice memo** (no transcript); there are no auto-summaries or AI captions. Think
"Apple Notes for a clinic."

> ⚠️ **The #1 rule:** In Basic there must be **no AI anywhere** — no "transcribing", no
> "processing/organizing", no sparkle (✨) icons, no auto-captions. Seeing any of those is a **bug**.

**Glossary** — **Capture:** one note/photo/audio. **Session/Visit:** one patient encounter. **Patient:**
the person. **Worklist / "Up next":** patients an assistant lined up for a doctor. **Share:** a read-only
link a patient opens (no login). **Persona:** Doctor / Assistant / Admin (staff).

## 1 · Environment & access
- **App:** `http://localhost:5183` (Chrome).
- **Sign in (dev stack, no password):** pick the **Basic** tier on the switch, then click a **persona** (Doctor /
  Assistant / Admin). Log out (top-right) to switch persona. Confirm the header reads *"Engram Demo Clinic (Basic)"*.
- **Against production** (`https://engram.ir`): the persona switch does **not** exist there — dev-login
  is disabled in production — so sign in with the real **email + password** of a test account in your
  clinic (the clinic owner can add one on the **Team** screen; you need two staff accounts for the A5
  multi-seat cases). Stick to **read-mostly** checks plus data you create yourself under a clearly
  marked `ZZ Test …` name. **Never** edit or delete real patient data, don't revoke a share link a
  real patient may still be using (A4.3 is fine on your own test patient), and skip **A5.4** — it
  changes the clinic's role presets — unless you revert the preset right after.
- **Test data:** create patients with a **unique, findable name** each run (e.g. `ZZ Test 2026-06-13 01`).
  **Don't delete** existing demo data.

## 2 · How to run & record
Work top-to-bottom within a section. Mark each **Result**: ✅ Pass / ❌ Fail + a note. Screenshot failures.
Fill the sign-off (section 5).

**Bug report** — `Case ID · Tier/Persona · What I did · Expected · Actually happened · Severity · Screenshot`.
**Severity** — **Blocker** (core flow broken; the ⭐ cases) · **Major** (important, has workaround) · **Minor** (cosmetic).

---

## A1 · Sign-in & navigation
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A1.1 | Dr | Sign in Basic → Doctor. | Loads to capture/active-session, no errors; header *"…(Basic)"*. | |
| A1.2 | Dr | Move through the main nav (capture / Clinical Memory / Search) and back. | Each opens without error; back returns you. | |

## A2 · Instant, zero-AI capture ⭐ (the heart of Basic)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A2.1 ⭐ | Dr | Type a note and save. | Saves **instantly** ("Saved on this device"); shows immediately. **No** processing/✨. | |
| A2.2 ⭐ | Dr | Add/take a photo. | Uploads, shows a thumbnail. **No** AI caption, **no** spinner. | |
| A2.3 ⭐ | Dr | Record an audio capture. | Saved as a **playable voice memo**. **No** transcript. | |

## A3 · Patients, search, assignment
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A3.1 | Dr/As | Create a patient (unique name + phone). | Saved; appears in list/search. | |
| A3.2 | Dr | Search by partial name (and Persian text if available). | Patient found; sensible results. | |
| A3.3 | Dr | Try creating a duplicate (same name/phone). | **Possible-duplicate warning** before creating. | |
| A3.4 ⭐ | Dr | Capture **without** a patient, then assign it to A3.1. | Starts **unassigned**; after assign, filed under patient → visit. | |

## A4 · Photos, last-visit recall, sharing
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A4.1 | Dr | Add photos on **two** visits for one patient; open the gallery. | **Grouped by visit**, recent prominent. | |
| A4.2 | Dr | Start a new capture for that **returning** patient. | Last visit's note + photos surface; **"same as last time"** pre-fills an editable note "from last visit" (not auto-saved). | |
| A4.3 ⭐ | Dr → no login | Curate items, create a **share link**, open it in incognito. Then **revoke** it. | Read-only; **only curated** items (no internal data). After revoke, link won't open. | |

## A5 · Multi-seat (multiple staff)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A5.1 ⭐ | Dr | Make a capture; check the author label. | Shows **"by &lt;user&gt; · time"**. | |
| A5.2 ⭐ | As, then Dr | **As:** register a patient + line up for a doctor ("up next"). **Dr:** see the worklist, tap → history → start a session. Then start a **fresh** capture **without** the worklist. | Doctor sees lined-up patients; **worklist never blocks fresh capture**; assistant lands on Memory. | |
| A5.3 | Dr | Toggle **"Mine" vs "Clinic"** on Today/lists. | Mine = your items; Clinic = everyone's. | |
| A5.4 ⭐ | Dr, then Ad | Non-owner tries to **edit** another's session → blocked by default. **Ad:** Settings → role permissions → change a preset → re-test. | Default blocks non-owner edits; after the change, behavior follows the preset. | |

## A6 · Cross-cutting
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| A6.1 ⭐ | Dr | Re-check the whole clinic: any transcript, AI caption, "processing", ✨ anywhere? | **No** — Basic is entirely AI-free. | |
| A6.2 | Dr | Reload the page after creating data. | Persists; **no capture stuck "trying to sync"**. | |
| A6.3 | Dr | Enter a **Persian** note. | Renders right-to-left correctly. | |

---

## 4 · 10-minute must-pass set (a fail here blocks release)
**A2.1–A2.3** (instant, AI-free capture) · **A3.4** (assign-later) · **A4.3** (share read-only/curated) ·
**A5.2 / A5.4** (worklist never blocks; non-owner can't edit) · **A6.1** (no AI anywhere).

## 5 · Sign-off
| Field | Value |
|---|---|
| Build / version | |
| Tester / date | |
| Browser / OS | |
| Cases pass / fail | / |
| Blockers found | |
| Verdict | ☐ Ship  ☐ Ship with known issues  ☐ Do not ship |
