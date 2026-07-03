# Compute-Cost Model — per-plan COGS & minimum profitable price

> **Superseded in part (2026-07).** The **AI-COGS** sections here (§3–§4, and the AI columns of
> §0/§6–§7) predate the shipped LLM report synthesis and assumed a *deterministic* report. Measured
> numbers live in [ai-usage-limits.md](ai-usage-limits.md): per-capture synthesis ≈ **$0.0203/visit**
> (~18× the $0.00115 modeled here), putting headline Pro AI cost at roughly **2×** this doc's figure.
> **Still canonical:** infra unit costs (§1, §5), storage compounding (§5a), fixed-compute levers
> (§5c), the minimum-profitable-price *methodology* (§7), and the revenue-model rationale (§9).
> Current price anchors: [pricing.md](pricing.md).

> **Scope:** monthly **compute cost only** (infra + AI). **No** human, support, sales, payment-fee,
> or other costs. Three plans: **aesthetics-Basic**, **aesthetics-Pro**, **therapy**. Sized for
> **50 clinics**. From COGS we derive a **minimum profitable monthly per-clinic price**.
> **Pre-PMF — every number is a tunable assumption, not a fact.** Change the **bold input cells** and
> the formulas recompute. Method for token sizing: **tokens ≈ characters ÷ 4**, grounded in the real
> job payloads/prompts (`apps/ai_engine/ai_engine/processing.py`,
> `apps/backend/app/services/{ai_jobs.py, patient_memory_intelligence.py, capabilities.py}`).
>
> **v2 changes:** (1) **therapy is capture-style, not ambient** — short in-session + post-session
> captures by the therapist (like aesthetics), **not** whole-session recording. This collapses
> therapy's transcription minutes ~8×. (2) Real **infra unit prices** plugged in (§1). (3) Added the
> self-hosted **AI gateway** server to fixed compute.

---

## 0. TL;DR

| Plan | AI $/clinic/mo | Infra $/clinic/mo | **COGS $/clinic/mo** | **Min price @ 80% GM** | ×50 COGS/mo |
|---|--:|--:|--:|--:|--:|
| **aes-Basic** (zero AI) | **$0.00** | $5.72 | **$5.72** | **~$29** | ~$286 |
| **aes-Pro** — gemini-**lite** | $4.15 | $5.89 | **$10.04** | **~$50** | ~$502 |
| **aes-Pro** — gemini-**3.5** | $11.55 | $5.89 | **$17.43** | **~$87** | ~$872 |
| **therapy** — gemini-**lite** | $5.83 | $4.22 | **$10.06** | **~$50** | ~$503 |
| **therapy** — gemini-**3.5** | $24.13 | $4.22 | **$28.35** | **~$142** | ~$1,418 |

AI numbers are **exact** under the given rates; infra uses **your supplied prices** (§1) and a
year-1-average storage figure (storage compounds — §5a).

**Headlines:**
1. **aes-Basic costs almost nothing and zero AI** — pure storage + egress + a slice of shared compute (~$5.7).
2. **With capture-style therapy, therapy ≈ aes-Pro** (~$10 lite COGS each). Therapy is **no longer** a
   cost outlier — that was the ambient-recording assumption. Therapy still carries **2.5× the
   transcription minutes** of aes-Pro (2,376 vs 960 audio-min/clinic/mo) because it has more
   encounters, so its 3.5 COGS ($28) runs above aes-Pro's ($17).
3. **Transcription minutes are still the #1 driver.** The **gemini-3.5 → -lite** swap saves
   **$7.4/clinic/mo (aes-Pro)** and **$18.3 (therapy)** — meaningful (~$900/mo across 50 for therapy)
   but no longer existential. **-lite is the sensible default; reserve 3.5 where accuracy is proven to matter.**
4. Every non-transcription LLM task is **sub-cent**; they sum to **~$2.1/clinic/mo (aes-Pro)**,
   **~$0.8 (therapy)**. Don't optimize there first.
5. **Aesthetics photo storage + egress** is the #2 driver but still single-dollar at these volumes.

---

## 1. Infra unit prices (supplied by owner) — **plugged in**

