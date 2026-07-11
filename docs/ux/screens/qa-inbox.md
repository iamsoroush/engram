# Q&A Inbox (Pro)

## Route

`/#qa-inbox` — Pro only (capability `post_session_qa`; hidden on Basic). Entry: a plain top-bar inbox
icon beside Search. Pending threads (awaiting the doctor's approval) are counted by the unified
[Attention indicator](../navigation.md) (Messages tier) and listed in the Attention sweep's Messages
section, which deep-links here. See [navigation.md](../navigation.md).

## Purpose

The clinic side of the post-session patient Q&A (AES-402): triage patient questions and send
doctor-verified replies. **Nothing is sent to a patient without a doctor approving it** — the AI
only drafts.

## Structure

- **Two tabs**: `Inbox` (default — the triage queue) and `Library` (the knowledge library — see below).
- **Thread-centric**: one card per patient conversation — a triaged message list, not a flat chat.
  Threads awaiting approval sort first (amber `Needs reply` badge); the rest follow by recent
  activity.
- Scope toggle: `Mine` (default — threads routed to me **plus** unrouted) / `Clinic`.
- Routing control: tenant-level `qa_routing_mode` — `ai_default` (auto-routes a new thread to the
  patient's treating doctor) or `manual` (starts unrouted; staff route it).
- **One control language**: `Inbox|Library` and `Mine|Clinic` are the shared **segmented control**
  (`Tabs`); the Routing control is the shared **select trigger** (`SelectMenu`) — the same two
  primitives, matched in height, that [Insights](insights.md) uses.
- Each card: patient name; a routing badge (`Treating` / `Rerouted` / `Unrouted` + doctor name);
  the pending question (or a one-line preview when resolved); and an expandable full conversation
  with **visit markers interleaved** chronologically (chat-style bubbles).

## Reply flow

Pending question → **suggested reply** → doctor edits → **Send** or **Dismiss**:

- The suggested reply is a backend-owned `qa_draft` AI job grounded in this patient's context plus
  the doctor's prior answers **plus the clinic's knowledge library** (AES-410); a gateway-less worker
  falls back to a deterministic draft. A stale/failed draft is silent and self-healing (re-dispatched
  on inbox read) — never a needs-input item; the doctor can always just write the reply.
- **Provenance chip** (doctor-only): when a draft is grounded in a library exemplar it shows a tappable
  `based on: {template name}` / `based on a previous reply` chip that opens the Library. Similarity
  scores stay internal — the chip is attribution, not a number.
- Editing is typed or **voice edit**: the doctor dictates a change and the AI revises or rewrites
  the draft (it decides which), with a one-tap **Undo** back to the pre-voice text. A `replace` clears
  the provenance chip (fresh dictation); a `revise` keeps it.
- **Send** confirms first, marks the question answered, captures the exchange into patient memory, and
  **auto-indexes the approved reply into the knowledge library** (Library › Indexed replies).
  **Dismiss** closes the question without replying (the patient sees it closed, no reply).
- **Save as template** on any sent reply copies it into a curated Library template (cold-start entry).
- **Re-route** to another of the patient's treating doctors appears when there are two or more.

## Library tab (AES-410)

The clinic's Q&A knowledge base — the retrieval corpus behind grounded drafting:

- **Templates**: clinic-curated Q+A guidance (optional title + question pattern + approved answer +
  tags). Create / edit / delete.
- **Indexed replies**: every doctor-approved sent reply, auto-indexed by default, listed with a one-tap
  **Exclude** (and **Re-include**) — the manage/exclude list, so a bad one-off answer is easy to evict.
  Never crosses tenants.
- Content (question/answer text) follows `reportLanguage` rules; all chrome is bilingual via `t()`.

## States

- Loading skeleton; calm inline error with the list intact.
- **Empty state teaches (AES-1503).** Instead of a dead-end line, the empty inbox shows the per-scope
  headline **plus** one teaching sentence (a thread starts when a patient asks from their Q&A link)
  **and** a **Share Q&A link** shortcut that opens the app-wide [finder](finder.md) to pick a patient
  and open their Q&A channel (`QaChannelButton`).
- Draft `pending`/`failed` shows a quiet hint (`Drafting…` / write your own) — never a blocker.
- Library empty states invite the first template / explain that approved replies index automatically.

## Main Components

- `DoctorQaInbox` (+ `useVoiceEdit`) with the `Inbox` / `Library` tabs; `LibraryTab`
- `QaChannelButton` — opens/reuses a patient's thread from clinic surfaces (e.g. the lot-recall
  outreach handoff in [patients.md](patients.md))

## Related APIs

Contract: [aes-pro-qa-api.md](../../backend/aes-pro-qa-api.md) — `GET /patient-qa/inbox`,
`POST /patient-qa/messages/{id}/send` · `/dismiss`, `POST /patient-qa/threads/{id}/route`,
`GET`/`PATCH /patient-qa/settings`; **library**: `GET /patient-qa/library`,
`POST`/`PATCH`/`DELETE /patient-qa/library/templates`, `POST /patient-qa/library/{id}/status`,
`POST /patient-qa/messages/{id}/save-template`.

The patient side is the public `/qa/{token}` page — [patient-surface.md](patient-surface.md).
