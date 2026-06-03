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

**Remaining (prioritized):**

1. **E — Pro Live report job** (currently deferred): regenerate the report by an AI job per
   capture from a template; remove the Generate button; exclude out-of-context captures; persist
   "Mark relevant". Unblocks the **B2** tab rename (Captures / Live report).
2. **A0** — `tenant.vertical` scaffolding (Patient is universal; `Session` is the clinic `Encounter`, typed by vertical).
3. **H3** — configurable match strictness (per-tenant, mirror the `tenant.tier` pattern).
4. **B1/B3 UI** — approved prototypes at `apps/frontend/design-prototypes/*.html`; build the
   Captures/Live-report rename (needs E), patient detail polish, unified create screen.
5. **A4** — inline per-capture generated-text edit (exists today via the source-preview sheet).
6. **G** — mostly already in code (`navigator.storage.persist()` + an 85% storage warning);
   remaining: guard before a long recording, export escape hatch, hard-stop when storage is full.

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
tests -p "test_*.py"` (36 green); frontend `cd apps/frontend && npx tsc --noEmit`. Visual checks
were done with throwaway Playwright specs under `apps/frontend/tests/visual/` that drive
`localhost:5183` and screenshot to `test-results/redesign/` (delete the spec afterward). Seeded
test patients: سروش معاصد, ثریا قاسمی, سارا نظری (national_id `0012345678`), نگار/بابک احمدی, Sara N.

---

## Epic A — Foundations (cross-cutting)

### A0 — Entity model (`design`+`impl`; backend, docs)
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

### A4 — Per-capture generated-text edit (`impl`; backend + frontend)
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

## Epic E — Append + Pro Live report — deps A1, A2, B2
- **E1 (AI):** emit `intents.append`; image captions + text decoration (Pro).
- **E2 (backend):** report refinement folds each new capture in incrementally; writes a
  `report_contribution` effect; the manual Generate path is removed.
- **E3 (frontend):** Live report renders Basic chronological vs Pro synthesized, with the
  "updating for captures X, Y" state.

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
  PATCH `/patients/{id}` — `updatePatient` made a **true partial PATCH** (only sends provided
  keys → blank = leave unchanged, no clobber); wired App `editPatientDetails` →
  PatientsHome → PatientTimelineDetail; verified by screenshot. Remaining: show current
  id/phone values (needs a `GET /patients/{id}`), sex/notes fields, a unified create screen.

---

## Epic G — Offline / resilience — deps B1, B2
- **G1 (frontend):** durability — request `navigator.storage.persist()`; "Saved on this
  device" before network; warn at ~80% via `navigator.storage.estimate()`; **guard before a
  long recording**; **export** escape hatch for queued captures; hard-stop new captures only
  when storage is full.
- **G2 (frontend):** AI-out is silent + self-healing; the Captures view stays fully
  functional offline; enrichment lag shows calm inline state, never an error/modal.

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

### H3 — Configurable match strictness (`impl`; backend + frontend)
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
- **Deps:** H2.

---

## Non-goals (v1)

The `edit` intent and field-level provenance/jump-to-section; the literal `Session →
Encounter` rename and per-vertical `attributes`; lab integrations (HL7/FHIR/DICOM/LIS/RIS);
multi-template reports; **LLM-assisted patient matching** (ranking over the backend-selected
candidate set — a future, Pro-tier upgrade to Epic H).
