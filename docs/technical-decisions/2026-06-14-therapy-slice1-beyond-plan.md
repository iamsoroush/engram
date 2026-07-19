# Therapy Slice 1 — Changes Beyond The Original Plan (2026-06-14)

The therapy-vertical slice-1 build (`build/therapy-core`) is recorded in the therapy vertical
spec, tracked in the `work-docs/` process area. The plan was narrow: a
note-first capture surface + "Session so far" + a `vertical=='therapy'` report-synthesis branch + a
**minimal** client view (sessions list + per-session note/report) + federated caseloads, with backend
edits kept localized to `ai_jobs`. The following changes went **beyond that plan**; captured here so
future agents know what was added and why.

- **Frontend reuses the aesthetics design system, not a bespoke shell.** The therapy app renders
  inside the shared `Shell` (topbar/nav + the Note/Audio/Photo capture footer) and reuses the shared
  capture dialogs + `PatientForm`, mirroring the aesthetics `clinical-row` / `patient-history-card` /
  `workspace-report-card` markup. *Why:* the first cut was a parallel-universe UI; design-system
  consistency across verticals (reviewer feedback). The aesthetics `CaptureScreen` is still untouched.
- **Client creation in the therapy app** (RegisterPatientForm + duplicate guard). *Why:* the
  "minimal client view" had no create path, but a therapist must be able to add a client.
- **Full Note/Audio/Photo capture** via the shared footer (audio standardized to WAV through
  `audio.ts`), not note-only. *Why:* capture-first needs all capture types present (feedback); notes
  remain the primary, but audio/photo must work.
- **Client file shows longitudinal "Client history"** (the AI patient-memory summary + Story so far /
  Worth remembering / Right now) + a session timeline, beyond "sessions list + note/report". *Why:*
  longitudinal memory is the core therapy value and was the missing half of the client surface.
- **Federated-caseload scoping touches several shared read paths** (`patients`, `patient_search`,
  `patient_memory`, `sessions`) + a `caseload.py` helper — broader than the "localized to ai_jobs"
  constraint. *Why:* privacy (foundation §7 — a therapist sees only their own clients) is inherently
  cross-cutting across the patient/session read paths; it cannot live in one file. Aesthetics is
  unaffected (the scope is a no-op for shared-workspace verticals).
- **Therapy session-action endpoints** with request schemas —
  `/sessions/{id}/therapy/{format,release,risk,reflections}`. *Why:* the two-plane summary's controls
  (DAP/SOAP/BIRP switch, explicit Release, clinician-confirmed dated risk, private reflections) need
  persistence and thin routes.
- **Dev provisioning extras:** a therapy demo tenant, a 2nd therapist persona (`therapist-b`), and a
  widened `DevLoginRequest` (`tier=therapy`, `persona=therapist-b`). *Why:* to provision a therapy
  tenant to test against and to demonstrate federated caseloads with two clinicians side by side.
- **AI job prompts made vertical-agnostic** (`verticals.domain_descriptor` → passed into every job
  context; the AI engine reads it via `processing.domain_framing()` with a neutral "clinic" fallback;
  removed hardcoded "aesthetics clinic"/procedure vocabulary). *Why:* the capture/patient-memory
  prompts hardcoded aesthetics framing, so therapy tenants were told they were an aesthetics clinic.
  See the **caution** added to [ai_engine/README.md](../ai_engine/README.md): jobs must not hardcode a
  vertical; extend the descriptor, never the prompts.
- **Durable screenshot tooling** (`apps/frontend/scripts/screenshot.mjs` + [dev/screenshots.md](../dev/screenshots.md))
  driving the **system Chrome** (`channel:"chrome"`). *Why:* the Playwright browser-download CDN is
  blocked in the sandbox/CI; this lets any agent screenshot the running app with no download.
- **Therapy design prototypes realigned to aes-Pro** (`design-prototypes/therapy-*.html`). *Why:* the
  prototypes had drifted from the aesthetics design language (reviewer-requested follow-up).
- **Dev-only `.env` MinIO credential alignment** (not committed — gitignored). *Why:* the shared
  infra MinIO root creds drift/recreate (the documented flaky cred-mismatch), which 500s capture
  uploads; aligning the worktree's object-storage creds to the running MinIO unblocks verification.
- **AI model selection is NOT a user setting.** Models are chosen and optimized *centrally* by us
  (per-task, via `services/ai_model_config.py` live overrides + worker env defaults) — the whole cost
  model assumes specific models (cheap transcription + report model). The old user-facing "AI models"
  picker in Settings was removed; do **not** re-add a model picker to any user surface. *Why:* model
  choice is a cost/quality decision that must stay under our control, not the clinic's. The backend
  override API remains for our internal/admin use only. See
  [business/ai-usage-limits.md](../business/ai-usage-limits.md).
- **Single-recording safety cap** (`MAX_RECORDING_SECONDS`, frontend `AudioDialog`): a live recording
  auto-stops + saves at 20 min so a mic left open can't burn a month of transcription budget in one
  clip. *Why:* the per-session capture-count cap and the monthly $ budget don't stop one runaway clip
  in the moment; auto-stop prevents the accident at the source. The clip captured so far is kept.
- **Fair-use $ budget is internal.** The per-seat AI budget (dollars) is never sent to the client or
  shown in the UI — only a percentage + status. `clinic_usage_state_dict` strips the dollar fields.
  *Why:* pricing/margin is internal economics, not something to surface to clinics.
