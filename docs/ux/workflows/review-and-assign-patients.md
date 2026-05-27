# Clinical Memory Workflow

## User Goal

Keep capturing with almost no friction while AesMem quietly saves, organizes, summarizes, and asks for help only when human judgment is required.

## Entry Points

- App navigation opens `Clinical Memory`.
- The route remains `/#patients` for compatibility.
- The default tab is `Today`.
- Patient search or a patient row opens patient detail and timeline.
- A Needs input item opens the smallest decision surface needed to resolve it.

## Main Flow

1. User opens Clinical Memory.
2. `Today` shows the current visit, recent memory updates, and a preview of any human-decision items.
3. User searches or opens `Patients` to find a patient memory row.
4. Patient rows show natural memory summaries and one primary action. They do not show nested session lists.
5. User opens a patient to view the patient assistant summary and timeline.
6. Timeline sessions are grouped by time, such as `Today`, `Earlier this week`, and `Earlier`.
7. Each session is summarized in human language and has one primary action.
8. `Needs input` contains only decisions the user must make.
9. The persistent capture bar stays visible so the user always understands where captures will go and whether they are safely saved.

## Involved Screens

- [Clinical Memory](../screens/patients.md)
- [Session review](../screens/session-review.md)
- [Search](../screens/search.md)

## Related Shared Rules

- Assistant-state, Needs input, and offline behavior: [UX states](../states.md)
- Clinical Memory layout and patient-card summary fallback: [Clinical Memory screen](../screens/patients.md)
