# Frontend Authentication And Login

## Summary

The frontend owns the login experience but not authorization. The backend issues and validates tokens. Frontend route hiding is only a usability layer.

## Login Entry

When no valid access token is available, show a login screen before the capture shell.

Development mode:

- Show quick persona buttons for `doctor`, `assistant`, `admin`, and `patient-preview`.
- Call `POST /api/v1/auth/dev-login`.
- Store returned user, tenant, memberships, and token state.
- Staff personas enter the capture-first app.
- Patient preview must enter a separate placeholder patient experience or show an access-limited state; it must not receive staff capture/review permissions.

Production mode:

- Show a normal login form.
- Call `POST /api/v1/auth/login`.
- Use the same response shape as dev login.

## Token Handling

Frontend behavior:

- Keep access token in memory where practical.
- Prefer refresh token in a secure HTTP-only cookie.
- Attach `Authorization: Bearer <token>` to API requests.
- On `401`, attempt one refresh and retry once.
- If refresh fails, clear auth state and return to login.

Dev-only fallback:

- Temporary browser storage for refresh tokens is acceptable only if clearly marked as development-only.

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

Generated organization should be labeled carefully. `Organized` can mean backend/fake organized, while `Verified` or `Reviewed` means doctor/assistant accepted it.
