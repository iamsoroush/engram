# Therapy — Comparable-Product Research Brief (Phase 0)

> ⚠️ **Archived** — one-time research input, superseded by the therapy spec [../redesign-therapy.md](../redesign-therapy.md). Kept for history.
>
> Greenfield design grounding for **Engram for Therapy** (Spine A, single-tier — the AI *is* the
> value; see [redesign-foundation.md](../redesign-foundation.md) §1, §5 and [../spines.md](../../spines.md)
> §2–4). Started 2026-06-11, **pre-PMF**. This brief scans the therapy-documentation landscape →
> distills the patterns that matter → names the gaps → states **where Engram-therapy differentiates**.
> The feature set, journeys, and prototype that build on it live in
> [redesign-therapy.md](../redesign-therapy.md).
>
> Method: targeted scan of the two product categories below (vendor docs + practitioner/comparison
> write-ups, 2025–2026) plus the clinical-standard primitives (note formats, MBC instruments, HIPAA
> psychotherapy-note rule, C-SSRS). Sources inline; this is a design brief, not a literature review —
> claims are at the granularity a design decision needs.

---

## 1. The landscape splits into two categories that are converging

**A. Practice-management / EHR** — *SimplePractice, TherapyNotes, Jane.* The system of record: scheduling,
client portal, telehealth, billing/insurance, intake forms, structured notes, treatment plans. The note
is a *form you fill*. AI note-drafting is now bolted on (SimplePractice ships AI notes), but the center
of gravity is the practice's back office, not the session.

**B. AI session tools / "AI scribes"** — *Upheal, Mentalyc, Eleos Health, Blueprint.* The system of
*action* around the session: listen (ambient or uploaded audio) → draft a compliant note → surface
insights. Some are pure scribes (Mentalyc), some are growing into EHRs (Upheal, Blueprint), some target
agencies/community care (Eleos). The note is *generated*, and the product increasingly wraps the whole
arc — **prep before, support during, documentation after.**

**The convergence is the headline.** Category B is the direction of travel: the winning therapy product
is no longer "where I store notes," it's **"the assistant that carries the thread between sessions."**
Blueprint states it plainly — surface insights *"before, during, and after every client session."* That
arc is exactly Spine-A's thesis (capture-first memory, narrative-secondary). **Engram-therapy enters as a
category-B product with a memory center of gravity** — and that's the right side of the trend.

---

## 2. Category patterns that matter (and our stance on each)

