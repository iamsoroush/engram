# Eval-system upgrade — plan + proposals

**Status:** reviewed by the user 2026-07-04 — decisions recorded in the final section; nothing
built yet. The qa_draft/qa_revise golden sets moved to [qa-knowledge-epic.md](qa-knowledge-epic.md)
(approval rides that epic, per CLAUDE.md §4).

**Fold destinations (when executed):** [`docs/ai_engine/evals.md`](../ai_engine/evals.md) (new
modules, coverage table, scoring/scorecard changes, harvest pipeline as-built),
[`docs/technical-decisions.md`](../technical-decisions.md) (dated entries: CI gating stance, harvest
privacy rules), `.github/workflows/eval.yml` (the workflow itself),
[`docs/ai_engine/processing.md`](../ai_engine/processing.md) (remove the qa_draft/qa_revise
known-gap note once covered), `eval/expectations/README.md` + `eval/fixtures/RECORDING_CHECKLIST.md`
(new recording items).

Ground truth read for this plan: `apps/ai_engine/eval/` (all nine modules + `_common.py` +
`run_all.py`), the committed expectations, [`evals.md`](../ai_engine/evals.md),
[`processing.md`](../ai_engine/processing.md), `.github/workflows/eval.yml`,
[`insights-feedback.md`](../backend/insights-feedback.md) + `apps/backend/app/services/feedback.py`,
and the qa job code (`processing.py` `qa_draft_prompt`/`qa_revise_prompt`, backend
`services/qa.py` payload builders).

---

## Part 1 — `qa_draft` / `qa_revise` golden sets — MOVED to the QA knowledge epic

**Review decision (2026-07-04):** the Q&A jobs are being re-designed around a clinic QA library +
retrieval-grounded drafting — see [qa-knowledge-epic.md](qa-knowledge-epic.md). Their golden-set
scenario proposals (QD-01…12, QR-01…10, the shared deterministic gates, harness shape, and the
r01–r10 recording plan) **moved to that epic's appendix** and will be finalized against the epic's
final payload shape (retrieval exemplars change the grounding inputs, and the sets gain
retrieval-grounded cases). Approval of the sets rides that epic; nothing qa-eval gets built here.

One rule stated here because it is eval-wide (and re-confirmed in review): **non-text eval data
(audio clips, photos) is always requested from the user/clinician via the recording checklist —
never auto-generated.** No TTS audio, no generated images, anywhere in the eval system.

---

## Part 2 — Upgrades to the nine existing modules

