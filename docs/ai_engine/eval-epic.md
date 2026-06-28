# AI Eval Epic — golden-set evals for every AI job

> **Goal.** Stop tuning prompts one bug at a time. Give every AI job a **golden-set eval** that runs
> the real gateway against fixed cases and scores it, so any prompt/model change is gated on a whole
> **scorecard** — and so regressions are caught before they ship. Synthetic cases give breadth fast;
> **real recordings** (clinician-provided audio/photo) expose the hard failures synthetic text can't.

Runner: `apps/ai_engine/eval/run_all.py` → one consolidated scorecard.
Existing pattern to copy: `eval/treatments_eval.py`, `eval/aftercare_conflict_eval.py`.
All evals **SKIP (exit 0) without a gateway**, so they never block CI; with a gateway, non-zero on fail.

```sh
docker exec engram-main-ai-engine-1 python /app/eval/run_all.py
```

---

## 1. AI jobs + what each eval must prove

| Job | Eval module | Quality the eval must gate | Fixtures | Status |
|---|---|---|---|---|
| **Transcription** (audio → text) | `transcription_eval.py` | Persian **native script** (no romanization), verbatim dose/brand/lot, digit handling, robustness to accent/noise | **real audio** (cannot be synthetic) | **LIVE on 9 real clips (9/9 safety)** + 12 self-tests + 3 judge smoke |
| **Image caption** (Job 2) | `caption_eval.py` | Neutral **objective** description (never a diagnosis — the caption is a neutral image→text extractor, not a clinical read), lot read off a label, language | **real photos** | harness green (12 self-tests + 3 judge smoke); **📷 real photos = TODO (deferred — clinician to provide p01–p05)** |
| **Report synthesis — treatments** (Job 3) | `treatments_eval.py` | area/product/brand split, quantity/unit verbatim, corrections vs additions, carry-forward, lot | synthetic transcripts (+ real) | **done (12 cases)** |
| **Report synthesis — aftercare** (Job 3) | `aftercare_conflict_eval.py` | which clinic protocols apply (completeness, per-procedure), dictation-vs-protocol **conflict** attribution | synthetic (+ real) | **done (6 cases)** |
| **Report synthesis — sections** (Job 3) | `report_sections_eval.py` | grounded prose (no invention), native script titles + body, image blocks reference real captureIds, empty sections stay empty | synthetic transcripts (+ real) | **done (3 cases + 5 self-tests)** |
| **Patient memory** (Job 4) | `patient_memory_eval.py` | story-so-far accuracy, since-last-visit delta, flags (no invented flags), no name-repeat (advisory) — over a multi-session fixture | synthetic multi-session (+ real) | **done (3 cases + 6 self-tests)** |
| **Patient matching** (AI auto-assign) | `patient_matching_eval.py` | **safety (LLM seam)**: spoken name extracted faithfully + assignment **basis** not over-escalated (a mention/near-miss must NOT be `explicit`) so the backend never silently auto-assigns | name fixtures (+ real audio names) | **LIVE on 6 real clips (5/6 + 1 knownGap)** + 13 self-tests + 2 judge smoke |

> The deterministic post-processing (correction/supersede/carry-forward, search ranking, and the
> exact-vs-fuzzy **auto-assign decision** itself) is already unit-tested in `tests/`
> (`test_ai_assignment_gate.py`, `test_patient_identity_matching.py`). These evals measure the **LLM
> behaviour** the unit tests can't — e.g. patient-matching here covers the transcription INPUT (name +
> intent) that feeds the backend gate, not the (already-tested, backend-only) gate logic.

> **Shared harness.** All five LLM evals run on `eval/_common.py` (tolerant Persian matching, the
> `gpt-5.4-mini` judge, the fixture store, the exit-code policy). Treatments + aftercare predate it and
> stay self-contained. A THIRD deterministic tier exists alongside safety/quality: **advisory**
> deterministic checks (e.g. patient-memory name-repeat) — reported, never blocking.

> **Fixture media live in object storage, never in git** (PII). `scripts/eval-fixtures.sh` stages a
> local intake dir, pushes/pulls the `notari-eval-fixtures` MinIO bucket (via a `minio/mc` sidecar on
> the `notari-shared` network), and the evals read fixtures from `EVAL_FIXTURES_DIR`. `fixtures/<job>/`
> in the repo is gitignored except `.gitkeep`. See `scripts/eval-fixtures.sh` + the staging README.