| # | Input cell | Unit | **Value used** | Note |
|---|---|---|--:|---|
| P1 | App/API instance (2 vCPU / 4 GB) | $/instance-mo | **$15** | given range $10–20; midpoint |
| P2 | AI-worker instance (2 vCPU / 4 GB) | $/instance-mo | **$15** | given range $10–20; midpoint |
| P3 | **AI-gateway** server (4 vCPU / 8 GB) | $/mo | **$25** | self-hosted redirector → providers |
| P4 | Managed Postgres (≈4 vCPU / 8 GB) | $/mo | **$50** | closest public plan |
| P5 | Managed Redis (1 GB) | $/mo | **$10.5** | |
| P6 | Load balancer (Layer-4 proxy) | $/mo | **$40** | self-host on app boxes → $0 (lever) |
| P7 | DNS zone | $/mo | **$0** | |
| P8 | DB block storage (~100 GB) | $/mo | **$15** | given range $10–19; midpoint |
| P9 | **Object storage** | **$/GB-month** | **$0.020** | media at rest |
| P10 | **Object-storage egress** | **$/GB** | **$0.012** | reads out of object store (AI processing, CDN fill) |
| P11 | **CDN egress** | **$/GB** | **$0.020** | media delivered to end users |
| P12 | CDN requests | $/10k req | **$0** | |

> **AI rates (given, fixed):** Transcription — **gemini-3.5-flash $0.0098/audio-min**,
> **gemini-3.1-flash-lite $0.0021/audio-min** (both include prompt overhead). LLM tasks —
> **gpt-5.4-nano $0.20 / 1M input tok, $1.25 / 1M output tok.** These hit the providers **through the
> self-hosted AI gateway** (P3) — a thin OpenAI-compatible redirector (matches the worker's OpenAI
> client + `base_url`); it adds **no per-token cost**, only the fixed server (P3). Audio/images leaving
> the gateway to providers ride the server's **included bandwidth** (≈0.1 TB/mo across 50 clinics → negligible).

---

## 2. Usage assumptions (tunable) — how these clinics actually run

Small/medium private Iranian clinics. Treat every cell as editable.

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

### 2b. Therapy (single plan) — **capture-style, not ambient**

Therapist makes a few **short in-session captures** + a **post-session dictation** — the aesthetics
capture pattern, **not** a recording of the whole 50-min session.

| Assumption | Cell | Default | Note |
|---|---|--:|---|
| Therapists / clinic | `T_thr` | **3** | |
| Sessions / day / therapist | `T_spd` | **6** | 50-min hours + breaks |
| Working days / month | `T_days` | **22** | |
| **Sessions / clinic / month** | `T_sess` | **= 3×6×22 = 396** | |
| In-session audio captures | `T_incap` | **2** × **1 min** | quick voice notes |
| Post-session dictation | `T_post` | **1** × **4 min** | reflective summary |
| **Audio minutes / session** | `T_aud` | **= 2×1 + 4 = 6** | **the cost driver — tune this first** |
| MB / audio-minute | `mb_min` | **0.6** | |
| Notes / session | `T_notes` | **2** | |
| Photos / session | `T_photos` | **0** | talk therapy; raise for derm-style |

> **`T_aud` is the single most important therapy assumption.** At **6 min** therapy ≈ aes-Pro; if real
> usage is **10 min/session**, therapy AI rises to **$39.6 (3.5) / $9.2 (lite)** per clinic/mo (see §8).

---

## 3. What AI actually runs per plan (from the capability matrix)

