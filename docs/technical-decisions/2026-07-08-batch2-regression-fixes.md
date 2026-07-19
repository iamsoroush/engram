# Batch-2 regression fixes — report-language default + technique-attribute whitelist (2026-07-08)

Two decisions from the Batch-2 production-regression pass that future agents must respect:

- **A tenant's `report_language` is seeded at sign-up, never left NULL.** `auth/service.register` now sets
  `report_language` from the sign-up language (mirrors `app_language`; `transcription_language` keeps its
  `"auto"` server default). A NULL `report_language` used to fall through to English section *titles* even
  while the AI wrote the *body* in the clinic's (Persian) language — a title/body language split. Defense in
  depth on the client: `LiveReport` resolves the section-title language as `report_language` → the report's
  own content script → `app_language` (never a bare English default). **Consequence:** a NULL
  `report_language` still means "follow the report-template default" for existing tenants, but new tenants
  are explicit; the client no longer assumes English when it is unset.
- **The treatment row renders a whitelist of genuine TECHNIQUE attributes only.** The synthesis attaches an
  open `attributes` map to each treatment; schema-v3 lets the model also drop STATUS / semantic keys there
  (e.g. `planned_vs_performed`) or coded uncertainties. `treatmentAttributeLines` now renders only known
  technique keys (needleGauge, depth, technique, plane, device, sessions, …) and drops everything else, so a
  status key can never leak as a raw `key · value` line — coded uncertainties keep flowing through the calm
  review-note path. **Consequence:** this is a **client-side** filter (no prompt/contract change, not
  eval-gated). If a genuinely new technique attribute needs surfacing, add its key to
  `TECHNIQUE_ATTRIBUTE_KEYS` in `captureModel.ts` rather than reverting to rendering every attribute.
