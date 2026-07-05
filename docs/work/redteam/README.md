# Red-team sweep — predictive failure audit of the AI pipeline (2026-07-05)

**Status:** findings register, owner-reviewed. Process docs — deleted when the correctness tracks
fold their fixes into system-state docs. The four appendix files are the verbatim agent reports
with full file:line evidence; [correctness-register.md](../correctness-register.md) is the deduped,
track-assigned index the fix agents work from.

Trigger: a production incident (silent swallowing of spoken patient-name corrections) exposed a
failure taxonomy; four parallel red-team agents then traced every AI job's full path (model output
→ apply semantics → UI surface) against it, BEFORE more of it reached production.

Taxonomy: **T1** silent exits · **T2** missing semantics · **T3** meta-speech leaking into clinical
content · **T4** prompt-invited outputs mishandled · **T5** phantom/stuck UI states · **T6**
orphaned side effects · **T7** cross-surface inconsistency · **T8** ordering/races · **T9**
staleness without invalidation.

Reports:

- [assignment.md](assignment.md) — capture→patient-assignment lattice (16 findings, A-F1…A-F16)
- [synthesis.md](synthesis.md) — synthesis apply, overlay, safety, user-state (15 findings, S-F1…S-F15)
- [projections.md](projections.md) — patient memory, shares, worklist, insights (13 findings, M-P1…M-P13)
- [qa.md](qa.md) — Q&A drafting + public patient surfaces (11 findings, Q-1…Q-11)
