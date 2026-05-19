# UX Navigation

## Route List

| Route | Screen | Notes |
| --- | --- | --- |
| `/` | Capture, after login | Defaults to capture unless the hash is `#organize`. |
| `/#capture` | Capture | Current session feed and capture dialogs. |
| `/#organize` | Organize | Session buckets. Opening a session shows an in-page dialog, not a new route. |

## Entry Points

- Unauthenticated users land on the login screen.
- After successful login, users are sent to Capture.
- A stored auth profile is refreshed on app load before staff screens render.
- Development builds show persona login buttons.
- Production-style builds show email/password login.
- Patient-preview persona lands on a limited-access screen with only Logout.

## Navigation Paths

- Capture to Organize: top nav `Organize`.
- Organize to Capture: top nav `Capture`; selected session dialog closes when returning to Capture.
- Any staff screen to capture dialogs: bottom actions `Record audio`, `Take photo`, `Write note`.
- Capture screen to a fresh draft context: `+ New session`, shown only when the active session has captures.
- Organize to session review: select a session row; the review opens in a dialog over Organize.

## Protected Behavior

- Staff-facing screens require an authenticated session.
- Staff API actions require backend roles `doctor` or `assistant`.
- Admin can access read-oriented staff/admin APIs but the current frontend still shows the staff shell; write operations may fail if attempted.
- Patient preview is blocked from Capture and Organize by `PatientPreviewGate`.

## Fallback Behavior

- Unknown hashes fall back to Capture.
- There is no dedicated not-found screen.
- If backend session loading fails after login, locally pending sessions remain visible and a toast says the backend is not reachable.
