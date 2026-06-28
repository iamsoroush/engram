# doc-impact — S3: capture/session + report chrome (highest traffic)

Branch `i18n/s3-capture` off main `f615699`. ~13 components + `captureModel.ts`/`metadata.tsx`.
This is the largest surface and the one with the safety-critical CHROME-vs-CONTENT boundary.

## The two-axis boundary (the safety gate) — held + verified

Two independent language axes, kept crisp:

- **App-language CHROME → `t()`** (the app UI furniture the clinician interacts with).
- **Report-language CONTENT → untouched** (the clinical document, which follows `tenant.reportLanguage`).

`REPORT_SECTION_TITLES_FA` / `localizedSectionTitle()` in LiveReport.tsx stay **100% `reportLanguage`-
driven — never routed through app `t()`**. Same for the in-report source-citation label and the
Before/After labels (caller-parameterized by `reportLanguage` in the report context; left as-is).

**Verified end-to-end** (Generator self-check, then deleted; reproduced for the Evaluator below):
- app=fa · report=en ⇒ section title **"Assessment"** (English, report-driven — NOT "ارزیابی"); the
  content token renders byte-identical; app chrome (capture bar) is Persian. ← the decisive catch.
- app=fa · report=fa ⇒ section title **"ارزیابی"**; content verbatim.
- app=en · report=en ⇒ "Assessment" + English chrome.

### Structural selectors (amendment 2) — chrome vs content

- **CONTENT region:** `.structured-report-section.structured-report-body` now carries `data-content`
  + `data-testid="report-body"`. Report prose/blocks/captions/treatment values/notes render inside it.
  A no-English-leak chrome scan should **exclude `[data-content]`** (legit-English content lives there
  when reportLanguage=en).
- **Section title:** `<h3 data-testid="report-section-title">` (reportLanguage-driven).
- Other content lives under stable classes: `.basic-report-entry-body` (Basic prose), `.treatment-item`
  (the treatment LABEL is content; its flags/`Fix at source`/`Confirm dose` are app chrome), source-
  detail transcript/caption bodies, `.session-context-*` patient-context values.
- **CHROME containers** (scan these): the capture bar, `.session-verify-bar`, `.report-meta-strip`,
  the account/report toolbars, dialogs/sheets, badges, the assignment sheet, status chips.

### Deterministic two-axis mock (hand-off for the Evaluator's gating spec)

```js
// payload: authPayload({role:"owner",tier:"pro"}) with tenant.appLanguage + tenant.reportLanguage set INDEPENDENTLY
// installAppMocks(page, payload), then override sessions:
await page.route("**/api/v1/sessions**", r => r.fulfill({ json: [SESSION] }));
const TOKEN = "ZZQOLTOKEN42";
const SESSION = {
  id: "s-twoaxis", status: "complete", patientId: "p-1", patientName: "Test Patient",
  capturedAt: "2026-06-20T08:30:00.000Z",
  items: [{ id: "c-1", type: "note", status: "processed", detail: "note", time: "08:30" }],
  reportModel: { sections: [{ id: "assessment", title: "Assessment",
                              blocks: [{ type: "paragraph", text: TOKEN }] }] },
};
// CRUCIAL: seed the workspace so the session is restored ACTIVE (else the report never renders):
await page.addInitScript(sid => localStorage.setItem("engram-active-workspace", JSON.stringify({
  schemaVersion: 1, tenantId: "tenant-1", screen: "active-session",
  activeSession: { id: sid, items: [] }, selectedSessionId: sid,
  assignmentSessionId: "", pendingCaptureKind: null, updatedAt: 1,
})), SESSION.id);
// then dev-persona login (Doctor), wait getByTestId("report-section-title").
// Oracle: section "assessment" → report=en "Assessment" / report=fa "ارزیابی"; report-body contains TOKEN both ways.
```

## RTL — directional-glyph mirror table (amendment 3)

| glyph | where | directional? | mirror under RTL? |
| --- | --- | --- | --- |
| `→` verify-bar "Review →" | SessionVerifyBar (split into `.verify-arrow`) | yes (points to content) | **yes — `[dir=rtl] .verify-arrow { scaleX(-1) }`** |
| `↗` source citation | LiveReport SourceCitation | diagonal "open" indicator | no (report-content axis; minor) |
| `▶` voice-memo play | SessionContextCard | media-control convention | no (play never mirrors) |
| `✎` Fix at source / `✓` Dose confirmed / `ⓘ` note / `⚠`/`⌀` | report/badges | no | no |

