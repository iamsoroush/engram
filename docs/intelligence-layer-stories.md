# Intelligence Layer — v1 User Stories

Maps the [contract](intelligence-layer.md) to vertical, demoable slices. Conventions:

- Each story has an **id**, **type** (`design` | `impl` | `verify`), **layers** it touches,
  the **story**, **acceptance criteria**, and **deps**.
- **Design stories** produce/refresh UX docs (`docs/ux/**`) and the visual design **before**
  their implementation stories run — this is the "dedicated re-design" work.
- Build order: **A → B (parallel) → C → then D/E/F/G** as capacity allows.

---

## Status & how to continue (handoff — 2026-06-03)

The intelligence layer was built and **verified against the live app/DB with real audio**.
Start here: read [intelligence-layer.md](intelligence-layer.md) (the contract — design source of
truth), then the `DONE`/`Implemented` markers in this file, then
[ux/redesign-capture-surface.md](ux/redesign-capture-surface.md) (visual design). Key decisions
in [technical-decisions.md](technical-decisions.md).

**Done & verified (all green):**

- **C1–C4 reassignment** — AI emits `intents` (transcript required, intents nullable); the gate
  in `ai_jobs.complete_worker_job` applies first-identity, overrides only on `basis="explicit"`,
  and surfaces `suggested_reassignment` on an implicit mention of an already-assigned visit; C3
  chips render (`Patient assigned` / `New patient + assigned` / `Suggested: reassign · Apply/Dismiss`).
- **H2 near-match** — a single high-confidence fuzzy `possible_match` → actionable suggestion
  (`near_match_suggestion`). H1 mostly already covered by `PERSIAN_LATIN_TRANSLITERATION`.
- **D out-of-context** — `out_of_context_marker` + dimmed capture card + chip + "Mark relevant" (local).
- **A5 sequential per-session processing** — `is_capture_chain_head` / `dispatch_next_session_capture`.
- **Retry tweak** — `requeue_failed_session_captures` (failed siblings retry when one succeeds).
- **A1 tier flag** — `tenants.tier` (migration `20260603120000`) gates AI auto-assignment to **Pro**.
- **Unassign** + **patient edit** (partial-PATCH "Edit details" form on the patient detail screen).
- **E — Pro Live report** — the report regenerates by an AI job each time a session's capture
  chain drains (also on capture delete / "Mark relevant"); `report_contribution` effect +
  `✓ Added to report` chip; out-of-context captures excluded ("M set aside"); persisted "Mark
  relevant"; manual **Generate removed** (`/save` retained for retry, Pro-gated). Frontend tabs
  renamed **Captures / Live report** (lands **B2**), Pro/Basic tier badge, calm `Updating…`
  state, Pro synthesized vs Basic chronological document. Verified live (real audio fixture →
  auto report job → `report_contribution_summary={included,set_aside}`) + screenshots in
  `apps/frontend/test-results/redesign/`.

**Remaining (prioritized):**

1. ~~**A0**~~ — **DONE (2026-06-05).** `tenant.vertical` + `session.attributes` scaffolding, the
   `encounter_label` vertical→label mapping, and `vertical`/`encounterLabel` on the `TenantProfile`
   (Patient is universal; `Session` is the clinic `Encounter`, no rename). See the A0 story below.
2. ~~**H3 / H4**~~ — **DONE (2026-06-05).** Configurable match strictness
   (`tenants.match_strictness` strict/balanced/lenient; `fuzzy_auto_apply_candidate` gates the
   single-candidate fuzzy auto-apply line) **+** the partial-match resolution & disambiguation
   surface (matched-vs-spoken identity + Keep match / Create new instead / Choose another / Edit
   details on the capture card). See the H3/H4 stories below. Remaining hook: the strictness control
   currently lives in the Shell user menu and should move to the **B4** Settings page.
3. ~~**B4**~~ — **DONE (2026-06-05).** Account dropdown redesigned → dedicated **Settings** +
   **Profile** pages; the language + match-strictness controls now live on the Settings page (the
   H3 hook is closed). See the B4 story below.
4. ~~**B1/B3 UI**~~ — **DONE (2026-06-05).** A shared `PatientForm`
   (`features/patient/PatientForm.tsx`) now powers **edit** (patient detail, pre-filled from
   `getPatient` incl. sex/notes), **create** (resolver), and **verify** (AI-created panel). The
   patient model already had sex/notes; `getPatient`/`updatePatient`/`createPatient` now read/send
   all fields. See Epic F below.
5. ~~**A4**~~ — **DONE (2026-06-05).** Inline **Edit** on the capture card's transcript/caption
   block (textarea in place; reuses the source-sheet edit handlers; edited-vs-AI attribution;
   feeds the live report). Note decorated-text edit deferred (user-authored). See the A4 story.
6. ~~**G**~~ — **DONE (2026-06-06).** Added the remaining durability guards: a **storage-full
   hard-stop** (`StorageGuardDialog`), a **long-recording warning** banner in the audio recorder,
   and an **export escape hatch** (dependency-free ZIP of queued captures), on top of the existing
   `persist()` + 85% warning + silent self-healing AI-out. See Epic G below.
