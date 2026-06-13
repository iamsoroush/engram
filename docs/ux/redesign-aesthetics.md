# Aesthetics Vertical — Design Spec (Basic + Pro)

> The aesthetics design track's spec + clickable prototypes (deliverable 4,
> [foundation §6](redesign-foundation.md)). Designed **both tiers together** — the **Basic↔Pro boundary
> *is* the design** ([foundation §6](redesign-foundation.md)). Reads against the north-star
> [redesign-foundation.md](redesign-foundation.md) (every decision below traces to a §-numbered *why*
> there) and the current capture surface [redesign-capture-surface.md](redesign-capture-surface.md),
> which it **reuses, not replaces**.
>
> **Companion deliverables:** research [aesthetics-research-brief.md](aesthetics-research-brief.md) ·
> journeys [aesthetics-journeys.md](aesthetics-journeys.md) · stories (build hand-off)
> [aesthetics-stories.md](aesthetics-stories.md). **Prototypes:**
> [`aesthetics-capture.html`](../../apps/frontend/design-prototypes/aesthetics-capture.html) (interactive
> Basic↔Pro) · [`aesthetics-report.html`](../../apps/frontend/design-prototypes/aesthetics-report.html) ·
> [`aesthetics-patient.html`](../../apps/frontend/design-prototypes/aesthetics-patient.html) ·
> [`aesthetics-patient-surface.html`](../../apps/frontend/design-prototypes/aesthetics-patient-surface.html) ·
> [`aesthetics-frontdesk.html`](../../apps/frontend/design-prototypes/aesthetics-frontdesk.html).
>
> **Build order:** aesthetics-**Basic** first ([foundation §6](redesign-foundation.md)). Story IDs
> (`AES-###`) reference [aesthetics-stories.md](aesthetics-stories.md). Proposed changes to the agreed
> set are in **§10**, flagged for human review — nothing is silently dropped or replaced.
>
> **Implemented — aesthetics-Basic frontend (`build/aes-frontend`).** The Basic clinic surfaces are
> built in [`apps/frontend/src/features/aesthetics/`](../../apps/frontend/src/features/aesthetics/)
> (capture extras, patient gallery, smart search, duplicate guard, last-visit / "same as last time",
> reception assign-suggestion, curate-&-share, aftercare-template settings). Manual test script:
> [`../qa/aes-frontend-scenarios.md`](../qa/aes-frontend-scenarios.md). A few **as-built refinements**
> from build-time review are folded into §8–§9: the per-capture teasers were consolidated to **one
> Try Pro per screen**; Basic audio drops the persistent "voice memo" badge (sync state only when
> offline); a Basic note is **tap-to-edit inline**; a Basic photo may carry an **optional free-text
> caption** (the doctor's own words — not a Before/After tag); and the active-visit header names the
> session **"{patient}'s Nth session"** (date+time when unassigned), badge-free unless offline.

## 1 · The Basic↔Pro boundary (the spine)

One rule decides every cell: **if a task needs AI, it's Pro** ([foundation §1](redesign-foundation.md)).
Basic is **deterministic, zero-AI, instant, offline** — a genuinely-better-than-Apple-Notes floor. Pro
adds the **understanding** layer. Lightweight AI shows in Basic **only** as a labelled `✨ Try Pro`
teaser (§8) — never a Basic feature, because the moment Basic has "a little AI" the pricing line
collapses ([foundation §1](redesign-foundation.md)). **And structure in Pro is *emergent*** — the AI
extracts it from dictation; **Basic never asks the user to fill structured fields** (a manual form would
make a fast capture app feel like a small EHR — [design-principles §2,§5](../design-principles.md)).
Basic's answer to "what did we use last time" is **fast retrieval** of the previous visit, not data entry.

| Capability | Basic (deterministic) | Pro (AI) | Story |
| --- | --- | --- | --- |
| Capture lifecycle | Note/photo primary; audio = **voice memo**; saved instant, local-first, **no AI job/`processing`** | **Audio-first** dictation; transcription · captions · note decoration | AES-101/102 |
| Patient filing | Auto-filed patient→visit (det. presentation) | + AI **matching** (match/create/reassign/suggest) | AES-201/208 |
| Before/after photos | **No tagging** — photos filed to the patient + a **gallery grouped by visit** (recent prominent); optional ghost-overlay align `⊕`; the eye pairs them | AI **captions** + **intelligently-assembled before/after pairs** + the aligned slider compare | AES-103/104/202 |
| Treatment detail | **Free-text note / photos** — no structured form | **Extracted** from dictation into *Treatment performed* | AES-108 |
| Report | **Chronological** document (notes+photos, honest timestamps, no synthesis) | **Structured** v1 report (synthesis + extraction); auto-**Complete** | AES-302/107 |
| Search | **Persian-aware deterministic** multi-field, instant at scale | (same) | AES-204 |
| Assign-later | **Deterministic** "Assign to …?" suggestion | AI auto-match; ambiguous → resolver | AES-301 |
| Patient memory | **Structural** recap, **no ✨**, never guesses from audio | **AI history** (Snapshot/Story/Worth-remembering/Right-now) + **recall** | AES-206/207 |
| Last-visit retrieval | **Det.** glance at last visit (note + before/after) + "same as last time" pre-fill | + AI **recall** ("what product/units last time") | AES-106 |
| Duplicate guard | **Det.** near-match warning at create | (same) | AES-205 |
| Smart lists / filters | — | **Pro** (seen this week · due follow-up · on product X · missing after-photo) | AES-501 |
| Lot/batch + recall | — (lot lives in your note text; not queryable) | **Pro** — extracted lots → recall every patient on a recalled lot | AES-502 |
| Flags / safety | — | **Pro** (allergy · consent · preference) surfaced each visit | AES-701 |
| Shareable report + aftercare | **Basic** (curated report + static aftercare) | (Pro pre-fills from structured report) | AES-303/304 |
| Post-session Q&A | — | **Pro** (AI-drafted, doctor-verified) | AES-402 |
| Try-Pro teasers | **the upsell line** (labelled, non-functional) | — | AES-801–804 |

**Personas** ([foundation §2](redesign-foundation.md)): Doctor (owns clinical content) · Assistant
(supports documentation) · Receptionist (intake; designed in §7) · Patient (read/limited-write via the
patient surface §6). **Capture-first never blocks reception** ([design-principles §1](../design-principles.md));
the non-blocking handoff is shown concretely in [journeys §4](aesthetics-journeys.md).

## 2 · Surfaces & IA additions

Aesthetics reuses the existing shell (Active Session · Clinical Memory · Search · Settings,
[navigation.md](navigation.md)) and adds vertical-specific surfaces. Deltas:

- **Active Session** — adds photo capture + before/after (**presented** in Basic, **prepared** in Pro),
  the free-text note, the patient-row **flags** (Pro), the **"same as last time"** / **recall** strip,
  and the teaser slots. ([capture prototype](../../apps/frontend/design-prototypes/aesthetics-capture.html))
- **Patient detail** — adds a **photo gallery** (grouped by visit; Basic presents, Pro prepares
  before/after pairs), **visit history** (Basic: a glanceable list of your own notes; Pro: a **treatment
  & lot table** from extraction), and a **flags** band (Pro); memory is tiered (det. structural ↔ AI
  history + recall). ([patient prototype](../../apps/frontend/design-prototypes/aesthetics-patient.html))
- **Clinical Memory** — adds Pro **smart lists** and an admin **lot recall** lookup. Reception uses
  Today as a **front-desk lens** (§7).
- **Q&A** — a new Pro surface (doctor inbox); reachable from the shell navigator. ([patient-surface prototype](../../apps/frontend/design-prototypes/aesthetics-patient-surface.html))
- **Patient surface** — the external clinic→patient channel (one primitive, two payloads, §6).
- **Settings** — adds **Products & lots** (Pro, AES-705), **Aftercare templates** (Basic, AES-702),
  the **report template** change-affordance (Pro, AES-706), and **Flags** config.

*Why reuse, not rebuild:* the capture surface, needs-input contract, patient IA, and states are already
designed and built ([redesign-capture-surface.md](redesign-capture-surface.md), [states.md](states.md),
[screens/patients.md](screens/patients.md)); aesthetics is a **presentation + capability** layer on the
shared core ([spines §3](../spines.md)), not a fork.

## 3 · Capture & active session
*Prototype: [`aesthetics-capture.html`](../../apps/frontend/design-prototypes/aesthetics-capture.html) —
toggle **Tier** (Basic/Pro) × **Patient** (returning/new) to watch the seam move.*

The capture surface is the existing one ([redesign-capture-surface.md](redesign-capture-surface.md))
with aesthetics content. Layout invariants from there hold: one report card with **Captures | Live
report** tabs, the patient row above, the sticky **Audio / Photo / Note** footer, RTL-per-line.

**Footer order encodes the tier** ([foundation §1](redesign-foundation.md)): **Basic** leads with
**Note** (primary) — audio is a labelled voice **memo**; **Pro** leads with **Audio** (`dictate`).

### 3.1 Before/after photos — present (Basic) vs prepare (Pro) (AES-103/104)
The aesthetics signature — *aesthetics is photos* ([foundation §3 Basic 3](redesign-foundation.md)).
**Amends foundation §3 Basic 3** (approved 2026-06-12): per-photo *pairing/tagging* moves Basic→Pro;
Basic keeps the gallery. *Why:* tagging photos Before/After is organizing work — the same friction we
stripped from the treatment note — so Basic's value is **presentation + retrieval**, and the AI does the
organizing in Pro.
- **Basic — present, don't tag:** the doctor just shoots; **zero labeling.** Photos are **filed to the
  patient, never the camera roll** (research §6 ADOPT) and shown **well** — a per-patient **gallery
  grouped by visit**, recent visits prominent (≈last 4), photos in capture order; at a returning visit
  last visit's photos surface at capture so the doctor compares **by eye**. The app organizes and
  surfaces; the human reads the before/after. **No Before/After/area tags, no app-built pairs, no
  slider.** **Ghost-overlay** is an optional "align to a previous photo" capture aid (`⊕`, §10) — no
  Before/After taxonomy needed.
- **Pro — prepare the comparison:** photos are **auto-captioned**, **area/angle detected**, and the
  actual **before/after pairs assembled intelligently** with the aligned **side-by-side + slider**
  compare (reversible). This feeds the structured report's Before/after media + the curated share, and
  powers "missing after-photo" (§5). In Basic the caption + "prepare my before/afters" is the
  `✨ Try Pro` teaser (AES-803).

### 3.2 Treatment capture & the structured report (AES-108/107)
*Structure in Pro is **emergent**, never data entry:* the doctor dictates naturally and the AI extracts
the fields — turning a note into structure is the core Pro value, so forcing a form (or giving the
extraction away) defeats the upgrade ([foundation §1](redesign-foundation.md)).
- **Basic:** treatment detail is **just what the doctor types or says** — a free-text note or a voice
  memo; **no `Area/Product/Units/Lot` fields.** *Why no form:* a structured row would make a fast
  capture app feel like a small EHR ([design-principles §2,§5](../design-principles.md)). The "what did
  we use last time" job is solved by **fast retrieval** (§3.3, §5), not entry. The Basic Live report
  stays **chronological** ([redesign-capture-surface.md B2 Basic](redesign-capture-surface.md)).
- **Pro:** the dictation (+ photos/notes) becomes the **fixed v1 structured report** — *Visit summary ·
  Concern/goals · Assessment · **Treatment performed** (area · product · brand · units/volume · **lot #**)
  · Before/after media · Plan & follow-up · Aftercare given* ([foundation §3 Pro 3](redesign-foundation.md)).
  Rebuilt as captures land; auto-**Complete**; no Generate, no verify gate; out-of-context excluded.
  Lots flow to the clinic **lot ledger** (§5). The report template is the fixed aesthetic default, name
  + **Change** in the meta strip, user-uploadable later (AES-706). See [`aesthetics-report.html`](../../apps/frontend/design-prototypes/aesthetics-report.html).

### 3.3 Patient row — flags, same-as-last-time, recall
- **Flags (Pro, AES-701):** `⚠ Allergy · Consent · Preference` ride the patient row at every visit and
  at check-in (§7) — never blocking, but prominent. *Why:* safety facts must be impossible to miss.
- **Last visit, one glance (Basic, AES-106):** for a returning patient the strip surfaces **last
  visit's note + before/after** at capture time (tap to open it) and offers a one-tap **"same as last
  time"** note pre-fill; never auto-saved without an edit. *This is how Basic answers "what did we use
  last time" — retrieval, not a form.*
- **Recall (Pro, AES-207):** the same strip becomes "Last time: forehead · Botox (Dysport) · 20u · lot
  D-4471" answered from structured data. In Basic this is a `✨ recall` teaser (AES-804).

### 3.4 Out-of-context (Pro, AES-109)
Unchanged from the generic build — dimmed, excluded from the report, never deleted, one-tap **Mark
relevant**. Pro-only (Basic has no synthesis to exclude from).

## 4 · Reports
*Prototype: [`aesthetics-report.html`](../../apps/frontend/design-prototypes/aesthetics-report.html).*

Two reports from the same captures (the boundary, made literal):
- **Basic — chronological notebook** (AES-302): clinic+patient header from template/DB, notes + photos
  shown, honest timestamps, **no synthesis, no AI chips**. Carries the `✨ Try Pro — structured report`
  teaser (AES-801).
- **Pro — structured v1 report** (AES-107): the fixed sections incl. the **Treatment performed** table
  with **lot**; auto-**Complete**; "Generated from N captures · M set aside".

### 4.1 Shareable patient report + aftercare (Basic, AES-303/304)
A **curated, read-only** artifact for the patient — the professional output Apple Notes can't make
([foundation §3 Basic 6](redesign-foundation.md)). Staff pick which before/after + sections are
included and an **aftercare template**; everything else is **withheld** (§6 contract). Pro pre-fills it
from the structured report; Basic curates from the chronological one.

## 5 · Patient file & memory
*Prototype: [`aesthetics-patient.html`](../../apps/frontend/design-prototypes/aesthetics-patient.html).*

- **Photo gallery, grouped by visit (Basic, AES-202)** — the whole photo history at a glance; **no
  tagging**, deterministic grouping (recent visits prominent), the eye reads progress. The
  camera-roll-chaos cure. **Pro** adds captions + **prepared before/after pairs** with the slider
  compare (AES-104).
- **Visit history & "what did we do last time" (AES-203)** — **Basic:** a **glanceable visit list** —
  each visit shows the doctor's own note + that visit's before/after, so the answer lives in the notes
  they already wrote, made instantly skimmable (**no structured table**). **Pro:** a longitudinal
  **treatment & lot table** (visit · area · product · units · **lot**) built from extraction — the
  structure **lot recall** + smart lists need, and it exists *because* Pro extracts, never because
  anyone filled a form ([research §3](aesthetics-research-brief.md)).
- **Flags band (Pro, AES-701)** — allergy/consent/preference at the top of the file.
- **Tiered memory** ([screens/patients.md](screens/patients.md)): **Basic** = honest **structural**
  recap, **no ✨**, never paraphrases audio; **Pro** = **AI history** (Snapshot · Story so far · Worth
  remembering · Right now) + one-tap **recall**. Basic shows the `✨ Try Pro` history teaser (AES-804) —
  it sells the *synthesis*, not the data (the gallery + log are already there).
- **Smart lists (Pro, AES-501)** + **Lot recall (Pro, AES-502)** live in Clinical Memory: filters over
  the structured data, and a recall lookup that returns every patient on a recalled lot and hands off to
  the patient channel ("Message all"). A real safety capability only structure can provide
  ([research §6](aesthetics-research-brief.md); FDA counterfeit-Botox recalls).

## 6 · Patient surface — the shared contract
*Prototype: [`aesthetics-patient-surface.html`](../../apps/frontend/design-prototypes/aesthetics-patient-surface.html).
[Foundation §4](redesign-foundation.md): one clinic→patient primitive, several payloads.*

Designed as a **contract**, not per-tier buttons — *why:* four-plus surfaces (aes-Basic, aes-Pro,
therapy, derm) need the same patient channel; ad-hoc-per-vertical guarantees divergence + duplicated
auth/consent ([foundation §4](redesign-foundation.md)).

- **Access** — a tokenized link, no heavy login; **revocable**.
- **Delivery** — channel-agnostic link; **SMS / WhatsApp** is the realistic channel for Iranian clinics
  but is a `⊕ candidate` delivery decision (§10, AES-404).
- **Shared vs withheld** — sharing is an **explicit, curated** clinic action with a per-share preview;
  clinical internals (raw captures, internal notes, **lots**, national ID, other visits) are **always
  withheld** (AES-403).
- **Payloads:** **aes-Basic** = the read-only **report + aftercare**; **aes-Pro** = the **post-session
  Q&A**.

### 6.1 Post-session Q&A (Pro, AES-402)
*Why:* turns the unmanaged WhatsApp/IG question deluge into a fast, in-context, **verified** channel that
accrues as data ([foundation §3 Pro 8](redesign-foundation.md), [research §3](aesthetics-research-brief.md)).
- **Patient side:** an in-thread question composer; replies arrive marked **doctor-verified**.
- **Clinic side (doctor inbox):** *"Patient X asks … · Suggested reply (grounded in this patient's
  context + the doctor's prior answers) … · **Send / Edit / Dismiss**."* **Nothing sends without
  approval** — verification is the gate that matters here ([spines §2](../spines.md): don't inherit the
  never-gate default where a human must sign off). Every exchange is captured into patient memory.

> **As built (`build/pro-qa`).** Public patient surface at `/qa/{token}` (composer + verified-reply
> thread; withholding per AES-403) and a Pro-gated **Q&A inbox** screen (`#qa-inbox`, Mine/Clinic
> scope + per-question Re-route). Routing is admin-configurable (`qa_routing_mode`, default
> AI-routes-to-treating-doctor). The reply draft is a backend-owned `qa_draft` AI job (deterministic
> fallback when no gateway). Contract: [`../backend/aes-pro-qa-api.md`](../backend/aes-pro-qa-api.md).

## 7 · Front desk / reception
*Prototype: [`aesthetics-frontdesk.html`](../../apps/frontend/design-prototypes/aesthetics-frontdesk.html).
Designs the receptionist persona **inside** aesthetics ([foundation §2](redesign-foundation.md)).*

Memara is **not** a booking/billing system ([design-principles §2](../design-principles.md)); the front
desk is a **light arrivals lens + registration**, not a scheduler. It is Clinical Memory's **Today** tab
+ the assignment resolver, framed for the desk.

- **Arrivals / Today (AES-602):** who's in, in plain language — `In chair · Needs patient · Waiting` —
  with Pro **flags** (allergy/consent) at check-in.
- **Register + duplicate guard (Basic, AES-601/205):** the shared patient form (name required, rest
  fill-later); as the name is typed a **deterministic, Persian-aware** near-match check warns **before**
  a duplicate is created — the failure mode that splits one Persian patient into many records
  ([research §3](aesthetics-research-brief.md)). **Use this** adopts the existing record; **Create
  anyway** never blocks.
- **Attach the doctor-captured visit (AES-603):** the capture-first handoff — an unassigned visit the
  doctor started gets a **deterministic suggestion** (the just-registered patient, ranked first) +
  *Detected in this session* + search + Keep unassigned / Create new. In **Pro** most visits
  **auto-match** and never reach the desk.

## 8 · The upsell line (✨ Try Pro teasers)
*[Foundation §3 Pro 9, §1](redesign-foundation.md). The teaser sits at the exact moment Pro would help —
a conversion lever, never a Basic feature; tapping it routes to upgrade (the capture prototype switches
the Tier toggle to Pro to *show* the result).*

| Teaser | Where (Basic) | Sells | Story |
| --- | --- | --- | --- |
| Structure this | Basic chronological report | the structured Treatment-performed report | AES-801 |
| Transcribe this | a Basic audio (voice-memo) card | transcription + structure (where audio stops being first-class) | AES-802 |
| Caption & auto-pair | a Basic photo | AI captions + auto-pairing | AES-803 |
| Recall / AI history | a returning patient's file + recall strip | cross-visit synthesis + "what did we use last time" | AES-804 |

**Rule:** every teaser is **labelled `✨`**, visually distinct (violet), and **non-functional in Basic**
— it never silently runs AI on Basic content. *Why:* keeps the pricing line legible and protects the
upsell ([foundation §1](redesign-foundation.md)).

**As built (`build/aes-frontend`): one Try Pro per screen.** The per-capture teasers above were
consolidated to a single placement each: a **"Do more with Pro"** card at the foot of the Basic
captures feed (one info box explaining transcription + caption/before-after pairing + the structured
report — AES-802/803/801), plus one teaser each on the Basic **report** (AES-801) and the **patient
file** (AES-804 recall / AI history). Tapping any teaser opens a labelled info box (it never runs AI).
*Why:* repeating ✨ on every capture read as upsell pressure; one consolidated explainer keeps Basic
calm while still selling Pro. The table above still records *what each capability sells* and its story.

## 9 · States
Inherits [states.md](states.md) wholesale. Aesthetics-specific notes:
- **Basic has no AI states** — no `Processing`/`Organizing`/`Updating`, no needs-input AI items.
  *As built:* audio is a **voice memo** (compact player, no transcript). There are **no persistent
  sync badges** — not on the session header, not per capture. A single **"Trying to sync"** marker
  (on the header + the affected captures) appears **only when offline / the backend is unreachable**;
  when connected, captures are badge-free. The header also names the active visit **"{patient}'s Nth
  session"** (date+time when unassigned). The only hard stop remains durable-storage-full
  ([redesign-capture-surface.md States](redesign-capture-surface.md)).
- **Flags / lot-recall warnings** are attention markers, never blockers ([design-principles §7](../design-principles.md)).
- **Q&A drafts** never auto-send; a stale/failed draft is silent and self-healing, never a needs-input
  item ([states.md](states.md)).
- Patient-surface link, send, and revoke are explicit, outward-facing actions — confirm before sharing.

## 10 · Proposed feature changes & candidate extensions (for human review)

Per the brief ([foundation §3](redesign-foundation.md)): the agreed set is **detailed**, not re-derived;
nothing is dropped. Below are **additions** surfaced by Phase-0 research — **proposals, not committed
scope.** Each: what · why · tier · recommendation. (No agreed feature is changed or removed; there are
**no deletions or replacements** to flag.)

| # | Extension | What | Why (research) | Tier | Recommendation |
| --- | --- | --- | --- | --- | --- |
| ⊕1 | **Ghost-overlay capture** (AES-105) | Optional "align to a previous photo" — overlay a prior shot at low opacity while shooting (no Before/After tags) | Comparisons stay angle/light-consistent | Basic (det.) | **Adopt in v1** — pure-deterministic, optional, high delight |
| ⊕3 | **Lot/expiry scan** (AES-503) | Scan a product box → lot/expiry onto the extracted treatment item + ledger | Makes lot capture accurate/effortless; powers recall | Pro | **Out of MVP** — deferred fast-follow; barcodes often don't encode lot (OCR risk); gate on real recall usage |
| ⊕4 | **Face-map injection viz** (AES-110) | Render *dictated* treatment onto a face diagram (a read-back; tap only to correct) | A glanceable visual of where/what was injected | Pro | **Derived viz only** (never tap-to-enter) + **later spike**, not alpha |
| ⊕5 | **Lightweight consent capture** (AES-703) | Attach/store a signed consent + a consent flag | Incumbents are heavy here; clinics need *some* consent on file | Both | **Dropped** — just a photo if a clinic wants it; don't build a consent feature |
| ⊕6 | **Pre-visit consent/questionnaire link** (AES-704) | Send an inbound patient-surface form, auto-attached to the visit | Proven pattern; removes in-clinic friction | Pro | **Defer** — reuses the patient surface inbound; sequence after Q&A |
| ⊕7 | **SMS/WhatsApp delivery** (AES-404) | The patient-surface delivery channel | The channel Iranian patients actually use | Both | **Copy-link / native-share / QR first**; automated SMS/WhatsApp later (provider + compliance) |

**Decided (2026-06-11 & 06-12 reviews):**

- **Before/after — present (Basic) vs prepare (Pro).** *Amends foundation §3 Basic 3* (approved
  2026-06-12): per-photo tagging/pairing moves Basic→Pro. **Basic** = a well-presented, visit-grouped
  **photo gallery, no tagging** (the eye pairs); **Pro** = AI captions + **intelligently-assembled
  before/after pairs** + the slider compare. Ghost-overlay (⊕1) reframed as an optional "align to a
  previous photo" aid. See §3.1.
- **No structured forms in Basic.** A Basic treatment/lot row (an earlier proposal) is **rejected** —
  Basic treatment detail is **free-text + fast retrieval** of the previous visit (§3.2, §5); structure
  exists only in Pro, by **extraction**. *Why:* keeps Basic from becoming a small EHR, true to the
  system's spirit ([design-principles §2,§5](../design-principles.md)). This also rules out a manual lot
  field in Basic — lot lives in the note text; cross-patient lot recall is Pro.
- **Lightweight consent (⊕5) — dropped.** Not the wedge; legally sensitive; incumbents own it and we
  shouldn't compete there. A signed form a clinic wants on file is **just a photo** we already capture.
  (The agreed Pro "consent" *flag* — an optional staff marker — is separate; keep only if check-in
  visibility is wanted.)
- **Delivery (⊕7) — copy-link / native-share / QR first**; defer *automated* SMS/WhatsApp to a later
  integration once the provider/channel is chosen. The surface stays channel-agnostic.
- **Face-map (⊕4) — derived visualization only** (render dictated treatment onto the diagram; never
  tap-to-enter), and a **later spike**, not alpha.
- **Lot scan (⊕3) — out of MVP**; deferred fast-follow, gated on real lot-recall usage.
- **Pre-visit link (⊕6) — agreed, deferred** (after Q&A). **Ghost-overlay (⊕1) — adopt for v1 Basic.**

**Still open:** the patient never installs anything — report + Q&A are a tokenized web link (confirmed).
No blocking questions remain.

---
*Cross-refs:* [redesign-foundation.md](redesign-foundation.md) · [spines.md](../spines.md) ·
[redesign-capture-surface.md](redesign-capture-surface.md) · [screens/patients.md](screens/patients.md) ·
[states.md](states.md) · [design-principles.md](../design-principles.md).
