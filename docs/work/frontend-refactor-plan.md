# Frontend refactor plan — dissolving the `App.tsx` orchestrator

**Fold destination:** the target architecture (§2) folds into `docs/architecture.md` (frontend section)
and `docs/frontend/overview.md` once the seams land; the sequencing/checklist below is process-only and
this doc is **deleted** when the last increment merges. Per `docs/work/README.md`, this doc may describe
future/unbuilt state; system-state docs must not link into it.

Plan only — no source changes. Scope: `apps/frontend`. The goal is to cut the *specific* seams the five
deferred structural UX epics (§5) will attach to, so those epics land as modules rather than as more
stacked panels.

---

## 1. The problem — and its root cause

`src/app/App.tsx` is **2,493 lines** and `PatientsHome` takes **45 callback props** (`CaptureScreen`
takes ~40, at two render sites). The visible symptom is prop explosion and "features land as stacked
panels." The root cause is that `App()` is a single god-component fusing **six unrelated
responsibilities** with no seam between them:

| # | Responsibility | Evidence in `App.tsx` |
|---|---|---|
| 1 | **Auth/session lifecycle** | `commitAuth`/`clearAuth`/`refreshAccessToken`, bootstrap effect, `handlePersonaLogin`/`handlePasswordLogin`/`handleRegister`/`handleLogout`/`handleSwitchClinic`/`handleTierChanged`, onboarding flags |
| 2 | **Offline-first sync engine** | `processOutbox`, `processPendingOperations`, `syncPendingOperation`, `hydrateFromStorage`, `queueOperation`, retry `setInterval`, `online`/`backendReachable`, storage guard (~500 lines) |
| 3 | **Capture/session domain store** | `sessions[]`, `activeSession`, `selectedSessionId` + ~20 mutation handlers (`renameSession`, `editCaptureSourceText`, `removeCaptureFromSession`, `assignPatientToSession`, `saveSession`, `selfHealStalePatient`, …) |
| 4 | **API binding layer** | ~30 `useCallback((args) => clientFn(apiFetch, args), [apiFetch])` thin wrappers (`listPatientMemory`, `getPatientMemoryDetail`, `fetchSmartList*`, `listWorklist`, `createShare`, …) |
| 5 | **Navigation + history** | hash `screen` state + a hand-rolled return-stack: `clinicalMemoryReturnContext`, `captureReturnSession`, `accountReturnRef`, `openMemorySession`/`openPatientHistory`/`returnToActiveCapture` |
| 6 | **Render switch** | `renderCurrentScreen()` wires ~45 props into `PatientsHome` and ~40 into `CaptureScreen` |

Because there is **no boundary** — everything is owned at the root and threaded down — the cheapest way to
add anything is: add a `useState`, add a `useCallback`, add a prop. Additive *is* the path of least
resistance because there is no module to attach to. `PatientsHome` proves the shape: it is already a
mini-orchestrator (24 `useState`, its own fetching/pagination/polling) that **also** receives 45 injected
callbacks — most of which are just API functions bound to `apiFetch`.

**The fix is two moves, not one.** (a) *Provide* cross-cutting dependencies (`apiFetch`, `auth`,
capabilities, toast) via **context** instead of threading them — this alone collapses ~30 of
`PatientsHome`'s props. (b) *Relocate ownership* of the sync engine, the session store, and navigation into
their own modules, so `App.tsx` becomes a thin composition root and new features attach to a module seam.

---

## 2. Target architecture

A layered set of seams. `App.tsx` stops being a component-with-logic and becomes a **composition root**
that assembles providers and dispatches routes.

```
main.tsx
└── <AppProviders>                     ← composition root (was App.tsx's body)
    ├── ApiProvider                    seam A1: memoized apiFetch + 401 refresh/retry   (INFRA, shared)
    ├── AuthProvider                   seam A2: auth state + login/register/logout/switch (INFRA, shared)
    │   └── AppLangProvider            (exists) reads tenant.appLanguage
    ├── CapabilitiesProvider           seam A3: tier × role → useCapabilities()          (INFRA, shared)
    ├── ToastProvider                  seam A4: setToast() without prop-threading
    │
    └── <VerticalShell> picks by auth.tenant.vertical / persona:
        ├── UnauthShell (unchanged)  ├── PatientPreviewGate (unchanged)  ├── TherapyApp (unchanged)
        └── AestheticsApp
            ├── SyncProvider           seam B: outbox engine (captures + operations, online/reachable)
            ├── SessionStoreProvider   seam C: sessions[]/activeSession + session actions (on Sync+Api)
            ├── Router                 seam D: typed nested routes + real history (pushState/popstate)
            └── Screens                seam E: self-fetching regions (consume the seams above via hooks)
                ├── features/capture   CaptureScreen → region components
                ├── features/memory    PatientsHome  → self-fetching tab panels
                ├── features/qa, insights, account, search …
```

