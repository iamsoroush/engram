# Launch backlog — open user-facing items

> **Fold destination:** [docs/backend/auth.md](../docs/backend/auth.md) +
> [docs/ux/screens/login.md](../docs/ux/screens/login.md) when these ship. Open **infra/hardening**
> debt is NOT tracked here — that register is
> [docs/production-alpha-tradeoffs.md](../docs/production-alpha-tradeoffs.md).

The go-live tracker (`production-readiness.md`) is retired — Engram is live at `engram.ir`.
These are the user-facing gaps that survived it:

- **Phone/OTP login** — sign-up/sign-in is email + password only. Iran-first users expect a
  phone number + OTP credential; the auth follow-up from the launch epic.
- **Password reset** — no self-service reset flow yet; a forgotten password currently needs an
  operator (owner sets a temp password via the Team screen, or manual intervention).

Still-open infra items (monitoring overlay undeployed, MinIO root key, local-only backups by
default, no resource limits, no staging, build-on-box deploys) live in
[production-alpha-tradeoffs.md](../docs/production-alpha-tradeoffs.md) — keep them there, don't
duplicate.
