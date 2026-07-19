# Model-comparison harness — fixtures + scoring spec

Reusable harness for comparing candidate models across all AI jobs (the bracket table below is the
2026-07-10 run's; a new comparison swaps the candidates). Every case file
here is **owner-designed and frozen**: executing agents implement the scorers and run the matrix;
they do not add, remove, or reinterpret cases.

## What is being decided

A **low-cost champion** and a **mid-cost champion** across the text AI jobs, plus the **price
consequence** of adopting each (how `visit_cost` and the AI-usage-limit headroom of
`docs/business/ai-usage-limits.md` §2–3 move vs today).

| Bracket | Candidates | Applies to |
| --- | --- | --- |
| Low-cost | `gpt-5.4-nano` vs `gemini-3.1-flash-lite` | every text job below |
| Mid-cost | `gpt-5.6-luna` vs `gemini-3.5-flash` | every text job below |
| Transcription (audio) | `gemini-3.1-flash-lite` vs `gemini-3.5-flash` | transcription only |

Jobs and their case files (captioning is explicitly out of scope):

| Job | Cases | Incumbent |
| --- | --- | --- |
| Report synthesis | [cases-synthesis.json](cases-synthesis.json) (34) | `gpt-5.4-nano` @ effort=low |
| Patient memory | [cases-patient-memory.json](cases-patient-memory.json) (10) | `gemini-3.1-flash-lite` (fallback) |
| Safety reconcile | [cases-safety-reconcile.json](cases-safety-reconcile.json) (10) | `gemini-3.1-flash-lite` (fallback) |
| Q&A draft | [cases-qa-draft.json](cases-qa-draft.json) (12) | `gemini-3.1-flash-lite` (fallback) |
| Q&A revise | [cases-qa-revise.json](cases-qa-revise.json) (8) | `gemini-3.1-flash-lite` (fallback) |
| Transcription | [transcription-scripts.md](transcription-scripts.md) (T01–T12, owner-recorded) | `gemini-3.1-flash-lite` |

## How to run a case

- Build each job's prompt with its production builder in `ai_engine/prompts/` — `synthesis.build`,
  `patient_memory.build`, `safety_reconcile.build`, `qa_draft.build`, `qa_revise.build` — feeding
  the case's payload in the exact shape that builder consumes (each case file's `note` states it;
  mirror `app/services/session_processing.py::_capture_input` for synthesis captures). Do not
  modify any prompt.
- Call the gateway (`https://gw.engram.ir/v1/chat/completions`, key from the ai-engine env) with
  `response_format=json_schema` using the job's schema from `ai_engine/contracts` where the
  production path does. If a provider rejects json_schema, report it as a finding.
- **3 samples per case per model**; a case's verdict per model is the majority. Report per-sample
  rates too.

**Transcription** is the one job whose evaluation data cannot be synthesized (audio is never
auto-generated — owner rule). The owner records the T01–T12 scripts in
[transcription-scripts.md](transcription-scripts.md) as one fresh dev-app session (one recording
per script, in order); the script text is the reference. Pull the recordings' source audio via the
capture API and score as that file specifies: CER/WER, exact clinical-token accuracy (doses, units,
drug/brand names, lot digits), romanization rate (Persian in Latin = fail). Same 3-samples-per-clip,
both candidate models.

## Scoring semantics (deterministic; implement once, no imports from `apps/ai_engine/eval/`)

Persian matching is substring-based after Unicode NFC normalization; treat `ی/ي`, `ک/ك`, and
ZWNJ/space as equivalent.

Synthesis (`cases-synthesis.json`) — "prose" = summary + section texts + uncertainty texts:

- `treatmentCount` (int or `{min,max}`); `treatments[]` each matching a distinct emitted item:
  `productAny`/`areaContainsAny`/`quantityTextContainsAny`/`brandContainsAny`/`unitAny` (substring
  any-of), `quantity` (numeric), `lot` (exact), `statusIn`, `supersedesRequired` (non-null
  `supersedesCaptureId`), `attributesContainAny`.
- `flags`: `expectNone`, or `expect[]` of `{kindIn, textContainsAny}` (distinct matches; no
  unexpected flag when `expectNone`).
- `prose`: `mustContainAnyGroups` + `forbidden`; `sectionRules[]` (per-section `forbidden`);
  `summaryForbidden`; `uncertainties` (`expectNone` | `mustCodeAny`).
- `aftercare`: `selected[]` `{templateId, statusIn}` + `notSelected[]`. Cases with
  `useAftercareTemplates` get the file's `aftercareTemplates` in context, serialized the way
  `_aftercare_templates_for_synthesis` sends them.
- `image`: `referencedOnce`; `latin`: `forbidLatinProse` + `allow`.

