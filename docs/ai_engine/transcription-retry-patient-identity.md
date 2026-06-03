# Transcription, Retry, And Patient Identity

## Purpose

Audio transcription should become a durable clinical-information extraction step,
not just speech-to-text. The worker should use enough clinic/session context to
produce useful transcripts and patient identity candidates while keeping patient
assignment, patient creation, and duplicate handling reviewable.

## Durable Retry Direction

AI jobs are backend-owned durable rows. The worker may execute Celery tasks, but
retry state lives in the backend so jobs survive worker crashes, broker
interruptions, gateway outages, and missing source files.

Audio transcription jobs should retry until one of these happens:

- the job succeeds
- the capture is deleted
- the job is explicitly marked non-retryable by backend-owned logic

Retry state includes:

- attempt count
- last attempted time
- next retry time
- last error
- retry reason, such as `source_missing`, `gateway_unavailable`, or
  `conversion_failed`

The backend uses bounded backoff, not tight loops. User-facing surfaces should
continue to use calm assistant language such as `Organizing` or `Saved. I will
update memory when ready.` Do not expose retry mechanics as normal clinician
work.

Recovery happens on worker startup and by a periodic recovery dispatcher, so
pending jobs do not depend on a manual recovery call or a fresh worker start.

## Context-Rich Transcription

Audio jobs should receive a stable transcription context from the backend. The
context should be tenant-scoped and include only data the worker needs:

- clinic context, including that the clinic is Persian/Iranian when applicable
- assigned patient context, when the session has a manually assigned patient
- session title, timing, and status
- previous transcripts from the same session
- text notes from the same session
- safe high-level patient history summary when available

The prompt should explain:

- audio may be Persian, English, or mixed
- names may be spoken in Persian but should be transliterated into English
- Iranian national IDs and phone numbers may be spoken as digits
- aesthetics-clinic terminology may include filler, Botox, laser, injection,
  aftercare, asymmetry, touch-up, and similar visit language
- do not infer patient identity unless it is explicitly present or strongly
  supported by context

The transcription output should be structured JSON, with transcript text and
identity extraction separated:

```json
{
  "transcript": "string",
  "language": "fa|en|mixed|unknown",
  "patient_information": {
    "raw_mentioned_name": "string|null",
    "standardized_display_name": "string|null",
    "alternate_transliterations": ["string"],
    "national_id": "string|null",
    "phone": "string|null",
    "date_of_birth": "string|null",
    "evidence": "string|null",
    "confidence": 0.0
  },
  "clinical_summary": "string|null",
  "uncertainties": ["string"]
}
```

The backend should store this under capture metadata without treating it as a
verified patient record.

## Patient Identity Normalization

Staff-entered patient records may contain Persian characters, inconsistent
Latin transliterations, or non-standard capitalization. Preserve staff-entered
display values, and make matching work through normalized identifiers and
aliases.

Do not overwrite patient display names automatically. Store searchable identity
values separately with source and confidence, such as:

- staff-entered raw value
- deterministic normalized value
- LLM-generated transliteration
- transcript-extracted candidate
- manually verified alias

Deterministic normalization should happen before LLM matching:

- normalize Arabic/Persian character variants
- remove diacritics and tatweel
- normalize whitespace and punctuation
- normalize Persian, Arabic, and English digits
- lowercase Latin search keys
- normalize Iranian phone numbers where possible
- normalize national IDs to digits only

Generated aliases are useful for search and matching, but they are lower trust
than exact identifiers or manually verified aliases.

## Patient Matching Boundary

Patient matching is backend-owned and separate from audio transcription. Audio
transcription stores structured `patient_information`; the backend then creates
a reviewable `patient_match_candidate` from normalized identifiers and aliases.

Matching order:

1. exact national ID
2. exact phone or email
3. exact normalized alias
4. fuzzy alias candidate search
5. LLM ranking of a small backend-selected candidate set

The LLM should rank or explain candidates, not search the whole patient table.
It should receive only a small candidate list selected by backend deterministic
search. It should return a candidate decision:

```json
{
  "decision": "matched|possible_match|no_match|insufficient_info",
  "patient_id": "string|null",
  "confidence": 0.0,
  "matched_on": ["string"],
  "reason": "string",
  "risks": ["string"]
}
```

Do not silently override a manually assigned session patient. Do not silently
merge patients. Do not let an LLM create a patient directly. If no safe match
exists, store a patient candidate for a later resolver where staff can assign an
existing patient, create a new patient, or mark identity unknown.

Current backend behavior:

- Uses `patient_identifiers` for deterministic aliases and normalized exact
  identifiers instead of rewriting patient display names.
- Runs exact national ID, contact, exact alias, then fuzzy alias matching.
- Stores the proposal on capture metadata and mirrors it to unassigned session
  metadata for existing assignment/choice flows.
- Includes confidence, reason, risks, and a capped candidate set. Optional LLM
  ranking is represented only after backend candidate selection; no whole-table
  LLM patient search is allowed.
- Does not create patients, assign sessions, merge duplicates, or override an
  already assigned session patient.
