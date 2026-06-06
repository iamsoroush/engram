# Account — Settings & Profile

Two dedicated pages reached from the **account menu** (top-right avatar). The menu offers a clean,
consistent list — **Profile**, **Settings**, **Logout** — and the first two *navigate* to pages
(no inline controls in the dropdown). Replaces the old dropdown that crammed inline language
`<select>`s next to Profile/Logout. See [navigation.md](../navigation.md) for routes.

## Account menu (the dropdown)

- Header: avatar + signed-in name + role.
- Actions: **Profile** (→ `/#profile`), **Settings** (→ `/#settings`), **Logout**.
- No inline preference controls; settings live on the Settings page.

## Settings (`/#settings`)

Tenant-level preferences, grouped, each saved on change with a calm toast (reuses
`PATCH /tenant/settings`). A **Back** action returns to the previous staff screen.

- **Languages**
  - *Transcription* — `Auto (verbatim)` | Persian | English | Arabic. Auto = transcribe verbatim in
    the spoken script (best for mixed-language clinics; avoids romanization that breaks matching).
  - *Report* — `Report default` | Persian | English | Arabic (the synthesized report's language).
- **Patient matching** (H3)
  - *Auto-apply strictness* — `Strict (exact only)` | `Balanced (close match)` | `Lenient (looser)`.
    Controls how aggressively AI auto-assigns a **fuzzy** name match: Strict = deterministic matches
    only; Balanced/Lenient also auto-apply a single high-confidence close match on an explicit
    instruction. The national-ID conflict guard and ambiguous routing apply at every level.
- **Plan**
  - *Tier* — read-only badge (`Pro` / `Basic`) + one line on what each includes.

## Profile (`/#profile`)

- Avatar + display name + email.
- Read-only fields: **Role**, **Clinic** (tenant name).
- Account actions: **Logout**.
- **Debug** (admin only): clear local capture cache.
- A **Back** action returns to the previous staff screen.

## States

- Save feedback is a toast (`Language preferences updated.` / `Patient-matching preference updated.`);
  failures show a calm error toast, no modal.
- Both pages require an authenticated staff session; the persistent capture bar stays visible
  (capture is never blocked).
