# Organize Screen

## Route

- `/#organize`

## Purpose

Show loaded sessions grouped by review status so staff can return to draft, unassigned, needs-review, verified, processing, or failed work.

## Primary Actions

- Search sessions locally.
- Open a session review dialog for processed sessions.
- Open draft sessions directly in Capture.
- Use bottom capture actions to start a new capture from anywhere in the shell.

## Visible Data

- Session buckets:
  - Drafts
  - Unassigned
  - Needs review
  - Verified
  - Processing
  - Failed, only when failures exist
- Session row title, full summary, patient/review label, assignment source, and status badge.

## Main Components

- `OrganizeHome`
- `SessionRow`
- `SessionStatusBadge`

## Loading State

- No full-screen loading state after shell render. If backend load fails, local pending sessions remain and a toast explains the backend is unreachable.

## Empty State

- Each bucket has compact empty copy.

## Error State

- Backend load failure falls back to local pending sessions and shows a toast.

## Success State

- Sessions appear in visually differentiated status buckets.
- Search filters the loaded session list.

## Related Workflows

- [Save and organize a session](../workflows/save-and-organize-session.md)
- [Review and assign patients](../workflows/review-and-assign-patients.md)

## Related APIs

- `GET /api/v1/sessions`

## Known Gaps

- Search is client-side over the currently loaded sessions only.
- No route-specific not-found or empty global state beyond per-bucket messages.
