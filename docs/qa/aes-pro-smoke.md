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

## B5 · Unified report surface + inline verify (Pro) ⭐

> Pro collapses the old `Captures`/`Live report` tabs: the **report is the primary surface**, raw captures
> live in a collapsible **"Sources · N captures"** drawer beneath it, and a sticky **"N to confirm"** bar
> drives verification. (Basic still uses the two tabs.)
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B5.1 ⭐ | Dr | Open a Pro visit with several captures. | The **report** is the main surface; captures are tucked into a **"Sources · N captures"** drawer (with audio/photo/note count chips) — not a separate tab. | |
| B5.2 ⭐ | Dr | Add a new capture to a visit that **already has** a synthesized report. | The prior report **stays visible** with an **"Updating · N captures…"** line + shimmer — it must **not** blank to "Preparing…"/draft. The refreshed report swaps in when ready. | |
| B5.3 ⭐ | Dr | Cause a blocker (e.g. carried-forward dose, or an AI-created patient). | Sticky **"N to confirm"** bar shows the count (**blockers only**); **Review** jumps to the first inline confirm. | |
| B5.4 | Dr | Confirm a carried-forward **dose** on its Treatment-performed row. | Flips to **"✓ Dose confirmed"** in place; the verify count drops by one and the confirmation **sticks** (does not revert when the report re-organizes). | |
| B5.5 | Dr | Find a soft gap (low confidence / missing lot) → use **"Fix at source"**. | Opens the **Sources drawer** at the originating capture; correcting it re-extracts (no direct treatment-field edit). | |
| B5.6 | Dr | On a Pro report, use the one-tap **"+ {aftercare template}"** add-button in the report card. | The aftercare section is added to the report (button lives in the report card, not a separate bar). | |

## B6 · Safety flags (opt-out) ⭐

> Pro synthesis surfaces **allergy / contraindication / consent** statements the clinician actually made as
> a calm **Safety panel above the verify region**. It is **not a blocker** — the clinician only **rejects**
> a wrong one. ("Warnings over blocking.")
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B6.1 ⭐ | Dr | Dictate a safety statement (e.g. *"patient is allergic to lidocaine"*); open the visit. | A **Safety panel** (red/amber) appears **above** the verify region with the flag. It does **not** gate the report and is **not** counted as a verify blocker. | |
| B6.2 ⭐ | Dr | **Reject (×)** a wrong/duplicate flag; then add another capture so the report re-synthesizes. | The rejected flag **stays gone** after re-synthesis (does not reappear). | |
| B6.3 | Dr | Open the patient later. | Non-rejected flags **carry to the patient** and surface at future visits (the flag text is in the **report language**). | |

## B7 · Capture undo / de-effect ⭐

> Deleting/undoing a wrong capture must revert **its effects**, not just drop it from the feed — most
> importantly a mis-transcription that spuriously **created or reassigned a patient**.
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B7.1 ⭐ | Dr | Produce a capture that makes the AI **create a new patient** (e.g. a mis-heard name); then **undo/delete** that capture. | The spuriously **created/assigned patient is reverted** along with the capture — the prior state returns; the report re-organizes without the bogus entry. | |
| B7.2 | Dr | Undo the most recent capture on a multi-capture visit. | Only that capture's effects are removed; the rest of the report is intact. | |

## B8 · Persian UI (fa/en + RTL)

> The authenticated app is **bilingual**: **chrome** (buttons, labels, toasts) follows the **app language**;
> **clinical content** (transcripts, captions, report prose) follows the **report language** and is **never
> translated**.
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B8.1 ⭐ | Admin/Owner | Settings → set the clinic **app language to Persian**. | The whole authed UI flips to **Persian + RTL** (right-aligned, mirrored layout); no English chrome left in the aesthetics app. | |
| B8.2 | Dr | With a **Persian** report, scan the report. | Section **titles are Persian**; the clinician's **dictated content** stays in the language it was produced in (content is **not** auto-translated). | |
| B8.3 | Dr | Switch app language back to **English**. | UI flips to **LTR English** cleanly (no stale RTL, no Gregorian/Jalali date mix-up). | |

## B9 · Smart lists + lot recall (Pro) ⭐

> A Pro **Lists** tab in Clinical Memory: deterministic named lenses (no AI) + an exact-match lot/product
> recall. Counts must be **trustworthy** — only real visits, the exact lot, no over-matching.
| ID | Persona | Steps | Expected | Result |
|----|----|----|----|----|
| B9.1 ⭐ | Dr (Pro) | Open Clinical Memory. | A **Lists** tab is present (Pro only). | |
| B9.2 | Dr (Pro) | Open the **Lists** tab. | Smart-list lenses with live counts — **Seen this week**, **Due to return** (last visit ≥12 weeks), **Missing after-photo** — each with a one-line definition. | |
| B9.3 | Dr (Pro) | Tap a smart list (e.g. Seen this week). | Opens the matching patients/visits; tapping a row goes to the patient (or the visit, for missing-after-photo). | |
| B9.4 ⭐ | As (Pro) | In the lot/product lookup, search a **lot** you dictated (try odd spacing/case, e.g. `d 4471`). | Returns **every patient who received that exact lot**, each row citing the visit + verbatim treatment. Different spellings (`D-4471` vs `D4471`) appear under **"Similar lots (not included)"**, never folded into the affected list. | |
| B9.5 ⭐ | As (Pro) | Check a lot that was **carried forward** ("same as last time") to a later visit. | The carried-forward visit is **not** counted as a separate administration — the count reflects real administrations only (the patient still appears via their original visit). | |
| B9.6 | Dr (Pro) | On a recall cohort, use **Open channel** on a patient. | Opens/reuses that patient's Q&A thread to send a message (per-patient, explicit — no bulk blast). **Copy affected list** is also available. | |
| B9.7 | Dr (Basic) | Log in as a **Basic** tenant, open Clinical Memory. | **No Lists tab** (the feature is Pro-gated; the API also returns 403 for Basic). | |

---

## 4 · 15-minute must-pass set
**B1.1** (audio transcribes) · **B2.1** (structured report builds with treatment specifics) ·
**B3.1 / B3.2** (Q&A: ask → inbox → draft → send) · **B5.2 / B5.3** (report doesn't blank on add; verify
bar counts blockers) · **B6.1** (safety flag surfaces, non-blocking) · **B7.1** (undo reverts a spurious
patient) · **B9.4 / B9.5** (lot recall is exact + excludes carried-forward).

## 5 · Sign-off
| Field | Value |
|---|---|
| Build / version | |
| Tester / date | |
| Browser / OS | |
| Cases pass / fail | / |
| Blockers found | |
| Verdict | ☐ Ship  ☐ Ship with known issues  ☐ Do not ship |
