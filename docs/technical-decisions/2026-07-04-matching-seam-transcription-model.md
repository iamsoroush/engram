# Matching Seam Runs on the Transcription Model — `m02` Near-Miss Stays a KnownGap (2026-07-04)

The patient-matching LLM seam (spoken-name extraction + assignment-intent) is **not a separate model**:
it is a by-product of audio transcription (`transcribe_audio_content` emits `patient_information` +
`intents`), so it runs on `AI_ENGINE_TRANSCRIPTION_MODEL` — live default **`gemini-3.1-flash-lite`**
([ai_engine/config.py](../../apps/ai_engine/ai_engine/config.py)). The `m02` eval knownGap (a near-miss
surname «نگار معمری» intermittently auto-corrected to the existing patient «نگار محمدی») is a property
of **that** model class: measured 3× per model, flash-lite returned «محمدی» twice / «معمری» once and
`gemini-3.5-flash` also snapped to «محمدی», while `gemini-3.1-pro-preview` preserved a distinct name.

**Decision: keep transcription (and therefore the matching seam) on the flash-lite class; the `m02`
knownGap stays open, not retired.** Transcription runs on **every** capture — it is the highest-volume
AI call — so a pro-class model there is not cost-justified for the whole pipeline just to harden one
near-miss path. The deterministic backend gate is the real safety net (a fuzzy near-miss is **never**
silently auto-assigned regardless of the extracted string — `test_ai_assignment_gate.py`), so the
model's occasional auto-correction degrades a *candidate suggestion*, not patient safety. Retiring the
knownGap is deferred until the matching seam can take a **pro-class model independently** of bulk
transcription (a separate per-task model for the name-extraction path), at which point the eval's `m09`
noisy re-record proves the fix under load. Tracked in [ai_engine/evals.md](../ai_engine/evals.md).