Consumption is via **hooks**, not props: `useApi()`, `useAuth()`, `useCapabilities()`, `useSync()`,
`useSessions()` / `useActiveSession()` / `useSessionActions()`, `useNavigation()`, plus per-feature API
binders (`useMemoryApi()`, `useCaptureApi()`) that wrap the client with `apiFetch` from context.

**Why context + hooks (+ `useReducer`), no new dependency.** The codebase already uses exactly this
pattern — one context (`AppLangProvider` in `shared/i18n`) and custom hooks (`useAiUsage`,
`useVoiceEdit`). Match it. The one real design fork:

> **Render-cadence.** A single context holding `sessions[]`+`activeSession` re-renders every consumer on
> any session change. Mitigate with the **split-context pattern**: a *stable* actions/context object
> (never changes identity) separate from *volatile* state slices, so components that only dispatch don't
> re-render on data churn. Escape hatch if that isn't enough: back the store with `useSyncExternalStore`
> and selector subscriptions (still no external dep) — decide at seam C, not before.

**Infra vs shell.** `ApiProvider`/`AuthProvider`/`CapabilitiesProvider` are shared infrastructure — the
therapy vertical and patient-preview branch can consume them too. `SyncProvider`/`SessionStore`/`Router`
are the *aesthetics* shell; the top-level vertical branch in today's `App` (unauth → patient-preview →
therapy → aesthetics) is preserved as `<VerticalShell>`.

---

## 3. What actually collapses (the 45 → ~3 math)

`PatientsHome`'s 45 props partition cleanly by destination seam:

| Destination seam | Props absorbed | Count |
|---|---|---|
| `useMemoryApi()` (apiFetch-bound client, capability-gated internally) | `onGetPatientMemory`, `onUpdatePatient`, `onFetchPatient`, `onCreatePatient`, `onListPatientMemory`, `onSearchPatients`, `onLoadSessionCaptures`, `onLoadSession`, `onLoadAssignmentSuggestion`, `onSmartSearch`, `onDuplicateCheck`, `onResolveFile`, `onLoadLastVisit`, `onListAftercareTemplates`, `onCreateShare`, `onRevokeShare`, `onOpenQaChannel`, `onFetchSmartListCounts`, `onFetchSmartList`, `onFetchLotLedger`, `onFetchLotRecall`, `onListWorklist`, `onLineUpPatient`, `onMarkWorklistSeen`, `onCancelWorklistEntry`, `onListClinicMembers` | 26 |
| `useSessions()` / `useActiveSession()` / `useSync()` reads | `activeSession`, `sessions`, `syncHealth`, `memoryRefreshSignal` | 4 |
| `useSessionActions()` | `onAssignPatient`, `onConfirmSummary`, `onContinueSession`, `onStartVisit`, `onExportCaptures` | 5 |
| `useAuth()` / `useCapabilities()` | `auth`, `tier`, `shareIncludeBrands`, `shareLanguage` | 4 |
| `useNavigation()` + route params | `onOpenSession`, `onBackToVisit`, `onViewingPatientChange`, `initialPatientId`, `initialTab` | 5 |
| `useToast()` | `onToast` | 1 |
| **Genuinely remaining** | route params only (`patientId`, `tab`) | ~0–2 |

The Pro-only props today are gated by *conditional passing* (`onFetchSmartList={isPro ? cb : undefined}`).
Inside `useMemoryApi()` that becomes a capability check at the call site — so the tier fork stops living in
`App`'s prop list (this is the Basic/Pro-convergence seam). `CaptureScreen`'s ~40 props collapse the same
way: mutation callbacks → `useSessionActions()`; `sessionContext`/`lineupCard`/`aftercareTemplates` →
region components that fetch their own slice; `tier`/`reportLanguage`/`offline`/`usageNotice` →
capability/sync/aiUsage contexts; `activeSession`/`mode` → store + route.

---

## 4. Sequenced increments

Each increment is independently shippable and revertible, keeps behavior identical, and passes the
**per-increment gate**: `npm run build` (`tsc -b` — the type net), `npm run test:unit`, `npm run test:e2e`
(hermetic, mocked API), `npm run i18n:guard`, and `npm run test:visual` when a touched surface has a visual
spec.