Patient memory — "text" = summary + history sections + card fields: `text` (same
mustContain/forbidden shape), `flags` (`expectNone` | `expect[]` with `labelContainsAny`),
`latin`, `cardSentenceMax` (max sentence-final marks per card field).

Safety reconcile: `duplicatePairs` (exactly ONE of the pair marked duplicate, `ofKey` = the other;
neither dropped), `keepAll` (every key decided keep), `supersededOld` (old key annotated
superseded), `decisionsComplete` (one decision per given flag).

Q&A draft / revise — "reply" = the drafted text: `reply` (mustContainAnyGroups/forbidden/
`forbiddenNumerics` = no digit or number-word duration/dose), `signOff` (doctor name present),
`latin`.

`flex` notes name acceptable-alternative outcomes: score the strict rule as PASS, record the flex
alternative as *partial* (both columns in the readout).

**Safety events** (tabulate separately; any occurrence disqualifies that model for that job
regardless of averages): wrong dose, invented treatment, dropped expected allergy/contraindication,
fabricated flag on `expectNone`, superseded value restated in prose, patient name in summary/memory,
cross-patient number copied into a reply, a reply contradicting the patient's own aftercare, a
reconcile decision that DROPS a distinct safety flag, transcription dose/drug-token errors.

## Quality judging (secondary, blind)

Pairwise per case within each bracket, judge = a model in neither bracket (e.g. `gpt-5.4-mini` on
the same gateway), identities hidden, order randomized. Judge scores break ties and inform the
memo; they never override deterministic safety events.

## Cost & usage-limit projection

1. Per model, measure real per-run cost from the gateway's priced usage fields:
   - synthesis: reproduce ai-usage-limits §1's 10-capture visit (coalesced + per-capture modes);
   - each other job: mean cost over its case set (report tokens in/out too);
   - transcription: mean $/audio-minute over the fixture clips.
2. Recompute §2's `visit_cost` and $/seat/mo (light/typical/heavy, Pro volume assumptions from
   `compute-cost-model.md` §2) for four adoption scenarios: **all-low champion set**, **all-mid
   champion set**, and each bracket's per-job mixed optimum.
3. Report: $/visit, $/seat/mo per scenario, **effective visits per $10/seat budget** (the usage-
   limit headroom) vs today's baseline, and what `ai_budget_usd_per_seat` would need to be to keep
   today's headroom under a pricier winner.

## Audio-format comparison (transcription add-on)

Framing (owner decision): the win to chase is **~10× smaller uploads/storage at equal accuracy**,
not better accuracy. The browser already records compressed speech (MediaRecorder opus/AAC); our
frontend re-encodes to WAV PCM 16 kHz mono (~1.92 MB/min), and Gemini normalizes ALL input audio to
16 kHz mono internally and bills by duration — so richer formats cannot help accuracy or cost, but
compressed formats cut mobile upload time and MinIO storage compounding ~10×. Accuracy is the
GUARDRAIL, size the metric.

- Source: the 12 WAV masters of session `ab64916e-…` (content held constant).
- Grid (transcode locally with ffmpeg, always 16 kHz mono): WAV PCM (control), FLAC, OGG/Opus
  32 kbps, OGG/Opus 16 kbps, MP3 64 kbps, MP3 32 kbps.
- Both transcription candidates × 6 formats × 12 clips × 3 samples; score with the same
  transcription scorer (clinical-token accuracy + number-normalized CER). A gateway/provider
  rejecting a format is a FINDING to report (the gateway is ours and extensible), not a reason to
  work around.
- Report: bytes/min per format, accuracy deltas vs the WAV control per model, and a verdict by the
  decision rule — **the smallest format with zero clinical-token regressions and CER within +0.5pp
  absolute of WAV**. If a compressed format wins, sketch (do not implement) the production change.
  Standardization to ONE canonical stored format stays mandatory (browsers record divergent
  containers — Chrome webm/opus, Safari mp4/AAC); the experiment only picks the canonical TARGET.
  The sketch must weigh where the conversion runs — client-side re-encode (WebCodecs opus support
  is patchy on Safari) vs server-side transcode-on-ingest (accept the native blob, normalize once,
  store only the canonical format) — plus backend validation + duration handling and the gateway
  format allowlist.

## Deliverable

Write the readout to a fresh `work-docs/<comparison>/readout.md` — verdict first (champions, per-job
exceptions if a bracket winner loses a specific job, usage-limit consequence of each adoption
scenario), then per-job deterministic tables, the safety-event table, judge win-rates, cost/latency
tables, and raw per-case JSON artifacts alongside. No production config, prompt, or eval-suite
changes; scripts stay in a scratch dir. Fold the verdict into `docs/technical-decisions/` and
delete the readout per the work-docs lifecycle (the 2026-07-10 run's verdict:
`docs/technical-decisions/2026-07-10-model-comparison-verdict.md`).
