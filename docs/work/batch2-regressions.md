# Batch-2 production regressions — triage + fix plan (2026-07-08)

Owner-reported from the live app (engram.ir; `ssh engram`) after Batch 2 merged. Fix before
Wave 5 / Track G. Delete when merged. Root causes diagnosed against `main` + prod DB.

## R1 — Report section titles render in English on a Persian report
**Symptom:** "Visit summary" / "Treatment performed" (English) above Persian report content.
**Root cause:** the prod tenant has `report_language = NULL` (`app_language=en`) — confirmed in
`SELECT report_language FROM tenants`. `localizedSectionTitle` (LiveReport.tsx:30) only maps to
Persian when `isPersianReport(reportLanguage)` is true; null → English fallback. The AI writes
Persian because it follows the transcript, so titles and body disagree.
**Fix:**
- Frontend: when `reportLanguage` is null/unset, infer the section-title language from the report's
  own content direction (the sections/body are RTL Persian) rather than defaulting to English — or
  fall back to `transcriptionLanguage`/`appLanguage` before English.
- Backend: default `report_language` to a real value at tenant creation (don't leave NULL) — mirror
  transcription/app or the market default. The Settings dropdown shows فارسی while the stored value
  is NULL (a save/display mismatch to also check).
- **PROD DATA FIX (immediate, no deploy):** set the live tenant's `report_language='fa'` so the
  owner's current sessions render correctly.

## R2 — Raw synthesis keys leak into the treatment row
**Symptom:** the treatment row shows `planned_vs_performed: نامشخص …`, `· low confidence`, and a
duplicated/oversized "Fix at source" block.
**Root cause:** `treatmentAttributeLines` (captureModel.ts:932) is meant for *open technique
attributes* (needleGauge, depth) but dumps **every** `attributes` entry as a raw "key · value"
line; synthesis schema-v3 (Batch 2) now places status/semantic keys (`planned_vs_performed`, …) in
`attributes`, so they render raw. The S-F11 uncertainty→treatment_review wiring (Track E2/B) also
surfaces `low_confidence`/coded notes too noisily.
**Fix:** whitelist the technique-attribute keys the row renders (or blacklist status/uncertainty
keys); route `planned_vs_performed` + coded uncertainties through the calm review-note path only,
never as an attribute line. Ideally the synthesis contract separates `techniqueAttributes` from
status codes — check `contracts/synthesis.py`. Eval-gated if the prompt/contract changes.

## R3 — Broken "Fix at source" circle (CSS)
**Symptom:** an empty circular container with "Fix at source" text floating in the treatment area.
**Root cause:** CSS regression from Track F's token/primitive sweep on `.treatment-fix-at-source`
(LiveReport.tsx:483/590) and/or `.treatment-review-note` — the note container renders as a
malformed circle. **Fix:** restore the review-note / fix-at-source styling to a calm inline chip.

## R4 — Top-bar icons misaligned + a detached "8" badge
**Symptom:** the search/chat/bell/avatar row is uneven; an "8" count sits detached in the top-right
corner.
**Root cause:** Track A added the Attention bell + count; Track F reworked the header. The
attention badge is absolutely-positioned to the page corner instead of anchored to the bell.
**Fix:** align the top-bar action row (Search · Q&A · Attention bell · avatar) on the shared header
grid; anchor the count badge to the bell icon; RTL-check.

## R5 — Audio captures won't open on click
**Symptom:** clicking an audio capture does nothing (both browsers).
**Root cause (to localize):** a click-handler / player-open regression in the capture card
(session-surface refactor). **Fix:** restore the audio card's open/expand + inline player.

## R6 — Safari shows 0s audio duration (Chrome correct)
**Symptom:** WAV audio plays in Chrome with correct length; Safari shows 0:00 duration.
**Root cause:** the stored audio is WAV/PCM with a correct `duration` in metadata (3.34s etc.), so
this is playback, not data. Safari requires HTTP **Range** support (`Accept-Ranges: bytes` + 206
Partial Content) to compute a WAV's duration; the capture file endpoint
(`/api/v1/captures/{id}/file`, streamed) or the presigned MinIO response likely returns 200 without
range support. **Fix:** serve capture media with range support (prefer redirecting to a presigned
MinIO URL — MinIO honors Range — or add range handling to the streaming endpoint). Verify in Safari.

## Sequencing
R1 prod-data fix is immediate (SQL, no deploy). R1-code/R2/R3/R4/R5/R6 are one focused frontend +
narrow-backend branch, CI-gated like any merge. R6 is backend/media; R2 may touch the synthesis
contract (eval-gated).
