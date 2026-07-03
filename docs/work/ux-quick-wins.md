# UX quick wins — aesthetics polish batch (Tier A)

**Fold destination:** the touched `docs/ux/` screen/state docs (each item updates its doc per the
CLAUDE.md §3 checklist); then delete this doc.

Small, high-value fixes from the 2026-07-03 design review. Each is independent; all must follow the
bilingual chrome rule (CLAUDE.md §5). Larger structural bets (unified attention model / "Close the
day", user-authored treatment overlay, Basic/Pro surface convergence, unified finder, session-screen
layout diet) are deliberately NOT here — they are design epics to be specced separately.

1. **Verify-bar "checks pending" ghost state.** `SessionVerifyBar` renders nothing while synthesis
   is in flight, so a clean screen is indistinguishable from not-yet-checked. Add a quiet
   "Checks pending · organizing" state while the report is updating (`isUpdatingReport` in
   `CaptureScreen.tsx`), so absence-of-warnings only reads as "all good" once analysis ran.
   Update `docs/ux/states.md` + `screens/capture.md`.
2. **One word for session/visit across chrome.** Capture screen says "session"
   (`capture.newSession`), memory surfaces say "visit". Pick "visit" for aesthetics — the
   Encounter/presentation-label seam in `intelligence-layer.md` §2 already supports per-vertical
   labels. Chrome strings only (both languages).
3. **Today's needs-input preview → up to 3 cards** (currently exactly one:
   `today.needsInputPreview` in `PatientsHome.tsx`), with the pill as overflow.
4. **Recall roster batch action.** On the recall cohort (Lists tab), add "Prepare all links / copy
   roster" (name · phone · link) so link-minting isn't serial per patient. Sending stays human and
   per-patient. Update `screens/patients.md` (Lists tab section).
5. **History entries for in-screen navigation.** Patient detail (`selectedPatientId` state in
   `PatientsHome.tsx`), smart-list drill-ins (`view` state in `SmartListsTab.tsx`), and historical
   review have no history entries — hardware back exits the area. Push history states for these
   levels so back steps back. Update `docs/ux/navigation.md`.
6. **Account-menu grouping.** Group Insights/Team/Plan under a "Clinic" section in the avatar menu
   (`Shell.tsx`), identity actions separate. Update `screens/account.md` + `navigation.md`.
7. **Offline return receipt.** After reconnect, when queued captures finish syncing/organizing,
   show one transient confirmation ("N captures from earlier are now in …") instead of silent
   change. Update `states.md` (offline section).
8. **Auto-collapse the session context card** once the report has content (condition in
   `CaptureScreen.tsx` around the `SessionContextCard` render) — it's a pre-capture aid; keep it
   one line, expandable, after captures exist. Update `screens/capture.md`.

Verification: `npm run test:unit`, `npm run i18n:guard`, and the hermetic e2e suite; screenshot the
changed surfaces in fa + en (see `docs/dev/screenshots.md`).
