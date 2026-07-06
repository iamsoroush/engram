# UX Epic — Session-screen layout diet

**Status:** design proposal for owner review. Not built. Do not fold into system-state until approved.

**Fold destination (when approved + built):** [`docs/ux/screens/capture.md`](../ux/screens/capture.md)
(the zone stack → the patient strip + auto-collapse), and a new `AES-13xx` band in
[`docs/ux/aesthetics-stories.md`](../ux/aesthetics-stories.md).

> Priority **4 of 5**. Renders the [the attention model](../ux/states.md#attention-model) severity language as
> strip chips, and shares the report-first shell with [tier-convergence](ux-epic-tier-convergence.md)
> — build all three at the seam.

---

## 1. Problem & evidence

On a phone, the Pro Active Session screen stacks **up to nine zones above the report** — so the
clinician scrolls past a wall of chrome before reaching the thing they came to read.

**Grounded in code** — the JSX render order in `features/capture/components/CaptureScreen.tsx`,
top → bottom:

| # | Zone | element |
| --- | --- | --- |
| — | back button (contextual) | `.context-back-button` |
| — | session header (title/status/meta) | `.active-session-summary` |
| — | read-only banner (contextual) | `.session-readonly-banner` |
| 1 | **AI usage notice** | `<AiUsageNotice>` |
| 2 | **verify bar** | `<SessionVerifyBar>` |
| 3 | **patient card** | `.patient-context-card` |
| — | next-lined-up nudge (contextual) | `.next-lined-up` |
| 4 | **safety panel** | `.session-safety-panel` |
| 5 | **session context card** | `<SessionContextCard>` |
| 6 | **verify region** (conflict + AI-created-patient resolvers) | `.session-verify-region` |
| 7 | **report card** | `.workspace-report-card` |

Even excluding the contextual rows, that's **five to seven stacked cards** before the report on a
device ~360 px wide. The session context card **already** auto-collapses once the report has content
(`SessionContextCard` behavior in [capture.md](../ux/screens/capture.md)) — proof the pattern works —
but it collapses **alone**, while the patient card, verify bar, safety panel, and verify region each
still hold their own full-height band. The identity/context/verify/safety information is **four
separate cards saying overlapping things about the same patient at the same moment**.

## 2. Design goal & non-negotiables

**Collapse identity + context + verify state + safety into one expandable *patient strip*** that sits
above the report, so the above-the-fold view on a phone becomes **strip → report** (everything else
one tap away).

Non-negotiables:

- **Never bury safety** ([capture.md](../ux/screens/capture.md): "safety is highest priority"). A
  safety flag stays visible even collapsed — a red chip, always.
- **Never block** ([design-principles §7](../design-principles.md)). Moving resolvers into an
  expansion must keep them one tap away with a visible count; capture-first is untouched (the capture
  bar stays the trust anchor beneath).
- **Assignment stays prominent while unassigned** ([states.md](../ux/states.md) soft-amber). The strip
  must not collapse away the `Assign` action on an unassigned visit.

## 3. The design

### 3.1 The patient strip

One component absorbs zones **3 (patient card) + 5 (session context) + 2's count (verify) + 4's
presence (safety)**. Two states: **collapsed** (one line) and **expanded** (the full stack).

**Collapsed (default once the report has content):**

```text
┌──────────────────────────────────────────────────────────────┐
│ (SM)  Sara M. · 3rd visit  ✓ assigned   ⚠ 2 to confirm  🩹    ⌄ │
└──────────────────────────────────────────────────────────────┘
        report begins immediately below
```

- **Identity:** avatar + name + visit ordinal + assignment state (`✓ assigned` / `Matched by AI` /
  soft-amber `Unassigned · Assign`).
- **Severity chips** (from [the attention model](../ux/states.md#attention-model)): an amber `⚠ N to confirm`
  (the S2 verify count) and a red `🩹` safety chip when flags exist. Tapping a chip expands the strip
  **scrolled to that section** (the verify resolvers / the safety panel).
- **Chevron** re-expands the whole strip.

**Expanded (the full stack, on tap or pre-capture):**

- patient card actions (`Assign`/`Change`, `History`)
- session context digest (last-visit digest, cross-visit photo strip — the current `SessionContextCard`)
- safety panel (full opt-out flag list)
- verify region (patient-conflict resolver + AI-created-patient panel)

Inline confirms **stay in the report** where the data is (the `Confirm dose` box on the treatment row
is already inside the report card — it does not move). The strip surfaces the *count*; the *fix* stays
at its source (the [the attention model](../ux/states.md#attention-model) in-place rule).

### 3.2 Auto-collapse state machine (the core ask)

| State | Strip | Why |
| --- | --- | --- |
| **Pre-capture** (no captures yet) | **expanded** | context is a glance aid before you capture (matches today's `SessionContextCard` fully-open-before-captures) |
| **Report has content** | **collapsed** to one line | the report is now primary; identity/context recede |
| **Unassigned visit** | **collapsed but `Assign` prominent** | never hide the pending assignment action (soft-amber) |
| **Blocker present** (S2 > 0) | collapsed, **severity chip visible** | one tap to the resolver; never a wall above the report |
| **Safety flags on record** | collapsed, **red safety chip visible** | safety never loses salience |
| **Undo all captures** | **re-expanded** | returns to the pre-capture glance state (matches capture.md) |
| **Historical review** (read-only) | **collapsed** | no pending actions to surface |

Manual override always wins: a tap expands, the chevron collapses; the state machine only sets the
*default*.

### 3.3 The other zones

- **AI usage notice (zone 1):** conditional already (only near/at budget). Reduce to a **thin
  dismissible bar** above the strip rather than a full card — it's rare and calm.
- **Verify region resolvers (zone 6):** move **into the strip expansion** (reached by the `⚠` chip),
  rather than always rendered above the report. This is the biggest space win. Never-block preserved:
  the chip is always visible when a blocker exists.
- **Session header / back / read-only banner:** unchanged (thin, contextual).

Above-the-fold result on a phone: `[thin AI-usage bar if any] → [one-line patient strip] → [report]`.
Nine zones → effectively two, with everything one tap away.

### 3.4 Copy (en, with fa notes)

| Surface | English | fa note |
| --- | --- | --- |
| Collapsed nudge | `3rd visit · Show visit context` | reuse capture.md's collapsed line |
| Assigned state | `✓ assigned` / `Matched by AI` / `Unassigned · Assign` | chrome via `t()`; name is content |
| Verify chip | `2 to confirm` | tabular; opens the resolver |
| Safety chip | `Allergy` (or count) | flag body is clinical content, RTL, untranslated |
| Expand/collapse | `Show visit context` / chevron | «نمایش سابقه ویزیت» |

## 4. Tier & persona behaviour (per [foundation.md](../ux/foundation.md))

- **Basic (zero-AI):** a **simpler strip** — identity + assignment + the deterministic last-visit
  digest. **No verify chip, no safety chip** (both Pro). This is exactly the shared shell the
  [tier-convergence](ux-epic-tier-convergence.md) epic needs: Basic and Pro use the same strip;
  Pro's simply lights up more chips. The AI layers are absent, not teased.
- **Pro:** full strip (identity + context + verify chip + safety chip).
- **Doctor / injector (primary beneficiary):** capture-first, one-handed, mobile — report-first with
  minimal scrolling is the whole win. Default collapse once capturing.
- **Reception:** rarely deep in a session (they live in Clinical Memory), so less affected; but the
  strip's prominent `Unassigned · Assign` helps their attach-the-visit flow
  ([AES-603](../ux/aesthetics-stories.md)).

## 5. Edge cases

- **Unassigned:** don't auto-collapse the `Assign` action away — the collapsed strip shows
  soft-amber `Unassigned · Assign` (a decision is pending).
- **Brand-new patient, nothing to show:** the context digest is empty (capture.md hides it) — the
  strip is just identity; nothing to expand into.
- **Safety salience under collapse (design tension):** a red safety chip is *always* shown collapsed,
  but a chip is less prominent than a panel. Mitigation: a **tenant setting** pins the full safety
  panel open (high-risk clinics never collapse safety). Flagged as an open question.
- **Blocker + collapsed:** the `⚠ N` chip is the always-visible affordance; tapping expands to the
  resolver. The per-session verify bar's `Review` still works (scrolls into the expanded region).
- **Tablet / landscape:** enough width to show the strip **expanded beside** the report (two-column) —
  the diet is a phone problem; don't force collapse on wide screens.
- **Accessibility:** collapsed chips are real buttons with adequate targets; screen readers announce
  "2 to confirm, button" and "allergy flag, button".
- **Sticky behavior:** the collapsed strip may stay **sticky** on scroll (so identity + safety + count
  are always visible while reading a long report) — open question on whether sticky or scroll-away.

## 6. Incremental build plan + AES-### candidates

Proposed as **candidate epic E13** (new band; not yet registered).

1. **AES-1301 — Unified patient strip.** Compose the patient card + session context + verify chip +
   safety chip into one component with collapsed (one-line) and expanded (full-stack) states.
2. **AES-1302 — Auto-collapse state machine.** Pre-capture expanded → report-has-content collapsed →
   unassigned keeps `Assign` → undo-all re-expands → historical collapsed. Manual override wins.
3. **AES-1303 — Resolver relocation.** Move the verify-region resolvers into the strip expansion
   (chip-triggered) while keeping inline confirms in the report; preserve the never-block invariant.
4. **AES-1304 — Safety chip + salience setting.** Always-visible red chip + a tenant "keep safety
   panel open" setting for high-risk clinics.
5. **AES-1305 — Tier variants.** Basic simple strip / Pro full strip (shared shell with
   [tier-convergence](ux-epic-tier-convergence.md)).
6. **AES-1306 (⊕) — Responsive expanded layout.** Two-column strip-beside-report on tablet/landscape.

## Decisions & open questions

**Resolved (owner review, 2026-07-04):**

- **High-risk clinic is a tenant setting.** A clinic self-declares "high-risk" in settings; when set,
  the safety panel stays **pinned open** (never collapses to a chip). The flag generalizes — it can
  later gate other safety-forward behaviors (never auto-collapse safety, stricter consent prompts)
  from one honest setting. Confirmed.

**Resolved (owner review, round 2 — 2026-07-04):**

- **Conflict resolvers — visible, never buried:** an active conflict keeps a **thin inline band
  above the report** (impossible to miss, resolvable in place); the strip expansion is a second
  entry point, not the only one. Principle recorded: *conflicts should be visible and easily
  resolved, not hidden somewhere.*
- **Sticky strip — pinned** while scrolling the report (identity + safety always visible).
- **AI-usage placement — thin bar above the strip** (as recommended).

**New requirement (owner review, round 2):** when a patient is **assigned or reassigned and has
history**, that history must become **automatically visible** — the context card / history strip
auto-surfaces (auto-expands) on the assignment event instead of waiting behind a tap. Patient
history is the natural primary source of context at that moment; requiring another action to see it
is bad UX. Interacts with the auto-collapse rule: collapse applies once the report has content *and*
the history has been surfaced — a new assignment event re-surfaces it.