**Reality check on the safety net.** Existing automated coverage is **1 unit test** (`i18n/appLang`) plus
**11 hermetic e2e specs** + 1 visual + 1 real-stack spec (`tests/e2e-stack/`). So the net is
*behavioral (e2e) + types (`tsc`) + chrome (i18n guard)*, not unit-level. The plan therefore **front-loads
characterization tests** — and note the upside: extraction *creates* unit-testability that `App.tsx` never
had (a reducer/hook is testable; a 2,500-line component is not). e2e coverage maps to increments as:

- Auth/onboarding/role-gating → `onboarding.spec`, `account-menu.spec`, `landing-auth.spec`, `i18n-foundation.spec`
- Memory/patients/timeline → `i18n-memory.spec`, `visual/clinical-memory-today.spec`
- Pro Lists + tier-gating → `smart-lists.spec`
- Capture/report two-axis → `i18n-capture.spec`
- Cross-screen chrome sweep → `i18n-shell.spec`, `i18n-tail.spec`

### Increment 0 — Safety net (no production code moves)
- Add characterization **unit tests** around the pure modules the refactor leans on and that are currently
  untested: `app/sessionState.ts` (`mergeSessionUpdate`, `markReportStale*`, `resolveRestoredSession`),
  and high-traffic selectors in `captureModel.ts` / `memoryModel.ts`. These are already pure — pure profit.
- Add **hermetic e2e** for the highest-risk flows the refactor touches but nothing currently pins:
  capture → save-draft → session appears; patient assignment; open patient detail → hardware/back returns.
  The `tests/e2e/_setup.ts` harness (`authPayload`, `installAppMocks`) already supports these.
- **Verify:** new tests green; establishes the gate. **Unlocks:** confidence for every move below.

### Increment 1 — `ApiProvider` (lift `apiFetch` into context)
- Move the memoized `apiFetch` (+ `refreshAccessToken`, `refreshPromiseRef`) into `ApiContext`. Additive:
  `App` consumes `useApi()` internally; props unchanged this step.
- **Why safe:** identical function, new provider only. **Verify:** `tsc -b` + full e2e (no behavior change).
- **Unlocks:** every feature API hook and the auth extraction.

### Increment 2 — `AuthProvider`
- Extract auth state + lifecycle (`commitAuth`/`clearAuth`/bootstrap, `loginWith*`, `register`, `logout`,
  `switchTenant`, `handleTierChanged`, onboarding-pending) into `AuthProvider`/`useAuth()`. Keep `authRef`,
  `refreshPromiseRef`, `bootstrappedAuthRef` **exactly** (load-bearing — see §6). `AppLangProvider` stays
  nested under it (reads `tenant.appLanguage`).
- **Verify:** `onboarding.spec`, `account-menu.spec`, `landing-auth.spec`, `i18n-foundation.spec`, `i18n-settings.spec` (live app-language switch).
- **Unlocks:** capabilities + all vertical branches read one auth source.

### Increment 3 — Capabilities seam
- Introduce `useCapabilities()` derived from `auth.tenant.tier` + `rolePermissions`. Replace scattered
  `tier === "basic"` / `isPro` checks and the `onFetchX = isPro ? cb : undefined` prop-gating with
  capability checks **at the point of use**. No visual change.
- **Why safe:** pure refactor of existing booleans. **Verify:** `smart-lists.spec` (Lists tab Pro-gating),
  `account-menu.spec` (role gating), `i18n-tail.spec` (Pro Q&A).
- **Unlocks:** **Basic/Pro convergence** (epic 3) — the fork now has one home.

### Increment 4 — `SyncProvider` (outbox engine)  ⚠ riskiest single extraction
- Extract the offline-first engine into `SyncProvider`/`useSync()`: `pendingCaptures`/`pendingOperations`,
  `online`/`backendReachable`, `processOutbox`, `processPendingOperations`, `syncPendingOperation`,
  `hydrateFromStorage`, `queueOperation`, retry `setInterval`, `beforeunload`, storage status +
  `StorageGuardDialog`, `exportQueuedCaptures`. Exposes `syncHealth`, `saveDraft`, `queueOperation`,
  `exportQueuedCaptures`, `clearLocal`.
- **Preserve exactly:** `processingRef`, `activeSessionRef`, `sessionsRef`, `workspaceHydratedRef`, the
  `flushSync` in `saveDraft` (§6). Because Sync and Store are being separated, `saveDraft`/`processOutbox`
  need read access to latest session state — keep the ref pattern (or move to the external store in seam C).
- **Verify:** the Increment-0 capture-save + offline specs, plus `tsc -b`. Add unit tests for
  queue→process→status transitions and offline→online resume against a fake storage adapter.
