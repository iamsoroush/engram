# Insights + AI-Quality Feedback (backend contracts)

Two small, self-contained backend subsystems. Exact request/response schemas: the OpenAPI schema
(`/api/v1/openapi.json`).

## Clinic insights (owner/admin analytics)

Read-only, tenant-scoped analytics over data the platform already captures — deterministic,
zero-AI aggregation (no revenue or scheduling metrics exist because the system stores no
price/invoice or appointment data; times aggregate in UTC). Router: `app/insights_api.py`
(thin handlers); all aggregation lives in `app/services/insights.py` as pure, unit-testable
functions over thin DB loaders. UX: [docs/ux/screens/insights.md](../ux/screens/insights.md).

All four endpoints are **owner/admin-gated** (`tenant_admin_required`) and take the same window
query params (`range` = `this-week` | `this-month` | `last-3-months` | `this-year` | `custom`,
plus `from`/`to` for custom):

| Endpoint | Payload |
| --- | --- |
| `GET /api/v1/insights/overview` | clinic pulse: KPIs + prior-period deltas, activity series, new/returning, busy-time heatmap, backlog |
| `GET /api/v1/insights/team` | per-member productivity (visits · patients · captures · last active) + workload share |
| `GET /api/v1/insights/patients` | patient panel: recency cohorts, age histogram, sex split, cumulative growth |
| `GET /api/v1/insights/treatments` | **Pro-gated** (`403` on Basic, gated on `live_report_synthesis`): top treatments, consumption-by-unit, top products, treatment-mix series, by-area |

The treatments lens reads the already-synthesized `Session.extracted_metadata["treatments"]` the
same way smart lists / the lot ledger do — no new AI job.

## AI-quality feedback (the eval golden-set harvester)

Every staff correction of an AI output and every report/brief thumbs rating is recorded as an
`ai_feedback_events` row — a candidate eval case, so real production corrections seed the eval
golden sets (see [docs/ai_engine/evals.md](../ai_engine/evals.md)). Two entry points:

- **Server-side harvesting** (non-bypassable): the correction services call
  `services/feedback.record_*` *inside the same transaction* as the edit they record — cheap,
  append-only, and wrapped so a logging bug can never break the user's action. Covers transcript /
  caption / treatment / patient-match corrections, confirmations, and safety-flag rejections, plus
  **Q&A reply** feedback (`services/qa`): a doctor editing the AI draft before sending, a voice
  revise/replace, or dismissing a drafted question all record the before/after so real edits seed the
  qa golden set (retrieval provenance travels in `context`).
- **Client-supplied signals** via `app/feedback_api.py`:
  - `POST /api/v1/feedback` (staff) — record a rating/signal (the report/brief thumbs).
  - `GET /api/v1/feedback` (staff_or_admin) — tenant-scoped read, newest first; filters `kind`,
    `aiOutputType`, `limit`. The harvest/QA read.

`kind` ∈ `correction` | `confirmation` | `rating` | `rejection`; `ai_output_type` ∈ `transcript` |
`caption` | `treatment` | `patient_match` | `report` | `brief` | `safety_flag` | `qa_reply`.

PII posture: the before/after AI-output *text* is stored verbatim (it is the eval target), but
structured patient PII (names, national ID, phone, DOB, address, match evidence) never enters the
`context` payload — `services/feedback.scrub_context` redacts it.
