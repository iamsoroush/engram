# Frontend Authentication And Login

## Summary

The frontend owns the login experience but not authorization. The backend issues and validates tokens. Frontend route hiding is only a usability layer.

## Unauthenticated shell

When no valid access token is available, `UnauthShell` renders before the capture shell as a
three-view state machine — **landing → login** / **landing → sign-up** — bilingual fa/en + RTL (see
[i18n](#bilingual--rtl-app-language) below). The authenticated app is also fully bilingual — full
language model in [i18n.md](i18n.md).

- **Landing** (`LandingPage`): what Engram is + CTAs to sign up or log in.
- **Sign-up** (`SignUpGate`): clinic name, your name, email, password. Calls `POST /api/v1/auth/register`,
  which creates the tenant + a founding `owner` user and returns the same response shape as login.
- **Login** (`LoginGate`): email + password via `POST /api/v1/auth/login`.

Development mode:

- The login view also shows a separated "Developer sign-in" block: quick persona buttons for
  `doctor`, `assistant`, `admin`, `patient-preview` (+ a Pro/Basic/Therapy tier switch) via
  `POST /api/v1/auth/dev-login`. The real email/password form is shown in every build, so real auth
  is testable without leaving dev mode.
- Staff personas enter the capture-first app; patient preview gets the access-limited screen and no
  staff capture/review permissions.

Production mode:

- Only the real landing/login/sign-up forms (no persona block). Same response shape throughout.

## Bilingual + RTL (app language)

The public surfaces use a lightweight `shared/i18n` seam (fa/en catalog + `t()` + `dir`/`lang` on
`<html>`). The UI language is persisted in `localStorage`, defaults from the browser (Persian
fallback, Iran-first), and is toggleable. `UnauthShell` resets `<html>` to LTR/English on unmount.
On sign-up the chosen language is sent as the new tenant's `app_language`.

The authenticated app picks language up from that tenant `app_language` via `AppLangProvider` (the
authed counterpart to this public seam). The two surfaces and the chrome-vs-content rule are
documented in full in [i18n.md](i18n.md).

## First-run onboarding

A brand-new founder (set at registration) is shown a one-time guided "capture your first visit"
overlay over the live capture screen; see [onboarding screen](../ux/screens/onboarding.md).

## Token Handling

Frontend behavior:

- Access token is kept in memory; the **refresh token + profile are persisted to `localStorage`**
  (`persistAuthProfile`), so a full page refresh rehydrates the session by re-issuing an access token
  via `/auth/refresh`. Without this, prod users are logged out on every refresh.
- Attach `Authorization: Bearer <token>` to API requests.
- On `401`, attempt one refresh and retry once.
- If refresh fails, clear auth state and return to login.

> **Alpha trade-off:** the refresh token in `localStorage` is an XSS exposure. The hardening path is a
> Secure **HTTP-only cookie** for the refresh token (backend sets it; frontend stops storing it). Tracked
> in [production-alpha-tradeoffs.md](../production-alpha-tradeoffs.md).

## Tenant Context

Every authenticated frontend session has an active tenant. In v2 development there is one seeded tenant, but the client should model tenant context explicitly so future multi-tenant switching does not require reworking all API calls.

Pending captures should not sync until the active tenant is known.

## Logout

Logout should:

- Call backend logout when reachable.
- Clear token and profile state.
- Keep IndexedDB pending captures.
- Stop outbox processing.
- Return to login.

Pending captures are clinical material. Do not delete them automatically on logout.

## Copy And UX

Staff users should land on `Capture` after login. The product should not open on patient search, dashboards, worklists, or admin screens.

Generated organization should be labeled carefully. `Organized` can mean backend/AI organized, while `Verified` or `Reviewed` means doctor/assistant accepted it.
