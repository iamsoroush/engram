# Aesthetics-Pro patient Q&A backend API (contracts)

> Request/response contracts for the **Pro** post-session patient↔clinic Q&A (AES-402/403) — the
> Pro payload of the shared patient surface ([foundation §4](../ux/foundation.md)). The
> Basic payload (report + aftercare) is in [`aes-basic-api.md`](aes-basic-api.md). The backend
> OpenAPI schema (`/api/v1/openapi.json`) remains the machine source of truth.

## Conventions

- **Base path:** `/api/v1`; JSON bodies, **camelCase** keys.
- **Capability gate:** every staff `patient-qa/*` endpoint requires the Pro `post_session_qa`
  capability → **`403`** on a Basic tenant. Read endpoints take `doctor | assistant | admin`
  (`staff_or_admin`); write endpoints take `doctor | assistant` (`staff`).
- **Public endpoints** (`/qa/{token}`) take **no auth** — the token in the URL is the capability;
  unknown/revoked tokens return **`404`** with no existence leak.
- **AI draft:** asking a question enqueues a backend-owned `qa_draft` AI job (reuses the
  patient-scoped `AiJob`; target message carried in `result_metadata` — no `ai_jobs` schema change).
  The worker drafts a reply from the treating doctor's prior answers + this patient's context + the
  clinic's **retrieved exemplars** (the knowledge library, below); a gateway-less worker falls back to
  a deterministic **starter** draft (grounded in the top exemplar when one is retrieved), surfaced to
  the doctor as a "Starter reply — please review" marker (`draftSource: "mock-deterministic"`) so it is
  never mistaken for a generated reply. A stale draft is silent and self-healing (re-dispatched on
  inbox read); a **terminally failed** draft resolves to a visible `failed` (initial) / `failed_revise`
  (voice edit) state instead of an endless "drafting…", never a needs-input item. Prior answers are
  cross-tenant-safe: a leading greeting **name** is stripped server-side before grounding, and the
  prompt forbids copying any dose/product/name from another patient's answer.
- **Metering + abuse (Q-8):** qa jobs are metered like any AI job, so when the clinic is over its
  fair-use AI budget drafting **pauses** (the question stays `draft_status: none`; the doctor can still
  reply by hand; the self-heal resumes once the budget frees). The public `/ask` endpoint is
  rate-limited per thread (rolling per-window cap) and refuses new questions past a concurrent
  unanswered-question ceiling — both `429` — so a leaked token neither floods the inbox nor buys
  unbounded LLM calls.
- **Draft invalidation (Q-5):** re-routing a thread to a different doctor, or excluding the library
  exemplar a draft was grounded on, resets the affected pending drafts to `none` (the self-heal
  re-drafts them for the new doctor / without the exemplar). Patient reassignment invalidates Q&A
  drafts through the reassignment path (`qa.invalidate_drafts_for_patient`).
- **Retrieval grounding (AES-410):** the backend builds `retrievedExemplars` into the `qa_draft`
  payload — the top hybrid lexical+embedding matches over the tenant's **knowledge library** (curated
  templates + auto-indexed sent replies; per-tenant scoped in SQL). The worker stays stateless (it
  only reads the exemplars). The top exemplar becomes the draft's **provenance** (`draftProvenance`),
  surfaced as a doctor-only "based on: …" chip. Retrieval math + storage:
  [ai_engine/processing.md](../ai_engine/processing.md) "Q&A draft"; the library table is
  `qa_knowledge_exemplars` ([data-model.md](data-model.md)). **The lexical `search_text` folds the
  exemplar title** (AES-1802) so a topic-label title still grounds a paraphrase; embeddings are
  optional (a startup/maintenance backfill re-embeds NULL rows once a gateway is configured, and the
  Library flags when semantic matching is off). Provenance is the structured **«بر اساس»** object
  (AES-1803): the top exemplar keeps the strong attribution while patient-record + conversation blocks
  add context chips, or an empty `sources` is the honest general-knowledge state.
