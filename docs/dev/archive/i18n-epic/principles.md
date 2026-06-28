# Persian-UI i18n — design principles (what "good" feels like here)

1. **One seam, zero hardcoded strings.** Every user-visible chrome string goes through the `shared/i18n`
   `t()` catalog (fa + en). A hardcoded literal in JSX is a bug. Prefer a guard/lint that fails on new
   hardcoded UI text so the codebase stays clean as it grows.
2. **App language ≠ report language.** `t()` follows **app** language; clinical CONTENT (report prose,
   captions, treatment text, patient-dictated aftercare) follows `reportLanguage` and is **never** run
   through `t()`. Translating clinical content would be a safety bug. Keep the boundary crisp.
3. **RTL is correctness, not decoration.** Under fa: `dir="rtl"`, logical CSS (margin/padding-inline,
   start/end), mirror only **directional** icons (back/forward, progress), never mirror logos/media.
   Test every screen in RTL, not just LTR-with-Persian-text.
4. **Mixed-script is the norm.** Persian prose routinely embeds Latin brand names (Juvéderm), Western or
   Persian digits, and dose units — these must render correctly inside RTL (use `dir="auto"`/bidi
   isolation where needed). Don't force everything to one script.
5. **Persian-native, clinical, warm.** Translations read like a Persian clinician wrote them, not a
   machine — concise, professional, consistent terminology (a small glossary: visit, capture, report,
   patient, treatment, dose, aftercare, …). Reuse the public-surface wording already chosen.
6. **No English regression.** en must look and behave exactly as before; fa is additive. The same
   components serve both — no forked screens.
7. **Translate the whole journey, not just the labels.** Statuses, toasts, errors, empty states,
   confirm dialogs, a11y labels, placeholders — the long tail is where untranslated English leaks.
