# Patient Q&A hardening — honesty, isolation, abuse-resistance, harvest (2026-07-05)

Track-D+ red-team fixes on the post-session patient Q&A path ([aes-pro-qa-api.md](../backend/aes-pro-qa-api.md)),
all on or near the send-to-patient path:

- **A voice edit that can't be applied fails visibly, never silently "Revised" (Q-1, INV-SILENT).** The
  gateway-less / unusable-output fallback echoes the current draft with a `mock-deterministic` source;
  the completion now treats a non-`ai:` source as a failure (`draft_status = failed_revise`, draft
  unchanged) and the UI only badges "Revised" when the draft carries a genuine `ai-voice:` source
  (`draftMode` set). The doctor is told the note didn't land instead of trusting an unchanged reply.
- **Draft ownership is an optimistic lock on `draft_job_id` (Q-2).** The inbox self-heal no longer
  dispatches over a `revising` draft, and every qa_draft/qa_revise completion writes only if the
  question still points at its job — a stale job that lost the race completes quietly, never clobbering
  a newer draft.
- **Cross-patient isolation is defence-in-depth (Q-3).** Prior answers (grounding comes from OTHER
  patients) have a leading greeting **name** stripped server-side, and the prompt's never-copy rule is
  now unconditional (renders even with zero exemplars) covering dose/product/brand/lot/date/name. Two
  new eval gate classes catch a copied cross-patient number and a leaked name.
- **State-change events invalidate dependent drafts (Q-5, INV-INVALIDATE).** Re-route, exemplar
  exclusion, and patient reassignment reset affected pending drafts to `none` so the self-heal
  re-drafts (new doctor's voice, without the excluded exemplar). Sent exchanges appended to
  patient memory are permanent by design (documented, not invalidated).
- **Terminal qa-job failure is a visible state (Q-7).** `fail_worker_job` marks the target question
  `failed` / `failed_revise` (was: stuck "drafting…" forever); the inbox polls pending drafts to land
  the state.
- **qa jobs are metered and pausable; the public ask is throttled (Q-8).** qa spend counts toward the
  fair-use budget and drafting **pauses** when over budget (the doctor can still reply by hand; the
  self-heal resumes when the budget frees). `/qa/{token}/ask` is rate-limited per thread with a
  concurrent-pending ceiling (`429`) so a leaked token can't flood the inbox or buy unbounded LLM calls.
- **Re-opening a revoked thread rotates its token (Q-9).** A revoked link was handed out to be dead;
  re-activation mints a fresh URL so the leaked one stays `404`.
- **The public Q&A page localizes to the clinic language + marks the deterministic fallback (Q-10).**
  The public payload carries `language`; the gateway-less starter draft is surfaced as "Starter reply —
  please review", not as a generated AI reply.
- **Doctor actions on a draft are harvested as eval signals (HALF-2).** A manual edit before send / a
  voice revise-replace is a `correction`, a dismiss is a `rejection`, recorded to `ai_feedback_events`
  as `ai_output_type = qa_reply` inside the same transaction (provenance in `context`; PII-scrubbed).
