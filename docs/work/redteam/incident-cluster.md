# The original incident cluster — identity-correction fixes 1–7 (owner-validated spec)

**Status:** owner-approved fix spec, 2026-07-05. Consumed by Track E1
([correctness-register.md](../correctness-register.md)). Source incidents: production session
`f3ee7cd5-3aa4-44cc-8d04-2897a3258b34` (five audios; spoken name corrections silently swallowed;
correction chatter promoted to "purpose of visit") and dev sessions `f681a5fb…`/`8b7ea6f8…`
(0.762 possible_match dead zone left a confidently-named visit unassigned + silent).

THE THEME: the assignment pipeline has silent exits; every one must become an action or a visible
choice.

## Fix 1 — identity-correction (rename) semantic
When an assignment intent fuzzy-resolves to the CURRENTLY assigned patient but the spoken name
differs materially from the stored name, that is a name CORRECTION, not an echo:

- **explicit basis** (+ capturer's role permitted) → **rename the patient in place**: update the
  identity, attribute the change, record before→after via the existing feedback-recording helpers
  (do NOT modify services/feedback.py — Track D+ owns it).
- **implicit basis** → a one-tap **"Correct name to X?"** suggestion (ride the existing
  suggested_reassignment surface with a new decision kind + copy).
- Guard: if a DIFFERENT existing patient matches the spoken identity better, prefer the reassign
  flow over rename.
- Aggressive rename only for AI-created + needs_verification patients; human-created patients get
  suggestion-only.

## Fix 2 — never-silent invariant (general form; = register INV-SILENT)
Any confident identity detection or explicit instruction must end in exactly one of:
applied effect · visible suggestion · visible "couldn't act on this" notice. Unit tests enumerate
the full decision lattice (exact / ≥auto-apply / suggest-band / below-band / no-match ×
assigned/unassigned × explicit/implicit × strictness × role-permission) so no cell is silent.

## Fix 3 — intent classification
«درستش» / «اصلاح بشه» correction directives must classify `explicit` (production audio 4 —
«اسم بیمار سروش معاضد هست درستش.» — came back `implicit`). Transcription prompt fix,
PROMPT_VERSION bump, eval-gated.

## Fix 4 — meta-speech never becomes clinical content
A capture that is assignment/correction-only (intent present, no clinical content) is excluded
from synthesis narrative and summaries while its intent still applies (like out-of-context). The
synthesis + summary + patient-memory prompts get the hard rule: identity/assignment/correction
speech is never treatment content, visit purpose, or summary material. Observed failures:
«هدف از ویزیت 'اصلاح بشه' عنوان شده است» and patient-assignment framing inside visit summaries.
(Prompt/apply side is Track E2's S-F13 batch; E1 owns the capture-level meta-only marker.)

## Fix 5 — verify-count correctness
(Assigned to Track B — its files.) `patientVerifyNeeded` gated on actual `needs_verification`
status (CaptureScreen.tsx:228 counts mere existence of ai_patient_action;
captureModel.ts:757 never filters by status), plus the structural invariant: every counted
blocker must render a reachable resolver — test-enforced.

## Fix 6 — orphan archive on reassign-away
Reassigning a session away from an AI-created needs_verification patient that nothing else
references archives that patient (reuse the undo path's `_archive_orphaned_ai_patient` helper).

## Fix 7 — kill the threshold dead zone
On an UNASSIGNED session with a detected identity, when no match clears the assign/suggest
thresholds (`NEAR_MATCH_SUGGEST_THRESHOLD = 0.78` vs the observed 0.762 possible_match):
treat as `no_match` for the decision → **create + assign** the spoken patient (capture-first,
first-identity-wins), keeping the near-miss visible as an informational chip
("Created سروش معاضد · similar to existing سورنا معاضد") with a one-tap use-existing/merge escape.
The 0.78 floor gates candidate promotion, never whether a resolution path exists.

## Golden cases i–vii (owner-approved)
(i) explicit same-person rename applies; (ii) implicit bare-name after a wrong assignment →
correction suggestion, never silence; (iii) «…هست درستش» → explicit; (iv) report sections never
contain correction chatter or meta-derived "purpose"; (v) summaries contain no
patient-identity/assignment framing; (vi) the never-silent lattice (unit-level); (vii) existing
similar patient + distinct new name on a fresh visit → new patient created+assigned with
similar-to note.

## Fixtures (owner-approved reuse — his own voice, no patient data)
Pull the production audio artifacts via `ssh engram` (session `f3ee7cd5…`, MinIO bucket
`engram-captures`) and the dev-stack clips (local MinIO, sessions `f681a5fb…`/`8b7ea6f8…`) into
the eval staging dir as new mNN/iNN items; author expectations; wire into transcription/matching
evals; update RECORDING_CHECKLIST.md.
