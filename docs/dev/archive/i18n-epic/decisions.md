# i18n loop — decision log (Planner)

- SCOPE: authenticated-app CHROME only. NEVER translate clinical CONTENT (report prose, captions,
  treatment text, dictated aftercare) — that follows `reportLanguage`, a separate setting. Public
  surfaces (landing/login/onboarding) are already bilingual — out of scope unless a shared seam needs it.
- LANGUAGES: fa + en only this run (structure for more, ship two).
- SEAM: extend the existing `shared/i18n` (built by the A-tier auth work) app-wide; do not invent a second.
- ORDER: S1 foundation → S2 shell → S3 capture/report → S4 memory → S5 settings/team/plan/share → S6 tail+RTL.
- RTL: correctness requirement (dir, logical CSS, mixed-LTR, directional-icon mirroring), tested per screen.
