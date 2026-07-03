# Q&A Inbox (Pro)

## Route

`/#qa-inbox` — Pro only (capability `post_session_qa`; hidden on Basic). Entry: a top-bar inbox
icon beside Search with a pending-count badge (threads awaiting the doctor's approval; caps at
`9+`). See [navigation.md](../navigation.md).

## Purpose

The clinic side of the post-session patient Q&A (AES-402): triage patient questions and send
doctor-verified replies. **Nothing is sent to a patient without a doctor approving it** — the AI
only drafts.

## Structure

- **Thread-centric**: one card per patient conversation — a triaged message list, not a flat chat.
  Threads awaiting approval sort first (amber `Needs reply` badge); the rest follow by recent
  activity.
- Scope toggle: `Mine` (default — threads routed to me **plus** unrouted) / `Clinic`.
- Routing control: tenant-level `qa_routing_mode` — `ai_default` (auto-routes a new thread to the
  patient's treating doctor) or `manual` (starts unrouted; staff route it).
- Each card: patient name; a routing badge (`Treating` / `Rerouted` / `Unrouted` + doctor name);
  the pending question (or a one-line preview when resolved); and an expandable full conversation
  with **visit markers interleaved** chronologically (chat-style bubbles).

## Reply flow

Pending question → **suggested reply** → doctor edits → **Send** or **Dismiss**:

- The suggested reply is a backend-owned `qa_draft` AI job grounded in this patient's context plus
  the doctor's prior answers; a gateway-less worker falls back to a deterministic draft. A
  stale/failed draft is silent and self-healing (re-dispatched on inbox read) — never a needs-input
  item; the doctor can always just write the reply.
- Editing is typed or **voice edit**: the doctor dictates a change and the AI revises or rewrites
  the draft (it decides which), with a one-tap **Undo** back to the pre-voice text.
- **Send** confirms first, marks the question answered, and captures the exchange into patient
  memory. **Dismiss** closes the question without replying (the patient sees it closed, no reply).
- **Re-route** to another of the patient's treating doctors appears when there are two or more.

## States

- Loading skeleton; calm inline error with the list intact; per-scope empty copy.
- Draft `pending`/`failed` shows a quiet hint (`Drafting…` / write your own) — never a blocker.

## Main Components

- `DoctorQaInbox` (+ `useVoiceEdit`)
- `QaChannelButton` — opens/reuses a patient's thread from clinic surfaces (e.g. the lot-recall
  outreach handoff in [patients.md](patients.md))

## Related APIs

Contract: [aes-pro-qa-api.md](../../backend/aes-pro-qa-api.md) — `GET /patient-qa/inbox`,
`POST /patient-qa/messages/{id}/send` · `/dismiss`, `POST /patient-qa/threads/{id}/route`,
`GET`/`PATCH /patient-qa/settings`.

The patient side is the public `/qa/{token}` page — [patient-surface.md](patient-surface.md).
