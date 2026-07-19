# Account — Menu, Settings & Profile

Utility pages reached from the **account menu** (top-right avatar). Account/utility screens have no
capture context, so they are the one place the persistent capture bar is hidden (it would overlap
their content). Each page has a **Back** action returning to the previous staff screen. Routes:
[navigation.md](../navigation.md).

**Shared chrome.** Every account/utility page (Settings, Profile, Team, Plan, Switch clinic,
Insights) renders the shared **`ScreenHeader`** — one back-button + title pattern. The back button
is a ≥44px tap target with an SVG chevron that mirrors under RTL (points toward the inline-start
edge in both fa and en); there is no literal `←` glyph. The content column matches the topbar width
(`--content-max`, 820px). See [frontend/overview.md](../../frontend/overview.md#shared-ui-primitives).

## Account menu (the dropdown)

- Header: avatar + signed-in name + role · clinic name, with a `Pro`/`Basic` tier pill.
- Items, in order — the navigating items open pages (no inline controls in the dropdown). Personal
  identity actions come first; the owner/admin clinic-management pages are grouped under a labelled
  **Clinic** section (the label and its items are omitted for other roles):
  - **Profile** → `/#profile`
  - **Settings** → `/#settings`
  - *Clinic* (section label — owner/admin only)
    - **Insights** → `/#insights` ([insights.md](insights.md))
    - **Team** → `/#team` ([team.md](team.md))
    - **Plan** → `/#plan` ([plan.md](plan.md))
  - **Switch clinic** → `/#switch-clinic` — only for users belonging to more than one clinic
  - **Replay guide** — re-runs the onboarding guide (shown when available)
  - **Logout**

## Settings (`/#settings`)

Tenant-level preferences, grouped; each control saves on change with a calm toast
(`PATCH /tenant/settings`). Dropdowns share one visual system — the styled `SelectMenu` and the
styled native `Select` are identical closed (same height, border, radius and mirrored caret). **On
tablet/desktop (≥768px) the setting cards flow in a two-column grid**; the header, the AI-usage card
and the tall aftercare-template editor span both columns, while the small groups pair up. Below
768px it is a single column. Card order reads top→bottom then start→end in both LTR and RTL.

- **Languages**
  - *App language* — `English` | `فارسی` | `العربية` (autonyms, each in its own script; sets the UI
    chrome language + RTL — clinical content follows the report language, per the
    [i18n model](../../frontend/i18n.md)).
  - *Transcription* — `Auto (verbatim)` | the three languages. Auto transcribes verbatim in the
    spoken script (best for mixed-language clinics; avoids romanization that breaks matching).
  - *Report* — `Report default` | the three languages (the synthesized report/content language).
- **Patient matching**
  - *Auto-apply strictness* — `Strict (exact only)` | `Balanced (close match)` | `Lenient (looser)`.
    Governs whether a single high-confidence **fuzzy** match auto-applies; the national-ID conflict
    guard and ambiguous-match routing hold at every level (decision matrix in
    [capture.md](capture.md)).
- **Patient sharing**
  - *Include brands* — checkbox (`shareIncludeBrands`, default **off**): whether the shared
    "what we did" lines may name brands; generic wording by default. The treatment table and lots
    stay always-withheld regardless ([patient-surface.md](patient-surface.md)).
- **Plan**
  - *Tier* — read-only `Pro`/`Basic` badge + a one-line description of what the tier includes.
  - *Workspace* — read-only vertical (e.g. Aesthetics) + the encounter label it uses.
- **AI usage** — the fair-use monthly AI-usage card: budget consumed, per-plan caps, and limit
  states ([states.md](../states.md#ai-usage-limits-pro); system:
  `docs/business/ai-usage-limits.md`).
- **Role permissions** (admin only; AES-905) — per-role **presets** for assistants and doctors:
  `contribute` · `+ reassign` · `full`. Permissive defaults (assistant = reassign, doctor =
  contribute); deliberately not a granular matrix. Drives session ownership and the policy-aware
  intent gate ([foundation §7](../foundation.md)).
- **Aftercare templates** (AES-702) — create/edit/delete the deterministic per-procedure aftercare
  templates the patient share uses.

There is deliberately **no AI model picker** — models are chosen and optimized centrally
(`docs/technical-decisions/2026-06-14-therapy-slice1-beyond-plan.md`: "AI model selection is NOT a user setting").

## Profile (`/#profile`)

- Avatar + display name + email.
- Read-only fields: **Role**, **Clinic** (the active tenant).
- Account actions: **Logout**.
- **Debug** (admin only): clear the local capture cache.

## States

- Save feedback is a calm toast; failures show a calm error toast, no modal.
- Both pages require an authenticated staff session.
