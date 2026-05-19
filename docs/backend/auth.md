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
  "persona": "doctor"
}
```

Supported personas:

- `doctor`
- `assistant`
- `admin`
- `patient-preview`

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
    "name": "AesMem Demo Clinic"
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

- `doctor`: capture, create patients, assign patients, review, retry processing, verify, reopen.
- `assistant`: same as doctor for v2 unless later restricted.
- `admin`: tenant/user administration plus read access to operational data.
- `patient`: future patient portal persona only; no staff capture/review permissions.

Authorization must be enforced in backend dependencies or service-layer guards, not by frontend route hiding.

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