- **Escalation at ingest (AES-1801):** the public `/ask` path classifies a question against a
  deterministic fa+en red-flag lexicon (`services/qa_knowledge/escalation.py`) and stamps
  `qa_messages.urgent` (+ `urgent_flags`). Urgent threads surface in the warning style, escalate the
  attention bell, and drive the badge/toast. Runs even gateway-less; sensitivity-biased. An LLM
  escalation flag from `qa_draft` is a registered fast-follow (AES-1804).
- **Withholding (AES-403):** the public read projects **only** the patient's own questions + sent,
  doctor-verified replies. Drafts, routing, provenance, internal status, and other patients are never projected.

---

## Routing policy (admin-configurable; foundation §7)

A tenant-level `qa_routing_mode` decides how a **new** thread routes:

- `ai_default` (default) — auto-routes to the patient's **treating doctor**: the doctor who owns the
  most (then most recent) of the patient's visits; falls back to the earliest active doctor, else
  unrouted.
- `manual` — the thread starts unrouted; staff route it.

Manual re-route to any of the patient's treating doctors is always available regardless of mode.

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/patient-qa/settings` | staff_or_admin | `{ "routingMode": "ai_default" \| "manual" }`. |
| `PATCH` | `/patient-qa/settings` | staff_or_admin | Body `{ "routingMode": "ai_default" \| "manual" }`. |

---

## Threads (staff)

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/patient-qa/threads` | staff | Body `{ "patientId" }`. Opens (or idempotently reuses) the patient's Q&A channel; auto-routes per policy. Re-opening a **revoked** thread rotates its token (the old link stays `404` — Q-9). Returns the **staff thread payload**. |
| `GET` | `/patient-qa/threads` | staff_or_admin | List threads, newest first. Query: `patientId`. |
| `GET` | `/patient-qa/threads/{id}` | staff_or_admin | One thread **with** `messages` (incl. each pending question's `draft`) + `treatingDoctors`. |
| `POST` | `/patient-qa/threads/{id}/route` | staff | Body `{ "doctorUserId" }` — must be an active doctor in the tenant (`400` otherwise). Sets `routingSource: "manual"`; on a real re-route, invalidates the thread's pending drafts so they re-draft for the new doctor (Q-5). |
| `POST` | `/patient-qa/threads/{id}/revoke` | staff | Revoke; idempotent. The public link then `404`s. |
| `GET` | `/patient-qa/patients/{patientId}/treating-doctors` | staff_or_admin | `{ patientId, treatingDoctors:[{ userId, name, sessionCount, lastVisitAt }] }` (the re-route picker source). |

Staff thread payload:
```jsonc
{
  "id": "uuid", "tenantId": "uuid", "patientId": "uuid",
  "token": "url-safe-token", "publicPath": "/qa/{token}",
  "payloadType": "post_session_qa",
  "status": "active",                                  // active | revoked
  "assignedDoctor": { "userId": "uuid", "name": "Dr. Demo" } | null,
  "routingSource": "ai_default" | "manual" | "unrouted",
  "pendingCount": 1,
  "createdAt": "iso", "updatedAt": "iso", "revokedAt": "iso|null",
  // on GET one / route / send / dismiss:
  "messages": [
    { "id": "uuid", "role": "patient", "body": "…", "status": "pending|answered|dismissed",
      "draft": "AI-suggested reply (doctor-only)", "draftStatus": "none|pending|ready|failed|failed_revise", "draftSource": "ai:…|ai-voice:…|mock-deterministic",
      "draftProvenance": { "kind": "template|sent_reply", "exemplarId": "uuid", "label": "…|null" } | null, "createdAt": "iso" },
    { "id": "uuid", "role": "doctor", "body": "sent reply", "status": "sent", "inReplyToId": "uuid", "createdAt": "iso" }
  ],
  "treatingDoctors": [ { "userId": "uuid", "name": "Dr. Demo", "sessionCount": 3, "lastVisitAt": "iso" } ]
}
```

---

## Doctor inbox + reply (staff)

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/patient-qa/inbox` | staff_or_admin | **Thread-centric**: one entry per patient conversation; threads awaiting approval sort first, then by recent activity. Query `scope` = `mine` (default; routed to me **+** unrouted) \| `all` (whole clinic). `total` counts threads awaiting approval (the badge). Self-heals a missing/failed draft on read. Each item + pending question carries `urgent` + `urgentFlags` (AES-1801). |
| `GET` | `/patient-qa/inbox/summary` | staff_or_admin | Lightweight counts for the top-bar Q&A badge + urgent toast (AES-1801) — one join, no full-payload build, no draft self-heal. Query `scope` = `mine` \| `all`. Returns `{ scope, pending, urgent, urgentThreads:[{ threadId, patientName, flags:[…] }] }`. `pending` matches the inbox's `total`. |
| `POST` | `/patient-qa/messages/{id}/send` | staff | Body `{ "reply"? }` — the approved text (the draft as-is, or an edit; omit to send the current draft). Creates the doctor reply, marks the question answered, and **captures the exchange into patient memory**. `409` if the question is no longer pending. Returns the staff thread payload. |
| `POST` | `/patient-qa/messages/{id}/dismiss` | staff | Dismiss without replying. |
| `POST` | `/patient-qa/messages/{id}/voice-edit` | staff | **Voice edit** of the reply: multipart `file` (the spoken note) + `draft` (the current editable text). Stores the audio transiently and enqueues an `AiJobType.qa_revise` job — the AI decides whether the note *revises* the draft or *replaces* it. `409` if the question is no longer pending. Returns `{ messageId, draftStatus: "revising", jobId }`. |
| `GET` | `/patient-qa/messages/{id}/draft` | staff_or_admin | Poll the question's current draft while a voice edit / initial draft runs: `{ messageId, status, draft, draftStatus, draftSource, draftProvenance, draftMode }`. `draftStatus` ∈ `none\|pending\|ready\|revising\|failed\|failed_revise`; `draftMode` (`revise`\|`replace`) is set **only** for a genuine `ai-voice:` result — a `failed_revise` means the voice note couldn't be applied and the draft is **unchanged** (never a silent "Revised"; Q-1). |
| `POST` | `/patient-qa/messages/{id}/save-template` | staff | **Save as template** — copy a sent doctor reply into a curated library template. Body `{ "title"? }`. Returns the new library item. |

Inbox payload (thread-centric):
```jsonc
{
  "schemaVersion": "2026-06-13.patient-qa.v1",
  "scope": "mine",
  "total": 1,                                    // threads awaiting approval (the badge)
  "items": [
    {
      "threadId": "uuid", "patientId": "uuid", "patientName": "Sara N.",
      "assignedDoctor": { "userId": "uuid", "name": "Dr. Demo" } | null,
      "routingSource": "ai_default|manual|unrouted",
      "needsApproval": true,
      "urgent": false, "urgentFlags": [],          // thread urgent = its pending question tripped a red flag (AES-1801)
      "pendingQuestion": {                         // the question to approve a reply to (or null)
        "messageId": "uuid", "question": "…", "askedAt": "iso",
        "suggestedReply": "…" | null,              // the AI draft, doctor-only
        "draftStatus": "ready|pending|failed|failed_revise|none",
        "draftSource": "ai:…|ai-voice:…|mock-deterministic|null",   // "mock-deterministic" → starter reply (review)
        "draftProvenance": {                       // the structured «بر اساس» panel (AES-1803); null on a failed draft
          "grounded": true,                        // false + empty sources ⇒ general-knowledge caution chip
          // patient_record/conversation sources carry a bounded `text` snippet (the chip reveals it); exemplar sources carry `exemplarId` (fetched on tap):
          "sources": [ { "type": "template|sent_reply|patient_aftercare|patient_summary|conversation", "exemplarId": "uuid?", "label": "…?", "text": "…?" } ],
          "kind": "template|sent_reply", "exemplarId": "uuid", "label": "…|null"   // legacy top-exemplar attribution (the strong chip + Q-5 invalidation)
        } | null,
        "urgent": false, "urgentFlags": ["vision"]   // red-flag category keys (localized qa.redflag.<key>)
      },
      "messages": [ { "id": "uuid", "role": "patient|doctor", "body": "…", "status": "…", "createdAt": "iso" } ],
      "visits": [ { "sessionId": "uuid", "title": "Botox follow-up", "date": "iso" } ],  // interleaved as markers
      "lastActivityAt": "iso"
    }
  ]
}
```

The reply-draft/revise models are configured centrally per task (internal-only — model choice is
not a user setting; see [the AI-model decision](../technical-decisions/2026-06-14-therapy-slice1-beyond-plan.md)).

### Internal (AI-engine worker; token-gated, not in OpenAPI)

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/internal/qa/voice/{job_id}` | Streams a `qa_revise` job's stored voice note to the worker (`404` if the job/audio is unknown). |

---

## Knowledge library (staff; AES-410)

The clinic's Q&A knowledge base: curated **templates** + auto-indexed **sent replies**, the retrieval
corpus behind grounded drafting. All `post_session_qa`-gated + strictly per-tenant. Auto-index happens
inside `POST /messages/{id}/send` (every approved reply enters the index by default) — never a separate
call. Rows: `qa_knowledge_exemplars` ([data-model.md](data-model.md)).

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/patient-qa/library` | staff_or_admin | The library. Query `kind` = `template` \| `sent_reply`; `status` = `active` \| `excluded`. Returns `{ templates:[…], sentReplies:[…], counts:{ templates, sentRepliesActive, sentRepliesExcluded }, semanticSearch }`. `semanticSearch:false` ⇒ embeddings unconfigured (lexical-only) → the Library shows one quiet notice (AES-1802). |
| `GET` | `/patient-qa/library/{id}` | staff_or_admin | One exemplar's Q/A (per-tenant) — the sent-reply provenance chip's reveal (AES-1803); never exposes the source patient's thread. |
| `POST` | `/patient-qa/library/templates` | staff | Create a curated template. Body `{ "title"?, "question"?, "answer", "tags"? }`. |
| `PATCH` | `/patient-qa/library/templates/{id}` | staff | Edit a template (templates only — `400` on a sent-reply row). Body as create. |
| `DELETE` | `/patient-qa/library/templates/{id}` | staff | Delete a template (`204`). Auto-indexed replies are excluded, not deleted. |
| `POST` | `/patient-qa/library/{id}/status` | staff | Exclude / re-include an exemplar — the manage/exclude list. Body `{ "status": "active" \| "excluded" }`. Excluding also drops the exemplar from any pending draft it grounded (Q-5). |

Library item:
```jsonc
{
  "id": "uuid", "kind": "template" | "sent_reply", "status": "active" | "excluded",
  "title": "…|null",                                  // templates only
  "question": "…|null", "answer": "…", "language": "fa|en|und",
  "tags": ["…"], "sourceMessageId": "uuid|null",       // set for an auto-indexed sent reply
  "indexed": true,                                     // status === "active"
  "createdAt": "iso", "updatedAt": "iso"
}
```

## Public patient surface (no auth — the token is the capability)

**`GET /qa/{token}`** — the patient's own thread (AES-401/403). `404` for unknown/revoked tokens.
```jsonc
{
  "schemaVersion": "2026-06-13.patient-qa.v1",
  "payloadType": "post_session_qa",
  "status": "active",
  "clinic": { "name": "Engram Demo Clinic" },
  "patientName": "Sara N.",
  "language": "fa",                                    // clinic language → the public page localizes its chrome (Q-10)
  "exchanges": [
    {
      "id": "uuid", "question": "Is the swelling normal?", "askedAt": "iso",
      "status": "answered" | "awaiting" | "closed",   // closed = dismissed (shown with no reply)
      "reply": { "text": "…", "repliedAt": "iso", "byline": "Dr. Demo", "verified": true } | null
    }
  ]
}
```
The AI `draft`, routing, and other patients are **never** in this payload.

**`POST /qa/{token}/ask`** — the patient asks a question. Body `{ "question" }`. Creates the question
and enqueues the reply-draft job; returns `{ id, question, askedAt, status: "awaiting" }`. The reply
appears only after a doctor approves + sends it. **`429`** when the thread has too many unanswered
questions or the per-window ask rate is exceeded (Q-8 abuse guard).