### Physical-L/R → logical CSS list

The capture/report stylesheet is already logical-first; only one physical prop was in scope:
- `.session-context-facts-label` `margin-right: 4px` → `margin-inline-end: 4px`.
- NEW `[dir="rtl"] .verify-arrow { transform: scaleX(-1) }` (+ `.verify-arrow { display:inline-block; margin-inline-start:4px }`).
- (Out of S3 scope, noted for S5: `.share-aftercare-select margin-left:auto`, `.share-preview-treatments padding-left` live in the patient-share sheet.)

## captureModel exhaustive enums (amendment 4)

Chrome-producing pure helpers were made translatable by threading a `Translator` (`t`) and returning
`model.*` keys; all call sites updated. Exhaustive status/stage/ordinal/title/attribution enums keyed in
BOTH catalogs — no reachable status renders raw English under fa. `AI_ORGANIZING_NOTICE` →
`aiOrganizingNotice(t)`. A second pass caught chrome that the first deferred (session meta
"Created/Updated…", `patientDetailRows` field labels, "Assigned patient"/"Not recorded", the
`Transcript/Caption/Extraction status` metadata labels, the low-confidence-caption review reason).

### Kept English (CONTENT, traced as persisted/document text — render inside `[data-content]`)

- `titleByType` storage defaults (re-keyed at render by `captureDraftLabel`), `detailByType`
  (`item.detail` — note/source body), `draftCaptureText` placeholders, `captureGeneratedText`
  fallbacks, treatment attribute KEY labels ("Body area"), and the "Generated by AI" **sentinel**
  (rendered as the ✨ spark icon, already labelled via `badge.generatedByAi`).

## Notes for the Planner

- Tiny en edge: ordinals > 10th now render "{n}th" uniformly (the original `ordinalWord` already did
  this past "tenth"; `SessionContextCard.ordinalText` previously emitted "21st/22nd" → now "21th").
  Negligible for visit counts; flagged for the wording pass.
- Catalog grew to **474 en / 474 fa keys** (matched; verified no fallback gaps). Guard baseline 541→423.

## App.tsx capture-flow chrome (CHANGES_REQUESTED fix — round 2)

The Evaluator correctly caught that doc-impact-S1 assigned the App.tsx capture-flow chrome to "→ S3",
but my S3 contract scoped only `features/capture/**`. Resolved by **translating** (not deferring):
`App()` renders ABOVE `AppLangProvider` (so no `useT()`), so a stable app-level translator
`appT = (k,v) => translate(toLang(authRef.current?.tenant.appLanguage), k, v)` is bound to the live app
language and threaded into `captureContextLabel(...)` + the capture toasts. +22 `capture.*` keys.

- **Translated (S3):** `captureContextLabel` ("Capturing for: {name} · Today's visit" / "· new visit" —
  patient NAME stays data), "Unassigned visit", "Current capture destination", and the capture toasts
  (new-session-ready, could-not-start-visit, generating-report + detail, report-generating,
  session-title-updated, could-not-update-title, capture-renamed, caption/transcript-updated,
  capture-deleted ×2, marked-relevant, dose-confirmed, could-not-confirm-dose, could-not-update-
  aftercare, could-not-load-captures, add-next-capture).
- **Still in App.tsx but correctly OWNED BY LATER STORES** (per doc-impact-S1 mapping, NOT S3):
  memory/patient toasts → S4 (Visit unassigned, Patient created, AI-created patient verified, …);
  settings/auth toasts → S5; offline/sync/storage toasts + the "No auth session" throw → S6.
- Verified: capture-bar context label Persian under fa (no "Capturing for" leak); en byte-unchanged.

## Non-blocking notes — disposition

- **Mixed digits** (Jalali dates show Persian digits ۰–۹, but interpolated counts like "1 ثبت" use
  Western digits): deferred to **S6** (a cross-cutting Persian-digit-formatting polish for interpolated
  numbers — belongs with the S6 RTL/polish sweep, not a per-surface fix). Tracked here for S6.
- **"21th" ordinal** (>10th): Planner wording pass (negligible; the original already did this past
  "tenth").
