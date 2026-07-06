# UX Navigation

## Route List

| Route | Screen | Notes |
| --- | --- | --- |
| `/` | Active Session, after login | Defaults to the active session workspace. |
| `/#active-session` | Active Session | Current session feed and capture dialogs. |
| `/#patients` | Clinical Memory | Today, Patients, and Needs input tabs. Patient rows open patient detail/timeline; the main view does not nest sessions under patients. |
| `/#qa-inbox` | Q&A inbox (Pro) | **Pro only** — reached from a top-bar icon + pending-count badge beside Search (not the primary nav pill); hidden on Basic (capability `post_session_qa`). **Thread-centric**: one patient conversation per entry (chat bubbles + interleaved visit markers), threads awaiting approval first. Each pending question shows an AI-suggested reply the doctor can Send / edit / Dismiss (AES-402); `Mine`/`Clinic` scope, a routing-mode control, and **Re-route** to one of the patient's treating doctors. |
| `/#search` | Finder (overlay) | **Not a screen — a deep-link into the [finder](screens/finder.md) overlay.** Opens the app-wide finder over the Clinical-Memory workspace and normalizes the hash to `#patients`. The finder is the top-level retrieval surface (patients / today's visits / Pro lot recall); the old local-substring search screen was retired and survives only as the finder's offline fallback. |
| `/#settings` | Settings | Tenant preferences: app/transcription/report languages, patient-match strictness, patient sharing (include-brands), aftercare templates, the AI-usage card, plan/workspace rows, and admin-only role-permission presets. Reached from the account menu; has a Back action. See [Account](screens/account.md). |
| `/#profile` | Profile | Signed-in user + tenant (name, role, clinic), account actions (logout), and admin debug. Reached from the account menu; has a Back action. |
| `/#insights` | Insights (clinic analytics) | **Owner/admin only** — clinic activity, staff productivity, patient panel, and (Pro) treatment/product insights. Reached from the account menu (hidden for other roles); has a Back action. See [Insights](screens/insights.md). |
| `/#team` | Team (member management) | **Owner/admin only** — add clinic members (doctor/assistant/admin) with a temporary password (or add an existing Engram account across clinics, no password), and change a member's role/status. Reached from the account menu (hidden for other roles) or the onboarding "Invite your team" link; has a Back action. See [Team](screens/team.md). |
| `/#plan` | Plan (Basic vs Pro) | **Owner/admin only** — compare the two plans and switch tier (no payment yet). Reached from the account menu or the onboarding "See the Pro plan" link; has a Back action. See [Plan](screens/plan.md). |
| `/#switch-clinic` | Switch clinic | **Multi-clinic users only** — list the clinics the user belongs to and switch the active one (`POST /auth/switch-tenant`). Reached from the account menu (hidden for single-clinic users); has a Back action. |
| `/share/<token>` | Patient surface (public) | **Separate public area, not the staff shell.** A real path (not a hash), no login — the token is the capability. Read-only curated report + aftercare (AES-401); revocable/expirable, and an unknown/revoked/expired token shows one graceful "no longer available" screen (AES-403). Served by its own page bundle, without the clinic stylesheet. |
| `/qa/<token>` | Patient Q&A (public, Pro) | **Separate public area, not the staff shell.** A real path (not a hash), no login — the token is the capability. The patient asks questions and reads doctor-verified replies (AES-402); they see **only their own thread** — drafts, routing, and other patients are withheld (AES-403). Unknown/revoked tokens show the same graceful "no longer available" screen. Served by its own page bundle, without the clinic stylesheet. |

## Entry Points

- Unauthenticated users land on the **landing page** (what Engram is + CTAs). It is the first view
  of the bilingual (fa/en + RTL) unauthenticated shell, which switches between **landing → login**
  and **landing → sign-up**. See [the unauthenticated shell](screens/login.md).
- **Sign-up** self-serve onboards a clinic (`POST /auth/register`: tenant + founding `owner` user)
  and signs the founder straight in; **login** serves existing users.
- After successful auth, owners/doctors are sent to Active Session; assistants/admins to Clinical Memory.
- A stored auth profile is refreshed on app load before staff screens render.
- Development builds keep persona quick-login (in a separated block on the login view); the real
  email/password form is available in every build.
- A freshly signed-up founder additionally sees the first-run [onboarding](screens/onboarding.md) tour.
- Patient-preview persona lands on a limited-access screen with only Logout.
- **Any screen to the [finder](screens/finder.md):** the top-bar **magnifier** opens the app-wide
  finder overlay (mobile-first full-screen sheet); on desktop **⌘K / Ctrl-K** opens it from anywhere.
  It floats over the current screen — not a nav pill, not a route.

## Navigation Paths

- Active Session to Clinical Memory: compact top-left navigator in the mobile-first header.
- Clinical Memory to Active Session: compact top-left navigator in the mobile-first header; selected historical review closes when returning to Active Session.
- Active Session to capture dialogs: sticky bottom actions `Audio`, `Take photo`, `Write note`; Audio shows `Tap to record`.
- Clinical Memory/Search to capture destination choice: sticky bottom actions first show a compact destination chooser with current/recent sessions or a new session.
- Active Session screen to a fresh draft context: `+ New visit`, shown only when the active visit has captures. (In aesthetics chrome the encounter reads "visit"; see the vocabulary note in [capture](screens/capture.md).)
- Clinical Memory Patients tab to patient detail/timeline: select a patient row.
- Clinical Memory session cards to Active Session: select a Today, Needs input, or patient timeline session card. Active Session shows a `Back` action that returns to the originating Clinical Memory tab or patient timeline.
- Clinical Memory Needs input tab to focused decision surface: primary actions open resolvers such as assign patient, choose patient, review summary, or review storage. They do not primarily redirect to the active session page.
- Finder to a patient timeline / session review / lot-recall cohort: select a finder result; a patient row opens the patient's Clinical-Memory file, a visit opens inline session review, and a Pro lot query opens the exact-match recall cohort. Selecting any result closes the overlay.
- Any screen to account pages: the **account menu** (top-right avatar) opens with an identity header, then the personal actions **Profile** and **Settings**, then a labelled **Clinic** section grouping the owner/admin clinic-management pages **Insights** + **Team** + **Plan** (the section and its items are hidden for other roles), then **Switch clinic** (multi-clinic users only), **Replay guide** (re-opens the first-run tour), and **Logout**. Each page has a **Back** action returning to the previous staff screen. Account/utility pages (Settings, Profile, Insights, Team, Plan, Switch clinic) **hide the capture bar** — there's no capture context there.

### Back navigation (in-screen levels)

The app is a single hash-routed page: top-level screen switches use `history.replaceState`, so they
deliberately do **not** stack in history. In-screen levels opened *over* a screen — an open **patient
file** (Clinical Memory), a **smart-list drill-in** (Lists tab), a **historical visit review**, and
the **[finder](screens/finder.md) overlay** — each push their own history entry, so a
hardware/browser **Back** steps back one level (to the list, or closes the finder)
instead of exiting the whole area; their in-screen back controls behave identically. The shared
controller (`shared/lib/backStack.ts`) batches this so opening one level while another closes in the
same render nets to no history churn.

## Protected Behavior

- Staff-facing screens require an authenticated session.
- Staff API actions require backend roles `doctor` or `assistant`.
- Admin can access read-oriented staff/admin APIs but the current frontend still shows the staff shell; write operations may fail if attempted.
- Patient preview is blocked from staff screens by `PatientPreviewGate`.
- The public patient surface (`/share/<token>`) requires **no** auth — the token in the URL is the capability. It serves only the curated snapshot and returns a graceful "no longer available" screen when the token is unknown, revoked, or expired; raw clinic internals are never reachable from it (AES-403).
- The public patient Q&A (`/qa/<token>`) likewise requires **no** auth — the token is the capability. It serves only that patient's own questions + the doctor-verified replies; AI reply drafts, routing, and every other patient are never sent to it (AES-403). The Q&A inbox + all `patient-qa/*` staff APIs are gated on the Pro `post_session_qa` capability (403 on Basic).

## Fallback Behavior

- Unknown hashes fall back to Active Session.
- There is no dedicated not-found screen.
- If remote loading is unavailable after login, locally saved sessions remain visible and the UI uses calm saved-state copy such as `Offline · Captures are saved on this device`.
- **Restore-last-screen vs. explicit hash (rule):** an explicit location hash present at load **always
  wins** over restore-last-screen. The app restores the last staff screen from local workspace state
  (after auth refresh) **only when the load carried no hash**. Whether the initial URL had a hash is
  captured once at load, so a deep link is race-proof against the async workspace hydrate (this closed a
  historical flake where a full reload of `/#patients` randomly landed on Active visit).
- The last active session and selected historical review are restored when matching local or remote session data is available.
