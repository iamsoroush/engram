# Q&A owner-testing gaps: arrival badge, deterministic escalation, retrieval grounding (2026-07-12)

Three gaps from the owner's Q&A testing, shipped as AES-1901/1902/1903 (fast-follow AES-1904
registered). Decisions worth recording:

- **Q&A messages get their own glanceable badge again (partial-revert of E16/AES-1003).** The unified
  bell keeps its merged Messages count, but the inbox icon regains a pending-thread badge (scoped like
  the inbox's Mine/Clinic). Rationale: a merged count is right for *routine* triage, but a between-visit
  patient question is time-sensitive enough to earn its own at-a-glance number. Both counts poll while
  visible (~60s + refetch on focus, paused when hidden) — no websockets at this stage.
- **Escalation is deterministic first, LLM second.** A patient can report an emergency (filler
  vascular occlusion) that must not read as routine. We classify **at ingest** against a small,
  sensitivity-biased fa+en red-flag lexicon (`services/qa_knowledge/escalation.py`) — it runs even
  gateway-less and can never be "the thing that's down". An urgent hit escalates the row, the badge,
  the attention bell (above safety), and fires a toast. A false-positive urgent costs one glance; a
  miss costs tissue. An LLM `escalate` flag from `qa_draft` is a **registered, eval-gated fast-follow**
  (AES-1904), layered *over* — never replacing — the deterministic floor.
- **Retrieval grounds on the title too; question becomes the primary field.** Root cause of the owner's
  "template didn't ground" repro: `search_text` folded only question+answer, so a topic-label title
  («ورزش بعد از بوتاکس») with an empty question never matched «کی میتونم ورزش کنم؟». Fix at all three
  layers: `search_text` now folds the **title**; the Library makes **question** the primary, required
  field (title an optional label) and a migration **moves** a question-shaped title into an empty
  question (a mis-entry repair — chosen over a literal "copy" so the redesigned label field isn't left
  showing a full question); and the embeddings gateway is wired in the env defaults with a
  startup/maintenance backfill, with a **visible Library notice** when semantic matching is off (silent
  degradation is how this went unnoticed). `qa_draft` prompt/evals unchanged.
- **Draft provenance is a structured object, not a single chip.** `qa_messages.draft_provenance`
  extends from top-exemplar-only to `{ grounded, sources[], + legacy kind/exemplarId/label }` — the
  «بر اساس» panel names every grounding source the payload carried, and an empty `sources` is the
  honest "general knowledge — no clinical source" state (the draft that deserves the hardest review).
  The legacy top-level keys stay for the strong chip + Q-5 exemplar invalidation. Built deterministically
  by the backend from the payload contents — no prompt or eval change.
