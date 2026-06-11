# Compute-Cost Model — per-plan COGS & minimum profitable price

> **Scope:** monthly **compute cost only** (infra + AI). **No** human, support, sales, payment-fee,
> or other costs. Three plans: **aesthetics-Basic**, **aesthetics-Pro**, **therapy**. Sized for
> **50 clinics**. From COGS we derive a **minimum profitable monthly per-clinic price**.
> **Pre-PMF — every number is a tunable assumption, not a fact.** Change the **bold input cells** and
> the formulas recompute. Method for token sizing: **tokens ≈ characters ÷ 4**, grounded in the real
> job payloads/prompts (`apps/ai_engine/ai_engine/processing.py`,
> `apps/backend/app/services/{ai_jobs.py, patient_memory_intelligence.py, capabilities.py}`).

---

## 0. TL;DR (illustrative — uses placeholder infra prices in §1; AI is exact)

| Plan | AI $/clinic/mo | Infra $/clinic/mo* | **COGS $/clinic/mo** | **Min price @ 80% GM** | ×50 COGS/mo |
|---|--:|--:|--:|--:|--:|
| **aes-Basic** (zero AI) | **$0.00** | ~$5.30 | **~$5.30** | **~$27** | ~$265 |
| **aes-Pro** — gemini-**lite** | $4.15 | ~$5.34 | **~$9.49** | **~$47** | ~$475 |
| **aes-Pro** — gemini-**3.5** | $11.55 | ~$5.34 | **~$16.89** | **~$84** | ~$845 |
| **therapy** — gemini-**lite** | $41.11 | ~$5.08 | **~$46.19** | **~$231** | ~$2,309 |
| **therapy** — gemini-**3.5** | $187.50 | ~$5.08 | **~$192.55** | **~$963** | ~$9,627 |

\* Infra uses **illustrative** unit prices (clearly flagged in §1) and a year-1-average storage figure.
**Replace the §1 input cells with your provider's real prices** — AI numbers are exact under the given rates.

**Headlines:**
1. **aes-Basic costs almost nothing and zero AI** — it's pure storage + egress + a slice of shared compute.
2. **Therapy transcription minutes are the dominant cost of the whole platform.** A 48-min session on
   **gemini-3.5** costs **$0.47** to transcribe; on **-lite**, **$0.10**. ×396 sessions/clinic/mo that is
   **$186 vs $40** — a **~$146/clinic/mo** swing on one model choice. **-lite is effectively mandatory for therapy economics.**
3. Every non-transcription LLM task is **sub-cent**; they sum to only **~$2.1/clinic/mo (aes-Pro)** and **~$1.2 (therapy)**.
4. **Aesthetics photo storage + egress** is the #2 driver, but at these volumes it's single-dollar.

---

## 1. Inputs you must supply (infra unit prices) — **owner action**

These are the only unknowns. Quantities (GB, vCPU, instances) are computed in §5; **you supply the
unit price** for your cloud/CDN/local provider. The *italic* value is an **illustrative placeholder**
used to produce the §0 / §6 numbers — **swap in your real prices.**

| # | Input cell | Unit | Placeholder used | Drives |
|---|---|---|--:|---|
| P1 | **App/API instance** (2 vCPU / 4 GB) | $/instance-mo | *$24* | compute |
| P2 | **AI-worker instance** (2 vCPU / 4 GB) | $/instance-mo | *$24* | compute |
| P3 | **Managed Postgres** (2 vCPU / 8 GB) | $/mo | *$60* | compute |
| P4 | **Managed Redis** (1 GB) | $/mo | *$15* | compute |
| P5 | **Load balancer** | $/mo | *$12* | compute |
| P6 | **DNS zone** | $/mo | *$5* | compute |
| P7 | **DB block storage** (~100 GB) | $/mo | *$10* | compute |
| P8 | **Object storage** | **$/GB-month** | *$0.015* | media storage |
| P9 | **Egress / CDN bandwidth** | **$/GB** | *$0.02* | serving media |
| P10 | (opt.) CDN requests | $/10k req | *$0* | serving media |

**Two prices matter most — please confirm them precisely:** **P8 ($/GB-mo)** and **P9 ($/GB egress)**.
Egress especially ranges from **$0.00** (Cloudflare R2) to **~$0.09** (AWS S3) per GB; the placeholder
$0.02 assumes a cheap CDN (e.g. Bunny/B2). Compute (P1–P7) is a **fixed platform cost shared by all 50
clinics**, so per-clinic it's small.