## 1b. Design decisions (brainstorm 2026-06-24)

- **Two tiers of cases, scored differently.** *Safety gates* — hard pass/fail, block ship: wrong dose
  transcribed, wrong patient auto-assigned, PII leaked into a share, a **diagnosis** in a caption, a
  treatment invented that wasn't said. *Quality metrics* — tracked to drive iteration: native-script
  fidelity, section grounding, brief usefulness, conflict-attribution precision.
- **LLM-as-judge for the quality tier.** Safety gates use deterministic matchers (substring / numeric /
  presence). The fuzzy quality dimensions (hallucination, missing info, structural correctness, tone)
  are scored by an **LLM judge** against a rubric — cheaper to author than exhaustive matchers and it
  scales to free-text. Judge rubric lives next to each eval; the judge runs on the same gateway.
- **Ground truth via scenarios → recordings.** The agent provides concrete scenarios (the catalog +
  `fixtures/RECORDING_CHECKLIST.md`); the clinician records the audio/photo; the agent authors the
  tolerant matchers / judge rubric and wires the eval. Real recordings are the moat — synthetic text is
  too clean (our aftercare eval passed 6/6 synthetic but mis-attributed on a real noisy session).
- **Seed the golden set from REAL failures (harvested, not remembered).** No backlog of known failures
  yet — they come from MVP user testing. So the app must emit **failure signals** to mine into cases:
  (1) **a user correcting an AI output is a failure flag** — when staff edits a transcript/caption/
  treatment/patient-match, log the before→after (PII-scrubbed) as a candidate eval case; (2) a
  lightweight **thumbs/rating** on a report/brief. This instrumentation is itself a build task (see the
  production list) — it turns every production correction into a future golden-set entry.
  - **BUILT (2026-06-25).** `ai_feedback_events` (backend table + migration) is the harvest store; a
    thin `POST/GET /api/v1/feedback` endpoint (`app/feedback_api.py` → `app/services/feedback.py`)
    serves the report/brief thumbs and a tenant-scoped read for the harvester. **Corrections are emitted
    server-side, non-bypassably**, in the existing correction transaction (like `audit`): a
    transcript/caption edit (`services/captures.update_capture`), a treatments-array edit + a
    carried-forward `confirmation` (`services/sessions`), and a patient-match reassignment
    (`services/sessions.assign_session_patient`). Rows carry `kind` (`correction`/`confirmation`/
    `rating`), `ai_output_type`, the before/after AI-output **text verbatim** (the eval target), and a
    **PII-scrubbed** `context` (names/national-id/phone/DOB/match-evidence redacted by
    `feedback.scrub_context`). **Harvest read:** `GET /api/v1/feedback?kind=correction&aiOutputType=transcript`
    (newest-first) — each row is a candidate eval case; the agent authors the matcher/judge from it.
- **Depth over breadth, transcription first.** Transcription is the foundation (garbage in → garbage
  everywhere); its failures (dose tokens ۲/۳/۲۳, confusable names معاضد/معاصد) are highest-stakes
  alongside patient-matching. Build it deep before spreading thin.

## 2. Fixture strategy

- **Synthetic** (inline in the eval module, like `treatments_eval.CASES`): fast, broad, deterministic
  to author. Good for the synthesis logic (corrections, carry-forward, aftercare conflict).
- **Real recordings** (clinician-provided): the ONLY way to eval transcription + caption, and the way
  to catch the failures that only show up with real speech/photos + a noisy multi-capture session
  (e.g. the aftercare-attribution miss that passed on clean synthetic text but failed on a real
  carried-forward visit). Stored as fixtures under `eval/fixtures/` with an expected-output JSON.

### Fixture layout (for real recordings)

```text
apps/ai_engine/eval/fixtures/
  transcription/
    t01-botox-forehead-20u.m4a
    t01-botox-forehead-20u.json      # { "expect": { "containsFa": ["بوتاکس","۲۰","واحد"], "noLatinWords": true } }
  caption/
    p01-filler-box-lot.jpg
    p01-filler-box-lot.json          # { "expect": { "lot": "ABC123", "noDiagnosis": true } }
  synthesis/
    s01-botox-filler-sun.m4a
    s01-botox-filler-sun.json        # { "treatments":[...], "aftercareSelections":[{"procedure":"botox","status":"conflicts"}, ...] }
```

