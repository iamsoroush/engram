# UX Navigation

## Route List

| Route | Screen | Notes |
| --- | --- | --- |
| `/` | Active Session, after login | Defaults to the active session workspace. |
| `/#active-session` | Active Session | Current session feed and capture dialogs. |
| `/#patients` | Clinical Memory | Today, Patients, and Needs input tabs. Patient rows open patient detail/timeline; the main view does not nest sessions under patients. |
| `/#search` | Search | Local search across loaded sessions and captures. Opening a session shows inline historical review. |
| `/#settings` | Settings | Tenant preferences: transcription/report language, patient-match strictness, and plan/tier (read-only). Reached from the account menu; has a Back action. |
| `/#profile` | Profile | Signed-in user + tenant (name, role, clinic), account actions (logout), and admin debug. Reached from the account menu; has a Back action. |

## Entry Points

- Unauthenticated users land on the login screen.
- After successful login, users are sent to Active Session.
- A stored auth profile is refreshed on app load before staff screens render.
- Development builds show persona login buttons.
- Production-style builds show email/password login.
- Patient-preview persona lands on a limited-access screen with only Logout.

## Navigation Paths

- Active Session to Clinical Memory or Search: compact top-left navigator in the mobile-first header.
- Clinical Memory or Search to Active Session: compact top-left navigator in the mobile-first header; selected historical review closes when returning to Active Session.
- Active Session to capture dialogs: sticky bottom actions `Audio`, `Take photo`, `Write note`; Audio shows `Tap to record`.
- Clinical Memory/Search to capture destination choice: sticky bottom actions first show a compact destination chooser with current/recent sessions or a new session.
- Active Session screen to a fresh draft context: `+ New session`, shown only when the active session has captures.
- Clinical Memory Patients tab to patient detail/timeline: select a patient row.
- Clinical Memory session cards to Active Session: select a Today, Needs input, or patient timeline session card. Active Session shows a `Back` action that returns to the originating Clinical Memory tab or patient timeline.
- Clinical Memory Needs input tab to focused decision surface: primary actions open resolvers such as assign patient, choose patient, review summary, or review storage. They do not primarily redirect to the active session page.
- Search to session review: select a session row; the review opens inline using the Active Session Workspace structure.
- Any screen to Settings or Profile: the **account menu** (top-right avatar) offers two actions — **Settings** and **Profile** — that navigate to dedicated pages (not inline controls). Each page has a **Back** action returning to the previous staff screen. Logout also lives in the account menu.

## Protected Behavior

- Staff-facing screens require an authenticated session.
- Staff API actions require backend roles `doctor` or `assistant`.
- Admin can access read-oriented staff/admin APIs but the current frontend still shows the staff shell; write operations may fail if attempted.
- Patient preview is blocked from staff screens by `PatientPreviewGate`.

## Fallback Behavior

- Unknown hashes fall back to Active Session.
- There is no dedicated not-found screen.
- If remote loading is unavailable after login, locally saved sessions remain visible and the UI uses calm saved-state copy such as `Offline · Captures are saved on this device`.
- If the URL has no hash, the app can restore the last staff screen from local workspace state after auth refresh.
- The last active session and selected historical review are restored when matching local or remote session data is available.
