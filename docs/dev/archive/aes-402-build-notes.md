# AES-402 build notes — what shipped, and what went beyond the planned step

> ⚠️ **Archived** — one-time build-notes input, superseded by the current Pro Q&A contract [`../../backend/aes-pro-qa-api.md`](../../backend/aes-pro-qa-api.md). Kept for history.
>
> The planned step was **AES-402 (Pro): post-session patient↔clinic Q&A + its patient-surface
> payload** (the Basic report/aftercare payload was already merged). During the build several changes
> landed that were **out of the original scope**. They are recorded here with their rationale so the
> deviations are deliberate and reviewable, not silent. Contract: [`../../backend/aes-pro-qa-api.md`](../../backend/aes-pro-qa-api.md).

## In scope (the planned step, as built)

- Patient surface **public Q&A** (`/qa/{token}`): composer + doctor-verified reply thread; withholding
  per AES-403 (the patient sees only their own thread).
- **Doctor Q&A inbox** (Pro): AI-drafted reply, doctor Send / edit / Dismiss; routing default =
  AI→treating doctor + manual re-route (foundation §7); every exchange captured into patient memory.
- The AI **draft job** (`qa_draft`), localized in `ai_jobs.py`; mostly-new files (`app/services/qa.py`,
  `app/qa_api.py`, the frontend `features/qa/*` + `features/patient-surface/PatientQaPage`).

## Out of scope — done, with why

1. **Dev-stack object-storage credential fix (infra).** `scripts/dev-stack.sh` + `.env.example`:
   pin `BACKEND_OBJECT_STORAGE_*` to the shared MinIO's real creds on every `up`.
   *Why:* a captured photo/audio was stuck "trying to sync" (`InvalidAccessKeyId`) on worktree
   stacks — the script defaulted to creds the live shared MinIO doesn't have. It blocked verifying any
   capture-dependent behaviour, recurred across worktrees, and the user hit it, so it was fixed at the
   source (all worktrees self-heal). See [[worktree-minio-cred-mismatch]] memory.

2. **Live-report contribution status (E2, not Q&A).** Replaced the persistent "✓ Added to report"
   success badge with an in-progress **"Adding to report…"** status that clears once folded in, plus an
   explicit report-freshness line (**"✓ Reflects all N captures"** / **"Updating · M not yet in this
   report"**).
   *Why:* user feedback — the success badge implied "queued" and didn't tell the doctor whether the
   current report actually reflects all captures. (Mechanism documented inline in `CaptureScreen.tsx`.)

3. **Top-bar navigation rework.** Q&A is a top-bar **inbox icon + pending-count badge** (not a primary
   nav-pill item); the user menu alignment was fixed; the primary nav is **icon-only on phones**.
   *Why:* adding a Q&A nav entry crowded the Session/Memory pill and overflowed/clipped the top bar on
   mobile (the user reported both). The icon-inbox model fits a triage queue and keeps the shell clean.

4. **AI model config surface.** `qa_draft` (and later `qa_revise` via it) added to the live per-task
   model selector (`AI_MODEL_TASKS`).
   *Why:* user asked the Q&A model to be selectable in the same Settings interface as transcription/
   caption/etc.

5. **Inbox iterations beyond the first cut:** thread-centric (one conversation per patient,
   needs-approval first) with interleaved **visit markers**; collapsed-list view with an explicit
   "View full conversation" disclosure; **re-route hidden** unless the patient has ≥2 treating doctors;
   a mobile CSS-grid overflow fix; a staff **"Open Q&A channel + copy link"** control on the patient
   page.
   *Why:* successive user feedback to keep the inbox legible and the controls meaningful.

6. **Voice edit of a reply (`qa_revise`) — an extension of AES-402.** The doctor can record a voice
   note; a dedicated AI job (one multimodal call to the same Q&A model) decides **revise vs. replace**
   and rewrites the draft; the doctor still reviews + Sends.
   *Why:* explicitly requested as "another feature." It reuses the Q&A job plumbing/model; the only new
   infra is transient audio storage + an internal fetch endpoint.

## Notes for the reviewer

- **Shared-file touches stayed minimal.** `ai_jobs.py` only gained a task-map entry + two adjacent
  worker-callback branches per Q&A job (delegating into `qa.py`); `main.py` only mounts two routers.
  Recovery re-dispatches Q&A jobs for free via the patient-scoped path (forever-retry on transient
  failure; terminal only when the target is deleted).
- **Tier gating:** Q&A is entirely Pro (capability `post_session_qa`; Basic = no AI capabilities →
  API 403 + no Q&A UI surfaces).
- A parallel multi-seat track also edits `ai_jobs.py`; the Q&A enum-value migrations are additive, so
  expect a routine two-head Alembic merge there.