Cross-cutting first (applies to #3–#5): `treatments_eval`, `aftercare_conflict_eval`, and
`safety_flags_eval` predate `_common.py` and are self-contained — no `knownGap` support, no judge
tier, and (`safety_flags`) naïve `in` matching instead of the tolerant `canon()` folding. **Unify
them onto the shared harness** (tolerant matchers, knownGap, judge availability, shared exit-code
policy). Pure eval-code refactor, no job changes (Decision 8).

### 1. `transcription_eval` — 9 real clips + 12 self-tests + 3 judge smoke; gates hard, judge advisory

- **Sharpest gap:** all clips are one speaker, one phone, one register; no confusable-dose minimal
  pairs (the exact failure the treatment-overlay epic cites: «بیست و چهار» heard as «بیست»), no long
  multi-fact dictation, no English/code-switch audio.
- Upgrades: **(a)** `t10–t14` recording batch: confusable-number minimal pair (24 vs 20), a ~60s
  multi-treatment monologue (completeness under length), an English clip, a fa clip with Latin brand
  + spoken lot, a second speaker. **(b)** Harvest-driven fixtures: every production transcript
  correction (Part 3a) is a candidate `tNN` — the failing utterance goes on the recording checklist
  for the user/clinician to re-record (human voice, never auto-generated). **(c)** Negative-number
  gate class: `numbersForbidden` (the *misheard*
  value must NOT appear) so minimal pairs gate both directions.

### 2. `caption_eval` — harness-only (12 self-tests + 3 judge smoke); **zero real photos**

- **Sharpest gap:** the job is only synthetically covered — `p01–p05` are the deferred fixtures.
- **The five photos (proposal, matching the committed `p01–p05.json` expectations):**
  - `p01-product-box.jpg` — a filler/botox box, **lot legible** (known: lot `PS18025`) → gates lot
    verbatim + `isProductLabel`.
  - `p02-treatment-area.jpg` — a cheek/forehead area shot → neutral objective caption, `noDiagnosis`.
  - `p03-injection-site.jpg` — injection-site close-up (fresh marks/redness visible) → objective
    findings allowed, assessment forbidden.
  - `p04-unreadable-lot.jpg` — a box with the lot **blurred/cut off** → must NOT invent a lot
    (judge `groundedNoInvention` carries this today — see upgrade (b)).
  - `p05-out-of-context.jpg` — a non-clinical photo (screenshot or parking receipt) →
    `expectOutOfContext` flag.
- **Unblocking recording:** none of the five needs a patient. p01/p04 are product boxes (photograph
  at the partner clinic during the current Tehran interview wave — add to that visit's checklist);
  p02/p03 use a **consenting staff volunteer** (a cheek photo, a pen-dot "injection site"); p05 is
  any receipt/screenshot. One 10-minute phone session → `stage`/`push`/`run`; `p01._todo` closes
  with the known lot.
- Other upgrades: **(a)** `p06` before/after pair — the `phase` gate has a self-test but no fixture.
  **(b)** Deterministic invented-lot gate for p04: a `forbiddenPattern` matcher (regex for a
  plausible lot token, e.g. `[A-Z]{1,3}[- ]?\d{3,}`) instead of leaning only on the judge.

### 3. `treatments_eval` — 12 synthetic fa cases, pass/fail, no judge, no self-tests, pre-`_common`

- **Sharpest gap:** no distractor/negative classes — every dictated dose in the set *was performed*.
  Nothing tests "mentioned but not done": plans («دفعه بعد دو سی‌سی می‌زنیم»), patient history
  recall, declined treatment.
- Upgrades: **(a)** Distractor cases: future-plan, prior-visit mention, declined-by-patient — all
  `count: 0` or must not extract the distractor dose. **(b)** Multi-capture cases (dictation split
  across 2–3 audio captures; a correction in capture 2 of capture 1's dose) — production sessions
  are multi-capture, the eval payload never is. **(c)** Structured-field **exact-match** tightening:
  `quantityText` verbatim assertion (the trust anchor) alongside the tolerant product match; seeded
  from harvested treatment corrections + (if approved) treatment-overlay edits (Part 3a). **(d)**
  Close the `s01–s04` loop: the recording checklist defines four full-visit synthesis clips but **no
  eval consumes `fixtures/synthesis/`** — add a fixture-driven path (transcribe clip → synthesize →
  treatments+aftercare gates). This is the "real noisy carried-forward session" lesson made
  permanent; clips are still unrecorded, so it also goes on the recording list.

### 4. `aftercare_conflict_eval` — 6 synthetic cases, 2 templates, pass/fail

- **Sharpest gap:** only two protocols ever offered, and no *agreement* case — a dictation that
  **restates** the protocol must be `applies`, not `conflicts` (the false-positive direction is
  untested).
- Upgrades: **(a)** Agreement case (clinician repeats the protocol's own advice → `applies`).
  **(b)** Irrelevant-template negative: add a third template (e.g. laser aftercare) that must NOT be
  selected when only botox/filler were performed. **(c)** Topic-attribution adversarial: a sun
  conflict must flag the sun clause's protocol while a same-visit massage remark leaves it alone —
  plus a `reason`/topic field assertion if the output carries one. **(d)** Consumes the `s01` real
  clip once recorded (via #3d).

### 5. `safety_flags_eval` — 8 synthetic cases incl. 2 negatives, exact-substring matching

- **Sharpest gap:** negation coverage is one plain case; no *history-vs-now* distinction («قبلاً به
  پنی‌سیلین حساسیت داشت ولی تست جدید منفی بود») and matching uses raw `in` (digit/ZWNJ brittle).
- Upgrades: **(a)** Tolerant matching via `_common.contains` (part of the harness unification).
  **(b)** Negation/temporal edge cases: resolved allergy, family history («مادرش آلرژی داره» — not
  the patient), hypothetical ("if she were pregnant"). **(c)** Over-extraction guard: aesthetic
  preferences/complaints must not become flags. **(d)** Flag-from-photo case: a caption (text
  capture in the payload) stating an allergy wristband/consent form — flags must come from any
  capture type, not just audio.

### 6. `safety_reconcile_eval` — 7 synthetic candidate-set cases

- **Sharpest gap:** tiny candidate sets (≤3 flags) and no *related-but-distinct* trap — the
  dangerous merge is penicillin vs amoxicillin (same family, distinct facts; dropping one is the
  never-drop failure).
- Upgrades: **(a)** Related-but-distinct pairs (drug-family, «حساسیت به لیدوکائین» vs «حساسیت به
  لیدوکائین موضعی با تورم شدید» — richer text, same concept → dedup, vs genuinely new severity
  info → keep/supersede). **(b)** Scale case: 10–12 accumulated flags with 2 duplicates buried —
  dedup precision at realistic panel size. **(c)** Cross-script duplicate (same allergy fa + en
  wording) → dedup. **(d)** Make the supersede case's "keep is acceptable-but-noted" an explicit
  **adv-det** tier instead of prose in a comment (report it, don't fail it).

### 7. `report_sections_eval` — 7 self-tests + 7 gateway cases, judge on all

- **Sharpest gap:** no multi-photo case (image-block ordering/coverage) and no
  contradiction-across-captures case (capture 2 corrects capture 1 — the prose must state the final
  fact, not both).
- Upgrades: **(a)** Multi-photo visit (3 photos incl. one product-label) — image blocks reference
  each real id at most once, no ghosts. **(b)** Cross-capture correction case (dose corrected in a
  later capture → only the final dose in prose; pairs with #3b). **(c)** An `en` `reportLanguage`
  case — the suite is currently fa-only end-to-end while the product contract is bilingual content.
  **(d)** Long-visit case (5+ captures) for completeness under length.

### 8. `patient_memory_eval` — 6 self-tests + 5 gateway cases (max 2 visits each)

- **Sharpest gap:** longitudinal depth — the job's whole point is long histories, but no fixture
  exceeds two visits; compression, recency weighting, and flag persistence over 6+ visits are
  untested.
- Upgrades: **(a)** Long-history patient (6–8 visits over 18 months, allergy stated once in visit 1,
  a product switch mid-history) — flags persist, `rightNow` reflects the latest visit only. **(b)**
  Superseded-fact case (pregnancy flagged, later resolved → memory must not still say pregnant —
  `forbidden` on the stale claim). **(c)** Cross-visit dose-trend recall («دوز از ۲۰ به ۲۴ واحد
  رسید») as `containsAny` groups. **(d)** Keep the name-repeat check advisory (it is cosmetic), but
  add it to the trend scorecard (Part 3c) so drift is visible.

### 9. `patient_matching_eval` — 6 real clips (m02 = knownGap) + 13 self-tests + judge smoke

- **Sharpest gap:** the `m02` near-miss knownGap is the suite's only xfail and its documented fix
  ("run matching on a pro-class model") is actionable — burn it down: verify the live model class
  for the transcription/matching path, and either retire the knownGap (it passes) or record the
  model decision in `technical-decisions.md`. A knownGap that never burns down is a silent hole in
  the keystone gate.
- Upgrades: **(a)** knownGap burn-down as above. **(b)** `m07` — name spoken mid-dictation (not as
  the lead phrase): «برای خانم محمدی امروز بیست واحد…» → extracted, `basis` implicit. **(c)** `m08`
  — two *similar-sounding existing* patients spoken about (محمدی vs محمودی) → faithful extraction of
  the one actually said, no correction to the other. **(d)** `m09` — noisy near-miss (the m02
  scenario re-recorded with clinic noise) so the fix is proven under the hard condition.

---

## Part 3 — Eval infrastructure

### 3a. Harvest-loop activation (feedback → golden cases)

**Today:** the write side is live and non-bypassable — `ai_feedback_events` rows for corrections /
confirmations / ratings / rejections across transcript, caption, treatment, patient_match, report,
brief, safety_flag; `context` PII-scrubbed at write (`scrub_context`); read via
`GET /api/v1/feedback`. **Nothing consumes it** — the loop from real clinician corrections to eval
cases is dormant.

**Proposed pipeline (v1 = an agent-run playbook, not a service):**

1. **Pull.** `scripts/eval-harvest.py`: authenticated `GET /api/v1/feedback?kind=correction` (and
   `kind=rejection`) per `aiOutputType`, newest-first, since a stored watermark (last-harvested
   `createdAt`, kept as `harvest-state.json` in the eval fixtures bucket). Output: a triage file per
   output type.
2. **Triage (agent + user).** A correction becomes a *candidate case* only when the before→after
   delta encodes a **model failure class** (wrong dose token, dropped brand, wrong/invented flag,
   mis-split treatment, name auto-corrected), not a stylistic edit. The agent classifies each row,
   drafts the matcher/judge spec from `after` (ground truth) vs `before` (the failure), and presents
   the batch; the user approves additions (same consultation rule as any golden set).
3. **Land text as-is; media only from the user.** (Loosened in the 2026-07-04 review.)
   - **No scrubbing rules for now:** harvested before/after text enters eval cases **verbatim,
     names and all** — the real names/values are part of the pipeline under test, and the alpha's
     data-handling posture accepts it. Revisit (pseudonymization, digit-stripping) before any
     external exposure of the eval set or a larger customer base; until then, no rule.
   - **Media-borne failures (audio/photo):** the harvest produces a *request to the user* — exact
     line to re-record / photo to stage goes on the recording checklist, and the user/clinician
     supplies the fixture. **Never auto-generated** (no TTS, no image generation) and never taken
     from patient media without the user explicitly providing it.
4. **Land.** Text-job cases land as inline `CASES` entries / expectations `.json`s; audio/photo
   cases land as new checklist items. Each harvest ends with a one-line ledger per module: N rows
   reviewed → M cases added.
5. **Cadence:** weekly during the current Tehran alpha wave (corrections are richest now), then
   monthly steady-state. Thumbs-down `rating` rows (report/brief) are a **second increment** — they
   need the session's captures pulled for context, so v1 handles corrections/rejections only.

**Treatment-overlay fold-in** (built — [aesthetics-stories §E11](../ux/aesthetics-stories.md); the
overlay write harvests `kind=correction, ai_output_type=treatment`): a human treatment-field edit
carries `treatmentKey + field + aiValue→value` — the most structured harvest signal available: it
converts directly into
**structured-field exact-match** treatments cases (transcript in → expected `quantity`/`lot` out),
upgrading #3's tolerant matchers with field-level ground truth. Recommend answering that epic's
question **yes**: harvest as `kind=correction, ai_output_type=treatment` with field granularity in
`context`. (Lot corrections are the highest-value rows — they feed the recall-cohort safety story.)

### 3b. CI gating — the staged path from manual/non-blocking to a real gate

**Today:** `eval.yml` is `workflow_dispatch`-only, and by design a regression or unreachable
gateway is a `::warning::` on a green job. The real gate is the CLAUDE.md §4 agent rule.

**Staged proposal:**

- **Stage 1 — deterministic PR gate (free, immediate).** New required check on PRs touching
  `apps/ai_engine/**`: run `run_all.py` with **no gateway configured**. Every module's gate
  self-tests + parser self-tests run — pure Python, zero cost, zero flake. This blocks harness bugs
  and matcher regressions on every PR today.
- **Stage 2 — scheduled full run (signal, not gate).** Nightly (or 3×/week) cron of the current
  full-gateway run against `gw.engram.ir` with fixtures mirrored from the runner-reachable S3
  (secrets already supported: `AI_ENGINE_TRANSCRIPTION_API_KEY`, `EVAL_FIXTURES_S3_*`). Publishes
  the JSON scorecard artifact (3c) and opens/updates a tracking issue on regression. Fixture-bucket
  creds: read-only, least-privilege — safe because 3a guarantees the bucket holds staff-recorded
  media only. Also uncomment the existing push-on-main path filter as a tripwire.
- **Stage 3 — merge gate for AI-job PRs (safety tier only, flake-managed).** `pull_request` on
  `apps/ai_engine/**`: run the **synthetic gateway modules** (treatments, aftercare, safety_flags,
  safety_reconcile, report_sections, patient_memory, + qa_draft once built — ~45 calls) as a
  blocking check with a **majority-of-3 flake policy** for the single-call synthesis evals (a case
  fails only if it fails ≥2 of 3 runs — this is the "majority-vote wrapper" already noted open in
  evals.md; implement in `run_all.py` / `_common` as `EVAL_VOTES=3` re-running only failed cases).
  **Judge-scored quality stays advisory in CI** (`EVAL_STRICT_QUALITY` off) — only deterministic
  gates block. Real-media modules (transcription, matching, caption, qa_revise) stay scheduled-only
  at first (S3 pull + audio cost + higher ambient flake), promoted case-by-case once Stage-2 trend
  data shows they're stable. Guardrails: `concurrency` cancel-in-progress, a per-run cost note in
  the job summary (the gateway spend is real money — reconcile with
  [`ai-usage-limits.md`](../business/ai-usage-limits.md) cost-per-job figures when enabling).
- **Stage 4 — knownGap policy in the gate.** A `knownGap` never blocks, but the Stage-2 report
  lists every active knownGap with age; a knownGap older than one cycle without a burn-down owner
  gets escalated in the tracking issue (prevents permanent xfails).

### 3c. Scorecard/reporting — trendable scores, not pass/fail logs

**Today:** `run_all.py` prints per-module PASS/FAIL and each module prints case lines; judge scores
scroll away — there is no way to see "caption groundedNoInvention drifted from 0.9 → 0.7 over the
last month" (exactly what an advisory tier is for).

**Proposal:**

1. **Machine-readable scorecard.** Each `*_eval.py` writes (in addition to stdout) a per-module JSON
   record via a `_common.write_scorecard()` helper: `{module, git_sha, models_under_test,
   judge_model, timestamp, cases: [{id, safety: pass|fail|known-gap, judge: {dim: score},
   reasons}], counts}`. `run_all.py` merges them into `eval/out/scorecard.json`. (The modules
   currently return only exit codes — this is the enabling refactor, and it lands naturally with the
   Part-2 harness unification.)
2. **History — v1 bucket, target MLflow-class (review decision).** v1 (ships with I1, zero infra):
   each CI/manual run appends its scorecard to the eval bucket under `scorecards/<date>-<sha>.json`
   (same `eval-fixtures.sh` plumbing, new prefix). **Target state (future work, once Stage-2 CI +
   the harvest loop exist):** a self-hosted experiment-tracking system (MLflow or similar,
   Postgres-backed, joins the existing self-hosted observability overlay) becomes the eval log —
   runs as experiments, per-case metrics, judge dimensions over time, model/prompt-version tags,
   comparison UI. The JSON scorecard schema is designed to import cleanly (flat metrics + tags), so
   the bucket era's history migrates in rather than being thrown away.
3. **Trend report.** Until the tracking system lands: a small `scripts/eval-trend.py` renders the
   bucket's series into one markdown table/sparkline block per module — safety pass-rate,
   per-dimension judge means, knownGap ages — posted as the Stage-2 workflow's job summary. This is
   what makes the advisory judge tier *actionable*: model swaps on the gateway become visible as
   dimension steps without ever flaking a build. Retired in favor of the MLflow-class UI when that
   arrives.

---

## Increments

1. **I0 — approvals.** DONE 2026-07-04 (decisions recorded below).
2. **I1 — cheap wins.** JSON scorecard emission (3c.1) + Stage-1 deterministic PR gate (3b) +
   harness unification of treatments/aftercare/safety_flags (Part-2 cross-cutting). No new model
   behavior under test.
3. **I2 — recording-list updates** (all fixtures requested from the user, never auto-generated):
   caption `p01–p06` unblock plan, transcription `t10–t14`, synthesis `s01–s04` revival.
   (qa_draft/qa_revise eval work — including the `r01–r10` clips — moved to
   [qa-knowledge-epic.md](qa-knowledge-epic.md).)
4. **I3 — Part-2 case batches** per module (#1–#9 upgrades) + m02 knownGap burn-down.
5. **I4 — harvest v1** (`eval-harvest.py`, watermark, first triage during the Tehran wave) + the
   treatment-overlay signal (approved — see decisions).
6. **I5 — Stage-2 scheduled run + trend report; then Stage-3 merge gate** once majority-vote lands
   and Stage-2 shows a stable baseline.

Each increment ends by updating [`evals.md`](../ai_engine/evals.md) (coverage table + how-it-works)
and, for I5, a dated `technical-decisions.md` entry on the CI gating stance; this doc is deleted
when I5 folds.

## Decisions from the 2026-07-04 review

1. **qa_draft golden set — MOVED** to [qa-knowledge-epic.md](qa-knowledge-epic.md); approval rides
   that epic (the sets gain retrieval-grounded cases first).
2. **qa_revise golden set — MOVED** likewise (r01–r10 recordings ride the epic; recorded by the
   user/clinician, never auto-generated).
3. **Caption photos — APPROVED:** p01–p05 sourcing plan (product boxes at the partner clinic,
   consenting staff volunteer for p02/p03, `p01` lot `PS18025`), attached to the Tehran-wave visit.
4. **Harvest privacy — LOOSENED:** no scrubbing rules for now; harvested text (names included)
   enters cases verbatim — the real values are part of the pipeline under test. Revisit before any
   external exposure. Standing rule kept: **non-text fixtures are requested from the user; no
   automatic generation of audio/images, ever.**
5. **Treatment-overlay harvest signal — YES:** field-level edits feed structured exact-match
   treatment cases.
6. **CI staging — APPROVED for Stage 1 + Stage 2 now;** Stage 3 (merge-gating with majority-of-3,
   real gateway spend per PR) decided after a stable Stage-2 baseline.
7. **Scorecard storage — eval-bucket time series as v1;** target: a self-hosted MLflow-class
   tracking system once eval-in-CI + harvesting exist (review 2026-07-04; scorecard schema designed
   to import into it).
8. **Harness unification — APPROVED** (lands in I1).