7. **Basic-tier polish** — Basic is now API-verified (transcribe-only, no report job / no AI
   assignment) and toggle-testable via dev-login `tier: basic`; remaining: a live screenshot of
   the Basic chronological Live-report UI, and real captioning/text-decoration enrichment (Pro)
   to replace the mock placeholders.

**Dev environment (docker-compose):** frontend `localhost:5183` (Vite; proxies `/api/v1` → the
backend container); backend host **8010** → container 8000 (uvicorn `--reload` picks up backend
edits); postgres `aesmem-postgres-1` (`aesmem/aesmem`, host 5442); minio `aesmem-minio-1`
(`aesmem-dev`/`aesmem-dev-secret`, host 9010, bucket `aesmem-captures`); redis. **Gotchas:** the
ai-engine Celery worker has **no autoreload** — `docker restart aesmem-ai-engine-1` after editing
`apps/ai_engine`; new alembic migrations only run on backend container start, so run
`docker exec aesmem-backend-1 sh -c "cd /app && alembic upgrade head"` after adding one.
Transcription gateway is configured (model `gemini-3.1-flash-lite`). Dev auth:
`POST /api/v1/auth/dev-login {"persona":"doctor"}`.

**Tests / verification:** backend `cd apps/backend && .venv/bin/python -m unittest discover -s
tests -p "test_*.py"` (57 green); ai-engine (20 green); frontend `cd apps/frontend && npx tsc --noEmit`. Visual checks
were done with throwaway Playwright specs under `apps/frontend/tests/visual/` that drive
`localhost:5183` and screenshot to `test-results/redesign/` (delete the spec afterward). Seeded
test patients: سروش معاصد, ثریا قاسمی, سارا نظری (national_id `0012345678`), نگار/بابک احمدی, Sara N.

---

## Epic A — Foundations (cross-cutting)

### A0 — Entity model (`design`+`impl`; backend, docs) — **DONE (2026-06-05)**
**Implemented:** `tenants.vertical` (String(40), default `clinic`) + `sessions.attributes` (JSONB,
reserved per-vertical extension point), migration `20260605130000` (run live). `Tenant.vertical` +
`Session.attributes` on the models. New [`services/verticals.py`](../apps/backend/app/services/verticals.py):
`encounter_label(vertical)` (clinic→"Session", radiology→"Study", pathology→"Case") + `normalize_vertical`
(unknown→clinic). `TenantProfile` now carries **`vertical`** + **`encounterLabel`** (read-only; all 3
builders wired). Frontend: `AuthTenant.vertical`/`encounterLabel` (flow through the direct auth cast) +
a read-only **Workspace** row on the Settings page. No `Session → Encounter` rename (deferred to the
second vertical); the apply layer was already vertical-neutral. Docs: architecture.md "Entity Model
(verticals)" + a technical-decisions.md entry. 59 backend tests (+2 `test_verticals.py`); tsc clean;
live profile verified (`vertical=clinic, encounterLabel=Session`).

As the platform, I want Patient first-class and the work-unit generic so we can expand to
new verticals without a schema fork.
- **AC:** Add `tenant.vertical` (`clinic` for now). Today's `Session` is documented as the
  clinic **Encounter**; reserve an `attributes` JSONB extension point on it. `Patient`
  stays the universal assignment target. No `Session → Encounter` rename in v1.
- **AC:** Presentation label for the work-unit comes from vertical ("Session" today), not
  hardcoded in core/apply logic.
- **Deps:** none.

### A1 — Tier flag + tier-aware pipeline (`impl`; backend, AI, frontend)
- **AC:** `tenant.tier` (`basic`|`pro`), exposed in the session/tenant payload the frontend
  already loads. Pipeline gates per §3: Basic = transcription + out-of-context; Pro adds
  assignment intent, captions, decoration, report refinement.
- **Deps:** A0.
- **DONE (assignment gate):** `tenants.tier` column (migration `20260603120000`, default
  `pro`) + `Tenant.tier`; `tenant_tier()` gates the whole AI-assignment block in
  `complete_worker_job` to **Pro** (Basic = manual assignment; out-of-context still flagged
  for both tiers); dev tenant seeded `pro`; tier surfaced in the auth `TenantProfile`. 36
  backend tests green. Captions/decoration/report tier-gating land with E; a frontend "Pro"
  badge is optional (assignment chips already only appear when the Pro backend produces them).

### A2 — Capture-intelligence output schema (`impl`; AI)
- **AC:** Emit `2026-06-03.capture-intelligence.v1` (transcript **required**, intents
  **nullable**). Adopt the gateway's structured-output schema + a thin normalization layer;
  a malformed/absent `intents` still yields a usable transcript (no hard failure).
- **Deps:** A1.

### A3 — Capture `effects` model (`impl`; backend + frontend)
- **AC:** Generalize `patient_action_badges` → a per-capture `effects` list (§6). Backend
  writes it; frontend has a render contract for chips. Empty list renders nothing. A
  capture may carry multiple effects (e.g. `created_and_assigned`).
- **Deps:** A0.