> **AI rates are given and fixed** (you do **not** supply these):
> Transcription — **gemini-3.5-flash = $0.0098/audio-min**, **gemini-3.1-flash-lite = $0.0021/audio-min**
> (both already include prompt overhead). LLM tasks — **gpt-5.4-nano = $0.20 / 1M input tok, $1.25 / 1M output tok.**

---

## 2. Usage assumptions (tunable) — how these clinics actually run

Small/medium private Iranian clinics. Treat every cell as an editable assumption.

### 2a. Aesthetics (Basic **and** Pro share the same visit volume)

| Assumption | Cell | Default | Note |
|---|---|--:|---|
| Doctors / clinic | `A_doc` | **2** | injectors |
| Visits / day / doctor | `A_vpd` | **10** | short 15–30 min visits |
| Working days / month | `A_days` | **24** | ~6-day week, minus holidays |
| **Visits / clinic / month** | `A_visits` | **= 2×10×24 = 480** | |
| Photos / visit | `A_photos` | **6** | before/after, multi-angle |
| MB / photo | `A_mbph` | **3** | compressed phone JPEG |
| Notes / visit | `A_notes` | **1** | |
| **Pro** dictation min / visit | `A_aud` | **2** | short procedure note |
| MB / audio-minute | `mb_min` | **0.6** | compressed (AAC/Opus) |
| **Pro** Q&A drafts / clinic / day | `A_qa` | **3** | → 72/mo |

### 2b. Therapy (single plan)

| Assumption | Cell | Default | Note |
|---|---|--:|---|
| Therapists / clinic | `T_thr` | **3** | |
| Sessions / day / therapist | `T_spd` | **6** | 50-min hours + breaks |
| Working days / month | `T_days` | **22** | |
| **Sessions / clinic / month** | `T_sess` | **= 3×6×22 = 396** | |
| **Audio minutes / session** | `T_aud` | **48** | the 50-min therapy hour — **the cost driver** |
| MB / audio-minute | `mb_min` | **0.6** | |
| Notes / session | `T_notes` | **1** | |
| Photos / session | `T_photos` | **0** | talk therapy; raise for derm-style |

---

## 3. What AI actually runs per plan (from the capability matrix)

