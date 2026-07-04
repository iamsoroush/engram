# Fair-use AI usage limits — measured cost model, caps & the shipped system

> **Goal:** never lose money on a plan. Meter **real** AI spend per clinic, warn early, and pause
> *background* AI enrichment at the monthly budget — **never** blocking a capture. Companion to
> [compute-cost-model.md](compute-cost-model.md): that doc estimates COGS with `tokens ≈ chars/4` and
> a *deterministic* report; this doc replaces the report line with **measured** numbers and defines
> the enforcement system. Every bold input recomputes.

## 1. What changed vs. the estimate — synthesis is now the dominant, per-capture cost

The compute-cost model assumed the session report was deterministic ($0.00115 once/visit). It is now
a real LLM job (`gpt-5.4-nano`) that **re-runs ~once per added capture**, re-feeding a ~2.3k-token
fixed prompt + the prior draft + all captures each run. Measured on the live gateway (gw.engram.ir),
`reasoning_effort=low`, a realistic 10-capture Persian aesthetics visit built capture-by-capture:

| Synthesis mode | $/visit | notes |
|---|--:|---|
| **Per-capture (R=N=10)** | **$0.0203** | 34.6k input + 10.7k output tokens across 10 runs |
| **Coalesced (R≈1)** | **$0.0023** | one run over all captures |

→ **~8.8× cost cut** from coalescing, **zero UX loss** (the deterministic baseline is always current;
synthesis is a quiet refinement). This is why synthesis dispatch **collapses redundant queued runs**
(queue-collapse dispatch, see §5): the first capture synthesizes immediately, then a burst of N
captures costs **≤ 2 runs** (an in-flight run + one collapsed follow-up) instead of N — approaching the
coalesced figure without any timer or added latency.

Other measured unit costs: **transcription** `gemini-3.1-flash-lite` **$0.0021/audio-min** (confirmed
live); **image caption** ~**$0.0005/photo** (measured vision call); **note decoration** $0 (passthrough);
patient-memory / QA are sub-cent and infrequent.

## 2. Scenario cost model (measured; recomputes)

`visit_cost = audio_min×$0.0021 + photos×$0.00054 + synthesis(R, #captures)`. Monthly volume from
compute-cost-model §2 (Pro 2 seats×240 visits = 480/clinic; therapy 3 seats×132 = 396/clinic).

**Pro aesthetics — $/clinic/mo:** light $2.24 · typical $3.96 · heavy $7.40 *(coalesced; per-capture
$4.17 / $9.01 / $19.71)*.
**Therapy — $/clinic/mo:** light $2.14 · typical $5.63 · heavy $10.73 *(per-capture $2.58 / $8.03 /
$14.89)* — transcription-minute-dominated, so coalescing helps less here.

Recompute with `scripts`-free model in the PR notes; change a rate in
`apps/backend/app/services/ai_usage/pricing.py` and the meter follows.

## 3. The caps (current)

- **Monthly $ backstop (authoritative):** **$10 of AI cost per seat / month** (`ai_budget_usd_per_seat`);
  clinic budget = **active seats × $10**. The meter tracks real spend; at 100% background enrichment
  pauses. $10 is ~**67%** of the $15 Pro price — deliberately generous; tighten toward ~40% as synthesis
  cost drops (queue-collapse dispatch + prompt-cache reuse, §5).
- **Per single recording:** auto-stop + save at **20 min** (frontend `MAX_RECORDING_SECONDS`) so a mic
  left open can't burn the budget in one clip.
- **Per-session soft cap (proxy):** **30** AI captures per session — pauses further per-capture
  enrichment for a single runaway session only; never blocks capture.
- Basic (zero-AI) has **no** limits.

Uncollapsed per-capture synthesis, a typical Pro doctor (~240 visits/mo) spends ~$4.5/seat and a heavy
one ~$9.9/seat — so $10 covers even heavy use; queue-collapse dispatch (§5) drops these toward ~$2 /
~$3.7. Tunable in `config.py` (`ai_budget_usd_per_seat`, `ai_session_soft_cap_captures`).

## 4. How it's metered & enforced (as built)

- **Real spend, not estimates.** Every gateway call already returns `usage`; the worker now captures
  it per job (`_MeteredClient` in `apps/ai_engine/ai_engine/core/gateway.py`) and ships it on the
  completion callback. Transcription is priced per audio-minute (duration via ffprobe); LLM/vision per
  token. The backend computes cost from `pricing.py` and accumulates into **`ai_usage_counters`**
  (per tenant/seat/calendar-month; cost in micro-dollars).
- **Enforcement is capture-first.** The capture + its artifact are committed *before* any AI dispatch.
  The three dispatch chokepoints (`orchestration.py` capture/session/patient-memory) consult
  `should_defer_dispatch`; when over budget (or over the session soft cap) the job is **parked**
  (kept queued, not sent to Celery). The recovery beat resumes parked jobs once the budget frees
  (new period / top-up / upgrade). **A capture is never lost or blocked.**
- **API:** `GET /api/v1/ai-usage` → the clinic's current-period state (plan, budget, spent, %, status
  ok/approaching/over, paused, captures, audio-min, reset date). Dev-only `POST /api/v1/ai-usage/dev/set`
  jumps to a target % for testing (guarded to dev auth mode).

## 5. Synthesis cost control — queue-collapse dispatch + cache-hit-before-dispatch

The biggest lever (~8.8×) is **not** re-synthesizing on every single capture. This is achieved with
**no timer and no debounce** — per-capture responsiveness is fully intact:

- **Queue-collapse dispatch.** Synthesis is single-flight per session with at most one pending job. The
  first capture synthesizes immediately; while a run is in flight, new triggers are no-ops (a *queued*
  job reads the full current capture set when it starts; a *running* job's completion dispatches the one
  collapsed follow-up). A burst of N captures therefore costs **≤ 2 runs** instead of N. `force=True`
  (content edits / manual regenerate) still re-synthesizes past the all-contributed guard.
- **Cache-hit before dispatch.** Every settle checks the content-addressed `session_report_versions`
  store for the current capture-set hash; a hit **restores** the stored synthesis deterministically (no
  LLM) instead of paying for a re-run — covering edit-then-revert, mark-relevant toggles, and re-adds.
- **Prompt-cache-friendly prefix (companion, worker-side).** With a stable-prefix synthesis prompt the
  re-fed context of a follow-up run hits the provider prompt cache (~10× cheaper input tokens), so even
  a non-bursty session's per-capture synthesis stays cheap.

None of this changes synthesis inputs/outputs — only *when* (and whether) it runs — so the eval
golden-set is unaffected. See [docs/backend/processing.md](../backend/processing.md) "Pro report
synthesis" for the dispatch mechanics and
[docs/architecture/pipeline-versioning.md](../architecture/pipeline-versioning.md) for the version store.

## 6. UI

Calm, bilingual (fa/en) + RTL. An "AI usage" card in Settings (ring + % + reset date + plan context)
and a non-blocking amber notice near the capture flow at approaching/at-limit ("captures are still
saved; AI enrichment resumes next cycle"). Nothing renders for Basic. See
`apps/frontend/src/features/aiUsage/`.