| Pattern | What the category does | Engram-therapy stance |
| --- | --- | --- |
| **Note formats** | SOAP / DAP / BIRP (+ GIRP, PIRP, PIE, EMDR, intake, MSE). Upheal/Mentalyc offer ~10 formats; DAP & BIRP dominate outpatient. | Ship **one strong default (DAP-leaning narrative)** + a small format switch. Don't open a 10-format template bazaar at v1 — but **structure-behind-narrative** so a format can be projected later. |
| **Treatment plan ("golden thread")** | Goals → objectives → interventions, SMART, tied to medical necessity; AI now drafts it from intake + early sessions (Upheal *Golden Thread*, Blueprint smart plans). | A **living plan that threads the arc** — but framed as *memory*, not an insurance artifact (our market isn't US payers). The plan is "where we're heading"; each session's summary references it. |
| **Measurement-based care (MBC)** | PHQ-9 / GAD-7 etc. completed via client portal on a cadence (often pre-session), auto-scored, trended over time; reviewed before the visit. Blueprint's whole wedge. | **Optional, light, and trend-first.** Outcome scores feed the **pre-session brief** ("GAD-7 down 4 since last month") — a brief input, not a compliance chore. Persian-localized instruments. |
| **Session prep / insights** | *Our direct competitor.* Blueprint: pre-session summary of last session + reminders of focus areas + assessment results to hand. Eleos: in-session co-pilot, risk indicators, treatment-fidelity feedback. Upheal: talk-ratio analytics, cross-session pattern recognition. | **This is our signature surface.** Everyone gestures at "prep"; nobody makes *walk in knowing the client* the product's front door. We do — built on the **existing patient-memory artifact** (summary + history). |
| **Client portal** | Booking, messaging, forms, payments, document sharing. Table-stakes in category A. | A **payload on the one shared patient-facing surface** (foundation §4) — privacy-gated, narrow. Not a full back-office portal; intake + measures + a withheld-by-default summary. |
| **Telehealth** | Built-in video (SimplePractice up to 15, TherapyNotes 16). | **Out of scope** for the design (commodity, infra-heavy). Capture is recording-/ambient-based and telehealth-agnostic. |
| **Privacy / consent** | HIPAA + the **psychotherapy-notes** carve-out (see §4). Recording-consent debates; Eleos markets *ambient, no recording stored*. | **Privacy is a first-class design axis, not a settings page** — see §4. Mental-health data + Iranian stigma context raise the bar above aesthetics. |

---

## 3. What the AI players actually do (and the gap)

- **Upheal** — EHR + AI notes in ~10 formats in <60s; *Golden Thread* drafts insurance-compliant
  treatment plans from intake + up to 3 sessions and recognizes cross-session patterns; *Smart Sections*
  let a clinician teach the AI custom note sections in their own voice; talk-ratio analytics.
- **Mentalyc** — focused AI scribe: SOAP/DAP/BIRP/GIRP/PIE from live audio, upload, dictation, or typed
  summary; an **AI progress tracker** trending themes across sessions; strong compliance posture
  (HIPAA + SOC 2, plus CA/AU regimes).
- **Eleos Health** — agency/community-behavioral-health focus; **ambient capture without storing the
  original conversation**; in-workflow co-pilot synthesizing client insights + guidelines across
  crisis/risk, EBP, SUD; metrics on talk ratio, empathy, evidence-based-technique use; markets
  outcome lift (3–4× vs. treatment-as-usual) and ~70% less documentation time.
- **Blueprint** — "AI assistant before, during, and after"; **smart session prep** (last-session summary
  + focus reminders), Guided MBC (*Blueprint Sessions*), in-session access to assessments/worksheets,
  post-session worksheet/assessment suggestions and homework. Closest in spirit to our pre-session brief.

**The shared gap:** these are **documentation-first** products with prep/insights as *features bolted to
a note engine*. The mental model the user lives in is still "my notes" or "my EHR." None of them make
**longitudinal client memory** the product's spine, the home screen, the thing you open. None treat the
*pre-session moment* — the 60 seconds before the client walks in — as the primary surface. And all are
US/HIPAA-shaped, English-first, payer-driven: none fit a **Persian, RTL, cash-pay, stigma-sensitive**
clinic.

---

## 4. Privacy & consent — the rules that shape the design

Therapy data is the most sensitive in Spine A, so the norms below become **design constraints**, not fine print.

1. **Two tiers of record exist, by law (US HIPAA) and by good practice everywhere.**
   - **Progress note** — the *required, shareable* clinical record: what happened, interventions,
     response, plan, risk, MSE, diagnosis. Discloseable to payers/other providers.
   - **Psychotherapy (process) note** — the therapist's *private* reflections, hypotheses, the verbatim
     content of the conversation. Specially protected; kept **physically separate**; even the client has
     no right of access; blending the two **destroys** the protection of the private note.
   - **Design implication:** Engram must model **two visibility planes** on every session —
     a **shareable summary** (progress-note-shaped) and a **private layer** (the therapist's reflections,
     the raw transcript). The patient-facing surface and any export draw **only** from the shareable
     plane. This is the single most important structural lesson from the category.

2. **Recording is contentious; storing the raw audio is a liability.** Eleos leans on *ambient, not
   stored*; others record. **Implication:** treat the **raw transcript/audio as the most private object**,
   default to deriving from it and de-emphasizing/retiring it (retention controls), never surfacing it on
   shared payloads.

3. **Risk is a flag with teeth.** C-SSRS (Columbia) screens suicide risk into low/med/high; platforms
   place a **dated flag on the client profile** when risk is high, and pair it with **safety planning**.
   **Implication:** risk/safety is a **first-class, persistent, dated element of patient memory** that the
   **pre-session brief surfaces at the top** — the one thing a clinician must never walk in not knowing.
   (Detection can be assisted, but a risk flag is clinician-confirmed, never silently AI-asserted.)

4. **Consent & confidentiality limits are an intake artifact** (informed consent, limits of
   confidentiality, privacy notice). **Implication:** the receptionist/intake workflow owns consent
   capture, and consent state **gates** what the patient-facing surface may ever show.

5. **Local context raises the floor.** Iranian, Persian-speaking, cash-pay, high mental-health stigma →
   **privacy-by-default, minimal patient-facing exposure, RTL-native, no payer plumbing.** A US-shaped
   "share everything to the portal" default is wrong here.

---

## 5. Differentiation — where Engram-therapy wins

1. **Memory is the product, not the note.** Competitors organize around the note/EHR; Engram organizes
   around **longitudinal client memory** (the existing summary + history artifact). The note/summary is a
   *projection* of memory, not the home.
2. **The pre-session brief is the front door.** We productize the moment everyone else treats as a
   feature: **walk in knowing the client** — arc position, themes to revisit, risk/safety flags, since-last
   changes (incl. MBC trend). One screen, 60 seconds, built on memory we already compute.
3. **Privacy is structural.** Two visibility planes (shareable vs. private) baked into the data model and
   every surface — not a disclaimer. Matches the psychotherapy-note rule by construction.
4. **Capture-first, narrative-leaning, audio-first.** No template gate, no "fill the form." Talk; the
   system writes the narrative summary and threads it into memory. (Foundation §1: therapy capture is
   audio-first.)
5. **Right market fit.** Persian/RTL-native, single flat plan, cash-pay, stigma-aware. The incumbents are
   English/HIPAA/payer machines; none serve this clinic.
6. **One platform underneath.** Patient memory, transcription, matching, the patient-facing surface
   primitive — already built for aesthetics; therapy is *configuration + presentation*, so we ship the
   differentiated surfaces without rebuilding the engine.

**What we deliberately do *not* chase at v1:** a 10-format note bazaar, built-in telehealth video, US
insurance/billing, agency-scale supervisor analytics (talk-ratio/empathy fidelity scoring). These are
category depth we can add later; none is the wedge.

---

## 6. Direct inputs to the design (→ [redesign-therapy.md](../redesign-therapy.md))

- **Signature surface = pre-session brief**, with a compact **arc strip** (mini-timeline) for longitudinal
  context, then sections ordered by clinical urgency: **safety/risk first**, *arc position*, *recurring
  themes*, *since last time* (qualitative trajectory), *today's prompt*.
- **Session capture** = **dictation-first** (in-session jots + a short post-session recap), private-by-default
  — **not** whole-session recording (cost + privacy; see redesign-therapy.md §1.2).
- **Session summary** = narrative + **two planes** (shareable progress-note-shaped / private reflections
  + the *recap* transcript); risk surfaced and dated.
- **Longitudinal history** = the existing memory artifact, therapy-shaped (arc, themes, risk timeline,
  qualitative trajectory).
- **Treatment thread** = a light living plan (goals/focus), memory-framed, referenced by each summary.
- **Intake/reception** = consent + confidentiality limits + first-visit context; consent gates the
  patient surface.
- **Patient surface (MVP)** = a privacy-gated payload on the shared primitive (foundation §4): intake +
  consent, and a *withheld-by-default* summary the clinician explicitly releases.
- **MBC (post-MVP)** = optional Persian-localized measures, trend-first — a whole subsystem, deferred; the
  brief's qualitative trajectory covers the core value until then (redesign-therapy.md §2 Post-MVP).

---

### Sources

Category B / AI tools: [Upheal](https://www.upheal.io/), [Upheal — Golden Thread](https://www.upheal.io/blog/the-golden-thread),
[Upheal — Smart Sections](https://www.upheal.io/blog/using-smart-sections-for-custom-ai-therapy-notes),
[Mentalyc — AI note taker](https://www.mentalyc.com/ai-note-taker),
[Mentalyc — AI progress tracker](https://www.mentalyc.com/ai-progress-tracker),
[Eleos — Documentation](https://eleos.health/documentation/), [Eleos](https://eleos.health/),
[Blueprint — Assistant](https://www.blueprint.ai/platform/assistant),
[Blueprint Sessions / GMBC](https://www.blueprint.ai/blog/introducing-blueprint-sessions-a-new-way-to-implement-guided-measurement-based-care-gmbc).
Category A / EHR: [SimplePractice vs TherapyNotes](https://www.choosingtherapy.com/therapynotes-vs-simplepractice/),
[Jane vs SimplePractice](https://jane.app/guide/jane-vs-simplepractice),
[SimplePractice — paperless intake](https://www.simplepractice.com/blog/paperless-intake-form-onboarding-easy/),
[SimplePractice — intake process](https://www.simplepractice.com/resource/therapy-intake-process/).
Clinical primitives: [Ensora — SOAP/DAP/BIRP](https://ensorahealth.com/blog/understanding-the-differences-between-dap-soap-and-birp-notes/),
[Mentalyc — note templates](https://www.mentalyc.com/blog/mental-health-progress-note-templates),
[SimplePractice — MBC](https://www.simplepractice.com/blog/measurement-based-care/),
[APA — MBC resource doc](https://www.psychiatry.org/getattachment/3d9484a0-4b8e-4234-bd0d-c35843541fce/Resource-Document-on-Implementation-of-Measurement-Based-Care.pdf),
[Mentalyc — C-SSRS guide](https://www.mentalyc.com/blog/columbia-suicide-severity-rating-scale),
[Blueprint — C-SSRS guide](https://www.blueprint.ai/blog/a-therapists-guide-to-the-columbia-suicide-severity-rating-scale-c-ssrs-seening-version),
[Mentalyc — SMART goals](https://www.mentalyc.com/blog/smart-goal-in-therapy).
Privacy: [CAP — psychotherapy vs progress notes](https://www.capphysicians.com/articles/psychotherapy-notes-and-progress-notes-whats-difference),
[HHS — HIPAA mental-health protections](https://www.hhs.gov/hipaa/for-professionals/faq/2088/does-hipaa-provide-extra-protections-mental-health-information-compared-other-health.html),
[Holland & Hart — HIPAA & psychotherapy notes](https://www.hollandhart.com/hipaa-psychotherapy-notes-and-other-mental-health-records),
[Headway — intake form](https://headway.co/resources/intake-form-template).
