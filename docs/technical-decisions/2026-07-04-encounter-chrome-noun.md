# Encounter Chrome Noun Is Per-Vertical — "Visit" for Aesthetics (2026-07-04)

The clinical encounter's underlying object (and code) stays `session`, but the **chrome noun** the
clinician reads is chosen **per vertical**: aesthetics (and any non-therapy vertical) says **visit**
everywhere — the primary-nav label, the `+ New visit` button, visit titles, the `Visit:` time label;
therapy keeps **session**. `Shell` picks the primary-nav label by `tenant.vertical`
(`nav.activeVisit*` vs `nav.activeSession*`); all other chrome is plain catalog strings. This is
**chrome only** — clinical CONTENT is never touched — and future aesthetics surfaces must not coin
`session` chrome (extends the `glossary.*` terms; the surface note lives in
[ux/screens/capture.md](../ux/screens/capture.md)).