Source of truth: `capabilities.py` + [spines.md](../spines.md) §3. **Critical:** matching and out-of-context
detection are **$0 incremental** — they're emitted by the *same* transcription call
(`patient_information` + `intents` in the structured JSON), and matching itself is **deterministic**
(`deterministic-patient-matching`, no LLM). The live/session report is **deterministic today**; the
*agreed* Pro feature set (§3 Pro #3) upgrades it to a real LLM synthesis, modeled here.

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
| Image caption | 1,800 | 40 | **$0.00041** | downsized image ~1,500 + ~300-tok prompt; 1–2-sentence caption |
| Note decoration | 450 | 90 | **$0.00020** | ~350-tok prompt + short note in/out |
| Structured report (per encounter) | 2,000 | 600 | **$0.00115** | the encounter's capture transcripts/notes + v1 7-section template |
| Cross-visit synthesis | 1,000 | 300 | **$0.00058** | prior memory + ≤8 distilled briefs (not raw transcripts) |
| Post-session Q&A | 1,500 | 120 | **$0.00045** | patient context + prior answers + question → drafted reply |

> `$/call = input_tok × 0.20/1e6 + output_tok × 1.25/1e6`. Because therapy is **capture-style**, its
> structured-report input is the short capture transcripts (≈2k tok), **not** a 6.5k-word full-session
> transcript — so therapy uses the same per-encounter report cost as aesthetics. Synthesis/brief stay
> flat as visits grow (they consume distilled briefs, not transcripts — `build_patient_memory_job_input`, ≤8 briefs).

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

Transcription is **81% (3.5) / 49% (lite)** of Pro AI; non-transcription totals **~$2.1/clinic/mo**.

### 4c. therapy — **capture-style** (per session, then × `T_sess` = 396)

| Component | Per-session (gemini-3.5) | Per-session (gemini-lite) |
|---|--:|--:|
| Transcription `T_aud × rate` = 6 × rate | $0.05880 | $0.01260 |
| Structured session report (1×) | $0.00115 | $0.00115 |
| Pre-session brief / synthesis (1×) | $0.00058 | $0.00058 |
| Note decoration `T_notes × 0.00020` = 2× | $0.00040 | $0.00040 |
| **Per session** | **$0.06093** | **$0.01473** |
| **× 396 sessions** | **≈ $24.13** | **≈ $5.83** |

Transcription is **96% (3.5) / 86% (lite)** of therapy AI; non-transcription totals **~$0.84/clinic/mo**.
Therapy's higher 3.5 number vs aes-Pro is purely **more transcription minutes** (396 sessions × 6 min =
**2,376 min/mo** vs aes-Pro 480 × 2 = **960 min/mo**).

---

## 5. Infra cost (computed quantities × §1 prices)

### 5a. Storage added per clinic / month (cumulative — it compounds)

`photo_GB = A_photos × A_mbph × A_visits / 1024` · `audio_GB = min × mb_min × count / 1024`

| Plan | Photo GB/mo | Audio GB/mo | **GB added / clinic / mo** |
|---|--:|--:|--:|
| aes-Basic | 6×3×480/1024 = **8.44** | ~0.1 (voice memos) | **≈ 8.5** |
| aes-Pro | 8.44 | 2×0.6×480/1024 = **0.56** | **≈ 9.0** |
| therapy | 0 | 6×0.6×396/1024 = **1.39** | **≈ 1.4** |

> **Storage compounds**: stored GB ≈ `months × GB_added` (minus deletion/lifecycle). The monthly bill
> **grows linearly**. We report a **year-1 average** = `6.5 × GB_added × P9`; month-12 is ~2× that. Set a
> **retention/lifecycle policy** (cold-tier media > 24 mo) to cap the long run. Therapy storage is now tiny.

| Plan | Yr-1-avg stored GB (6.5×) | **Storage $/clinic/mo @ P9=$0.020** | (month-12) |
|---|--:|--:|--:|
| aes-Basic | 55.3 | **$1.11** | $2.05 |
| aes-Pro | 58.5 | **$1.17** | $2.16 |
| therapy | 9.0 | **$0.18** | $0.33 |

### 5b. Egress / bandwidth per clinic / month

Three components — all small: **(i)** client media delivery via CDN, **(ii)** origin→CDN cache fill,
**(iii)** the worker reading each media once from object storage to send to the AI gateway.

`served_GB = view_mult × media_GB` · fill assumes 70% CDN cache-hit (`0.3 × served`)

| Plan | (i) CDN deliver `served×P11` | (ii) Origin fill `0.3×served×P10` | (iii) AI reads `media×P10` | **Egress $/clinic/mo** |
|---|--:|--:|--:|--:|
| aes-Basic | 25.3 GB → $0.506 | $0.091 | $0 (no AI) | **$0.60** |
| aes-Pro | 25.3 GB → $0.506 | $0.091 | 9.0 GB → $0.108 | **$0.71** |
| therapy | 0.7 GB → $0.014 | $0.003 | 1.4 GB → $0.017 | **$0.03** |

(`view_mult` = **3** for aesthetics photos; therapy audio rarely re-streamed → **0.5**.)

### 5c. Compute (fixed platform footprint — shared by all 50 clinics)

Models run on **external providers via the AI gateway** (P3), so our servers only orchestrate + light
ffmpeg conversion → modest footprint.

| Component | Qty | Sizing | Cell | $/mo |
|---|--:|---|---|--:|
| App/API | 2 | 2 vCPU / 4 GB (HA) | P1 | $30 |
| AI worker (Celery) | 2 | 2 vCPU / 4 GB | P2 | $30 |
| **AI gateway** | 1 | 4 vCPU / 8 GB | P3 | $25 |
| Postgres (managed) | 1 | ≈4 vCPU / 8 GB | P4 | $50 |
| Redis (managed) | 1 | 1 GB | P5 | $10.5 |
| Load balancer | 1 | Layer-4 | P6 | $40 |
| DNS | 1 | — | P7 | $0 |
| DB block storage | 1 | ~100 GB | P8 | $15 |
| **Fixed total** | | | | **$200.5/mo** |

