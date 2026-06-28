# doc-impact — S4: Clinical Memory / patients / timeline

Branch `i18n/s4-memory` off main `8692dfb`. ~14 components + `memoryModel.ts` + the S4-assigned
App.tsx toasts. All app-chrome (no reportLanguage two-axis); the only boundary is **chrome vs patient
DATA**. +353 catalog keys (now **865 en / 865 fa, matched**); guard baseline 423→273.

## Amd 1 — chrome vs patient-DATA (structural, so the no-leak scan excludes data)

Patient DATA is wrapped in a **`data-content`** marker on the rendering element (subagents added these),
so a fa no-English-leak chrome scan should **exclude `[data-content]`** (a patient named "John Smith",
a typed note, phone/ID, the search query, visit dates are legit-English under fa). DATA marked:
- **PatientsHome / MemoryCards:** patient name (`PatientRow h3`), latest-visit label, memory summary,
  needs-input context/session/since values, history snapshot/section bodies, line-up story/flags,
  capture counts, hero caption.
- **MemorySheets:** patient names (`h2`/`strong`), session/visit titles, capture summaries, decision
  title/reason, suggestion reasons, the summary textarea/`<p>`.
- **WorklistSection:** `entry.patientName`, lined-up patient/clinician names, doctor `<option>` names,
  `entry.note`.
- **PatientTimeline / SearchHome:** patient name (`h1`), card title/summary, session-time/updated/
  attribution labels (Jalali dates), search result label/summary/patient-name. **Search input `value`
  is never `t()`'d.**
- **patient forms / gallery:** the typed field values (name/phone/ID/dob/sex/notes inputs), candidate
  name/reason, visit date/title.
- **CHROME containers to scan** (NOT data): the memory tabs (`Today/Patients/Needs input`), section
  headers, badges, buttons, empty/loading/no-results states, search **placeholder**, sheet titles/labels.

## Amd 2 — RTL mirror table + physical-L/R→logical CSS

| element | decision |
| --- | --- |
| **timeline vertical spine** (`.patient-timeline::before`) + **nodes** (`.patient-timeline-marker`) | flip to inline-start via logical props (no glyph) — spine + markers now sit on the RIGHT under RTL |
| **"Recap ›"** forward chevron (WorklistSection) | mirrored — fa value uses `‹` |
| `.capture-generated summary::before` `›` disclosure chevron | **S3 surface, NOT S4** — flagged for S6 polish (directional disclosure chevrons app-wide) |
| memory list/card layout (flex/grid + logical gaps) | auto-flips; no physical props remained |

**Physical-L/R→logical CSS changes:** `.patient-timeline` `padding-left`→`padding-inline-start`;
`.patient-timeline::before` `left`→`inset-inline-start`; `.patient-timeline-marker` `left`→
`inset-inline-start` (both base + ≤media-query); `.last-visit-link` / `.patient-gallery-meta` /
`.patient-detail-share` `margin-left`→`margin-inline-start`. (`.phone-shell` padding-left also went
logical incidentally — identical under LTR, RTL-correct.)

## Amd 3 — glossary reconciliation (one term/concept)

Parallel subagents used a shared glossary; the central merge reconciled the conflicts:
`capture`=**ثبت** (memoryModel's ضبط→ثبت), `assign`=**تخصیص** (memoryModel's اختصاص→تخصیص), `Mine`=**مال من**
(worklist's خودم→مال من), `Cancel`=**انصراف** (لغو→انصراف), `Create patient`=**ساخت بیمار** (ایجاد→ساخت),
`AI`=**هوش مصنوعی** (دستیار→هوش مصنوعی), `Updated`=**به‌روزرسانی** (بروزرسانی→به‌روزرسانی). Canonical:
patient=بیمار, visit=ویزیت, session=جلسه, Today=امروز, Patients=بیماران, "Needs input"=نیازمند ورودی,
search=جستجو, timeline=خط زمانی, "Clinical Memory"=حافظهٔ بالینی (matches S2 nav.memory).

## Amd 4 — empty / loading / needs-input states (all translated)

"No patients yet" / "No active visit" / "All caught up · Nothing needs your input right now" /
"No visits updated today" / "No matching patients found" (+digit/filter variants) / "No one is lined
up right now" / "No visits yet" (timeline) / "No matching loaded memory" (search) / "Loading…" /
"Searching…" / "Patient search is unavailable right now". memoryModel summary placeholders translated
too. No English empty/loading-state leak under fa.

## memoryModel architectural note

The pure helpers (status badges, action labels, summaries) are now `Translator`-threaded (`memmodel.*`,
~104 keys). **Critically, the English-string comparisons that drove badge CSS were refactored to stable
enums** — `timelineSessionStatus`→`{label, tone}`, `PatientRowModel.badges`→`PatientBadge[]{label,kind}`,
`timelineUpdatedLabel`→`{label, assignedToday}` — so styling/logic survive fa (no `startsWith("Needs
input")` against a now-Persian string). DATA (names, dates, summaries) stays verbatim.

## Amd 5 — gating-spec hand-off (mock + oracle)

**Reach Clinical Memory:** dev-persona login, then click the memory nav: `.app-navigator button` nth(1)
(NOT a workspace-screen seed — the app restores session, not screen). PatientsHome then renders.
- **Oracle (fa):** tabs «امروز» / «بیماران» / «نیازمند ورودی»; search placeholder «جستجوی بیماران بر اساس
  نام، تلفن یا کد ملی…»; empty state «هنوز بیماری وجود ندارد.». **en:** Today / Patients / Needs input.
- **Data-verbatim:** mock `**/api/v1/patients**` → `[{ id, displayName: "Sara", ... }]`; assert "Sara"
  renders verbatim (it's under `[data-content]`) and dates render Jalali under fa.
- **No-leak scan:** scope to chrome, exclude `[data-content]`.
- **CORE journey:** Clinical Memory → tab (Today/Patients/Needs input) → type in search → open a patient
  timeline — works in fa and en.

Self-verified: tsc 0 · catalog 865/865 matched, all keys resolve · guard 0 (273) · en regression e2e
20/20 (S1/S2/S3 gating + existing) · fa/en memory-tabs smoke ✓.