Source of truth: `capabilities.py` + redesign-foundation §3. **Critical:** matching and
out-of-context detection are **$0 incremental** — they're emitted by the *same* transcription call
(`patient_information` + `intents` in the structured JSON), and matching itself is
**deterministic** (`deterministic-patient-matching`, no LLM). The session/live report is **deterministic
today**; the *agreed* Pro feature set (§3 Pro #3) upgrades it to a real LLM synthesis, modeled here.

| Capability | Calls | aes-Basic | aes-Pro | therapy | Billed as |
|---|---|:-:|:-:|:-:|---|
| Transcription (+ identity + intents folded in) | per audio capture | — | ✓ | ✓ | **audio-min × rate** |
| Patient matching | per audio | — | ✓ | ✓ | **$0 (deterministic)** |
| Out-of-context detection | per audio | — | ✓ | ✓ | **$0 (in transcription JSON)** |
| Image caption | per photo | — | ✓ | ✓* | LLM tokens (vision) |
| Note decoration | per note | — | ✓ | ✓ | LLM tokens |
| Structured session report | per visit/session | — | ✓ | ✓ | LLM tokens |
| Cross-visit synthesis (patient memory) | per visit/session | — | ✓ | ✓ | LLM tokens |
| Pre-session brief (therapy) | per session | — | — | ✓ | (reuses synthesis) |
| Post-session Q&A | occasional | — | ✓ | — | LLM tokens |

\* therapy default has 0 photos, so captions ≈ $0 there.

### 3a. Per-task token estimates (method: chars ÷ 4, from real prompts/payloads) & unit cost

| Task | Input tok | Output tok | $ / call | Basis |
|---|--:|--:|--:|---|
| Image caption | 1,800 | 40 | **$0.00041** | downsized image ~1,500 + ~300-tok prompt; 1–2-sentence caption out |
| Note decoration | 450 | 90 | **$0.00020** | ~350-tok prompt + short note in/out |
| Structured report (aes visit) | 2,000 | 600 | **$0.00115** | 1–2 transcripts + notes + captions + v1 7-section template |
| Cross-visit synthesis | 1,000 | 300 | **$0.00058** | prior memory + ≤8 distilled briefs (not raw transcripts) |
| Post-session Q&A | 1,500 | 120 | **$0.00045** | patient context + prior answers + question → drafted reply |
| Therapy session summary | 8,000 | 500 | **$0.00223** | **full ~48-min transcript in** (~6.5k words) → narrative summary |
| Therapy pre-session brief | 1,000 | 300 | **$0.00058** | same as synthesis (briefs, not transcripts) |

> `$/call = input_tok × 0.20/1e6 + output_tok × 1.25/1e6`. All non-transcription tasks are **sub-cent**;
> the synthesis/brief tasks stay flat as visits grow (they consume distilled briefs, not raw transcripts —
> see `build_patient_memory_job_input`, capped at 8 briefs).

---

## 4. AI cost per clinic / month

### 4a. aes-Basic
**AI = $0.00.** No transcription, no LLM, no jobs — by design (zero-AI value floor). ✔ stated explicitly.

### 4b. aes-Pro (per visit, then × `A_visits` = 480, + Q&A)

| Component | Per-visit (gemini-3.5) | Per-visit (gemini-lite) |
|---|--:|--:|
| Transcription `A_aud × rate` = 2 × rate | $0.01960 | $0.00420 |
| Captions `A_photos × 0.00041` = 6× | $0.00246 | $0.00246 |
| Decoration `A_notes × 0.00020` = 1× | $0.00020 | $0.00020 |
| Structured report (1×) | $0.00115 | $0.00115 |
| Cross-visit synthesis (1×) | $0.00058 | $0.00058 |
| **Per visit** | **$0.02399** | **$0.00859** |
| **× 480 visits** | **$11.51** | **$4.12** |
| Q&A `72 × 0.00045` | $0.03 | $0.03 |
| **aes-Pro AI / clinic / mo** | **≈ $11.55** | **≈ $4.15** |

Non-transcription tasks total only **$0.00439/visit → ~$2.11/clinic/mo** (+Q&A $0.03). Transcription is
**81% (3.5) / 49% (lite)** of Pro AI.

### 4c. therapy (per session, then × `T_sess` = 396)

| Component | Per-session (gemini-3.5) | Per-session (gemini-lite) |
|---|--:|--:|
| Transcription `T_aud × rate` = 48 × rate | $0.47040 | $0.10080 |
| Session summary (1×) | $0.00223 | $0.00223 |
| Pre-session brief / synthesis (1×) | $0.00058 | $0.00058 |
| Note decoration (1×) | $0.00020 | $0.00020 |
| **Per session** | **$0.47341** | **$0.10381** |
| **× 396 sessions** | **≈ $187.5** | **≈ $41.1** |

Non-transcription is **$0.003/session → ~$1.19/clinic/mo**. Transcription is **>99%** of therapy AI.
**This is the platform's single biggest lever.**

---

## 5. Infra cost (parameterized) — quantities computed, unit prices from §1

### 5a. Storage added per clinic / month (cumulative — it compounds)

`photo_GB = A_photos × A_mbph × A_visits / 1024` · `audio_GB = min × mb_min × count / 1024`

| Plan | Photo GB/mo | Audio GB/mo | **GB added / clinic / mo** |
|---|--:|--:|--:|
| aes-Basic | 6×3×480/1024 = **8.44** | ~0.1 (voice memos) | **≈ 8.5** |
| aes-Pro | 8.44 | 2×0.6×480/1024 = **0.56** | **≈ 9.0** |
| therapy | 0 | 48×0.6×396/1024 = **11.14** | **≈ 11.1** |

> **Storage compounds**: stored GB ≈ `months × GB_added` (minus any deletion/lifecycle). Monthly storage
> **bill grows linearly**. We report a **year-1 average** = `6.5 × GB_added × P8`. Headline cost at
> **month 12** is ~2× that; long-run, set a **retention/lifecycle policy** or this becomes the slow driver.

| Plan | Yr-1-avg stored GB (6.5×) | **Storage $/clinic/mo @ P8=$0.015** | (month-12) |
|---|--:|--:|--:|
| aes-Basic | 55.3 | **$0.83** | $1.53 |
| aes-Pro | 58.5 | **$0.88** | $1.62 |
| therapy | 72.2 | **$1.08** | $2.00 |

### 5b. Egress / CDN per clinic / month

`egress_GB = view_mult × photo_GB` (media re-served to staff, before/after compares, patient reports).
Therapy audio is rarely re-streamed → low.

| Plan | view_mult | Egress GB/mo | **Egress $/clinic/mo @ P9=$0.02** |
|---|--:|--:|--:|
| aes-Basic | **3** | 25.3 | **$0.51** |
| aes-Pro | **3** | 25.3 | **$0.51** |
| therapy | — | ~2 | **$0.04** |

### 5c. Compute (fixed platform footprint — shared by all 50 clinics)

Models run on **external gateways** (gemini, gpt-5.4-nano), so our servers only orchestrate + do light
ffmpeg conversion → modest footprint. Load for ~24k aes visits + ~20k therapy sessions/mo is low average
QPS but bursty.

| Component | Qty | Sizing | Input cell |
|---|--:|---|---|
| App/API | 2 | 2 vCPU / 4 GB (HA) | P1 |
| AI worker (Celery) | 2 | 2 vCPU / 4 GB | P2 |
| Postgres (managed) | 1 | 2 vCPU / 8 GB | P3 |
| Redis (managed) | 1 | 1 GB | P4 |
| Load balancer | 1 | — | P5 |
| DNS | 1 | — | P6 |
| DB block storage | 1 | ~100 GB (metadata only; media in object store) | P7 |

`fixed_compute/mo = 2·P1 + 2·P2 + P3 + P4 + P5 + P6 + P7`
Illustrative = 2·24 + 2·24 + 60 + 15 + 12 + 5 + 10 = **$198/mo** → **÷50 = $3.96/clinic/mo** (≈ $4).

> Self-hosting Postgres/Redis on the app boxes can cut this further; managed prices shown. Scale workers
> with volume (knob), but transcription concurrency lives at the gateway, not here.

### 5d. Infra total per clinic / month (illustrative, year-1 avg)

| Plan | Compute | Storage | Egress | **Infra $/clinic/mo** |
|---|--:|--:|--:|--:|
| aes-Basic | $3.96 | $0.83 | $0.51 | **≈ $5.30** |
| aes-Pro | $3.96 | $0.88 | $0.51 | **≈ $5.34** |
| therapy | $3.96 | $1.08 | $0.04 | **≈ $5.08** |

---

## 6. Totals — AI vs infra, per clinic & ×50 (both gemini options)

| Plan | AI | Infra | **COGS/clinic/mo** | **×50 / mo** | **×50 / yr** |
|---|--:|--:|--:|--:|--:|
| **aes-Basic** | $0.00 | $5.30 | **$5.30** | $265 | $3,180 |
| **aes-Pro** · lite | $4.15 | $5.34 | **$9.49** | $475 | $5,694 |
| **aes-Pro** · 3.5 | $11.55 | $5.34 | **$16.89** | $845 | $10,134 |
| **therapy** · lite | $41.11 | $5.08 | **$46.19** | $2,309 | $27,714 |
| **therapy** · 3.5 | $187.50 | $5.08 | **$192.55** | $9,627 | $115,530 |

Recompute formula per plan:
`COGS = AI(usage, rate) + fixed_compute/50 + (6.5 × GB_added × P8) + (egress_GB × P9)`

---

## 7. Minimum profitable monthly price per plan

**Definition.** *Break-even* = COGS (compute floor; below this you lose money on infra+AI alone).
*Minimum profitable* = `COGS ÷ (1 − target_GM)`. **Recommended target gross margin = 80%** — the healthy-
SaaS standard, and necessary here because **COGS excludes all human/support/sales cost**; the 80% headroom
is what funds those + profit. (Sensitivity: 70% and 50% shown.)

| Plan | COGS | **Break-even** | **@ 80% GM (rec.)** | @ 70% GM | @ 50% GM |
|---|--:|--:|--:|--:|--:|
| aes-Basic | $5.30 | $5.30 | **$27** | $18 | $11 |
| aes-Pro · lite | $9.49 | $9.49 | **$47** | $32 | $19 |
| aes-Pro · 3.5 | $16.89 | $16.89 | **$84** | $56 | $34 |
| therapy · lite | $46.19 | $46.19 | **$231** | $154 | $92 |
| therapy · 3.5 | $192.55 | $192.55 | **$963** | $642 | $385 |

**Take the recommended (80% GM) prices to compare against clinic income.** If a clinic's monthly revenue
makes (e.g.) **$231/therapist-trio** or **$48/aes-Pro clinic** trivial, the plan is comfortably profitable;
if not, push to gemini-lite and/or a metered model (§9).

---

## 8. Cost drivers & sensitivity (what moves the number)

1. **Therapy transcription minutes — by far #1.** Linear in `T_sess × T_aud`. The
   **gemini-3.5 → lite swap saves ~$146/clinic/mo (~$7.3k/mo across 50)** at near-equal everything else.
   **Default therapy to -lite**; reserve 3.5 for clips where accuracy is proven to matter.
2. **gemini-3.5 vs -lite swing** (transcription only):

   | | per audio-min | aes-Pro/clinic/mo | therapy/clinic/mo |
   |---|--:|--:|--:|
   | 3.5 | $0.0098 | $9.41 transcription | $186.3 |
   | lite | $0.0021 | $2.02 transcription | $39.9 |
   | **Δ** | | **$7.4** | **$146.4** |
3. **Aesthetics photo storage + egress — #2, but single-dollar** at these volumes. Sensitive to
   `A_photos`, `A_mbph`, `view_mult`, **P8/P9**. **Egress provider matters**: free-egress object store
   (R2) zeroes the egress line; S3-class ($0.09/GB) ~4.5×'s it (still only ~$2.3/clinic/mo).
4. **Storage compounding** — flat each month but cumulative; year-3 storage ≈ 3× year-1. A retention
   policy (e.g. archive/cold-tier media > 24 mo) caps it.
5. **Non-transcription LLM is noise** — all of captions+decoration+report+synthesis+Q&A is
   **~$2.1/clinic/mo (aes-Pro)** and **~$1.2 (therapy)**. Don't optimize here first.

---

## 9. Revenue model — flat per-clinic vs. metered (recommendation)

**Default (assumed): flat monthly per-clinic subscription.** Good fit for **aes-Basic/Pro** — their COGS is
**storage/photo-bound and predictable**; a flat price per clinic rarely gets blown out by a heavy user.

**Therapy needs a usage component.** Therapy COGS is **~90% linear in audio-minutes**, so a flat price
carries real variance risk: a clinic running 2× sessions **doubles** your COGS while paying the same.
Recommended hybrid:

- **Per-seat base** (per therapist) — captures the seat-linear part, and
- **Included minutes + overage** (e.g. *N* transcription-minutes/seat/mo bundled, then **$/min** above) —
  passes the one volatile driver straight through.

This keeps therapy gross margin stable regardless of how busy a clinic gets, and it's the natural place to
price the gemini-3.5↔lite quality choice as a tier. **Aesthetics can stay flat per-clinic** (Basic vs Pro
is already the value line); only add metering there if photo volumes turn out far heavier than `A_*` assume.

---

## 10. Caveats & method notes

- **Agreed vs. built.** AI here models the **agreed feature set** (redesign-foundation §3). Today's code is
  even cheaper: the session report is **deterministic (no LLM)**, Q&A isn't built, matching is deterministic.
  So these are **ceiling** AI numbers for the agreed product, not today's spend.
- **No double-counting.** Transcription rate **includes prompt overhead** and emits identity+intents in one
  call → matching/out-of-context are **$0 incremental**.
- **Tokens ≈ chars ÷ 4**, sized from real prompts (`processing.py`) and input builders
  (`build_patient_memory_job_input`, `build_session_processing_input`). Image-caption input tokens are a
  vision-model estimate (~1.5k/photo); adjust if your gateway tokenizes images differently.
- **Excluded by scope:** retries/failed jobs (small uplift — exponential backoff, capped), dev/staging
  infra, backups, monitoring, payment fees, and **all human cost**.
- **Storage** reported as a **year-1 average**; it grows monthly — see §5a.
- Everything keys off **§1 inputs** and **§2 assumptions** — change a bold cell, re-run the formulas.
