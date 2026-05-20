# Patients Screen

## Route

- `/#patients`
- `/#organize`, legacy fallback

## Purpose

Primary long-term memory surface for patient-linked session history and unassigned sessions. This screen is the main longitudinal memory view.

## Primary Actions

- Review patient-linked sessions grouped by patient context.
- Review unassigned sessions.
- Open session review without leaving the Patients surface.
- Continue a session in the Active Session workspace.
- Assign or reassign a patient inline.
- Verify a session from its card.
- Use persistent bottom capture actions from anywhere in the shell.

## Visible Data

- Patients section.
- Unassigned Sessions section.
- Patient cards with patient name, concise mocked AI history summary, status badges, and session cards.
- Session cards with timestamp, status badge, short summary, and quick actions.
- State appears as lightweight badges only: `Capturing`, `Processing`, `Needs review`, `Unassigned`, `Verified`, or `Failed`.
- Needs-review behavior appears as badges/indicators only.

## Quick Actions

- `Open session` opens inline historical review.
- `Continue` returns the session to the Active Session workspace as the current capture destination.
- `Assign patient` expands a compact inline name/national-ID form on the card.
- `Verify` marks the session verified without hiding it or requiring a separate queue.

## Known Gaps

- Patient cards are currently derived from loaded sessions rather than a dedicated patient timeline API.
- Patient history summaries are mocked from loaded session summaries until backend patient memory support lands.
- Inline assignment currently creates a patient when no exact loaded match is found; richer duplicate review is future work.
