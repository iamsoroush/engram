# Spine-A Redesign — Design Foundation (North Star)

> Cross-cutting decisions every vertical/tier design track must share, so parallel tracks have
> matching seams. **Read this before designing any aesthetics or therapy surface.** Strategy:
> [../spines.md](../spines.md). Status: **pre-PMF — aesthetics is the alpha; therapy is a later
> alpha**.
>
> **Every decision below carries its *why*. Don't reverse one without engaging its rationale** — most
> of these look like they could be "simplified," and each was deliberate.

## 1. Tiers are a value floor, not a feature checklist

- **Basic = recall (deterministic, ZERO AI).** No AI, no background jobs, no `processing`/AI-derived
  states. A capture is *saved* instantly (local-first, Apple-Notes feel) and assigned manually;
  everything is computed deterministically/synchronously. *(Aesthetics only.)* Primary capture =
  **note + photo** (audio is a secondary voice-memo, since there's no transcription).
  *Why:* a legible value floor makes pricing obvious (deterministic vs. AI), protects the Pro upsell,
  and keeps the cheap tier free of AI cost, foreign-API dependency, and latency — and it's the only
  way Basic feels truly instant/offline.
- **Pro = understanding (AI).** Primary capture shifts to **dictated audio** (transcription makes it
  first-class); note + photo support it. Adds synthesis, matching, structuring, the structured report,
  and the patient Q&A.
- **The boundary is a deliberate upsell line — if a task is worth AI, it's Pro.** Lightweight AI may
  appear in Basic **only** as a clearly-labelled "✨ Try Pro" teaser, never a Basic feature.
  *Why:* the moment Basic has "a little AI," pricing collapses into a muddy "how much AI per tier"
  argument and the upsell blurs. The most tempting cheap-LLM task — structuring a note — is exactly
  the core Pro value, so giving it away kills the reason to upgrade; as a teaser the same AI becomes a
  *conversion lever* instead.
- **Therapy = a single plan** (no Basic/Pro). *Why:* therapy's value floor IS the AI — a raw
  transcript without synthesis is low-value and a liability, so a deterministic therapy tier would sit
  *below* the usefulness floor (a crippled product, not a standalone one).

## 2. Personas & permissions (both verticals)

- **Doctor/clinician** — captures, reviews, treats; owns clinical content.
- **Assistant** — supports documentation.
- **Receptionist** — intake: creates/manages patients, scheduling-adjacent. Design it *inside* each
  vertical track under this shared model. *Why:* what intake captures differs per vertical, so a
  vacuum-designed persona wouldn't fit any of them.
- **Patient** — read / limited-write via the patient-facing surface (§4).
- **Capture-first never blocks a role** — a doctor can capture without waiting on reception;
  assignment catches up. *Why:* the product dies the moment it adds friction or blocking to the
  natural clinical workflow; "save now, organize later" is non-negotiable.

## 3. Aesthetics — the agreed feature set (Basic + Pro)

> **This is the feature set we have already decided.** The aesthetics design track **starts from
> here** — it *details* this (journeys, stories, prototype) and may *validate or extend* it from
> research, but must **not re-derive it from scratch or silently drop items.** (Therapy is greenfield,
> so its features are research-led; see §5.)
>
> **Build status (planning estimate — confirm against the codebase at build time):**
> `(exists)` built today · `(new)` not built · `(modify)` built but needs change for this model.

Thesis: a clinic's data is *already structured* (patient → visit → treatment + before/after photos),
but Apple Notes treats it as flat dumb text. **Basic** organizes that reality with deterministic
superpowers; **Pro** adds the AI understanding layer + the upsell.

### Basic — the "really better than Apple Notes" spine (zero AI)

1. **Shared clinic workspace** `(exists)` — multi-tenant/multi-user backend is built. *Why:* Notes is
   siloed to one Apple account/device; a clinic needs the same patient base across doctor,
   receptionist, and every iPad.
2. **Patient-centric, automatic** filing by patient → visit `(modify)` — the patient/session/capture
   model exists; the *zero-AI Basic presentation* of it is new. *Why:* Notes is a flat pile you title
   and search by hand.
3. **Visual-first**: per-patient gallery auto-grouped by visit `(new)` — photo capture exists; the
   zero-AI gallery presentation is new. *Why:* aesthetics *is* photos; camera-roll/Notes chaos is the
   pain felt every visit. *(Amended 2026-06-12: per-photo **before/after pairing** moved to **Pro** — see
   Pro #1 — because tagging photos Before/After is organizing work, and Basic's value is presentation +
   retrieval, not labeling. Basic keeps the well-presented gallery; the eye pairs. Spec:
   [redesign-aesthetics.md §3.1](redesign-aesthetics.md).)*
4. **Smart search**: deterministic, Persian-orthography-aware, multi-field, instant at scale
   `(modify)` — a basic patient list/search exists; the smart, fuzzy, Persian-aware, fast-at-scale
   version is an upgrade. *Why:* Notes' search is dumb and slow, worse for Persian names.
5. **Capture-first / assign-later** with a deterministic "Assign to …?" notification `(modify)` —
   capture-first is core DNA `(exists)`; the *deterministic, non-AI* assign-later suggestion is new
   for Basic. *Why:* capture must never block; auto-organization by patient is the win Notes can't
   match.
6. **Shareable patient report** (curated before/after + aftercare) + **static aftercare instructions**
   the patient can view `(new)`. *Why:* Notes can't produce a professional patient-facing artifact.
7. **"Same as last time"** note pre-fill `(new)` · **duplicate-patient guard** `(new)` — cheap
   deterministic polish.
8. **The zero-AI capture lifecycle** `(modify)` — freeform notes, photos, audio-as-voice-memo, saved
   instantly with **no AI jobs, no `processing` states, no "live report."** Today Basic still runs the
   AI pipeline; this is the core P1 change. Local-first instant capture itself `(exists)`.

### Pro — understanding + upsell (capture is audio-first; everything in Basic, plus AI)

1. **Capture enrichment**: audio **transcription** `(exists)` · image **captions** `(modify — mock
   today)` · note **decoration** `(modify — mock today)` · **before/after pairing** — captions +
   intelligently-assembled pairs + the aligned slider `(new; amended 2026-06-12, moved from Basic #3)`.
2. **AI patient matching** (auto match / create / reassign / suggest) `(exists)` + **out-of-context
   detection** `(exists)`.
3. **Structured session report** `(modify)` — the AI turns the **dictated session** (+ photos/notes)
   into a structured per-visit document and extracts the treatment specifics. The report exists today
   only as a deterministic grouping, so this is real structured synthesis. *Why structured:* it's the
   core Pro value — exactly why structure lives in Pro, not Basic.
   **Default report structure (v1 — fixed; user-defined templates are a future version):**
   - **Visit summary** (1–2 lines)
   - **Concern / goals** (what the patient wanted)
   - **Assessment** (clinician findings)
   - **Treatment performed** — per item: *area · product · brand · units/volume · lot #*
   - **Before / after media**
   - **Plan & follow-up**
   - **Aftercare given**

   The AI's job: populate these sections from the dictation/captures and extract the structured
   *Treatment performed* fields. *Why fixed for now:* a defined target makes the AI unambiguous and
   the report consistent; per-clinic templates are a known future axis (the same template capability
   radiology/pathology will need).
4. **Cross-visit synthesis** — patient summary + history `(exists)` + **recall** ("what did I use last
   time", from the structured treatment data) `(new)`.
5. **Smart lists / filters** (seen this week · due for follow-up · on product X · missing after-photo)
   `(new)`.
6. **Lot/batch tracking + recall** — find every patient who received a recalled lot `(new)`.
7. **Flags / safety** (allergy · consent · preferences) surfaced each visit `(new)`.
8. **Post-session patient Q&A — AI-drafted, doctor-verified** `(new)`. Between visits the patient
   sends a question (e.g. "is this swelling normal?", an aftercare worry). The system drafts a reply
   from the doctor's *prior answers* + this patient's context and surfaces it to the doctor —
   *"Patient X asks: …  Suggested reply: …  → Send / edit / dismiss."* The doctor approves and it's
   sent; every exchange is captured into the patient's memory. *Why:* it turns the unmanaged
   phone/WhatsApp question-deluge into a fast, in-context, verified channel — and accrues the Q&A as
   data.
9. **"✨ Try Pro" teasers** in Basic `(new)` — lightweight AI as a conversion lever, never a Basic
   feature.

(Patient-surface payloads — Basic report/aftercare, Pro Q&A — per §4.)

## 4. The patient-facing surface (one shared primitive)

A single clinic→patient (and later patient→clinic) channel, consumed by several payloads:

- **aes-Basic:** the shareable curated report + static aftercare instructions (read-only for the patient).
- **aes-Pro:** the post-session Q&A (§3 Pro #8) — patient→clinic questions + doctor-verified replies.
- **therapy / derm:** their own payloads (later).

Design it as a **contract** — access, delivery, consent, *what is shared vs. withheld* — not as
per-vertical buttons. *Why:* four-plus surfaces need the same patient channel; building it ad-hoc per
vertical guarantees divergence, duplicated auth/consent work, and an inconsistent patient experience.
One primitive = build once, stay coherent.

## 5. Per-vertical design is research-grounded

Every track opens with **comparable-product research** (how the category solves it → patterns + gaps +
where Memara differentiates). Aesthetics: lighter (med-spa EMRs + how clinics misuse Apple Notes) —
and the §3 feature set already frames it. Therapy: deep, and more *generative* (it's greenfield, no
current product to iterate from).

## 6. Deliverables every track produces (against this foundation)

1. **Comparable-product research brief** (patterns · gaps · differentiation).
2. **User-journey maps** — per persona, per tier.
3. **User-story inventory** — `As a <persona>, I want <goal>, so that <value>` + acceptance notes,
   tagged **Basic/Pro**, **persona**, and **build status** (exists/new/modify). This is the hand-off
   to build.
4. **Clickable prototype + spec** — match `redesign-capture-surface.md` +
   `../../apps/frontend/design-prototypes/*.html`.

> **Aesthetics track — delivered (design, for review).** Spec: [redesign-aesthetics.md](redesign-aesthetics.md).
> Research: [aesthetics-research-brief.md](archive/aesthetics-research-brief.md). Journeys:
> [aesthetics-journeys.md](archive/aesthetics-journeys.md). Stories (build hand-off):
> [aesthetics-stories.md](aesthetics-stories.md). Prototypes:
> `../../apps/frontend/design-prototypes/aesthetics-{capture,report,patient,patient-surface,frontdesk}.html`.
> Proposed extensions for human review: [redesign-aesthetics.md §10](redesign-aesthetics.md).

**Design Basic + Pro together (one aesthetics track), not as separate parallel agents.** *Why:* the
Basic↔Pro boundary *is* the design (what's deterministic vs. AI, where the upsell sits) — design the
halves apart and they won't meet at the seam.

Output is for human review. Design runs ahead of build (cheap, parallel); **build starts with
aesthetics-Basic.** *Why:* pre-PMF, aesthetics is the alpha that gets into clinics and teaches you —
ship the thin slice, learn, then earn the rest.

## 7. Multi-seat clinics (multi-user)

> Most clinics have several users. **The model differs by vertical, and permissions are configurable,
> not imposed** — never block the workflow.

- **Aesthetics = shared workspace** (any provider, any patient; the base is the clinic's). **Therapy =
  federated caseloads** (a client belongs to *their* therapist; clients + clinical content are
  **private between clinicians** by default). *Why:* aesthetics is collaborative; therapy is a
  confidential 1:1 relationship.
- **Active session is user-scoped; the patient base is tenant-scoped.** *Why:* concurrency without collision.
- **Session ownership** — owned by the clinician who created it (capture-first → the capturer owns); the
  owner is the *default* edit-holder; everything is **attributed** ("by &lt;user&gt; · time"). *Why:*
  accountability + a clear default, not a wall.
- **Permissions are tenant-configurable, permissive by default.** The admin sets what each non-owner
  role (assistant · receptionist) may do — **contribute (append) · reassign · edit** — as a few
  **presets** (not a granular matrix). Zero-config default for a small clinic: contribute open ·
  reassign = receptionist + owner · edit = owner; each loosenable ("receptionist: full") or tightenable.
  *Why:* small clinics have fluid roles; rigid RBAC fights the no-friction principle — **the product
  adapts to the clinic's org, it doesn't impose one.**
- **The intent gate is policy-aware (Pro).** A capture's intent (append/reassign/edit) auto-applies
  **iff the capturer's role is permitted**; otherwise it **doesn't block — it suggests to the owner**
  (reuse `suggested_reassignment`). *Why:* permissions decide *auto-apply vs. suggest*, never *stop*.
- **Soft worklist, both directions, never forced.** Reception can **pre-assign** (register + line a
  patient up for a doctor → the doctor's **"Today / up next"** → tap to start), and doctor-captured
  **unassigned** work flows back to reception's Needs-input. Either way capture-first still works (the
  footer always starts fresh). *Why:* multi-user assignment without breaking capture-first — a
  convenience lane, not a gate. A soft "Today" list, **not a scheduler.**
- **"Mine vs Clinic"** filters on Today / search / lists (deterministic).
- **Q&A routing (Pro only)** — admin-configurable; default AI-routes to the treating doctor (plural for
  multi-provider patients) + manual override; therapy = always the client's own therapist.
- **Therapy privacy is layered** — the *shareable* plane (progress note) may reach a supervisor /
  covering clinician **with consent + audit**; the *private* plane (reflections + transcript) is
  individual-only; reception sees schedule + identity, **not** clinical content. *Why:* confidentiality
  is the therapy non-negotiable.

Stories: aesthetics **E9** in [aesthetics-stories.md](aesthetics-stories.md) (a later increment, not in
the in-flight Basic build); therapy's caseload + privacy surfaces are detailed in
[redesign-therapy.md](redesign-therapy.md) at build time.
