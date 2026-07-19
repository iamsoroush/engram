# Synthesis-context prompt & cache restructure + first-class treatment status (2026-07-09)

Track-G — the AI-prompt/context restructure and the planned-vs-performed treatment status. Standing
rules future agents must respect:

- **Stable-prefix synthesis context layout.** The synthesis context is serialized in an explicit,
  deterministic order — static framing → clinic-stable block → patient-stable block → captures as ONE
  flat append-only chronological list → per-run volatile tail (`changeset`, `priorDraftTreatments`,
  `priorReportModel`, reconcile memo) LAST — NOT `json.dumps(sort_keys=True)`. `serialize_synthesis_context`
  (`services/session_processing.py`) is the byte authority; the ai_engine synthesis prompt mirrors the same
  ordering with `sort_keys=False` and MUST stay in lockstep. **A new synthesis-context field APPENDS to
  the volatile tail (or, if genuinely tenant-stable, to the END of the stable block) — never spliced into
  the middle of the stable region**, which would move the gateway prefix-cache boundary and re-price every
  re-run. The prior report is fed **exactly once** (`priorReportModel`); re-feeding `session.extracted_metadata`
  is gone (~43% smaller context for a 5-capture visit, before the prefix-cache win). Captures are a flat
  chronological list, never grouped by type, so a new capture byte-EXTENDS the prior prompt.
- **`planned` never counts as `performed` — anywhere.** A treatment classified `status:"planned"`
  (future-tense / stated intent) is STORED with its status but excluded from every performed view via the
  `performed_treatments` seam (`services/treatment_overlay.py`): treatment-performed prose, recall/lot
  cohorts, smart lists, insights, patient-memory brief + line-up recap, patient-surface "what we did",
  carry-forward reference. It selects no aftercare and raises no dose-confirmation review item; the frontend
  renders it under Plan & follow-up. Tense/intent decides status, never the confidence field. A declined or
  prior-visit-recalled treatment is neither performed nor planned — not extracted. **Consequence:** any new
  treatments consumer must choose `performed_treatments` (performed record) vs `effective_treatments` (all,
  incl. planned — the frontend projection) deliberately.
- **Capture jobs get identity-minimal context.** Transcription receives the assigned patient's
  name-spelling fields only (nationalId/phone/DOB/email/sex withheld at the source); caption receives no
  patient identity at all. Removing the temptation to "confirm" a half-heard identifier from context pairs
  with the shipped A-F5 name/ID cross-check; the caption is a neutral objective extractor.
