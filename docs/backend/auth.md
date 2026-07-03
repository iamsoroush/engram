# Backend Authentication

## Summary

Authentication is owned by the backend. Nginx only handles TLS, static file serving, reverse proxying, and security headers. The frontend displays login UI and attaches tokens to API requests, but it does not make authorization decisions.

Development must stay low-friction, so local environments use a dev login endpoint with seeded personas.

## Modes

Backend auth mode is controlled by:

```sh
BACKEND_AUTH_MODE=dev | production
```

Development mode:

- Enables `POST /api/v1/auth/dev-login`.
- Seeds one default tenant, sample staff users, and sample patients.
- Requires no password.
- Returns the same token/profile shape as production login.

Production mode:

- Disables `dev-login`.
- Enables real `login`, `refresh`, `logout`, and `me` behavior.
- Requires strong secrets and secure refresh-token handling.

`register` (clinic sign-up) is **not** mode-gated — it is the real credential path and is available
in both modes (in dev it coexists with `dev-login`, which stays the low-friction default).

## Registration (clinic sign-up)

Endpoint:

```text
POST /api/v1/auth/register
```

Self-serve onboarding of a new clinic. One call atomically creates the **tenant** (the clinic) and
its **founding user**, links them with an `owner` membership, and returns a normal authenticated
session (same shape as `login`), so the founder is signed straight in.

Request:

```json
{
  "clinicName": "Glow Aesthetics",
  "fullName": "Dr. Sara Noori",
  "email": "sara@glow.example",
  "password": "at-least-8-chars",
  "appLanguage": "fa"
}
```

Behavior:

- Email is normalized (trimmed + lowercased) and must be unique across users (`409` on conflict).
- Password must be ≥ 8 characters (schema-level `422`, with a service-level `400` guard).
- A unique tenant `slug` is derived from the clinic name (non-latin names fall back to `clinic-N`).
- New tenant defaults: `vertical = aesthetics`, `tier = basic` (provisioned/upgraded out-of-band,
  read-only to the clinic), `app_language` = the `appLanguage` the founder signed up in (Persian
  when omitted, Iran-first).
- The founder's membership role is `owner` (see Authorization).

## Token Contract

Access tokens are JWTs validated by FastAPI dependencies.

Required claims:

- `sub`: user ID.
- `tenant_id`: active tenant ID.
- `roles`: roles for the active tenant.
- `token_type`: `access`.
- `exp`, `iat`, `jti`.

Refresh tokens:

- Should be long-lived opaque tokens or JWTs with `token_type=refresh`.
- Prefer secure HTTP-only cookies for production.
- If local development temporarily stores refresh tokens in browser storage, document it as dev-only.

## Dev Login

Endpoint:

```text
POST /api/v1/auth/dev-login
```

Request:

```json
{
  "persona": "doctor",
  "tier": "pro"
}
```

Supported personas:

- `doctor`
- `assistant`
- `admin`
- `therapist-b` (a second therapist, for demonstrating the therapy vertical's federated caseloads)
- `patient-preview`

`tier` (optional, default `pro`) selects which seeded dev tenant the session is issued for:
`pro` / `basic` pick the aesthetics Pro/Basic demo clinics; `therapy` picks the single-plan
therapy demo tenant (`vertical = therapy`).

Response:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "user": {
    "id": "user_...",
    "displayName": "Dr. Demo",
    "persona": "doctor"
  },
  "tenant": {
    "id": "tenant_demo",
    "name": "Engram Demo Clinic"
  },
  "memberships": [
    {
      "tenantId": "tenant_demo",
      "role": "doctor"
    }
  ]
}
```

The frontend should render quick persona buttons in dev mode. This removes password friction while exercising real authenticated API calls.

## Authorization

Every tenant-owned query must be scoped by the authenticated `tenant_id`.

Staff permissions:

- `owner`: the clinic's founding user (from sign-up). A full superset — everything `doctor` can do
  (capture/review/etc.) **plus** tenant/user administration. Additive role: it passes every staff and
  admin gate and is always `full` in the multi-seat permission model. `doctor`/`assistant`/`admin`
  keep their exact prior semantics (notably, `admin` still cannot capture).
- `doctor`: capture, create patients, assign patients, review, retry processing, verify, reopen.
- `assistant`: same as doctor for v2 unless later restricted.
- `admin`: tenant/user administration plus read access to operational data.
- `patient`: future patient portal persona only; no staff capture/review permissions.

Authorization must be enforced in backend dependencies or service-layer guards, not by frontend route hiding.

`get_current_principal` derives roles from the **live** active membership for `(user, tenant)` on every
request — not from the token's `roles` claim. So disabling a member or changing their role takes effect
on their **next request** (not only at access-token expiry); a request with no active membership is `403`.

## Member management

Owner/admin-only endpoints (`tenant_admin_required` = roles `owner` or `admin`) to manage clinic
staff after sign-up. MVP model: the owner creates the account directly with a temporary password they
hand over — there is no email/SMS invite delivery yet.

- `GET /api/v1/clinic/team` — list all non-patient members (any status): name, email, role, status.
- `POST /api/v1/clinic/team` — add a member: `fullName`, `email`, `role` (doctor | assistant | admin),
  and `password`. If the email is **new**, `password` (≥ 8) is required and a user is created. If the
  email **already belongs to a Engram user**, `password` is ignored and that account is added to this
  clinic (cross-clinic membership); a `409` is returned only if they are already a member here. The
  response includes `created` (false when an existing account was attached).
- `PATCH /api/v1/clinic/team/{userId}` — change `role` and/or `status` (active | disabled). The
  **owner** membership and the **caller's own** membership are protected (`403` / `400`).

`PATCH /api/v1/clinic/plan` — switch the clinic plan/tier (`{ "tier": "basic" | "pro" }`), owner/admin
only, no payment. Returns the updated tenant profile; capabilities follow the new tier.

(`GET /api/v1/clinic/members` stays separate — the active-staff line-up picker for the worklist.)

## Multi-clinic switch

A user can belong to more than one clinic (the cross-clinic member case above). Auth responses list
**all** their active memberships, each with `tenantName`, so the client can offer a clinic switcher.

`POST /api/v1/auth/switch-tenant` — `{ "tenantId": "…" }`, authenticated. Re-issues a session
(tokens + profile) for another clinic the user actively belongs to; `403` if they don't, `400` on a
bad id. Login still defaults to the user's first active membership.

## Frontend Contract

The frontend:

- Shows login before the capture shell when unauthenticated.
- Uses dev persona buttons when backend advertises dev auth mode.
- Stores access token in memory where practical.
- Sends `Authorization: Bearer <token>` on API calls.
- On `401`, attempts one refresh and retries the original request once.
- Returns to login if refresh fails.
- Does not sync pending IndexedDB captures until a user and tenant are authenticated.

Pending local captures survive logout. After a new login, the frontend must confirm or infer the active tenant before syncing old pending captures.

## Security Notes

- JWT secrets must not be committed.
- Production cookies must use `HttpOnly`, `Secure`, and `SameSite=Lax` or stricter.
- Tokens must include tenant context.
- Audit login, logout, token refresh failures, and authorization failures.
- Nginx should not bypass backend auth for any `/api/v1` route.
