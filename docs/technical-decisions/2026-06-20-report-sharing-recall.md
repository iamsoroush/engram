# Report Sharing And Recall Decisions (2026-06-20)

Durable decisions from the Pro-report and recall builds:

- **One report, no separate patient projection.** The patient share is a curated subset of the
  *same* synthesized report — there is no second, patient-specific report artifact. Withholding is
  enforced server-side (only curated content is copied into the share snapshot), never by client
  filtering. See [ux/screens/patient-surface.md](../ux/screens/patient-surface.md).
- **Share treatment specifics are generic by default.** A per-clinic `share_include_brands`
  setting (default **off**) controls whether shared treatment lines name brands; with it off the
  wording is generic. The structured treatment table and **lot numbers are always withheld** from
  patient shares regardless of the setting.
- **Assessment on the patient share is opt-in, default off.** Clinician findings can alarm out of
  context, so the assessment section is only shared deliberately per send.
- **Carried-forward dose gates completeness.** An unconfirmed carried-forward dose keeps a session
  out of `Complete` (`session_contracts.py:41`) — the one deliberate safety-critical exception to
  the warnings-over-blocking principle. Other review items (low-confidence, ambiguous, missing
  lot) stay non-blocking. See [ux/screens/session-review.md](../ux/screens/session-review.md).
- **Lot-recall matching is exact-only.** Lot identity normalizes by uppercase + trim + collapse
  internal spaces, keeping hyphens/dots; near-misses are *never* merged into a recall cohort (a
  recall list must be trustworthy — fuzzy expansion belongs to a human, not the query).
