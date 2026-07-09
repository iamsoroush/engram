# AI Evals — golden-set scoring for the AI jobs

Every AI job is gated on a **golden-set eval** that runs the real gateway against fixed cases and
scores it, so a prompt/model change is judged on a whole **scorecard** — not eyeballed one job at a
time (CLAUDE.md §4: re-implementing an AI job must not regress the suite; a **new** AI job must ship
its own eval, with golden-set scenarios agreed with the user first).

Runner: `apps/ai_engine/eval/run_all.py` → a printed consolidated scorecard **plus** a machine-readable
one under `eval/out/` (see [Machine-readable scorecard](#machine-readable-scorecard)).

```sh
docker exec engram-main-ai-engine-1 python /app/eval/run_all.py
# or with staged real fixtures:  scripts/eval-fixtures.sh run
```

No gateway → each eval runs its **deterministic self-tests only** and is green (exit 0) unless a
matcher/harness regressed; the gateway tier is skipped. With a gateway it exits non-zero if any eval
fails. A new job's eval is added by dropping a `*_eval.py` in `apps/ai_engine/eval/` and listing it in
`run_all.py`.

> Code comments referencing the retired `eval-epic.md` map here: *§1b (feedback harvester)* →
> [Feedback → golden-set harvest](#feedback--golden-set-harvest); *§2a (fixture `.json` format)* →
> [Expectations format](#expectations-format-the-fixture-json).

## How scoring works — two tiers + a deterministic third

- **Safety gates** — deterministic matchers (substring / numeric-token / presence / no-Latin).
  **HARD pass/fail, block ship**: a wrong dose transcribed, a wrong patient auto-assigned, a
  diagnosis in a caption, an invented treatment/flag, a romanized Persian transcript.
- **Quality — LLM-as-judge**, scored 0..1 against a per-eval rubric (hallucination, missing info,
  native-script fidelity, tone). **Advisory by default** — reported in the scorecard so prompt/model
  drift is visible, but LLM nondeterminism never flakes the suite red. `EVAL_STRICT_QUALITY=1`
  promotes below-threshold quality (and judge-smoke misses) to blocking.
- **Advisory deterministic checks** (e.g. patient-memory name-repeat) — reported, never blocking.

**Judge model:** `gpt-5.4-mini` (override with `EVAL_JUDGE_MODEL`) on the same gateway — kept
independent of whichever model is under test, so the grader doesn't move when a job's model swaps.

**Always-on harness checks** keep an eval honest before any recordings exist: deterministic **gate
self-tests** (positive + negative synthetic inputs proving each matcher catches what it must — run
even with no gateway) and gateway **judge smoke cases** (synthetic reference/candidate pairs proving
the rubric separates clean output from romanized / wrong-dose output). A fixture dropped in later is
scored on top with no code change.

**`knownGap` (xfail):** a case may set `"knownGap": "<reason>"` when it fails due to a *documented
model limitation* (not a harness bug). It is reported loudly (`KNOWN-GAP …`) but not counted as a
blocking failure — and if it starts passing, that is surfaced too. Use sparingly, always with a reason
+ the intended fix.

The shared harness (tolerant Persian matching, the judge, the fixture store, the `knownGap` xfail, the
exit-code policy, and the machine-readable scorecard) is `eval/_common.py`. **Every module uses it** —
each `*_eval.py` runs deterministic gate self-tests over synthetic output dicts (proving its matchers
catch what they must), then the gateway/fixture cases, and returns the shared `exit_code()`.

## Machine-readable scorecard

Alongside the printed summary, each `*_eval.py` calls `_common.write_scorecard()` once at the end of
`main()`, writing `eval/out/<module>.json`; `run_all.py` merges them into `eval/out/scorecard.json`
(both gitignored run artifacts — trend history is archived to object storage, never git). The schema is
deliberately **flat metrics + tags** so a scorecard imports cleanly into an experiment tracker
(MLflow-class) later:

- **tags** (top level): `module`, `git_sha`, `timestamp`, `gateway`, `judge_model`, `models_under_test`,
  and a `run_config` block `{model, reasoningEffort, promptVersion}` — the attributes a trend needs to
  explain a step (a model swap, an effort change, a prompt bump). All three are **tolerant** (absent →
  null, never an error), so the schema is stable whether or not the jobs already stamp a `promptVersion`
  in their output envelope (`_common.capture_prompt_version` reads it the moment they do).
- **`metrics`**: one flat scalar per key — the trendable series (`self_tests_ok`, `safety_pass`,
  `safety_fail`, `known_gap`, `advisory` where an advisory-deterministic tier exists,
  `quality_pass`/`quality_fail` and `judge_smoke_ok` where a judge tier exists, `cases_total`).
- **`cases`**: per-case drill-down (`id`, `safety`: `pass`/`fail`/`known-gap`, `judge` dimension
  scores, `reasons`).

The merged `scorecard.json` carries a run-level `summary` (`evals_run`, `evals_green`,
`modules_with_scorecard`) and each module's record under `modules`. A gateway-less run still emits a
full scorecard (every module's `self_tests_ok` + zeroed gateway metrics), which is what the CI gate
(below) uploads as an artifact.

## Coverage — the eleven modules `run_all.py` runs

| Module | Job / seam | What it gates | Fixtures |
| --- | --- | --- | --- |
| `transcription_eval.py` | Audio transcription | Native script (no romanization), verbatim dose/brand/lot, digit handling, negation/laterality/allergy preserved; a confusable dose **minimal pair** gated both ways (`numbers` + `numbersForbidden`) | **Real audio** (9 live clips + the `t10`–`t14` edge batch pending) + self-tests + judge smoke |
| `caption_eval.py` | Image caption | Neutral **objective** description — never a diagnosis; lot read off a label; an invented lot caught deterministically (`forbiddenPattern`); language; before/after `phase` | Harness green (self-tests + judge smoke); **real photos `p01`–`p06` pending** — scored the moment they land, no code change |
| `treatments_eval.py` | Synthesis — `treatments[]` (+ real-clip synthesis path) | area/product/brand split, quantity/unit + **`quantityText` verbatim**, corrections vs additions, carry-forward, lot; **planned-vs-performed** (G7 — a future-tense treatment is `status:planned`, counted under neither performed nor aftercare, not flagged `planned_vs_performed`; a mixed dictation splits performed+planned); **declined / prior-visit-recall** not extracted; multi-capture correction | Synthetic Farsi dictations (incl. the owner's planned-vs-performed golden cases) + **real full-visit clips `s01`–`s04`** (transcribe→synthesize, treatments+aftercare) when recorded |
| `aftercare_conflict_eval.py` | Synthesis — `aftercareSelections` | Protocol completeness (per performed procedure) + dictation-vs-protocol **conflict** attribution; **restating** a protocol is `applies` not a conflict; an irrelevant protocol is not selected | Synthetic Farsi cases |
| `safety_flags_eval.py` | Synthesis — `safetyFlags` | Right `kind` for stated allergy/contraindication/consent, grounded native-script text, **no invention** (clean visit / negation / **family-history / hypothetical / resolved / preference** → no flags); a flag from **any capture type** (note/photo, not only audio) | Synthetic Farsi cases |
| `safety_reconcile_eval.py` | Cross-visit safety reconcile | Dedup same-concept (incl. cross-script), keep distinct (drug-family, added-severity), never merge kinds, **never drop a distinct allergy**; supersede is the ideal — a bare **keep** is reported as an **advisory**, only a *dropped* distinct flag fails | Synthetic candidate sets (incl. a realistic-scale panel) |
| `report_sections_eval.py` | Synthesis — sections (prose half) | Grounded prose (no invention), image blocks reference real captureIds only + **each at most once** (`imageRefsUnique`), empty sections stay empty, native-script, all ids present; cross-capture correction → final fact only; **meta-speech exclusion** (administrative talk to staff/the app never leaks into the report/summary — `forbiddenAnywhere`); `en` reportLanguage | Synthetic Farsi + `en` transcripts + self-tests |
| `patient_memory_eval.py` | Patient memory | Story/delta accuracy over multi-visit briefs, no invented flags, no name-repeat (advisory, counted — the name is never sent to the model), grounded recall of dose/brand; **flags persist** over a long history, a **superseded** fact isn't restated, dose **trend** recalled, **moved visits** (wrong→right cleanup) recall a treatment once (no double-count) | Synthetic multi-session fixtures (incl. 6–8-visit history + moved-visits dedup) + self-tests |
| `patient_matching_eval.py` | Matching's **LLM seam** (transcription input) | Spoken name extracted **faithfully** (a near-miss must not be "corrected"; a similar-name pair not swapped; a mid-dictation mention still caught) + assignment `basis` never over-escalated to `explicit`; **incident cluster (E1):** a `درستش`-style correction directive classifies `explicit`, an in-clip self-correction keeps the corrected name, a correction-only clip is **not** out-of-context, and a detach/negation sets `intents.detach.present` with no name | **Real audio** (6 live clips + `m07`–`m09`, `i01`–`i04` pending; `m02`/`i03` = `knownGap`) + self-tests (incl. 7 E1 gate cases) + judge smoke |
| `qa_draft_eval.py` | Q&A reply draft (AES-402/410) | No invented numbers (a dose the doctor never stated), red-flag cases **forbid reassurance** + require a clinic-contact tail, patient-language native script, sign-off present; **retrieval-grounded** cases — exemplar generic guidance adopted (exemplar-followed) and patient context **overriding** a contradicting exemplar (exemplar-overridden); **cross-patient leak** — a dose that lives ONLY in another patient's exemplar/prior answer must not be copied (`noCrossPatientNumbers`, `QD-X1`) and a stranger's greeting name must not be addressed to this patient (`QD-X2`) | Synthetic payloads (`QD-01`…`12` + retrieval + cross-patient cases) + gate self-tests + judge smoke |
| `qa_revise_eval.py` | Q&A reply voice-edit (AES-402) | revise-vs-replace **mode** classification, **numbers-preserved** on a revise, escalation tail survives, native script, sign-off; parser fallback on unusable output | **Real audio** (`r01`–`r10` recorded by the clinician, pending) + parser + gate self-tests + judge smoke |

The deterministic post-processing these jobs feed (correction/supersede/carry-forward, search
ranking, the exact-vs-fuzzy **auto-assign decision** itself) is unit-tested in `tests/`
(`test_ai_assignment_gate.py`, `test_patient_identity_matching.py`, `test_treatment_synthesis.py`);
the evals measure the **LLM behaviour** unit tests can't.

Durable real-audio lessons baked into the matchers: models normalize spoken number words to digits
(«بیست»→«20») — dose gates accept either via `containsAny`; a lot VALUE is read reliably while the
surrounding label word drifts — gates check the value, not the word; flash-class models intermittently
auto-correct a near-miss name to a known patient — the `m02` `knownGap`. That gap **stays open by
decision, not oversight**: the matching seam rides the bulk-transcription model (`gemini-3.1-flash-lite`,
the highest-volume call), a pro-class model only fixes it there at whole-pipeline cost, and the
deterministic backend gate never auto-assigns a fuzzy near-miss regardless — so it is deferred until the
seam can take a pro model independently. See
[technical-decisions.md](../technical-decisions.md) → *Matching Seam Runs on the Transcription Model*.

### Coverage gaps

- **`qa_revise` real clips (`r01`–`r10`) pending.** The `qa_draft` golden set + the `qa_revise`
  harness (parser + gate self-tests + judge smoke) are wired and green; `qa_revise`'s scored cases are
  voice notes, so they are **recorded by the user/clinician** (never auto-generated) per
  `fixtures/RECORDING_CHECKLIST.md` → `qa_revise/`, and score the moment they land (no code change).
- Caption real photos (`p01`–`p06`), the transcription edge batch (`t10`–`t14`), the full-visit
  synthesis clips (`s01`–`s04`), and matching (`m07`–`m09`, plus the incident-cluster `i01`–`i04` — pull
  the owner's own prod/dev clips per `RECORDING_CHECKLIST.md` Batch 3) are recorded-when-available (see
  `fixtures/RECORDING_CHECKLIST.md`); the harness is green without them, and each is scored the moment
  it lands with no code change (the synthesis clips flow through `treatments_eval`'s fixture-driven path).

## Expectations format (the fixture `.json`)

Media fixtures live under `eval/fixtures/<job>/` as `<case>.<media>` + a sibling `<case>.json`.
`transcription_eval.py` is the reference implementation; the other media evals use the same shape.
A `.json` carries up to two blocks — include only what a case must prove:

```jsonc
{
  "said": "بیست واحد بوتاکس روی پیشانی زدم.",   // OPTIONAL ground truth — the judge's reference;
                                                 // judge skipped if absent.
  "context": {"preferredLanguage": "fa"},        // OPTIONAL processing-context overrides (merged).

  "expect": {                                    // SAFETY GATES — deterministic, HARD pass/fail
    "containsFa":     ["بوتاکس", "واحد"],        //   every string appears (script/ZWNJ/digit tolerant)
    "containsAny":    [["بیست", "۲۰"]],          //   each group: ≥1 appears (dose as WORD or DIGITS)
    "numbers":        [20],                       //   each number appears as a digit token
    "brandsVerbatim": ["ژوویدرم"],               //   brand strings appear verbatim
    "lot":            "ABC123",                   //   lot/batch string appears verbatim
    "noLatinWords":   true,                       //   anti-romanization
    "allowLatin":     ["Juvederm"],               //   legitimate-Latin exceptions
    "forbidden":      ["میلی‌گرم"],              //   must NOT appear (wrong unit / hallucination)
    "language":       "fa"                        //   expected detected language
  },

  "judge": {                                     // QUALITY — LLM judge, 0..1 (advisory)
    "dimensions": ["nativeScript", "doseFidelity", "brandLotFidelity", "completeness", "noHallucination"],
    "minScore": 0.7
  }
}
```

Expected outputs use **tolerant matchers** because LLM phrasing varies — the clinical facts must
hold, not the exact words. Synthetic cases (the synthesis/memory evals) live inline in their module
(e.g. `treatments_eval.CASES`) instead of fixture files.

## Fixture store — object storage, never git

**Fixture media are PII and never enter git** (`eval/fixtures/<job>/*` is gitignored except
`.gitkeep`; only `RECORDING_CHECKLIST.md` is committed). They live in the `notari-eval-fixtures`
MinIO bucket,
managed by `scripts/eval-fixtures.sh` (a `minio/mc` sidecar on the stack's shared network; all
settings env-overridable):

```sh
scripts/eval-fixtures.sh stage     # create the local intake dir (~/notari-eval-fixtures) + .json templates
scripts/eval-fixtures.sh push      # intake dir → the MinIO bucket
scripts/eval-fixtures.sh pull      # bucket → local (teammates / CI)
scripts/eval-fixtures.sh run       # copy eval code + staged media into the ai-engine container and score
scripts/eval-fixtures.sh ls        # list the bucket
```

Evals read media from `EVAL_FIXTURES_DIR` (kept outside the repo), falling back to the in-repo
fixtures dir.

### Adding a recording (clinician workflow)

1. Pick a scenario from `eval/fixtures/RECORDING_CHECKLIST.md` (or the staged intake README —
   `eval/expectations/README.md`) and record it on a phone: short (5–15 s), natural clinical Farsi.
2. Drop the file in the matching intake folder (`transcription/`, `caption/`, `matching/`,
   `synthesis/`), named per the checklist, next to its `.json` template.
3. Fill the `.json` expected facts — or hand the `_todo` to the agent to author the
   matchers/rubric.
4. `scripts/eval-fixtures.sh push` then `run` — the fixture is scored, and from then on guards
   against regressions.

Real recordings are the moat: synthetic text is too clean (the aftercare eval passed 6/6 synthetic
but mis-attributed on a real noisy carried-forward session).

## Feedback → golden-set harvest

Golden-set cases are seeded from **real production failures, harvested — not remembered**. The
`ai_feedback_events` table is the harvest store, fed two ways:

- **Corrections, emitted server-side and non-bypassably** in the existing correction transaction: a
  transcript/caption edit (`services/captures.update_capture`), a treatments-array edit + a
  carried-forward confirmation (`services/sessions`), a patient-match reassignment
  (`services/sessions.assign_session_patient`), and **Q&A reply** feedback (`services/qa`): a doctor
  editing the draft before send or a voice revise/replace is a `correction` (before = the AI draft,
  after = what shipped); dismissing a drafted question is a `rejection`. `ai_output_type = qa_reply`;
  retrieval provenance travels in `context`. Rows carry `kind`
  (`correction`/`confirmation`/`rating`/`rejection`), `ai_output_type`, the before/after AI-output
  **text verbatim** (the eval target), and a **PII-scrubbed** `context`
  (names/national-id/phone/DOB/match-evidence redacted by `feedback.scrub_context`).
- **Ratings:** a lightweight thumbs on the report/brief via
  `POST /api/v1/feedback` (`app/feedback_api.py` → `app/services/feedback.py`).

Harvest read: `GET /api/v1/feedback?kind=correction&aiOutputType=transcript` (newest-first,
tenant-scoped) — each row is a candidate eval case; the agent authors the matcher/judge from it.

## CI ladder

Two workflows, split by cost and determinism:

- **Stage 1 — deterministic PR gate (blocking).** `.github/workflows/ai-eval-gate.yml` runs on every
  `pull_request` touching `apps/ai_engine/**`. It runs `run_all.py` with **no gateway configured**, so
  every module runs only its deterministic gate self-tests + matcher/parser self-tests — pure Python,
  **zero gateway spend, zero LLM flake**. A harness bug or matcher regression fails the job and blocks
  the PR; the merged `scorecard.json` is uploaded as an artifact. This is the workflow meant to be a
  **required** status check in branch protection (job name: *AI eval self-tests (no gateway)*).
- **Stage 2 — scheduled gateway run + trend (signal, not gate).** `.github/workflows/eval.yml` runs the
  suite against the production gateway (`gw.engram.ir`), pulling fixtures from S3 when the
  `EVAL_FIXTURES_S3_*` secrets are configured. It fires on a **schedule** (Mon/Wed/Fri 03:00 UTC), on
  `workflow_dispatch`, and — as a **tripwire** — on `push` to `main` touching `apps/ai_engine/**`. It is
  **non-blocking by design**: a regression or unreachable gateway emits a `::warning::` and the job
  stays green (the gateway run is non-deterministic and costs money, so CI treats it as a signal), and
  **judge-scored quality stays advisory** (`EVAL_STRICT_QUALITY` unset — only deterministic gates warn).
  Each run **archives the merged `scorecard.json` to the eval bucket under `scorecards/<date>-<sha>.json`**
  and renders `scripts/eval-trend.py` (the bucket's series → a per-module safety pass-rate table +
  per-dimension judge-mean drift + active-knownGap ages) into the **job summary**. That trend is what
  makes the advisory judge tier actionable: a model/prompt swap on the gateway shows up as a step in a
  dimension mean without ever flaking a build — the bucket-backed v1 of the eventual MLflow-class tracker
  (the `run_config` scorecard tag is designed to import into it cleanly).

Beyond CI, the real gate on model/prompt behavior is the CLAUDE.md §4 rule: an agent changing an AI
job runs `run_all.py` where a gateway is reachable and must not regress the scorecard. Next on the
ladder (not yet built): **Stage 3**, a merge gate for AI-job PRs over the synthetic-gateway modules with
a majority-of-3 flake policy for the single-call synthesis evals — promoted once Stage-2 trend data
shows a stable baseline.