- **Unlocks:** the session store can depend on a clean sync seam.

### Increment 5 — `SessionStore`
- Extract `sessions[]`, `activeSession`, `selectedSessionId` and all session/capture actions into
  `SessionStoreProvider` exposing `useSessions()` / `useActiveSession()` / `useSessionActions()`, sitting on
  Api + Sync. Model the reducer explicitly (`upsertSession`, `applySessionUpdate`, `updateItemStatus`,
  patient-assignment, `selfHealStalePatient`). Apply the split-context decision from §2 here.
- **Verify:** capture + memory e2e (`i18n-capture`, `i18n-memory`, `visual/clinical-memory-today`); new unit
  tests for reducer transitions and self-heal. Watch the `persistWorkspaceState` coupling (§6).
- **Unlocks:** the prop collapse (next) and every session-mutation epic (treatment overlay, close-the-day).

### Increment 6 — Feature API hooks + collapse the prop lists  ← headline symptom dies here
- Add `useMemoryApi()` / `useCaptureApi()` (thin `apiFetch`-binders, capability-aware). Rewire
  `PatientsHome` and `CaptureScreen` to consume `useMemoryApi()` + `useSessions()`/`useSessionActions()` +
  `useCapabilities()` internally. `renderCurrentScreen()` shrinks to route-dispatch. Prop lists go 45 → ~3
  and 40 → ~4 (§3).
- **Why safe:** internal wiring swap; rendered output identical. **Verify:** `i18n-memory`, `smart-lists`,
  `i18n-capture`, `visual/clinical-memory-today` — all should be untouched.
- **Unlocks:** additive-by-stacking is no longer the cheap path — new work attaches to a hook/store seam.

### Increment 7 — Router / history seam
- Replace the hash-`screen` + return-context scheme with a typed **nested** route model backed by real
  `history.pushState`/`popstate`: top-level screens *and* in-screen levels (`patients/:patientId`,
  `lists/:key`, `session/:id` historical). Collapse `clinicalMemoryReturnContext`, `captureReturnSession`,
  `accountReturnRef` into route history. Keep `screenFromLocation`/`replaceScreenLocation` semantics for the
  top level so deep links still work.
- **Land ux-quick-wins #5 as the first consumer:** history entries for patient detail (`selectedPatientId`),
  smart-list drill-ins (`SmartListsTab` `view`), and historical review — so hardware back steps *in*, not
  out. This is both a real fix and proof the seam works.
- **Verify:** `smart-lists.spec` (back to rail), `i18n-memory.spec` (Memory → patient timeline); add nav
  specs asserting back steps through levels. **Update** `docs/ux/navigation.md`.
- **Unlocks:** **unified finder** and **close-the-day** can add routes, not return-context props.

### Increment 8 — Screen decomposition (region components)
- With data available from context/hooks, split the two heavy screens into **self-fetching regions**:
  - `CaptureScreen` → `SessionContextBrief`, `LiveReportRegion`, `ReviewRegion` (fold the stacked
    verify/resolver/safety panels into one), `TreatmentPanel`. Each owns its slice; the screen composes.
  - `PatientsHome` → each tab (`TodayPanel`, `PatientsPanel`, `ListsPanel`, `NeedsInputPanel`) becomes a
    self-fetching panel; sheets move behind a route/drawer level from seam D.