`fixed_compute = 2·P1 + 2·P2 + P3 + P4 + P5 + P6 + P7 + P8 = $200.5` → **÷50 = $4.01/clinic/mo**
(range with the given instance/block bands: **$175.5–224.5/mo → $3.51–4.49/clinic**).

> **Levers:** self-hosting Postgres/Redis on the app boxes and dropping the managed LB (P6 $40 → $0,
> proxy on the app instances) takes fixed compute toward ~$110/mo (~$2.2/clinic). The AI gateway being a
> thin redirector, one $25 box serves all 50 clinics; scale it only if request QPS demands.

### 5d. Infra total per clinic / month (year-1 avg)

| Plan | Compute | Storage | Egress | **Infra $/clinic/mo** |
|---|--:|--:|--:|--:|
| aes-Basic | $4.01 | $1.11 | $0.60 | **$5.72** |
| aes-Pro | $4.01 | $1.17 | $0.71 | **$5.89** |
| therapy | $4.01 | $0.18 | $0.03 | **$4.22** |

---

## 6. Totals — AI vs infra, per clinic & ×50 (both gemini options)

| Plan | AI | Infra | **COGS/clinic/mo** | **×50 / mo** | **×50 / yr** |
|---|--:|--:|--:|--:|--:|
| **aes-Basic** | $0.00 | $5.72 | **$5.72** | $286 | $3,430 |
| **aes-Pro** · lite | $4.15 | $5.89 | **$10.04** | $502 | $6,024 |
| **aes-Pro** · 3.5 | $11.55 | $5.89 | **$17.43** | $872 | $10,459 |
| **therapy** · lite | $5.83 | $4.22 | **$10.06** | $503 | $6,034 |
| **therapy** · 3.5 | $24.13 | $4.22 | **$28.35** | $1,418 | $17,011 |

Recompute formula per plan:
`COGS = AI(usage, rate) + fixed_compute/50 + (6.5 × GB_added × P9) + egress(P10,P11)`

---

## 7. Minimum profitable monthly price per plan

**Definition.** *Break-even* = COGS (compute floor; below this you lose money on infra+AI alone).
*Minimum profitable* = `COGS ÷ (1 − target_GM)`. **Recommended target gross margin = 80%** — the
healthy-SaaS standard, and necessary here because **COGS excludes all human/support/sales cost**; the
80% headroom funds those + profit. (Sensitivity: 70% and 50% shown.)

| Plan | COGS | **Break-even** | **@ 80% GM (rec.)** | @ 70% GM | @ 50% GM |
|---|--:|--:|--:|--:|--:|
| aes-Basic | $5.72 | $5.72 | **$29** | $19 | $11 |
| aes-Pro · lite | $10.04 | $10.04 | **$50** | $33 | $20 |
| aes-Pro · 3.5 | $17.43 | $17.43 | **$87** | $58 | $35 |
| therapy · lite | $10.06 | $10.06 | **$50** | $34 | $20 |
| therapy · 3.5 | $28.35 | $28.35 | **$142** | $95 | $57 |

**Take the recommended (80% GM) prices to compare against clinic income.** All three plans now sit in a
**$29–$142/clinic/mo** band — a far easier sell than the old ambient-therapy estimate. On **-lite**,
**aes-Pro and therapy are both ~$50/clinic/mo**; if a clinic's monthly revenue makes $50 trivial,
the plans are comfortably profitable on compute.

---

## 8. Cost drivers & sensitivity (what moves the number)

1. **Transcription minutes — still #1.** Linear in `count × audio-min`. Aesthetics = 960 min/clinic/mo;
   therapy = 2,376 (more encounters × 6 min). **`T_aud` is the therapy lever** — re-run it if real
   capture behavior differs:

   | therapy `T_aud` | AI 3.5 /clinic/mo | AI lite /clinic/mo |
   |---|--:|--:|
   | 6 min (default) | $24.13 | $5.83 |
   | 10 min | $39.65 | $9.16 |
   | 20 min | $78.46 | $17.47 |
   | 48 min (ambient — *not* our model) | $187.5 | $41.1 |