The `*_eval.py` for a job loads each `<case>.<media>` + its `<case>.json`, runs the real job, and
asserts against `expect`. Expected outputs use **tolerant matchers** (substring / numeric / presence)
because LLM phrasing varies — the clinical facts must hold, not the exact words.

### 2a. Two-tier `.json` format (reference impl: `transcription_eval.py`)

`transcription_eval.py` is the built reference for the two-tier pattern; the other media evals
(caption, synthesis fixtures) follow the same `.json` shape. A fixture's `.json` carries up to two
blocks — include only what a case needs to prove:

```jsonc
{
  "said": "بیست واحد بوتاکس روی پیشانی زدم.",   // OPTIONAL ground-truth transcript — the LLM judge's
                                                 // reference + documentation; judge skipped if absent.
  "context": {"preferredLanguage": "fa"},        // OPTIONAL processing-context overrides (merged).

  "expect": {                                    // SAFETY GATES — deterministic, HARD pass/fail (block ship)
    "containsFa":     ["بوتاکس", "واحد"],        //   every string appears verbatim (script/ZWNJ/digit tolerant)
    "containsAny":    [["بیست", "۲۰"]],          //   each group: ≥1 appears (dose as WORD or DIGITS)
    "numbers":        [20],                       //   each number appears as a digit token (normalized to Latin)
    "brandsVerbatim": ["ژوویدرم"],               //   brand strings appear verbatim
    "lot":            "ABC123",                   //   lot/batch string appears verbatim
    "noLatinWords":   true,                       //   no Latin-script words (anti-romanization)
    "allowLatin":     ["Juvederm"],               //   exceptions to noLatinWords (brands legitimately Latin)
    "forbidden":      ["میلی‌گرم"],              //   strings that must NOT appear (wrong unit / hallucination)
    "language":       "fa"                        //   expected detected language code
  },

  "judge": {                                     // QUALITY — LLM-as-judge, scored 0..1 (tracked, advisory)
    "dimensions": ["nativeScript", "doseFidelity", "brandLotFidelity", "completeness", "noHallucination"],
    "minScore": 0.7
  }
}
```

**Scoring + exit code.** Safety gates are deterministic and HARD: any failure exits non-zero (this is
the dose-token / no-romanization gate). Quality (the judge) is **advisory by default** — reported in
the scorecard so prompt/model changes are visible, but LLM nondeterminism never flakes CI red. Set
`EVAL_STRICT_QUALITY=1` to promote below-threshold quality (and judge-smoke misses) to blocking too.

**Judge model.** The judge runs on **`gpt-5.4-mini`** (eval-only config; override with
`EVAL_JUDGE_MODEL`). It uses the shared gateway but a model chosen for grading, kept **independent of
whichever model is under test** so the grader doesn't move when you swap the transcription model.

**Always-on harness checks** (so the eval is honest before any recordings exist): deterministic
**gate self-tests** (positive + negative synthetic transcripts proving each matcher catches what it
must — run even with no gateway) and gateway **judge smoke cases** (synthetic reference/candidate
text proving the rubric separates clean Persian from romanized / wrong-dose output). When a fixture
is later dropped in, it is scored on top of these with no code change.

**`knownGap` (xfail).** A real fixture may set `"knownGap": "<reason>"` when a case fails due to a
*documented model limitation* (not a harness bug). It is then reported loudly (`KNOWN-GAP …`) but NOT
counted as a blocking safety failure, so a known model weakness doesn't redden the suite — and if it
starts passing, that's surfaced too. Use sparingly, always with a reason + the fix.

### 2b. First real-audio findings (clinician recordings, 2026-06-27)

The first real clips (15 audio under patient «نگار محمدی») landed and surfaced exactly the kind of
failure synthetic text can't:

- **Near-miss patient name = the highest-stakes finding.** «نگار **معمری**» (a near-miss of the existing
  «نگار **محمدی**») is *intermittently auto-corrected to the existing patient* by the flash models
  (`gemini-3.1-flash-lite` returned «محمدی» 2/3 runs; `gemini-3.5-flash` too) — which would drive an
  unsafe silent auto-assign. `gemini-3.1-pro-preview` preserved a distinct name («معماری»). → marked
  `knownGap` on `m02`; **recommendation: run the matching/name-extraction path on a pro model.**
