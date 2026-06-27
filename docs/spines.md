# Spines — Platform & Product Strategy

> Living strategy doc (started 2026-06-10, **pre-PMF**). Captures the multi-vertical direction, the
> tier model, and per-spine next steps. For the in-flight Spine-A capture→intelligence work see
> [intelligence-layer.md](intelligence-layer.md); for product/UX see [product.md](product.md) and
> [ux/overview.md](ux/overview.md).

## 1. Platform and products

The codebase is **one platform** serving multiple clinical verticals through a shared
**capture → structure → retrieve** core (plus intent detection — "just start, the system figures out
the rest"). Verticals are not separate products built one-by-one; they group into **three product
spines**.

- **Engram** is the single brand — the platform/organization (GitHub org, repo, services, infra, API)
  **and** the customer-facing Spine-A product: capture-first clinical memory (aesthetics, therapy,
  dermatology). Verticals are *editions* of Engram ("Engram for Aesthetics / for Therapy"), not
  separate brands.
- Spines B and C get their **own product names** when built.

Entity model is shared and vertical-typed: `Patient` is universal; the work-unit (Session / Study /
Case) generalizes as an **Encounter** typed by `tenant.vertical`
(see [architecture.md](architecture.md#entity-model-verticals)).

## 2. The three spines

**Spine A — capture-first memory** (aesthetics, therapy, dermatology) · product **Engram**
Center of gravity = patient memory; the report is narrative/secondary; value = fast capture +
retrieval + longitudinal understanding. *This is the product we have today* (aesthetics-first).
Therapy and dermatology are configuration + presentation on the same core.

**Spine B — report-first dictation→document** (radiology)
Center = the report document; single author, synchronous, template-bound. Radiologist dictates → the
system fills the clinic's own template, asks for what's missing, exports to their format. **Inverts**
Spine A's center of gravity (home screen = the report, not the captures). **Deferred** (less traction
than pathology); later a *subset* of Spine C's machinery.

**Spine C — multi-actor case workflow** (pathology)
Center = a Case moving through roles over days; value = orchestrating a messy async pipeline into a
verified structured report + export (Word / LIS). A **superset** of radiology (report-first +
template/export + multi-role + sign-off). The mental model is **branch/merge**: a Case forks into
parallel role-scoped contributions (reception, grossing/macroscopic, history-gathering via
WhatsApp/questionnaire, microscopic, comments) and assembles + verifies into the final report.

> The current product's "never block / never gate" UX philosophy is **Spine-A-specific**. Diagnostic
> reports (B/C) are legal documents — verification IS a gate. Don't inherit the wrong defaults there.

## 3. Capabilities and tiers

Express the platform as **capabilities** (transcription, image_caption, note_decoration,
patient_matching, out_of_context, cross_visit_synthesis, live_report_synthesis, pre_session_brief,
structured_report, template_export, multi_role_workflow, …). Each **(vertical, tier)** = a subset of
capabilities + vertical-specific presentation. **Gate features on resolved capabilities, not on
`tier` directly** — a thin resolver `capabilities(vertical, tier) → set` (not a plugin framework).

Principle: **Basic = recall (deterministic), Pro = understanding (synthesis/matching)**.

**Tier structure is per-vertical and follows where the *value floor* sits:**
- *Organizational* floor → two tiers, split on the **AI line** (a deterministic layer has standalone
  value; AI is the upsell).
- *Understanding* floor → **single tier** (the AI *is* the value; a no-AI tier is below the
  usefulness floor — a crippled product, not a standalone one).

| Capability | Aesthetics · Basic | Aesthetics · Pro | Therapy *(single)* |
|---|:-:|:-:|:-:|
| Structured capture + patient memory + search *(deterministic)* | ✓ | ✓ | ✓ |
| Transcription | — | ✓ | ✓ |
| AI matching · captions · decoration · out-of-context | — | ✓ | ✓ |
| Cross-visit synthesis *(memory, history, live report)* | — | ✓ | ✓ |
| Pre-session brief surface | — | — | ✓ |

- **Aesthetics** = organizational floor → **Basic + Pro**. Basic = no AI (deterministic Notes-killer);
  transcription is **Pro-only** here (deliberate packaging exception — protects the upsell, contains
  Basic cost).
- **Therapy** = understanding floor → **single plan** (no Basic/Pro). A raw transcript without
  summarization is low-value / a liability; therapy's value starts at the AI.
- **Dermatology** (fast-follow) likely patterns like aesthetics (organizing patient-submitted
  photos/symptom logs has deterministic value) → may keep a real Basic; settle when its
  patient-capture channel is built.

## 4. Sequencing

Pre-PMF (no paying customers yet). Strategy: **one platform + one GTM** (small/medium private Iranian
clinics & labs); light up spines in sequence — never two new spines at once. The first move is to
redesign the current app into a **Spine-A platform for design-partner testing — pluggability, not
three polished products.**

**Spine-A redesign**
- **P0 — Foundations:** capability resolver (re-gate the AI block off `tier`); expand
  `tenant.vertical` taxonomy (`clinic`→`aesthetics`, add `therapy`, `dermatology`); per-vertical
  config module.
- **P1 — Aesthetics to the agreed line:** Basic = genuinely AI-free Notes-killer (fast capture,
  patient-centric structure, search, performance as data grows); Pro = full current intelligence,
  re-gated via capabilities.
- **P2 — Therapy as vertical #2:**
  - **P2a — Therapy UX design** *(dedicated design step — every new vertical gets one).* Design the
    pre-session brief surface ("walk in knowing the patient"), in/post-session capture, and the
    narrative, privacy-aware summary presentation. Output: prototype + spec under `docs/ux/`.
  - **P2b — Therapy build:** vertical config (single tier; transcription in the Basic-set),
    therapy prompt-shaping for summaries/history, the pre-session brief surface (reusing the existing
    patient-memory artifact), terminology.
- Then **derm patient-capture channel** (fast-follow) → **Spine C (pathology)**.

> **Per-vertical UX design is a first-class step.** Each vertical has a different preferred UX; do not
> ship a vertical on aesthetics' screens by default. Radiology and pathology each get their own design
> phase before build.

## 5. Per-spine next steps

**Spine A (Engram) — active**
1. P0 foundations (capability resolver + vertical taxonomy + config). ← next
2. P1 aesthetics Basic/Pro to the agreed line.
3. P2 therapy: **UX design step (P2a)** → build (P2b).
4. (later) derm patient-capture channel.

**Spine C (pathology) — next strategic bet (after Spine-A)**
1. Design-partner discovery + workflow mapping of a real lab (the branch/merge case lifecycle).
2. UX + workflow design phase: roles & permissions; **case state machine with handoffs**;
   **specimen→block(→slide) hierarchy**; **contribution/section model** (macroscopic/microscopic/
   comments); **query/comment thread** (the ping-pong); **hard sign-off gate**.
3. Report/template pipeline: LLM-based template extraction + export-friendly generation (pixel-faithful
   to the lab's own Word template; LIS export). *Deterministic-only won't achieve this.*
4. Persian medical ASR tuned for dictation; design the UX for ASR failure modes.

**Spine B (radiology) — deferred**
1. Build after pathology; reuse Spine C's report/template/export engine minus the multi-actor
   workflow (single author).
2. "Retrieve call": the radiologist starts dictating; the system identifies the study and brings up
   the latest report version (reuses the intent-detection machinery).

## 6. Naming

- **Engram** (finalized) is the single brand for the organization, platform, GitHub org, repo, **and**
  the Spine-A product. An *engram* is the physical trace a memory leaves in the brain — apt for a
  capture-first clinical-memory platform.
- Spines B/C get their own product names at build time.
- Rule in code/docs: **use Engram everywhere** (see [CLAUDE.md](../CLAUDE.md)).

Related: [intelligence-layer.md](intelligence-layer.md) · [product.md](product.md) ·
[ux/overview.md](ux/overview.md) · [architecture.md](architecture.md) ·
[technical-decisions.md](technical-decisions.md).
