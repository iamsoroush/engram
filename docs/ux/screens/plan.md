# Plan (Basic vs Pro)

## Route

`/#plan` — an account-style page reached from the **account menu** (owner/admin only) or the
[onboarding](onboarding.md) "See the Pro plan" link. Has a Back action.

## Purpose

Compare the two plans and switch between them. **No payment yet** — the switch flips the tenant tier
directly so a clinic can explore each plan.

- **Basic** (capture-first, zero AI): fast capture, on-device + synced, captures organized into visit
  sessions, last-visit reference.
- **Pro** (adds the full AI layer): AI transcription + photo captions, AI-drafted reports & summaries,
  AI patient matching + out-of-context checks, longitudinal patient memory, doctor-verified patient
  Q&A.

The current plan is marked; the other shows a **Switch to …** button. Switching updates the in-app
tenant tier immediately, so capabilities + tier-gated UI (capture-bar order, Q&A inbox, patient
memory, onboarding content) follow without a re-login.

## Main Components

- `PlanScreen` (bilingual fa/en + RTL via the app-language seam, like the other account screens).

## Related APIs

- `PATCH /api/v1/clinic/plan` — `{ tier: "basic" | "pro" }`, owner/admin-gated (`tenant_admin_required`);
  returns the updated tenant profile.

## Known Gaps

- No billing/payment. Switching to Pro does not retroactively AI-process captures taken on Basic;
  new captures get Pro processing.
