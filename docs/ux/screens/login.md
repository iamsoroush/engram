# Unauthenticated Shell (Landing / Login / Sign-up)

## Route

No hash route of its own. The whole unauthenticated surface renders before authenticated staff
screens, managed by `UnauthShell` as a three-view state machine: **landing → login** or
**landing → sign-up**. On successful auth it unmounts and the staff app takes over.

## Language (bilingual + RTL)

These public surfaces are bilingual **fa/en** with a language toggle in the top bar. The choice is
persisted (`localStorage`) and defaults from the browser language, falling back to Persian
(Iran-first). The selected language sets `dir`/`lang` on `<html>` (RTL for Persian). On login the
authenticated app takes over via `AppLangProvider` (tenant `app_language`) — it is also fully bilingual;
see [frontend/i18n.md](../../frontend/i18n.md). (The shared seam lives in `shared/i18n`.)

## Views

### Landing (`LandingPage`)

- A composed marketing page (two-column hero on desktop, single column on mobile): a stylized
  in-product preview (capture bar with audio/photo/note) beside the copy + CTAs (**Create your
  clinic** → sign-up, **Log in** → login), then **How it works**, a **trust/privacy** block, and a
  **Plans** section with placeholder pricing.
- **Tier-honest:** Basic (the default for new sign-ups) is presented on its own; the AI layer is the
  Pro upgrade lane in Plans — not promised as a standard feature. Pricing amounts are placeholders.

### Login (`LoginGate`)

- Real email + password form (calls `POST /api/v1/auth/login`).
- A link to sign-up for new clinics.
- **Development only:** a separated "Developer sign-in" block with the persona quick-buttons
  (Doctor / Assistant / Admin / Patient preview) + the Pro/Basic/Therapy tenant tier switch, so dev
  velocity is unchanged. The real form is shown in dev too, so real auth is testable without leaving
  dev mode.

### Sign-up (`SignUpGate`)

- Self-serve clinic onboarding: clinic name, your name, email, password (≥ 8 chars). Calls
  `POST /api/v1/auth/register`, which creates the tenant + a founding **owner** user and signs the
  founder straight in (see [backend auth](../../backend/auth.md)).
- Maps backend errors to friendly copy (email already exists → 409; weak password → 422).
- The new founder is flagged for the first-run [onboarding](onboarding.md) tour.

## Visible Data

- Product name + language toggle.
- Pending local-capture notice when unsynced captures exist (on login + sign-up).
- Inline auth/validation errors.

## Main Components

- `UnauthShell`, `LandingPage`, `LoginGate`, `SignUpGate`, `PatientPreviewGate`

## States

- **Loading:** skeleton card while a stored-auth refresh runs.
- **Error:** inline copy for invalid credentials, failed persona login, or sign-up validation.
- **Success:** login/sign-up navigates to Active Session (owner/doctor) or Clinical Memory
  (assistant/admin); patient preview shows limited-access copy. A brand-new founder additionally
  sees the onboarding tour.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)
- [Onboarding](onboarding.md)

## Related APIs

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/dev-login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

## Known Gaps

- No password reset, phone/OTP credential, or tenant picker UI (email + password only for MVP).
- New tenants default to the Basic tier; tier is provisioned/upgraded out-of-band (read-only in app).