### A4 — Per-capture generated-text edit (`impl`; backend + frontend) — **DONE (2026-06-05)**
**Implemented (frontend; reuses the existing edit handlers):** an inline **Edit** affordance on
the capture card's generated-text block (`CaptureGeneratedText` in `CaptureScreen.tsx`) — the
transcript (audio) / caption (photo) turns into a textarea + **Save/Cancel** in place, no longer
requiring the source-preview sheet. Save calls the same `onUpdateCaptureTranscript`/`Caption`
handlers (`editCaptureSourceText`, threaded `CaptureScreen → LiveDraftReport →
LiveDraftCaptureItem`), which write `source: "staff_edit"` + editor attribution and mark the report
stale so the edit **feeds the live report**; the heading flips "Generated by AI" → "Edited by …".
RTL-aware textarea. **Scope:** transcript + caption (the AI blocks with a backend field); note
**decorated text** is left as-is for now (user-authored; no edit field). tsc clean; screenshots
`test-results/redesign/a4-edit-{affordance,editor}.png`.

As staff, I want to fix a transcript / caption / decorated text inline, so the record is
right without leaving the capture.
- **AC:** Each generated text block has an **Edit** affordance; saved edits show edited-vs-AI
  attribution and feed the live report. (This is editing the capture's text — NOT the
  deferred report-`edit` intent.)
- **Deps:** A3, B1.

### A5 — Sequential per-session capture processing (`impl`; backend/worker) — **DONE**
As the system, I want a session's captures processed strictly **in capture order**, because
the assignment gate and the report depend on the cumulative session state — parallel
processing races (e.g. capture 2 applying before capture 1's assignment commits → wrong
gate branch, or a name matched against a not-yet-assigned session).
- **AC:** Capture-processing jobs for the **same** session run one-at-a-time in `captured_at`
  order (per-session ordering key / single-flight lock / chained dispatch); different
  sessions still process in parallel.
- **AC:** A late or retried capture re-evaluates against the latest committed session state.
- **Deps:** A2 / C2. *(Surfaced during C4 real-audio testing.)*
- **Implemented:** `is_capture_chain_head` + `dispatch_next_session_capture` in `ai_jobs.py`,
  ordered by `captured_at`. Upload dispatches only the chain head; completion dispatches the
  next; both recovery loops are gated by the head check (so the 60s recovery self-heals a
  stalled chain). Verified by a pure-helper unit test + a live DB smoke test.

---

## Epic B — Design (the re-design stories)

### B1 — Capture card + effect chips (`design`; → `screens/capture.md`, `states.md`)
Re-design the capture card to show each capture's effect and its reversibility.
- **AC:** States/mocks for: assignment/reassignment chip (+ Undo), "added to report",
  out-of-context (dimmed + "actually relevant"), and calm processing/offline states.
- **AC:** Undo affordance + copy defined; chip prominence scales with risk×(1−confidence).
- **Deps:** A3 contract.

### B2 — Captures / Live report (`design`; → `screens/capture.md`, `workflows/save-session.md`)
- **AC:** Tabs renamed **Captures / Live report**; **Generate button removed**; Live report
  always present. Basic = clean chronological render; Pro = synthesized, with a quiet
  "updating for captures X, Y" state. "Verify" re-cast as a calm confirm, not a gate.
- **Deps:** A1.

### B3 — Patient management IA (`design`; → `screens/patients.md`, `workflows/review-and-assign-patients.md`, `navigation.md`)
- **AC:** Assignment resolver gains **Unassign / Keep unassigned**; a dedicated **patient
  detail** screen for full view/edit (name, national_id via identifiers, phone, DOB,
  aliases, notes, visit history); one shared **create** flow with multiple entry points
  (resolver, Patients tab, AI auto-create lands flagged "verify").
- **Deps:** none.

