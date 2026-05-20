# UX Navigation

## Route List

| Route | Screen | Notes |
| --- | --- | --- |
| `/` | Active Session, after login | Defaults to the active session workspace. |
| `/#active-session` | Active Session | Current session feed and capture dialogs. |
| `/#patients` | Patients | Patient-centered memory and unassigned sessions. Opening a session shows inline historical review. |
| `/#search` | Search | Local search across loaded sessions and captures. Opening a session shows inline historical review. |
| `/#capture` | Active Session | Legacy hash fallback. |
| `/#organize` | Patients | Legacy hash fallback. |

## Entry Points

- Unauthenticated users land on the login screen.
- After successful login, users are sent to Active Session.
- A stored auth profile is refreshed on app load before staff screens render.
- Development builds show persona login buttons.
- Production-style builds show email/password login.
- Patient-preview persona lands on a limited-access screen with only Logout.

## Navigation Paths

- Active Session to Patients or Search: top-left primary navigation.
- Patients or Search to Active Session: top-left primary navigation; selected historical review closes when returning to Active Session.
- Active Session to capture dialogs: bottom actions `Record audio`, `Take photo`, `Write note`.
- Patients/Search to capture destination choice: bottom actions first show a compact destination chooser with current/recent sessions or a new session.
- Active Session screen to a fresh draft context: `+ New session`, shown only when the active session has captures.
- Patients/Search to session review: select a session row; the review opens inline using the Active Session Workspace structure.

## Protected Behavior

- Staff-facing screens require an authenticated session.
- Staff API actions require backend roles `doctor` or `assistant`.
- Admin can access read-oriented staff/admin APIs but the current frontend still shows the staff shell; write operations may fail if attempted.
- Patient preview is blocked from staff screens by `PatientPreviewGate`.

## Fallback Behavior

- Unknown hashes fall back to Active Session.
- There is no dedicated not-found screen.
- If backend session loading fails after login, locally pending sessions remain visible and a toast says the backend is not reachable.
- If the URL has no hash, the app can restore the last staff screen from local workspace state after auth refresh.
- The last active session and selected historical review are restored when matching local or backend session data is available.
