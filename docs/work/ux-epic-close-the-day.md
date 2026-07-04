# UX Epic — Close the day / unified attention model

**Status:** design proposal for owner review. Not built. Do not fold into system-state until approved.

**Fold destination (when approved + built):** [`docs/ux/states.md`](../ux/states.md) (a single
"Attention model" section replacing the scattered verify-bar / needs-input / safety rules),
[`docs/ux/screens/patients.md`](../ux/screens/patients.md) (the Needs-input tab evolves into the
sweep lens), [`docs/ux/screens/capture.md`](../ux/screens/capture.md) (in-place severity language),
and a new `AES-10xx` band in [`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md).

> Priority **1 of 5** structural epics. Companion docs:
> [`ux-epic-treatment-overlay.md`](ux-epic-treatment-overlay.md),
> [`ux-epic-unified-finder.md`](ux-epic-unified-finder.md),
> [`ux-epic-session-layout-diet.md`](ux-epic-session-layout-diet.md),
> [`ux-epic-tier-convergence.md`](ux-epic-tier-convergence.md). This epic defines the **severity
> language** the layout-diet epic renders as strip chips — build the two together at the seam.

---

## 1. Problem & evidence

Today a clinician's "something needs you" signal is split across **four independent systems**, each
with its own count, its own placement, and its own scope — and none of them aggregates the one item
an injector accumulates most: the unconfirmed carried-forward dose.

| System | Where it lives | Scope | What it surfaces | Doc |
| --- | --- | --- | --- | --- |
| **Verify bar** (`SessionVerifyBar`) | sticky, inside one session | **per-session** | blockers: unconfirmed carried-forward dose, AI-created-patient identity, patient conflict | [capture.md](../ux/screens/capture.md) "Verify bar" |
| **Needs-input tab** | Clinical Memory tab | **cross-session** | patient-assignment decisions only (assign / choose / verify patient) + storage warning | [patients.md](../ux/screens/patients.md) "Needs Input Tab" |
| **Safety panel** (`session-safety-panel`) | inside one session, above verify region | **per-session** (projects onto patient) | allergy / contraindication / consent flags | [capture.md](../ux/screens/capture.md) "Safety panel" |
| **Q&A badge** | top-bar icon beside Search | **cross-session** | patient questions awaiting a reply (Pro) | [qa-inbox.md](../ux/screens/qa-inbox.md) |

The consequences:

- **Unconfirmed doses are only discoverable per-session.** The verify bar lives *inside* a session.
  An injector who saw 12 patients today, three with a carried-forward dose the synthesis couldn't
  confirm, has **no single place** that says "3 doses need confirming." They must reopen each visit.
  The Needs-input tab — the one cross-session inbox — deliberately excludes doses (it is patient-
  assignment + storage only).
- **Four counts, four mental models.** The verify bar counts blockers-in-this-session; the Needs-
  input tab badge counts assignment decisions clinic-wide; the Q&A badge counts pending replies;
  the safety panel doesn't count at all (it's opt-out awareness). A clinician can't answer "how much
  is open, and how bad is it?" from one glance.
- **No severity ordering across systems.** A safety contraindication (highest stakes) and a low-
  confidence lot footnote (cosmetic) live in unrelated surfaces with unrelated visual weight. The
  product never says *this matters more than that*.
- **No end-of-day close-out.** The natural injector rhythm — "before I leave, clear what's open" —
  has no supporting surface. Attention items decay silently in sessions nobody reopens.

**Grounded in code.** `SessionVerifyBar` (`features/capture/components/SessionVerifyBar.tsx`) shows
`verifyCount = openDoseConfirmations.length + (patientVerifyNeeded ? 1 : 0) + patientConflicts.length`
computed in `CaptureScreen.tsx` from `activeSession` **alone** — nothing sums doses across sessions.
The safety panel is inline JSX (`.session-safety-panel` in `CaptureScreen.tsx`), explicitly excluded
from `verifyCount` ("warnings over blocking"). The Q&A badge is `.app-qa-badge` in `Shell.tsx`, fed by
`fetchQaInbox("mine").total`. The Needs-input tab (`PatientsHome.tsx`) fetches the backend
`filter=needs-input` decision set — whose only categories are `verify` / `choose-patient` /
`resolve-conflict` / `assign-patient` (`memoryModel.ts` `decisionActionForSession`). A frontend grep
for `close.the.day` / `end.of.day` / a session-list blocker sum returns **nothing**: the *only* item
that appears in both the per-session bar and the cross-session tab is the AI-created-patient
`verify`; **doses and safety flags roll up nowhere**.

## 2. Design goal & non-negotiables

**One severity-tiered attention system.** A single taxonomy that every "needs you" signal maps into,
**rendered in place** at each item's source (unchanged inline behavior) **and aggregated** into one
end-of-day **Close-the-day sweep** for injectors.

Non-negotiables carried from [design-principles.md](../design-principles.md):

- **Never block** (§7). Attention is warnings / review markers, never a gate. Capture-first stays
  sacred; you can end the day with items open. No hard "you have unconfirmed items" modal.
- **Surface by exception** ([states.md](../ux/states.md)). An empty attention surface means the
  checks *ran and passed*, never "not yet checked" (the verify bar already distinguishes
  `Checks pending · organizing` from a clean empty — keep that).
- **Hide technical detail** (§6). Severity is clinical/human ("safety", "confirm", "suggested"),
  never job/queue language.
- **Highest priority is safety** ([capture.md](../ux/screens/capture.md)): safety must never lose
  salience to a layout change.

## 3. The design

### 3.1 One severity ladder (the reusable contribution)

Every attention signal maps to exactly one tier. Tier drives color, ordering, and whether it counts
toward the aggregate. This is the shared language the [layout-diet strip](ux-epic-session-layout-diet.md)
renders as chips and the sweep renders as sections.

| Tier | Name | Colour | Requires | Examples | Counts in aggregate? |
| --- | --- | --- | --- | --- | --- |
| **S1** | **Safety** | red / amber | *awareness* (opt-out) | allergy · contraindication · consent flag | shown, not counted as "to do" (never a blocker) |
| **S2** | **Confirm** | amber | *a decision* | unconfirmed carried-forward **dose**, AI-created patient to **verify**, patient **conflict**, **unassigned** visit (assign) | **yes** — this is "N to confirm" |
| **S3** | **Suggested** | blue | *optional one-tap* | suggested reassignment (implicit mention), partial-match | yes, as a separate "optional" count |
| **S4** | **Note** | gray | *nothing* (fix if you like) | low-confidence extraction, missing lot | no — calm footnote, fix-at-source |
| **Q&A** | **Messages** | violet (Pro) | *a reply* | patient question awaiting doctor approval | yes, separate "messages" count (async cadence) |

Rationale for the split:

- **Safety is tier-0 for *visibility*, not a to-do.** Flags are opt-out (kept by default; the
  clinician only rejects a wrong one — [capture.md](../ux/screens/capture.md) "Safety panel"). So
  S1 sorts first and is always visible, but it is **not** a blocker and does **not** inflate the
  "N to confirm" count. Collapsing safety must never hide it — see the salience rule below.
- **S2 is the only true "N to confirm".** It merges the verify bar's blockers **and** the Needs-
  input tab's assignment decisions into one count. A dose and an unassigned visit are the same kind
  of ask ("a human decision keeps the record honest"), so they belong in one number.
- **S4 never counts.** Low-confidence / missing-lot are quality polish; counting them would make a
  clean visit read dirty. They stay as gray fix-at-source footnotes exactly as today.

### 3.2 In place: nothing moves away from its source

The unified model **re-skins**, it does not relocate. Each item still renders where the data is
(the surface-by-exception rule in [states.md](../ux/states.md)):

- The inline `Confirm dose` box stays on the treatment row; it now wears the **S2 amber** chip style.
- The safety panel stays at its position; it wears **S1**.
- Suggested-reassignment chips wear **S3**; low-confidence footnotes wear **S4**.
- The per-session verify bar stays, but its "N to confirm" is now literally the S2 count for that
  session — the same number the aggregate rolls up.

Only the **language and colour** unify. This keeps the fix where the context is while making the
aggregate a faithful roll-up (no divergence between "what the sweep says" and "what the session says").

### 3.3 One aggregate indicator (replaces two badges)

The top-bar **Needs-input badge and the Q&A badge merge** into a single **Attention indicator**
(a bell with a severity-coloured count) beside Search. It shows the highest open tier's colour and
a compact breakdown on open:

```text
🔔 5
   ⚠ 4 to confirm     (S2, amber)
   💬 1 message        (Q&A, violet)
   · 2 suggested       (S3, quiet)
```

Tapping it opens the **Close-the-day sweep** (§3.4). The per-session verify bar is unchanged
(it is the in-session view of the same S2 items).

### 3.4 The Close-the-day sweep (the injector lens)

A single cross-session surface — the **Needs-input tab evolves into this** (it already aggregates,
just too narrowly). Severity-ordered, session-grouped, resolve-in-place.

**Entry:** the Attention indicator, or a `Close the day · N items` card at the top of Clinical
Memory → Today when anything is open near end of day.

**Layout (severity-ordered):**

```text
Close the day                                  Mine ▾   3 of 8 cleared

⚠ Confirm (4)
  Sara M. · Follow-up · Today 4:23 PM
    Confirm dose — “botox, same as last time” · 20 units?      [Confirm] [Edit]
  Unassigned visit · Today 2:15 PM
    3 captures, no patient                                     [Assign patient]
  …
🩹 Safety to review (1)
  Reza K. · lidocaine allergy detected                        [Keep] [Not right ✕]
💬 Messages (1)
  Niloofar — “is this swelling normal?”                       [Open reply]
· Suggested (2)
  Maryam D. — reassign to Maryam Dabiri?                      [Apply] [Dismiss]
```

Properties:

- **Resolve in place.** Each item opens the *same* focused resolver it uses at its source — the
  inline dose confirm, the assign/choose/verify resolver ([patients.md](../ux/screens/patients.md)
  routing), the safety keep/reject, the Q&A reply. No new resolvers; the sweep is a router + a list.
- **Progress, never completion pressure.** `3 of 8 cleared` reassures; leaving with items open is
  fine. No blocking, no red "incomplete day".
- **Scope** `Mine` / `Clinic` (reuse the [AES-904](../ux/aesthetics-stories.md) toggle). Default
  `Mine` for a doctor (their doses/safety/messages), `Clinic` for reception (assignment/intake).
- **Empty state:** `All caught up — nothing needs you.` (surface-by-exception).
- **Day boundary** = the user's calendar day (reuse Today's definition in
  [patients.md](../ux/screens/patients.md)), plus any older still-open S2 items surfaced under an
  `Older, still open` group so nothing decays silently.

### 3.5 Copy (en, with fa notes)

| Surface | English | fa note |
| --- | --- | --- |
| Indicator tooltip | `Attention` | «توجه لازم» — chrome, via `t()` |
| Sweep title | `Close the day` | «جمع‌بندی روز» (end-of-day framing); avoid a literal "close/shut" verb — pick the "wrap-up" sense |
| Aggregate | `4 to confirm · 1 message` | numbers tabular; RTL-mirror the row |
| Progress | `3 of 8 cleared` | «۳ از ۸ رسیدگی شد» |
| Empty | `All caught up — nothing needs you.` | «همه‌چیز مرتبه — کاری برای شما نمونده» |
| Section heads | `Confirm` · `Safety to review` · `Messages` · `Suggested` | clinical nouns, not "errors/queue" |
| Older group | `Older, still open` | «قدیمی‌تر، هنوز باز» |

All chrome routes through `shared/i18n` `t()` per [CLAUDE.md §5](../../CLAUDE.md); clinical CONTENT
inside items (a flag body, a dictated dose string) stays `reportLanguage`, per-line RTL.

## 4. Tier & persona behaviour (per [foundation.md](../ux/foundation.md))

- **Basic (zero-AI):** the ladder is naturally sparse — only deterministic S2 items exist
  (**unassigned visit**, storage warning) plus the duplicate-patient guard. No dose confirmation
  (no extraction), no safety flags (Pro), no Q&A (Pro), no AI-created-patient verify (no matching).
  The sweep still exists but shows only what Basic can produce — a **legible upgrade**, never an
  empty Pro category shown as a teaser ([foundation §1](../ux/foundation.md)).
- **Pro:** the full ladder (S1–S4 + Q&A).
- **Doctor / injector:** the primary audience for the sweep — end-of-day dose confirmation across
  many quick visits, plus safety review and messages. Default scope `Mine`.
- **Assistant / reception:** their attention is **intake** — unassigned/ambiguous visits to attach,
  duplicate guards, storage. Default scope `Clinic` (they coordinate the room). Safety and dose are
  the treating doctor's; reception sees assignment items, and clinical S1/S2 dose items appear
  read-only ("waiting on Dr X") under `Clinic`.
- **Multi-seat / owner-only actions** ([foundation §7](../ux/foundation.md),
  [pipeline-versioning](../architecture/pipeline-versioning.md) permissions): an item only the owner
  may resolve (owner-only dose confirm/undo) shows in `Clinic` as read-only with the owner named,
  never as an actionable row for a non-owner — permissions decide *actionable vs. informational*,
  never *block*.

## 5. Edge cases

- **Resolved elsewhere while the sweep is open** (multi-seat concurrency): the item marks done and
  the count decrements live; a vanished item self-heals like the
  [stale-reference](../ux/states.md#stale-reference-self-heal-deletedmerged-patient) pattern — no
  stuck row.
- **Offline:** the sweep shows locally-known items; a dose confirm queues via the outbox and clears
  on drain (the return-receipt banner already exists in [states.md](../ux/states.md)).
- **Synthesis still in flight:** an item that *might* become a blocker shows nothing yet — the
  session's `Checks pending · organizing` state is respected; the sweep never invents a premature
  "to confirm".
- **Safety salience under collapse** (ties to [layout-diet](ux-epic-session-layout-diet.md)): a
  safety flag must stay visible even when the patient strip is collapsed — a red S1 chip is always
  shown when flags exist, and a tenant setting can pin the full panel open for high-risk clinics.
- **Never a completion gate:** ending the day with S2 open is allowed. If a gentle nudge is added
  (⊕ below) it is opt-in and dismissible, never a wall.
- **Q&A cadence:** messages arrive between visits, not tied to a today-visit — they appear in the
  sweep and the aggregate but deep-link to the [Q&A inbox thread](../ux/screens/qa-inbox.md); the
  sweep does not reimplement the reply flow.

## 6. Incremental build plan + AES-### candidates

Proposed as **candidate epic E10** (new band; not yet registered — this is a proposal). Build the
severity language (E10.1–2) jointly with the [layout-diet strip](ux-epic-session-layout-diet.md).

1. **AES-1001 — Severity taxonomy + unified attention feed.** Define S1–S4 + Q&A; one backend
   aggregation over the existing sources (verify blockers, the needs-input decision set, detected
   safety, pending Q&A), scoped `Mine`/`Clinic`. *Backend: extend the existing backend-computed
   needs-input decision set into a superset attention feed. No new clinical logic — a roll-up.*
2. **AES-1002 — In-place severity language.** Re-skin the verify bar, safety panel, suggestion
   chips, and soft footnotes to the shared tier colours/labels. No behaviour change. *(Shared with
   the strip chips in the layout-diet epic.)*
3. **AES-1003 — Unified Attention indicator.** Merge the Needs-input and Q&A top-bar badges into one
   severity-coloured indicator with a breakdown; opens the sweep.
4. **AES-1004 — Close-the-day sweep lens.** Evolve the Needs-input tab into the severity-ordered,
   session-grouped, resolve-in-place sweep with progress, scope, empty state, and the `Older, still
   open` group.
5. **AES-1005 — Role & tier scoping.** Basic-sparse ladder; reception-vs-doctor default scope;
   owner-only items shown read-only for non-owners.
6. **AES-1006 (⊕) — Opt-in end-of-day nudge.** A dismissible "N items still open — review before you
   go?" prompt, tenant/user opt-in. Candidate; recommend *after* validating the sweep in use.

## Decisions & open questions

**Resolved (owner review, 2026-07-04):**

- **Replace the Needs-input tab** — the sweep *is* the evolved tab (rename → "Attention"), one inbox,
  superset scope. Confirmed.
- **Safety = awareness, not counted.** A detected safety flag is shown first (highest priority) but
  does **not** add to the "N to confirm" count. *Why:* flags are kept-by-default (you act only to
  reject a wrong one); counting them would pressure a clinician to "clear" safety, inverting the safe
  default. Confirmed.
- **Q&A is a section in the sweep** (end-of-day is when a doctor clears patient messages), but it
  **deep-links to the [Q&A inbox](../ux/screens/qa-inbox.md) thread** for the actual reply — the sweep
  never reimplements the reply flow. Confirmed.

**Resolved (owner review, round 2 — 2026-07-04):**

- **Day boundary — calendar day**, with a **carry-over requirement**: anything left undecided from
  previous days does not vanish at midnight — the Attention sweep always includes an **"Earlier"**
  group (undecided items from prior days) alongside today's items. The day lens is a view, never a
  data boundary; nothing becomes unreachable because the day rolled over.
- **Opt-in nudge (AES-1006) — YES, as a pure reminder.** Non-enforcing by definition: a quiet,
  dismissible end-of-day prompt; never blocks or gates anything (never-block holds).