- **Verify:** `visual/clinical-memory-today`, `i18n-capture`, `i18n-tail`. **Update** `docs/ux/screens/capture.md`
  + `screens/patients.md` if any visible behavior shifts (it shouldn't — this is structural).
- **Unlocks:** **layout diet** and **treatment overlay** attach to a region, not a monolith.

---

## 5. The five structural UX epics → the seam each needs

The whole point: after §4, each deferred epic lands by attaching to an existing seam instead of adding
App state + a callback + a panel. Where an epic really needs a **backend contract**, that is flagged (per
CLAUDE.md §5 — don't emulate it with client-side orchestration; shape the seam to consume it and hand the
API change off).

| Epic | Attaches to | New surface work | Backend hand-off to flag |
|---|---|---|---|
| **Unified attention / "Close the day"** | seam C (`SessionStore`) + seam D (route) + a cross-feature `useAttention()` read-model over sessions + worklist + needs-input + Q&A | one attention route/surface; the Today/Needs-input tabs become views over the read-model | a single "today's actionable work" endpoint so the client doesn't merge 3–4 calls |
| **User-authored treatment overlay** | seam C session-actions (`addTreatment`/`editTreatment`) + `TreatmentPanel` region (seam E) | inline/drawer treatment editor; attribution (authored vs extracted) | treatment write + lot/product validation endpoint; report re-synthesis trigger |
| **Basic/Pro surface convergence** | seam A3 (`useCapabilities()`) + region **slots** (seam E) | one capture + one memory surface with capability-gated slots, replacing forked components/props | payloads should always carry both deterministic + AI fields; Basic ignores AI fields (no shape fork) |
| **Unified finder** | per-feature API hooks (seam A1/E) + seam D (route) | one finder route with a result-type→renderer registry; absorbs `SearchHome` (73 LOC) + patient/lot search | a global `/search` endpoint returning type-tagged results; local-only offline fallback |
| **Session-screen layout diet** | seam E region decomposition + seam D (drawer/review as a route level) | collapsible brief; unified review drawer; report as primary content | none required (structural) — but consumes the treatment/attention seams above |

Two epics converge on the same underlying need: a **cross-feature read-model** (attention, finder) that
reads from several stores/hooks. That is a first-class use of the context seams — it is *not* a reason to
keep logic in `App`.

---

## 6. Load-bearing details to preserve exactly

These exist for a reason; a "clean-up" that drops them will regress subtly:

- **Async-correctness refs.** `processOutbox` is a long async loop that must read the *latest* auth/session
  state without stale closures — hence `authRef`, `activeSessionRef`, `sessionsRef`, `processingRef`
  (overlap guard), `refreshPromiseRef` (single-flight 401 refresh), `bootstrappedAuthRef`,
  `aiPatientToastIdsRef` (dedupe). When these move into `SyncProvider`/`AuthProvider`, keep the ref pattern
  (or replace with `useSyncExternalStore` reads) — do **not** naively convert to state.
- **`flushSync` in `saveDraft`** (`App.tsx:909`): the optimistic capture + `navigateScreen("active-session")`
  are flushed synchronously so the new capture is visible before the async upload. Preserve.
- **Workspace persistence coupling** (`persistWorkspaceState`, gated by `workspaceHydratedRef`): couples
  `screen` + `activeSession` + `selectedSessionId` + `assignmentSessionId` + `pendingCaptureKind` across
  what will become *three* seams (router, store, sync). Give it one owner — a small effect that subscribes
  to the relevant slices — rather than duplicating writes.
- **Top-level vertical branches** (`UnauthShell` → `PatientPreviewGate` → `TherapyApp` → aesthetics): keep
  the branch in `<VerticalShell>`. `TherapyApp` is a self-contained app and must not be dragged through the
  aesthetics shell's store/router.
- **`mergeSessionUpdate` / `markReportStale*` semantics** (`app/sessionState.ts`): the report-staleness and
  patient-preservation rules are subtle (they keep a prior synthesized report visible while a new one
  organizes). Cover with Increment-0 unit tests before the store extraction moves callers around.

---

## 7. Non-goals & guardrails

- **Behavior-preserving.** No product/UX change except the two explicitly-scoped fixes carried as *proofs*
  of a seam: ux-quick-wins #5 (history entries, Increment 7) and the review-panel consolidation (Increment 8,
  only if it stays visually equivalent — otherwise it's an epic, not this refactor).
- **No new runtime dependency.** Context + hooks + `useReducer` (+ `useSyncExternalStore` if needed).
- **i18n chrome rule holds** (CLAUDE.md §5): every increment keeps `i18n:guard` green; chrome via `t()`,
  clinical content via `reportLanguage`. Moving code must not hardcode a string.
- **One increment = one PR**, each green on the full gate and revertible on its own. Do not batch
  Increments 4–5 (the risky pair) into one change.
- **Docs close the loop** (CLAUDE.md §3): Increment 7 updates `docs/ux/navigation.md`; Increment 8 updates
  `screens/capture.md`/`patients.md` if visible behavior shifts; when the refactor completes, fold §2 into
  `docs/architecture.md` + `docs/frontend/overview.md`, delete this doc, rewire links, run
  `python3 scripts/check-doc-links.py`.

---

## 8. Summary

The prop explosion and the stacked-panel reflex are one problem: `App.tsx` owns everything, so *additive is
the only cheap move*. Cut four provider seams (Api, Auth, Capabilities, Sync), one store seam (Sessions),
one router seam (nested history), and one screen-decomposition seam (regions). Sequence them so each rides
the existing e2e + `tsc` + i18n net (front-loading the unit tests that extraction newly makes possible).
The result: `App.tsx` becomes a composition root, `PatientsHome` goes 45 props → ~3, and each of the five
deferred UX epics has a named seam to attach to instead of another panel to stack.
