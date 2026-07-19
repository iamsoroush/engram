# Treatment-row actions consolidated; no theme-based UI for now (2026-07-08)

- **A treatment row has two actions, not three.** Correcting a field is the inline ✎ **Edit** (an
  instant human overlay — the treatment-overlay decision: never route a field correction through a
  re-synthesis); `↗ source` stays for traceability. The row's **"Fix at source" button was removed**
  — it duplicated the overlay path and contradicted that decision. `Fix at source` survives only on a
  coded review **note** with no editable row (low confidence / missing lot). Don't re-add it to rows.
- **Action chips are chrome → app language.** The `↗ source` citation now resolves via `t()`
  (`report.sourceCitation`), not the report's content language. Previously it followed
  `reportLanguage`, so a Persian report + English app showed "منبع" next to an English "Fix at
  source" on the same row.
- **No `prefers-color-scheme` in the app.** The only two dark-theme blocks (session patient strip +
  treatment editor, in `sessionSurface.css`) were removed so no section darkens alone on a
  dark-default browser. The app is single-theme (light) until a real theming pass is scoped.