2. **gemini-3.5 vs -lite swing** (transcription only):

   | | per audio-min | aes-Pro /clinic/mo | therapy /clinic/mo |
   |---|--:|--:|--:|
   | 3.5 | $0.0098 | $9.41 | $23.28 |
   | lite | $0.0021 | $2.02 | $4.99 |
   | **Δ** | | **$7.4** | **$18.3** |

   Across 50 clinics, defaulting therapy to **-lite** saves **~$915/mo**. Recommended default; reserve 3.5 for clips where accuracy is proven to matter.
3. **Aesthetics photo storage + egress — #2, single-dollar.** Sensitive to `A_photos`, `A_mbph`,
   `view_mult`, **P9/P11**. With **$0.020/GB** object storage and a CDN at **$0.020/GB**, aesthetics
   storage+egress ≈ **$1.8/clinic/mo** (year-1) and grows with the photo archive.
4. **Storage compounding** — flat monthly but cumulative; year-3 aesthetics storage ≈ 3× year-1. A
   retention/cold-tier policy caps it. Therapy storage is negligible now (~$0.18).
5. **Fixed compute is the floor for small fleets** — $4/clinic at 50 clinics, but it's *fixed*, so at 20
   clinics it's $10/clinic and at 100 it's $2. The managed LB (P6) + Postgres (P4) are 45% of it; the
   §5c levers cut it roughly in half.
6. **Non-transcription LLM is noise** — captions+decoration+report+synthesis+Q&A = **~$2.1 (aes-Pro)** /
   **~$0.8 (therapy)** per clinic/mo. Don't optimize here first.

---

## 9. Revenue model — flat per-clinic works; meter only if minutes spike

**Default (assumed): flat monthly per-clinic subscription.** With **capture-style therapy**, all three
plans have **modest, predictable COGS** ($6–$28/clinic/mo), so a flat per-clinic price is a clean fit —
the old reason to meter therapy (ambient minutes blowing out COGS) is gone.

**Keep one guardrail for therapy.** Therapy COGS is still ~90% transcription-minute-linear, so a clinic
that captures far more than `T_aud`=6 min/session drifts up (§8 table). Cheapest insurance, only if
needed:

- **Per-seat base** (per therapist) — captures the seat-linear part, and
- a **fair-use minute ceiling** (e.g. bundled transcription-minutes/seat/mo, then a small **$/min**
  overage) — passes the one volatile driver through *only for outliers*.

**Aesthetics stays flat per-clinic** (Basic vs Pro is already the value line). Add metering anywhere only
if observed `A_*`/`T_aud` run well above these assumptions. The gemini-3.5↔lite quality choice is a
natural **tier** axis (e.g. "premium transcription") that also recovers its extra cost.

---

## 10. Caveats & method notes

- **Therapy = capture-style.** Modeled as short in-session + post-session captures (`T_aud`=6 min/session),
  **not** ambient whole-session recording. If a clinic opts into ambient mode, use the §8 sensitivity
  (48-min row) — its economics are an order of magnitude different.
- **Agreed vs. built (updated 2026-07).** AI here modeled the then-agreed feature set with a
  deterministic session report. That has since inverted: the live report is now a **real LLM synthesis
  job that re-runs per capture**, and post-session Q&A is built — so these AI numbers are a **floor**,
  not a ceiling. Measured costs: [ai-usage-limits.md](ai-usage-limits.md). Matching remains
  deterministic ($0).
- **No double-counting.** Transcription rate **includes prompt overhead** and emits identity+intents in one
  call → matching/out-of-context are **$0 incremental**.
- **AI gateway** (P3) is a thin OpenAI-compatible redirector (a sample runs at `194.5.193.5:8081/docs`);
  it adds **no per-token cost**, only the fixed $25 server, and its provider-bound bandwidth is within the
  server's included allowance.
- **Tokens ≈ chars ÷ 4**, sized from real prompts (`processing.py`) and input builders
  (`build_patient_memory_job_input`, `build_session_processing_input`). Image-caption input is a vision-model
  estimate (~1.5k tok/photo); adjust if your gateway tokenizes images differently.
- **Excluded by scope:** retries/failed jobs (small uplift — capped exponential backoff), dev/staging infra,
  backups, monitoring, payment fees, and **all human cost**.
- **Storage** reported as a **year-1 average**; it grows monthly — see §5a.
- Everything keys off **§1 prices** and **§2 assumptions** — change a bold cell, re-run the formulas.
