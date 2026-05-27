# Generate Structured Session Report

## User Goal

Generate structured session output from the live draft while keeping the Active Session Workspace usable. Report, summary, and extracted-finding contracts already exist and evolve as captures are added.

## Entry Point

- Active Session `Generate Structured Report` button on a safely saved capturable session.

## Current Behavior

1. User captures one or more items.
2. Capture material must be safely saved before report generation is available.
3. User selects `Generate Structured Report`.
4. The session moves into assistant-style `Organizing` language.
5. The frontend shows subtle generation feedback while the live draft remains available.
7. The live draft remains available as a switchable report view while structured output is generating.
8. When memory is updated, Clinical Memory reflects the visit in Today, patient detail/timeline, or Needs input if a human decision is required.
9. Inline historical review shows the generated report, summary, extracted findings, and source captures when present.
10. If a user adds capture material after processing, the same session receives deterministic progressive report, summary, finding, and processing-status updates.

## System Behavior

- Structured report generation is available only when the session has saved capture material.
- The system organizes the session into summary, structured report, extracted findings, and patient-memory updates when available.
- The frontend renders clinic and patient information around the generated report body using session context.
- Patient information in rendered reports comes from the assigned patient record and identifiers, not generated body text.
- Previous generated summary/report/metadata snapshots may be retained for future recovery UI, but are not exposed as normal user tasks.
- A confident patient match can attach the session to an existing patient; uncertain matches go to Needs input.

## Involved Screens

- [Active Session](../screens/capture.md)
- [Clinical Memory](../screens/patients.md)
- [Search](../screens/search.md)
- [Session review](../screens/session-review.md)

## Important States

- Capturing
- Saved
- Organizing
- Needs your input
- Memory updated
- Saved on this device
- Missing patient information, shown as a human-decision item

## Related APIs

- `POST /api/v1/sessions/{session_id}/save`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`

## Known Gaps

- Structured report progress uses assistant-style organizing feedback plus inline draft evolution until final output is available.
