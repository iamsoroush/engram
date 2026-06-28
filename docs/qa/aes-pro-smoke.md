# Engram (Aesthetics) — **Pro tier** QA/QC Smoke Suite

> **Audience:** QA/QC testers. **No coding required.** **Goal:** verify the most important **Pro-tier**
> workflows. **Budget:** ~30–45 min. Basic tier has its own suite: [aes-basic-smoke.md](aes-basic-smoke.md).
>
> 🚧 **Pro is in active development** (the "Pro capture-intelligence wave"). Some cases below describe the
> **target** behavior and may be partially in flight — check with the build owner which features are live
> in the build you're handed before filing failures as bugs.

## 0 · What you are testing
**Engram** files a clinic's notes/photos/audio by **patient** and **visit**. **Pro** adds an **AI layer** on
top of capture: audio is **transcribed**, photos get **captions**, notes are **cleaned up**, each visit
produces a **structured report**, and patients can ask **questions** answered by the clinic. (Basic, by
contrast, has *no* AI — that contrast is itself a key test; see the Basic suite.)

> ⚠️ **About AI in this test environment.** Some AI tasks run **placeholder processors** — captions and
> note "decoration" may return fixed stand-in text (e.g. *"Caption placeholder…"*), and transcription uses
> a configured gateway (real transcript, or "unavailable" if the gateway can't be reached). **Verify the
> *flow*, not the AI wording:** a job runs, a result appears in the right place, it stays **editable**, the
> report **assembles** — placeholder text is expected, not a bug.

**Glossary** — **Capture:** one note/photo/audio. **Session/Visit:** one encounter. **Structured report:**
the per-visit document with fixed sections. **Q&A:** patient↔clinic questions. **Persona:** Doctor /
Assistant / Admin / Patient preview.

## 1 · Environment & access
- **App:** `http://localhost:5183` (Chrome).
- **Sign in (no password):** pick the **Pro** tier on the switch, then a **persona**. Header should read
  *"Engram Demo Clinic"* (Pro). Log out (top-right) to switch persona.
- **Test data:** unique patient names per run; don't delete existing demo data.

## 2 · How to run & record
Top-to-bottom per section. Mark **Result**: ✅ / ❌ + note. Screenshot failures. Sign-off in section 5.
**Bug report** — `Case ID · Tier/Persona · What I did · Expected · Actually happened · Severity · Screenshot`.
**Severity** — **Blocker** (core flow broken; ⭐) · **Major** · **Minor**.

---

## B1 · Capture **with** AI enrichment ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B1.1 ⭐ | Dr | Dictate an **audio** capture. | Transcribed (brief processing/✨, then a transcript); transcript is **editable** with edited-vs-AI attribution. | |
| B1.2 | Dr | Add a photo. | An AI **caption** appears (real or placeholder text — flow matters). | |
| B1.3 | Dr | Type a rough note. | It's **cleaned/decorated** (with attribution), still editable. | |

## B2 · Structured visit report ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B2.1 ⭐ | Dr | Dictate treatment **specifics** (e.g. *"1 ml of [brand] filler to the cheeks, lot 1234"*); open the visit report. | Fixed sections — Visit summary · Concern/goals · Assessment · **Treatment performed** (area · product · brand · units/volume · lot #) · Before/after · Plan & follow-up · Aftercare. Your specifics land in **Treatment performed**. Builds automatically (no "Generate" button). | |
| B2.2 | Dr | Make an **off-topic** capture (e.g. unrelated phone call). | **Dimmed & excluded** from the report (not deleted); **"Mark relevant"** re-includes it. | |

## B3 · Patient Q&A ⭐
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B3.1 ⭐ | Patient preview | As the **patient**, submit a question to the clinic. | Accepted; patient sees it in their thread. | |
| B3.2 ⭐ | Dr | **Q&A inbox** → find the question with a **suggested AI-drafted reply** → edit (try **voice edit**) → send. | Draft present; doctor **approves before sending**; reply then appears in the patient's thread. | |
| B3.3 | Dr / Patient | Confirm default routing to the **treating doctor**; try a **manual re-route**; as patient, confirm you see **only your own** thread. | Routing + re-route work; **no leakage** of other patients/clinic internals. | |

## B4 · Shared features on Pro (spot-check — same engine as Basic)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B4.1 | Dr | Create + search a patient; assign an unassigned capture. | Same correct behavior as Basic. | |
| B4.2 | Dr → no login | Curate + share to a patient; open the read-only link. | Read-only, curated-only. | |
| B4.3 | As/Dr/Ad | Reception worklist, attribution, mine-vs-clinic, role permissions. | Same correct behavior as Basic. | |

---

## 4 · 15-minute must-pass set
**B1.1** (audio transcribes) · **B2.1** (structured report builds with treatment specifics) ·
**B3.1 / B3.2** (Q&A: ask → inbox → draft → send).

## 5 · Sign-off
| Field | Value |
|---|---|
| Build / version | |
| Tester / date | |
| Browser / OS | |
| Cases pass / fail | / |
| Blockers found | |
| Verdict | ☐ Ship  ☐ Ship with known issues  ☐ Do not ship |
