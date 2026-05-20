# Login Screen

## Route

No route of its own. It renders before authenticated staff screens.

## Purpose

Authenticate a user and establish tenant context before showing staff screens.

## Primary Actions

- Development: choose Doctor, Assistant, Admin, or Patient preview persona.
- Production-style mode: enter email and password.
- Logout is available from patient-preview limited access.

## Visible Data

- Product name.
- Pending local capture warning when unsynced captures exist.
- Login errors.

## Main Components

- `LoginGate`
- `PatientPreviewGate`

## Loading State

- Skeleton card while stored auth refresh runs.

## Empty State

- None.

## Error State

- Inline copy for invalid credentials or failed persona login.

## Success State

- Successful login navigates to Active Session.
- Patient preview shows limited-access copy instead of staff tools.

## Related Workflows

- [Capture a session](../workflows/capture-session.md)

## Related APIs

- `POST /api/v1/auth/dev-login`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

## Known Gaps

- No password reset or tenant picker UI.