### B4 — Account menu → Settings & Profile pages (`design`+`impl`; design, frontend, backend) — **DONE (2026-06-05)**
**Design:** [ux/screens/account.md](ux/screens/account.md) + routes/nav in
[ux/navigation.md](ux/navigation.md). **Impl:** new `Screen`s `settings` + `profile` (`/#settings`,
`/#profile`) in `navigation.ts`; `SettingsScreen` + `ProfileScreen` (`features/account/AccountScreens.tsx`)
rendered in `App.renderCurrentScreen` with a **Back** that returns to the screen you came from
(`accountReturnRef`). The **account dropdown redesigned** (`Shell.tsx`): an identity header + clean
**Profile · Settings · Logout** items (icons; navigate, don't inline) — the inline language/strictness
`<select>`s were **moved out** onto the Settings page. **Settings page** groups **Languages**
(transcription/report), **Patient matching** (H3 strictness, with copy), and **Plan** (tier badge,
read-only); each select saves on change via the existing `PATCH /tenant/settings` →
`handleUpdateTenantSettings`. **Profile page** shows avatar/name/email, Role + Clinic, Logout, and an
admin-only Debug (clear local cache). No backend change (reuses `GET /me` + `PATCH /tenant/settings`).
Verified desktop + mobile (dropdown, Settings, Profile screenshots; live PATCH round-trip); tsc clean,
57 backend tests green.

The account dropdown currently crams inline language `<select>`s next to Profile/Logout; the
menu UI is weak and inconsistent, and settings don't belong inline.
- **AC (design):** Redesign the account dropdown for a clean, consistent look; it offers two
  actions — **Settings** and **Profile** — that **navigate to dedicated pages** (not inline
  controls). Add routes + nav entries (`docs/ux/navigation.md`); design both screens.
- **AC (Settings page):** Hosts tenant/user preferences — **transcription & report language**
  (today's `PATCH /tenant/settings`), **match strictness** (H3), tier display, and future
  settings; grouped, with clear save/confirm affordances.
- **AC (Profile page):** Shows the signed-in user + tenant (name, role, clinic), account
  actions (logout), and any per-user identity fields.
- **AC (backend):** Reuse `GET /me` + `PATCH /tenant/settings`; add a per-user settings surface
  only if per-user preferences (e.g. strictness override) are introduced.
- **Migrate:** move the inline language control out of the Shell dropdown into the Settings page
  once it exists.
- **Deps:** none (coordinates with H3, which lives on the Settings page).

---

## Epic C — Reassignment end-to-end (first slice; fixes the live bug) — deps A1, A2, A3, B1

### C1 — Emit assignment intent (`impl`; AI, Pro)
- **AC:** `intents.assignment {present, basis: explicit|implicit, confidence, evidence}`
  populated from audio; "change the patient to X" → `basis: explicit`.

### C2 — Apply with override (`impl`; backend)
- **AC:** Replace the suppression gate in `ai_jobs.complete_worker_job` with §5: append an
  assignment timeline event over an existing/verified assignment **iff `basis == explicit`**
  and the match is deterministic; ambiguous → human resolver. Precedence per **D1** (staff
  overridden only by staff or explicit-basis AI). Latest-wins recompute applies.
- **AC:** Writes an `assignment` effect (`action: reassigned`) on the basis capture.

### C3 — Reassignment chip + undo (`impl`; frontend) — dep B1
- **AC:** The basis capture shows "Patient reassigned → the new patient · Undo"; undo removes the
  event/capture contribution and recomputes; superseded earlier chip shown as superseded.

### C4 — Verify the live scenario (`verify`)
- **AC:** The real ثریا→سروش session reassigns to Soroush; undo reverts to ثریا; override
  works on a `verified` session; a Basic tenant does **not** auto-reassign (manual only).

---

## Epic D — Out-of-context (both tiers) — deps A2, A3, B1
- **D1 (AI):** emit `intents.out_of_context {present, confidence, reason}`.
- **D2 (backend):** write `out_of_context` effect; exclude the capture from the report
  (Pro); never delete.
- **D3 (frontend):** dim the capture card; one-tap "actually relevant" clears it.
- **DONE:** D1 verified live (gateway emits `out_of_context.present=true`). D2:
  `out_of_context_marker` writes a staff-overridable marker on capture metadata in
  `complete_worker_job`. D3: `captureOutOfContext` → dimmed card (`.is-out-of-context`) +
  amber "Out of context · not in report" chip + "Mark relevant" (local clear for now).
  Verified on the real "Hi, this is a test audio" capture. Report-exclusion (Pro) + persisted
  "Mark relevant" land with E/F.

**Retry tweak (DONE):** `requeue_failed_session_captures` — when a capture succeeds (gateway
proven up), failed-retryable siblings reset to queued before chain dispatch, so they retry
immediately instead of waiting for the ~60s recovery beat.

---

## Epic E — Append + Pro Live report — deps A1, A2, B2 — **DONE**
- **E1 (AI):** emit `intents.append`; image captions + text decoration (Pro).
- **E2 (backend):** report refinement folds each new capture in incrementally; writes a
  `report_contribution` effect; the manual Generate path is removed.
- **E3 (frontend):** Live report renders Basic chronological vs Pro synthesized, with the
  "updating for captures X, Y" state.

**Implemented & verified (backend 44 + ai-engine 16 tests green; frontend tsc clean; live
end-to-end on the dev stack):**

- **E1 (append + tier gate):** `intents.append` was already emitted/normalized
  (`normalize_intents` + the transcription prompt; covered by ai-engine tests) — surfaced into
  the report contribution via `has_append_intent`. The captions/decoration **"(Pro)"** gate is
  realized at the backend apply layer (where `tenant.tier` lives): Pro gets the synthesized
  report job + AI effect chips + `report_contribution`; Basic stays a chronological render with
  no synthesis and no AI chips. In the mock engine the placeholder caption/decorated-text are
  tier-neutral passthrough; a real Pro processor replaces them — so no breaking worker change.
- **E2 (auto Pro live report):** `maybe_dispatch_session_report_job` (in `ai_jobs.py`)
  auto-dispatches a `session_organize` report job **once a session's capture chain drains**
  (Pro only; guarded against pending capture jobs / a report job already in flight / no
  reportable capture). Wired into `complete_worker_job` (after `dispatch_next_session_capture`),
  `delete_capture`, and the "Mark relevant" path. Per-capture `report_contribution` effect:
  `pending` at capture completion → `added` when the report job folds it in
  (`mark_session_report_contributions`), with an `report_contribution_summary`
  ({included, set_aside}) on the session for the meta strip. **Out-of-context captures are
  excluded** from the report (`capture_is_out_of_context` filters
  `build_session_processing_input` + the session-job capture list) and counted as "set aside".
  **"Mark relevant" is persisted** as a non-destructive staff override of the AI marker
  (`update_capture` → `out_of_context.overridden_by_staff`) which re-folds the capture and
  re-triggers the Pro report. The **manual Generate path is gone**: `/sessions/{id}/save` is
  retained only for explicit retries and is now Pro-gated (Basic = no-op).
- **E3 (frontend live report):** tabs renamed **Captures / Live report**; **Generate button
  removed**; a **Pro/Basic tier badge** by the title; a calm `Updating for …` state (right of
  the title + footer) while the Pro report regenerates. Pro = the synthesized document
  (`ProLiveReport`: clinic + patient header + body + a `Generated from N captures · M set aside`
  meta strip); Basic = a chronological document (`BasicLiveReport`: transcripts + images, honest
  timestamps, no chips). New per-capture **`✓ Added to report`** chip (Pro). "Verify" recast as a
  calm `Verify report` confirm. "Mark relevant" now calls the backend (`markCaptureRelevant`) and
  refreshes; `tenant.tier` is surfaced on `AuthTenant` and threaded from `App` → `CaptureScreen`.
  **This also lands the B2 tab rename** (Captures / Live report) as part of the slice.

---

## Epic F — Patient management — deps B3
- **F1 (backend):** Unassign action; patient edit (identifiers/DOB/aliases/notes); one
  unified create endpoint shape.
- **F2 (frontend):** resolver + Unassign; patient detail view/edit screen; unified creation
  reachable from resolver, Patients tab, and AI auto-create ("verify" state).
- **DONE (Unassign):** backend `assign_session_patient` already supported `patientId:null`
  (timeline `manually_unassigned` event → recompute); added a client `unassignSessionPatient`,
  an `unassign` flag routed through the assignment outbox operation, and an **Unassign** button
  in the resolver. Verified (resolver screenshot + API smoke → 200 → patient_id NULL).
  Patient detail/edit screen + unified creation still pending.
- **DONE (patient edit):** an "Edit details" form on the patient detail screen
  (`PatientIdentityEditor` in MemoryScreens) edits name/national_id/phone/DOB via the existing
  PATCH `/patients/{id}` — `updatePatient` made a **true partial PATCH**; wired App
  `editPatientDetails` → PatientsHome → PatientTimelineDetail.
- **DONE (B1/B3 — shared PatientForm; 2026-06-05):** a single
  [`features/patient/PatientForm.tsx`](../apps/frontend/src/features/patient/PatientForm.tsx)
  (name, national ID, phone, DOB, **sex**, **notes**) now backs **all three** patient surfaces:
  **edit** (`PatientIdentityEditor` — pre-filled from `getPatient` on open, with a loading state;
  WYSIWYG so a cleared field clears it), **create** (`PatientAssignmentSheet` resolver — a "Create
  new patient" toggle opens the full form, seeded from the search query), and **verify**
  (`AiCreatedPatientPanel` — seeded from the AI-extracted identity). The Patient model already had
  `sex`/`notes`; the gap was the frontend — `getPatient` now returns `notes`, `updatePatient` sends
  `sex`/`notes`, `createPatient` sends **all** demographic fields (was name+national_id only), and
  `StructuredPatientInformation` + `PatientAssignmentDraft` gained the fields. No backend change.
  Verified: 57 backend tests; tsc clean; live POST/GET/PATCH round-trip with sex/notes; screenshots
  `test-results/redesign/{b1-edit-prefilled,b3-resolver-create,b3-ai-verify}.png`.
- **DONE (Patients-tab create + pagination; 2026-06-05):** the **Patients tab** now has a **+ New
  patient** entry (the 4th unified-create entry point — App `createNewPatient` → `createPatient` →
  opens the new patient's detail + refreshes the list via a `patientListVersion` bump). The patient
  list is now **paginated** (`PATIENT_PAGE_SIZE = 25`, `GET /patient-memory?limit&offset` already
  returned `total`): a **Load more** button + a `Showing N of M` count, with offset reset to 0
  whenever the **search query**/filter changes (kept in sync with the shared search box). Avoids
  rendering the entire patient table at once. tsc clean; verified by screenshots
  `test-results/redesign/{b3-patients-list,b3-patients-create}.png`.

---

## Epic G — Offline / resilience — deps B1, B2 — **DONE (2026-06-06)**
- **G1 (frontend):** durability — request `navigator.storage.persist()`; "Saved on this
  device" before network; warn at ~80% via `navigator.storage.estimate()`; **guard before a
  long recording**; **export** escape hatch for queued captures; hard-stop new captures only
  when storage is full.
- **G2 (frontend):** AI-out is silent + self-healing; the Captures view stays fully
  functional offline; enrichment lag shows calm inline state, never an error/modal.
- **DONE:** `persist()` + the ~85% Clinical-Memory warning + G2 (silent self-healing AI-out via
  the durable job-retry path; Captures view always available offline) already shipped. This slice
  adds the remaining G1 durability guards, all frontend:
  - **Shared storage status** (`services/storage/storageStatus.ts`): `estimateStorageStatus()` →
    `{usageRatio, remainingBytes, level: ok|warn|full}` (warn ~85% / <150 MB; full ~97% / <25 MB),
    refreshed on auth-ready + after every capture (`refreshPendingCount`).
  - **Hard-stop when full** (`StorageGuardDialog`): `beginCapture` is blocked when `level==="full"`
    ("a new capture can't be guaranteed to save"), showing usage% + the export CTA instead of the
    recorder.
  - **Guard before a long recording**: the `AudioDialog` shows a calm amber banner when `level==="warn"`
    ("storage is N% full — a long recording may not fit"), non-blocking.
  - **Export escape hatch** (`services/storage/exportCaptures.ts`): a dependency-free store-only
    **ZIP** of every queued (unsynced) capture's media blob + a `manifest.json`, downloaded; the
    ZIP format was validated (`unzip -t` clean). `exportQueuedCaptures` (App) is reachable from the
    hard-stop dialog **and** the proactive **Review storage** sheet (warn level).
  - Verified: tsc clean; 59 backend tests (no backend change); screenshots
    `test-results/redesign/g-{storage-full,audio-warning}.png` + a Node unzip check.

---

## Epic H — Matching robustness (surfaced in C4 real-audio testing)

ASR transcribes names imperfectly (e.g. spoke معاصد, transcribed معاضد), so exact-match-only
assignment silently does nothing. Keep **apply-then-notify**: auto-apply only safe matches,
make everything uncertain a one-tap fix — never silently reassign to the wrong patient.

### H1 — Orthographic name normalization (`impl`; backend) — *mostly already done*
**Largely covered:** `PERSIAN_LATIN_TRANSLITERATION` already folds within-group letters in the
transliterated match key (ث/ص→s, ذ/ض/ظ→z, ط→t, …), so e.g. قاصمی≡قاسمی already match. Remaining
work is an **audit/extend** pass for any unfolded confusions (ه/ح, alef/ی/و variants) — low
priority. *(Cross-group cases like معاصد↔معاضد (/s/↔/z/) are genuinely different sounds and stay
fuzzy — handled by H2.)*
- **Deps:** none.

### H2 — Near-match → actionable suggestion (`impl`; backend + frontend) — **DONE**
Implemented in `ai_jobs.near_match_suggestion` + the apply branch of `complete_worker_job`: a
single dominant high-confidence (`≥0.78`) `possible_match` is surfaced as a
`suggested_reassignment` (carrying the matched patient) → the existing C3 chip
"Suggested: reassign to N · Apply / Dismiss". Ties / low confidence stay choose-patient. No
frontend change needed (reuses C3).

### H2 — Near-match → actionable suggestion (`impl`; backend + frontend)
As staff, when AI is confident-but-not-certain about a name, I want a one-tap reassignment
suggestion instead of nothing.
- **AC:** When matching yields a **single high-confidence fuzzy/`possible_match`** candidate
  (especially with an explicit reassignment intent), emit a `suggested_reassignment` carrying
  that candidate instead of a silent `possible_match`.
- **AC:** Renders the existing C3 chip — "Suggested: reassign to N · Apply / Dismiss"; Apply
  records a staff reassignment. Multiple comparable candidates still route to the
  choose-patient resolver.
- **Deps:** C2, C3.

### H3 — Configurable match strictness (`impl`; backend + frontend) — **DONE (2026-06-05)**
**Implemented:** `tenants.match_strictness` (`strict`|`balanced`|`lenient`, default **`strict`** =
preserves prior deterministic-only behavior), migration `20260605120000`, on `Tenant` +
`TenantProfile`, settable via `PATCH /tenant/settings` (`matchStrictness`). `tenant_match_strictness`
+ `fuzzy_auto_apply_candidate` (in `ai_jobs.py`) gate the single-candidate fuzzy auto-apply line:
`MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD = {strict: None, balanced: 0.82, lenient: 0.78}` (fuzzy conf
is capped at 0.84, so `balanced` catches a strong single variant like معاضد→معاصد, `lenient` reaches
the suggestion floor). Auto-apply fires **only** on an **explicit** basis + a single dominant
candidate with **no** national-ID conflict and **no** tie; everything else stays an H2 suggestion.
The conflict guard / ambiguous routing win at every level. A frontend **Patient matching → Auto-apply**
select in the Shell user menu (next to Languages; moves to the B4 Settings page later). Backend 57
tests green (10 new in `test_ai_assignment_gate.py`); tsc clean; screenshot
`test-results/redesign/h3-match-strictness.png`.

As a clinic/user, I want to choose how aggressively the system auto-applies name matches —
some prefer strict (deterministic only), others can afford auto-applying a close variant
(e.g. accept "معاضد" → "معاصد").
- **AC:** A per-user (with a per-tenant default) **match strictness** setting controls the
  auto-apply-vs-suggest boundary: `strict` = auto-apply only deterministic matches
  (national_id / exact alias / contact); `balanced` = also auto-apply a single fuzzy match
  ≥ a high threshold; `lenient` = lower threshold. Anything below the threshold always becomes
  an **H2 suggestion**, never a silent change.
- **AC:** The national-ID **conflict guard** and ambiguous-multi-candidate routing apply at
  every strictness level; strictness only moves the single-candidate auto-apply line.
- **Real case (2026-06-04):** an audio explicitly said to change the patient and transcribed
  correctly (معاضد), but معاضد≠معاصد is a genuine /z/↔/s/ difference (stays fuzzy), so it
  surfaced as a `Suggested: reassign` (H2) instead of auto-applying — *working as designed under
  the default strictness*. H3's `balanced`/`lenient` is what lets such a single high-confidence
  fuzzy match (especially with an **explicit** reassignment intent) auto-apply. Lives on the B4
  Settings page.
- **Deps:** H2.

### H4 — Partial-match resolution & disambiguation surface (`design`+`impl`; design, frontend, backend) — **DONE (2026-06-05)**
**Design:** the 3-axis decision matrix (basis × match-quality × visit-state) + the capture-card
quick-action surface are specified in [redesign-capture-surface.md](ux/redesign-capture-surface.md)
"Partial-match resolution", [screens/capture.md](ux/screens/capture.md), and
[workflows/review-and-assign-patients.md](ux/workflows/review-and-assign-patients.md); apply
semantics in [intelligence-layer.md §5.4](intelligence-layer.md). **Backend:** suggestions now carry
`matchedName` + `spokenName` (`spoken_name_from_information`) for the "Matched X · you said Y" line;
`suggested_reassignment_candidate` promotes a dominant fuzzy candidate's `patientId` so Apply
reassigns the existing patient (not a duplicate); a strictness-permitted close match auto-applies
(reversible) with `autoAppliedCloseMatch`/`closeMatch` flags (folds into H3's
`fuzzy_auto_apply_candidate`). **Frontend (`CaptureScreen.tsx`):** the suggested chip expands to the
quick-action surface — matched-vs-spoken identity + **Keep match · Create new instead · Choose
another** (Dismiss retained), rendered as real buttons (primary/outlined/ghost). *Keep match*
applies the match; *Create new instead* opens an inline **New patient details** form (name +
national ID, prefilled from the spoken identity, editable) → create+assign flagged verify — this is
also the "edit details" surface and never renames the matched record; *Choose another* opens the
resolver (`onOpenResolver`). An auto-applied close match shows a quiet `· close match · you said …`
note for easy spot-and-undo. Backend 57 + ai-engine 20 tests green; tsc clean; screenshots
`test-results/redesign/h4-{partial-match-desktop,buttons,create-form}.png`.

As staff, when AI lands on a *partial* (fuzzy) patient match, I want a fast, reliable way to
confirm it, reject it for a new patient, or pick someone else — and to fix the details — without
leaving the capture. This unifies the half-built pieces (H2 done / H3 / C3 / B1 / B3) into one
coherent partial-match UX, framed as a 3-axis decision matrix.

- **Decision matrix (the design backbone):** **basis** (explicit | implicit) × **match quality**
  (exact | partial | none) × **visit state** (unassigned | already-assigned). Exact and none are
  mostly settled (exact → assign; none-with-usable-identity → create+assign, flagged "verify",
  editable — today's `AiCreatedPatientPanel`). **H4 specifies the partial cells.**
- **AC (partial · default = suggest, not silent-assign):** A partial match is **never silently
  applied** (CLAUDE.md: never mis-assign). Default is the H2 `Suggested: reassign to N` chip
  (one-tap apply). It **auto-applies** (reversible, with notify) **only** when H3 strictness
  permits — `balanced`/`lenient` + a single high-confidence candidate, strongest with an
  **explicit** reassignment intent. The national-ID **conflict guard** + ambiguous-multi-candidate
  routing win at every strictness level.
- **AC (capture-card quick actions — the new part):** On a partial/suggested capture, show **what
  was matched vs. what was spoken** (e.g. "Matched *معاصد* · you said *معاضد*") and offer one-tap:
  **Keep match**, **Create new patient instead** (seeds a new patient from the spoken identity →
  create+assign, flagged "verify"), **Choose another** (resolver), and **Edit details**. Reuses
  the C3 chip + the timeline-derived alternate-candidate switching already built.
- **AC (editing scope — challenged):** **Edit** edits the *assignment's* patient. For a
  newly-created patient, edit its fields freely (reuse `AiCreatedPatientPanel`/B3). For a
  **matched existing** patient, do **not** silently rename a shared record from a fuzzy capture —
  prefer **Create new instead**; any edit of an existing patient is an explicit, separate action.
- **AC (implicit):** Same surface and quick actions, but **no auto-apply** — implicit partial is
  always a suggestion (first-identity-wins still applies only to *deterministic* matches, per §5).
- **AC (no-match parity):** The "Create new instead" action and the existing no-match create flow
  converge on **one** create+edit+verify surface (B3 unified create), seeded from the spoken
  `patient_information`.
- **Overlap / merge:** subsumes the UX hinted by **H2** (done), **H3** (strictness gate), **C2/C3**
  (apply/undo/switch), **B1** (chip design), **B3** (patient detail/edit + unified create). Impl
  folds into H3 + C3 extensions; the **design** (matrix + quick-action surface) is the new work.
  Update `docs/ux/screens/capture.md`, `redesign-capture-surface.md`, and
  `workflows/review-and-assign-patients.md`.
- **Deps:** H2 (done), H3, C2/C3, B1, B3.

---

## Backlog — found in testing (2026-06-04)

Bugs/improvements surfaced while testing Epic E; not yet scheduled.

1. **Out-of-context card dims its "Mark relevant" button** (Epic D/E3) — **DONE (2026-06-04).**
   The whole-card `opacity` is gone; dimming now applies to the inner content
   (marker/title/status/media/generated-text) only, so the `Out of context · not in report`
   chip and its **Mark relevant** action stay full-opacity and one-tap correctable. *(styles.css.)*
2. **Applying a `Suggested: reassign` didn't move the source or clear the chip** (Epic C2/C3) —
   **DONE (2026-06-04).** Apply now carries a `basisCaptureId`: `AssignPatientRequest` +
   `assign_session_patient` attribute the timeline event to that capture (so
   `active_patient_assignment_action.captureId` matches → the capture shows `Patient assigned →
   N`) and drop its `patient_match_candidate` (the suggestion chip clears). The frontend derives
   per-capture **alternate candidates** from the assignment timeline
   (`sessionAssignmentCandidates`), so the **prior source capture** now offers a switchable
   `Suggested: reassign to <its patient>`; the suggestion is suppressed on the active source.
   Verified live (basis-capture attribution) + screenshot.
3. **Assignment resolver "Suggested matches" is a flat/arbitrary list, not smart** (Epic F/B3) —
   **DONE (2026-06-04).** `detectedSessionPatients` surfaces patients seen in this session
   (assignment timeline, per-capture `patient_match_candidate`/candidateSet, `ai_patient_action`)
   **first**, labelled `Detected in this session`, before the search fallback.
4. **Assignment/edit sheet showed session metadata instead of patient info** (Epic F/B3) —
   **DONE (2026-06-04).** Dropped the date/captures/clinician/clinic summary; the assigned-patient
   block now shows National ID / Phone / DOB (with the assignment source), and an unassigned
   prompt otherwise. Details come from `report.patientInformation`, falling back to an on-demand
   `getPatient` (`GET /patients/{id}`) fetch — so they show **universally**, including sessions
   with no report model (Basic, or before the first Pro report job).
5. **Dev tooling — make both tiers testable side-by-side** (Epic A1) — **DONE (2026-06-04).**
   `ensure_dev_seed` now provisions two dev tenants — `DEV_TENANT_ID` (Pro) and
   `DEV_TENANT_BASIC_ID` (Basic, "AesMem Demo Clinic (Basic)", own "Bita B." seed patient) — with
   every persona a member of both. `POST /auth/dev-login` takes an optional `tier: pro|basic`
   (default `pro`); the login screen shows a **Tier · Pro / Basic** toggle. Log in to each in
   separate tabs to compare. Verified: Basic upload transcribes but dispatches **no report job**,
   writes **no `report_contribution`**, and does **no AI assignment**.
6. **Report refinement froze the capture surface** (Epic E) — **DONE (2026-06-04).** The
   `.workspace-report-card.processing` rule set `pointer-events:none` + dimmed the toolbar/feed
   while the Pro report refined — leftover from the old Generate flow — interrupting capture.
   Removed it: refining is now a calm header/footer "Updating…" cue only; the Captures feed,
   tabs, and capture footer stay fully interactive. Backend self-heal: a capture added *while a
   report job runs* stays `report_contribution: pending` (not falsely marked added) and the
   next idle moment regenerates (`session_has_uncontributed_capture` + a re-dispatch after report
   completion); `maybe_dispatch_session_report_job(force=True)` still regenerates on
   delete/mark-relevant. The user keeps capturing; structuring catches up silently.
7. **Persian audio transcribed as romanized Latin → reassignment silently failed** (Epic A/E) —
   **DONE (2026-06-04).** Validated: the gateway returned romanized Persian ("Bimar ro avaz kon
   be Soroush Moazed"); the explicit reassignment intent *was* detected (basis=explicit, conf
   1.0), but the romanized name only fuzzy-matched the Persian-script DB patient → `possible_match`
   (below the 0.78 suggestion threshold) → nothing surfaced. Fix = a **language preference**
   system: `tenants.transcription_language` (default `auto`) + `tenants.report_language` (NULL =
   template default), migration `20260604120000`, exposed on the `TenantProfile`, settable via
   `PATCH /tenant/settings` and a **Languages** control in the app's user menu. The transcription
   prompt now forbids translation/romanization and transcribes in the original script (auto), or
   in the chosen language's native script — threaded via `transcriptionContext.preferredLanguage`.
   Report language is threaded into the session-processing context (`reportLanguage`) for a real
   synthesizer; the placeholder body is language-neutral. **Tenant-level** (per-user is a future
   refinement, mirroring H3). Caveat: live Persian-script validation is gateway-dependent — the
   local fixtures are English clips, so re-test with Persian audio.
8. **Deleting the reassign-source capture did not revert to the prior patient** (Epic C/F) —
   **DONE (2026-06-05).** Root cause: the DB session is `autoflush=False`, so `delete_capture`
   set `capture.status = deleted` in Python but `apply_active_patient_assignment` then queried for
   non-deleted captures to drop the deleted capture's assignment event — and that query still saw
   the capture as active, so the active-source deletion never reverted (the visit kept the
   reassigned patient). Fix: `db.flush()` in `delete_capture` before the recompute (with a comment
   so it isn't removed). Verified live (deleting the reassign capture now reverts the session
   `patient_id` to the prior patient, in both the API response and the DB). The timeline drop-logic
   itself was already correct (`test_patient_assignment_timeline`).

## Non-goals (v1)

The `edit` intent and field-level provenance/jump-to-section; the literal `Session →
Encounter` rename and per-vertical `attributes`; lab integrations (HL7/FHIR/DICOM/LIS/RIS);
multi-template reports; **LLM-assisted patient matching** (ranking over the backend-selected
candidate set — a future, Pro-tier upgrade to Epic H).
