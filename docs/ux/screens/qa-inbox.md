# Q&A Inbox (Pro)

## Route

`/#qa-inbox` — Pro only (capability `post_session_qa`; hidden on Basic). Entry: a top-bar inbox icon
beside Search that carries a **pending-thread count badge** (AES-1801 — messages earn their own
glanceable badge again, a deliberate **partial-revert** of the E16 merge; the unified
[Attention indicator](../navigation.md) keeps its merged Messages count and still deep-links here).
The badge is scoped like the inbox (Mine for a doctor, Clinic for reception) and **turns to the danger
tone when a pending question is urgent**. Both counts poll while the app is visible (~60s + refetch on
window focus, paused when hidden). See [navigation.md](../navigation.md).

## Arrival & escalation (AES-1801)

Incoming patient questions are classified **at ingest** against a deterministic red-flag lexicon
(fa+en: vision «تاری/دید», necrosis/blanching, breathing, severe/spreading pain, fever — built from
the aesthetics red-flag set; sensitivity-biased, so a false-positive urgent is cheap and a miss is
not). A hit marks the thread **urgent**: the thread row + top-bar badge render in the warning style,
the row shows a **«فوری» badge + a red-flag banner** naming the flag, the attention **bell escalates**
to the urgent tier (above safety), and an **in-app toast** fires when the app is open («سؤال فوری
بیمار — تاری دید»). An LLM escalation flag from the draft is a registered fast-follow (AES-1804).

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
- **«بر اساس» provenance panel** (doctor-only; AES-1803): a compact source row beneath every ready
  draft, built deterministically by the backend from what the payload actually contained — a tappable
  **template** chip (`الگوی کلینیک: {title}`, opens the Library entry) / **previous clinic reply** chip
  (opens only that exemplar's Q/A — never the other patient's thread), one chip per non-empty
  **patient-record** block («مراقبت پس از درمان بیمار», «خلاصه ویزیت اخیر»), a **conversation** chip,
  and — when none grounded it — the honest caution chip «**دانش عمومی — بدون منبع کلینیکی**» (the state
  that deserves the hardest review). Distinct from the gateway-less starter marker. Similarity scores
  stay internal — the chips are attribution, not numbers.
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

- **Templates**: clinic-curated Q+A guidance. The **question is the primary, required field** (AES-1802
  — it's the retrieval signal; «سؤال بیمار چیست؟»); **title** is an optional label. Create / edit /
  delete. Retrieval folds the title into the match text too, so a topic-label title still grounds a
  paraphrase; when the embeddings gateway is unconfigured the Library shows **one quiet notice** that
  semantic matching is off (retrieval is keyword-only).
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
`GET /patient-qa/inbox/summary` (the badge's lightweight pending/urgent counts),
`POST /patient-qa/messages/{id}/send` · `/dismiss`, `POST /patient-qa/threads/{id}/route`,
`GET`/`PATCH /patient-qa/settings`; **library**: `GET /patient-qa/library`,
`GET /patient-qa/library/{id}` (the sent-reply provenance chip's Q/A reveal),
`POST`/`PATCH`/`DELETE /patient-qa/library/templates`, `POST /patient-qa/library/{id}/status`,
`POST /patient-qa/messages/{id}/save-template`.

The patient side is the public `/qa/{token}` page — [patient-surface.md](patient-surface.md).
