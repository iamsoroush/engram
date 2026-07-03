# AI Evals — golden-set scoring for the AI jobs

Every AI job is gated on a **golden-set eval** that runs the real gateway against fixed cases and
scores it, so a prompt/model change is judged on a whole **scorecard** — not eyeballed one job at a
time (CLAUDE.md §4: re-implementing an AI job must not regress the suite; a **new** AI job must ship
its own eval, with golden-set scenarios agreed with the user first).

Runner: `apps/ai_engine/eval/run_all.py` → one consolidated scorecard.

```sh
docker exec engram-main-ai-engine-1 python /app/eval/run_all.py
# or with staged real fixtures:  scripts/eval-fixtures.sh run
```

No gateway → each eval **SKIPs (exit 0)** — the suite is green but the scorecard says "skipped".
With a gateway it exits non-zero if any eval fails. A new job's eval is added by dropping a
`*_eval.py` in `apps/ai_engine/eval/` and listing it in `run_all.py`.

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

**`knownGap` (xfail):** a real fixture may set `"knownGap": "<reason>"` when it fails due to a
*documented model limitation* (not a harness bug). It is reported loudly (`KNOWN-GAP …`) but not
counted as a blocking failure — and if it starts passing, that is surfaced too. Use sparingly, always
with a reason + the intended fix.

The shared harness (tolerant Persian matching, the judge, the fixture store, the exit-code policy)
is `eval/_common.py`; treatments + aftercare predate it and stay self-contained.

## Coverage — the nine modules `run_all.py` runs

| Module | Job / seam | What it gates | Fixtures |
| --- | --- | --- | --- |
| `transcription_eval.py` | Audio transcription | Native script (no romanization), verbatim dose/brand/lot, digit handling, negation/laterality/allergy preserved | **Real audio** (9 clips, live) + self-tests + judge smoke |
| `caption_eval.py` | Image caption | Neutral **objective** description — never a diagnosis; lot read off a label; language | Harness green (self-tests + judge smoke); **real photos `p01`–`p05` TODO** — scored the moment they land, no code change |
| `treatments_eval.py` | Synthesis — `treatments[]` | area/product/brand split, quantity/unit verbatim, corrections vs additions, carry-forward, lot | Synthetic Farsi dictations (~12 cases) |
| `aftercare_conflict_eval.py` | Synthesis — `aftercareSelections` | Protocol completeness (per performed procedure) + dictation-vs-protocol **conflict** attribution, per-procedure | Synthetic Farsi cases |
| `safety_flags_eval.py` | Synthesis — `safetyFlags` | Right `kind` for stated allergy/contraindication/consent, grounded native-script text, **no invention** (clean visit / negation → no flags) | Synthetic Farsi cases |
| `safety_reconcile_eval.py` | Cross-visit safety reconcile | Dedup same-concept, keep distinct, supersede annotated (not dropped), never merge kinds, **never drop a distinct allergy** | Synthetic candidate sets |
| `report_sections_eval.py` | Synthesis — sections (prose half) | Grounded prose (no invention), image blocks reference real captureIds only, empty sections stay empty, native-script, all fixed ids present | Synthetic Farsi transcripts + self-tests |
| `patient_memory_eval.py` | Patient memory | Story/delta accuracy over multi-visit briefs, no invented flags, no name-repeat (advisory), grounded recall of dose/brand | Synthetic multi-session fixtures + self-tests |
| `patient_matching_eval.py` | Matching's **LLM seam** (transcription input) | Spoken name extracted **faithfully** (a near-miss must not be "corrected" to an existing patient) + assignment `basis` never over-escalated to `explicit` | **Real audio** (6 clips, live; `m02` near-miss = `knownGap`) + self-tests + judge smoke |

The deterministic post-processing these jobs feed (correction/supersede/carry-forward, search
ranking, the exact-vs-fuzzy **auto-assign decision** itself) is unit-tested in `tests/`
(`test_ai_assignment_gate.py`, `test_patient_identity_matching.py`, `test_treatment_synthesis.py`);
the evals measure the **LLM behaviour** unit tests can't.

Durable real-audio lessons baked into the matchers: models normalize spoken number words to digits
(«بیست»→«20») — dose gates accept either via `containsAny`; a lot VALUE is read reliably while the
surrounding label word drifts — gates check the value, not the word; flash-class models
intermittently auto-correct a near-miss name to a known patient — the `m02` `knownGap`, resolved by
running the matching path on a pro-class model.

### Coverage gaps

- **`qa_draft` / `qa_revise` have no eval suite.** They shipped without one — per CLAUDE.md §4 a new
  AI job must ship its own eval, so this is the outstanding debt. Golden-set scenarios (question
  types, tone, escalation cases, voice-edit revise-vs-replace splits) **need user consultation
  first** — do not design the set unilaterally.
- Caption real photos (`p01`–`p05`) are recorded-when-available (see the workflow below); the
  harness is green without them but the job is only synthetically covered until they land.

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
  carried-forward confirmation (`services/sessions`), and a patient-match reassignment
  (`services/sessions.assign_session_patient`). Rows carry `kind`
  (`correction`/`confirmation`/`rating`), `ai_output_type`, the before/after AI-output **text
  verbatim** (the eval target), and a **PII-scrubbed** `context`
  (names/national-id/phone/DOB/match-evidence redacted by `feedback.scrub_context`).
- **Ratings:** a lightweight thumbs on the report/brief via
  `POST /api/v1/feedback` (`app/feedback_api.py` → `app/services/feedback.py`).

Harvest read: `GET /api/v1/feedback?kind=correction&aiOutputType=transcript` (newest-first,
tenant-scoped) — each row is a candidate eval case; the agent authors the matcher/judge from it.

## CI reality

`.github/workflows/eval.yml` runs the suite on a GitHub-hosted runner against the production gateway
(`gw.engram.ir`), pulling fixtures from S3 when the `EVAL_FIXTURES_S3_*` secrets are configured. It
is **manual-only** (`workflow_dispatch`; the on-push trigger for `apps/ai_engine/**` is present but
commented out) and **non-blocking by design**: a regression or unreachable gateway emits a
`::warning::` and the job stays green — the eval is non-deterministic and costs money, so CI treats
it as a signal, not a merge gate. The real gate is the CLAUDE.md §4 rule: an agent changing an AI
job runs `run_all.py` where a gateway is reachable and must not regress the scorecard. Known
open item: a majority-vote wrapper for the flaky single-call synthesis evals.
