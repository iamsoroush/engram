# Team (Member management)

## Route

`/#team` — an account-style utility page, reached from the **account menu** (top-right avatar),
shown only to **owner/admin**. Has a Back action returning to the previous screen. Also reachable
from the final [onboarding](onboarding.md) step's "Invite your team" link.

## Purpose

Self-serve sign-up creates a solo `owner`; this lets the owner (or an admin) add staff and manage
their roles. **MVP model:** the owner creates the account directly with a **temporary password** they
hand over — no email/SMS invite delivery (that is out-of-scope infra). The created member signs in
with their email + that password.

## Primary Actions

- **Add a member:** full name, email, role (doctor / assistant / admin), and a temporary password.
  - **New person** → a temporary password (≥ 8) is required; the notice reminds the owner to share it.
  - **Existing Engram account** (email already in use, e.g. a clinician who works at another clinic) →
    leave the password **blank**; they're added across clinics with their existing credentials, and
    the notice says so. Re-adding someone already in this clinic is blocked (already a member).
- **Per-member:** change role (doctor / assistant / admin) and **Disable / Enable** (membership
  status). The **owner row** and **your own row** are protected (no controls); the backend enforces
  this too. Changes take effect on the member's **next request** (authorization is re-checked live,
  not at token expiry) — a disabled member loses access immediately.

## Visible Data

- Member list (owner first): name, email, role, and a Disabled badge when applicable.

## Roles & permissions

Members use the existing role + multi-seat permission-preset system (admins tune `doctor`/`assistant`
presets in [Settings](../../backend/auth.md)). `owner` and `patient` are not assignable here.

## Main Components

- `TeamScreen` (bilingual fa/en + RTL via the app-language seam, like the other account screens).

## Related APIs

- `GET /api/v1/clinic/team` · `POST /api/v1/clinic/team` · `PATCH /api/v1/clinic/team/{userId}` —
  all owner/admin-gated (`tenant_admin_required`).

## Known Gaps

- No email/SMS invites or self-set passwords; no forced first-login password reset.