- **Number words → digits.** The transcription model normalizes spoken «بیست»→«20», «سه»→«3» — the
  dose gates accept either via `containsAny`.
- **Lot captured, label word drifts.** `PS18025` was read off the box correctly, but «شماره لات» was
  transcribed «شماره محصول» — so the gate checks the lot VALUE, not the word «لات».
- Transcription otherwise strong: 9/9 safety on the real clips (allergy, negation, decimals,
  laterality all preserved).

## 3. Scenario catalog — what to record

Each scenario below becomes one fixture (media + `.json`). Record in **natural clinical Farsi**, as
you actually dictate. Save under the path shown; the matching eval picks it up automatically.

### Transcription (record short AUDIO)

- **T1 botox dose** — "بیست واحد بوتاکس روی پیشانی زدم." → expect `بوتاکس`, `۲۰`/`بیست`, `واحد`; no Latin.
- **T2 filler + brand** — "یک سی‌سی ژل ژوویدرم توی گونه چپ." → expect `ژوویدرم` verbatim, `سی‌سی`.
- **T3 lot off label (spoken)** — "شماره لات A B C یک دو سه." → expect the lot string verbatim.
- **T4 correction mid-sentence** — "دو سی‌سی... نه اشتباه گفتم، سه سی‌سی." → expect both quantities verbatim.
- **T5 noisy / fast** — any of the above with clinic background noise / fast speech → still accurate.

### Image caption (record PHOTO)

- **P1 product box with lot** — a filler/botox box where the lot is legible → expect the lot read.
- **P2 patient area (before)** — a treatment area photo → neutral objective caption, **no diagnosis**.
- **P3 injection site** — close-up → objective description only.

### Report synthesis (record a full-visit AUDIO)

- **S1 botox+filler, sun conflict** — "بیست واحد بوتاکس پیشانی و یک سی‌سی فیلر لب. به بیمار گفتم تا یک
  هفته از آفتاب مستقیم پرهیز کنه." → treatments=[botox, filler]; aftercare botox=**conflicts** (sun
  1wk vs protocol 3d), filler=**applies**. *(The exact real-session case that mis-attributed before.)*
- **S2 carry-forward** — "بوتاکس پیشانی مثل دفعه قبل، همون مقدار." → carriedForward=true, lower confidence.
- **S3 own aftercare** — "...مراقبت‌ها رو خودم کامل گفتم، محدودیت آفتاب نداره." → aftercare=**superseded**.
- **S4 consult only** — "فقط مشاوره بود، تزریقی انجام نشد." → treatments=[].

### Patient matching (record AUDIO of a name)

- **M1 exact name** — "بیمار نگار محمدی." → matches the existing patient.
- **M2 near-miss** — "بیمار معاضد..." (slight mis-say) → **not** silently auto-assigned (surfaces a candidate).

## 4. Sequencing

1. **Done:** runner + all 7 evals on the shared `eval/_common.py` harness; the two synthesis evals
   (treatments, aftercare) + report-sections + patient-memory green on synthetic cases.
2. **Done:** transcription (9 real clips, 9/9 safety) + patient-matching (6 real clips) are **LIVE on
   real clinician audio**, persisted in the `notari-eval-fixtures` object-storage bucket.
3. **TODO (deferred — needs media):** 📷 **caption real photos** (`p01`–`p05`) — clinician to provide
   later; the caption harness is green on self-tests + judge-smoke and scores them the moment they land
   (`scripts/eval-fixtures.sh push` then `run`). No code change needed.
4. **CI:** run `run_all.py` on a gateway-enabled runner; gate prompt/model PRs on the scorecard. Also
   open: a majority-vote wrapper for the flaky single-call synthesis evals (treatments/aftercare); the
   `m02` near-miss `knownGap` resolves by running the matching path on a pro model.

## 5. How to add a recording (clinician workflow)

1. Pick a scenario (e.g. **S1**), record the audio/photo on your phone.
2. Drop the file at the path in §2 (e.g. `eval/fixtures/synthesis/s01-botox-filler-sun.m4a`).
3. Add the sibling `s01-...json` with the expected facts (or hand it to the agent to author).
4. Run `run_all.py` — the new fixture is scored, and from then on guards against regressions.
