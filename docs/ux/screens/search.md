# Search Screen

## Route

- `/#search`

## Purpose

Global retrieval surface for clinical memory. Phase 1.1 implements this as frontend-only local search over sessions and captures already loaded in the app.

## Primary Actions

- Search loaded sessions and captures.
- Open session review from a result.
- Use persistent bottom capture actions from anywhere in the shell.

## Visible Data

- Matching session cards.
- Patient or review context.
- Session status badges.

## Known Gaps

- Search is currently local to loaded frontend session data.
- Backend global search across patients, sessions, captures, and extracted findings is future migration work.
