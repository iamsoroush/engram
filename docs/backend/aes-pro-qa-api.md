# Aesthetics-Pro patient Q&A backend API (contracts)

> Request/response contracts for the **Pro** post-session patient↔clinic Q&A (AES-402/403) — the
> Pro payload of the shared patient surface ([foundation §4](../ux/redesign-foundation.md)). The
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
  The worker drafts a reply from the treating doctor's prior answers + this patient's context; a
  gateway-less worker falls back to a deterministic draft. A stale/failed draft is silent and
  self-healing (re-dispatched on inbox read), never a needs-input item.
- **Withholding (AES-403):** the public read projects **only** the patient's own questions + sent,
  doctor-verified replies. Drafts, routing, internal status, and other patients are never projected.

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
| `POST` | `/patient-qa/threads` | staff | Body `{ "patientId" }`. Opens (or idempotently reuses) the patient's Q&A channel; auto-routes per policy. Returns the **staff thread payload**. |
| `GET` | `/patient-qa/threads` | staff_or_admin | List threads, newest first. Query: `patientId`. |
| `GET` | `/patient-qa/threads/{id}` | staff_or_admin | One thread **with** `messages` (incl. each pending question's `draft`) + `treatingDoctors`. |
| `POST` | `/patient-qa/threads/{id}/route` | staff | Body `{ "doctorUserId" }` — must be an active doctor in the tenant (`400` otherwise). Sets `routingSource: "manual"`. |
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
      "draft": "AI-suggested reply (doctor-only)", "draftStatus": "none|pending|ready|failed", "draftSource": "ai:…|mock-deterministic", "createdAt": "iso" },
    { "id": "uuid", "role": "doctor", "body": "sent reply", "status": "sent", "inReplyToId": "uuid", "createdAt": "iso" }
  ],
  "treatingDoctors": [ { "userId": "uuid", "name": "Dr. Demo", "sessionCount": 3, "lastVisitAt": "iso" } ]
}
```

---

## Doctor inbox + reply (staff)

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/patient-qa/inbox` | staff_or_admin | Query `scope` = `mine` (default; routed to me **+** unrouted) \| `all` (whole clinic). Self-heals a missing/failed draft on read. |
| `POST` | `/patient-qa/messages/{id}/send` | staff | Body `{ "reply"? }` — the approved text (the draft as-is, or an edit; omit to send the current draft). Creates the doctor reply, marks the question answered, and **captures the exchange into patient memory**. `409` if the question is no longer pending. Returns the staff thread payload. |
| `POST` | `/patient-qa/messages/{id}/dismiss` | staff | Dismiss without replying. |

Inbox payload:
```jsonc
{
  "schemaVersion": "2026-06-13.patient-qa.v1",
  "scope": "mine",
  "total": 1,
  "items": [
    {
      "messageId": "uuid", "threadId": "uuid",
      "patientId": "uuid", "patientName": "Sara N.",
      "question": "Is the swelling normal?", "askedAt": "iso",
      "suggestedReply": "…" | null,              // the AI draft, doctor-only
      "draftStatus": "ready|pending|failed|none",
      "assignedDoctor": { "userId": "uuid", "name": "Dr. Demo" } | null,
      "routingSource": "ai_default|manual|unrouted"
    }
  ]
}
```

---

## Public patient surface (no auth — the token is the capability)

**`GET /qa/{token}`** — the patient's own thread (AES-401/403). `404` for unknown/revoked tokens.
```jsonc
{
  "schemaVersion": "2026-06-13.patient-qa.v1",
  "payloadType": "post_session_qa",
  "status": "active",
  "clinic": { "name": "Memara Demo Clinic" },
  "patientName": "Sara N.",
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
appears only after a doctor approves + sends it.
