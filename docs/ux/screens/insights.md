# Insights (Clinic analytics)

## Route

`/#insights` — an account-style utility page, reached from the **account menu** (top-right avatar),
shown only to **owner/admin** (same `canManageTeam` gate as [Team](team.md)/Plan). Placed directly
above **Team** in the menu. Has a **Back** action returning to the previous screen. Like all
account/utility pages, it hides the capture bar (there is no capture context here — see
[navigation.md](../navigation.md)).

## Purpose

Give the clinic **owner/admin** a real pulse on the clinic and its people — activity, retention,
staff productivity, patient panel, and (Pro) treatment/product insights — from data the platform
already captures. Two lenses: **clinic-wide** and **individuals** (both staff and patients).

**Deliberate constraints (no fabricated data):**

- **No revenue/financials.** The system stores no price/cost/invoice/payment field. Insights are
  activity- and clinically-derived only. Not shown, not estimated.
- **No scheduling.** No appointment/booking model exists (the worklist is a soft lane, no time slot),
  so no no-show / utilization / booking-funnel metrics.
- All metrics are **deterministic** (no AI). Treatment metrics read the already-extracted
  `session.extracted_metadata.treatments[]`; they do not run new AI jobs.

## Tiering (Light Basic, full Pro)

- **Basic** — Overview (volume + data-hygiene, no treatment cards), Team (volume-based), Patients
  (demographics + recency). The **Treatments** tab renders a blurred preview behind an **"Unlock
  treatment & product insights with Pro"** panel (reuses the Plan-screen tier framing).
- **Pro** — all of the above **plus** the Treatments tab and the per-person treatment-mix detail.

Treatment/product data only exists on Pro (extraction is a Pro capability), so this split is a data
fact, not just packaging.

## Global controls (sticky header)

- **Time range**: `This week` · `This month` (default) · `Last 3 months` · `This year` · `Custom`.
  Choice is persisted (client preference).
- **Compare to previous period** toggle → each KPI shows a **delta chip** (Δ% vs the equivalent prior
  window). Deltas are **neutral/informational** styling — never red-alarm (fewer filler visits is not
  inherently "bad").
- **Sub-tabs**: `Overview · Team · Patients · Treatments`.

## Sub-tabs & visible data

### Overview (clinic pulse)

- **KPI cards** (label · big value · neutral delta chip · tiny sparkline): **Visits**, **New
  patients**, **Active patients**, **Captures**.
- **Activity over time** — area/line chart; series toggle (Visits · Captures · New patients).
- **New vs returning** — split (donut) + headline **repeat rate**.
- **Busy times** — day-of-week × hour heatmap (informs staffing).
- **Needs attention** — the one *actionable* strip: chips for **unassigned captures**, **sessions
  awaiting review**, **failed captures**; each deep-links into the existing queue. (Basic + Pro.)

### Team (individuals · staff)

- **Workload share** — horizontal bars, each staff member's % of total activity.
- **Member cards** — avatar · name · role · `patients · visits · captures` · **last active**;
  sortable (patients seen / visits / captures / recency).
- **Per-person detail** (tap) — that member's activity trend, recency, and (Pro) **treatment mix +
  specialization**.
- **Honesty note** (always visible): work is **attributed to whoever captured** the visit
  (`created_by_user_id`), which is usually — but not guaranteed to be — the treating clinician.

### Patients (individuals · panel)

- **Panel recency** — three cohort cards: **Active** (<3 mo) · **Lapsing** (3–6 mo) · **Lapsed**
  (>6 mo). Lapsing/Lapsed deep-link into **recall / smart-lists** for outreach (reuses the existing
  due-to-return logic).
- **Age distribution** — histogram (age bands from `date_of_birth`).
- **Sex split** — donut (from `sex`; excludes unknown).
- **Panel growth** — cumulative patient count over time.

### Treatments (Pro; locked on Basic)

- **Top treatments** — ranked horizontal bars (by count).
- **Consumption** — big-number cards grouped by unit family (e.g. **Neurotoxin** total units,
  **Filler** total ml), summing `treatments[].quantity` by `unit`.
- **Top products / brands** — ranked bars (`treatments[].product` / `brand`).
- **Treatment mix over time** — stacked area (share shift, e.g. tox vs filler).
- **By area** — **ranked bar list** (`treatments[].area`). (A stylized face/body heat-map is a
  possible fast-follow, out of v1 scope.)
- Excludes `carriedForward` items from consumption/recall-style counts (same convention as the lot
  ledger), to avoid double-counting "same as last time".

## Charts

**No charting library.** Purpose-built lightweight **SVG** components live in a shared `charts/`
module: `Sparkline`, `BarList` (ranked horizontal bars), `AreaLine`, `Donut`, `Heatmap`, `StatCard`.
All are **RTL-correct by construction** (axis/origin mirror under RTL) and render **locale digits**
(Persian under fa) via the existing i18n number seam. This keeps zero new dependencies and matches
the app's minimal-deps ethos.

## Bilingual / RTL

All **chrome** (labels, tab names, tooltips, range options) routes through the `shared/i18n` `t()`
seam — no hardcoded UI strings. Treatment/product/area **names are clinical CONTENT** surfaced from
extraction, so they follow the content language, not `t()`. Charts mirror and use Persian digits
under fa.

## Main components

- `InsightsScreen` — sticky header (range + compare + tabs), routes to the four tab panels.
- `OverviewTab`, `TeamTab`, `PatientsTab`, `TreatmentsTab` (+ `MemberDetail` sheet).
- `charts/` — the shared SVG primitives above.
- Presentational charts stay separate from the data-fetch/orchestration layer (per frontend rules).

## Related APIs

Four thin, **tenant-scoped, deterministic** endpoints returning **pre-aggregated** JSON (frontend does
no heavy reshaping — per frontend rules), each taking `?range=` (+ custom `from`/`to`):

- `GET /api/v1/insights/overview` — KPIs (+ prior-period), activity series, new/returning, busy-time
  heatmap, needs-attention counts.
- `GET /api/v1/insights/team` — per-member `{patients, visits, captures, lastActiveAt}` + workload
  share.
- `GET /api/v1/insights/patients` — recency cohorts, age histogram, sex split, growth series.
- `GET /api/v1/insights/treatments` — top treatments, consumption-by-unit, top products/brands, mix
  series, by-area (**Pro-gated**; 403/upsell payload on Basic).

All owner/admin-gated (`tenant_admin_required`) and tenant-scoped. Aggregation is **query-time** over
`sessions` / `captures` / `patients` / `memberships` (+ the `treatments[]` JSONB). Query-time is fine
at alpha scale; **materializing treatments into a table is noted as a later optimization** if it gets
slow.

## States

- **Loading** — per-card **skeletons** (header stays interactive).
- **Empty / not-enough-data** — per-card friendly empty state ("Not enough data yet"); important since
  clinics are early/alpha. A brand-new clinic sees mostly empties, not zeros dressed as charts.
- **Error** — calm inline retry per section, no modal.
- **Basic on Treatments tab** — blurred preview + Pro upsell panel.

## Known gaps / non-goals

- No revenue/financial insight (no pricing data exists). If a pricing layer is ever added, an
  estimated-revenue view could layer on without changing these endpoints.
- No scheduling/utilization/no-show metrics (no appointment model).
- No clinical-outcome tracking (no pre/post outcome fields).
- Staff attribution = capturer, not a distinct "treating clinician" field.
- Body-area heat-map (face/body diagram) deferred; v1 ships the ranked bar list.
