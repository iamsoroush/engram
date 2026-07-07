// Barrel for the Clinical Memory screens.
//
// This screen used to be a single ~3.8k-line god-file. It has been decomposed
// (pure mechanical move, no behavior change) into sibling files:
//   - memoryModel.ts             pure data/model helpers + types
//   - MemoryIcons.tsx            inline SVG icon components
//   - MemoryCards.tsx            shared presentational cards/pills
//   - MemorySheets.tsx           resolver/review sheets
//   - PatientTimeline.tsx        patient timeline detail + cards
//   - PatientsHome.tsx           Clinical Memory home (Today/Patients/Needs input)
//   - CaptureDestinationPanel.tsx
//
// The old SearchHome (top-nav `/#search` local-substring screen) was retired by the unified finder
// (features/finder) — its local-filter behavior survives only as the finder's offline fallback.
//
// These re-exports preserve the original public import surface so existing
// imports (e.g. App.tsx) keep working unchanged.
export { PatientsHome } from "./PatientsHome";
export { CaptureDestinationPanel } from "./CaptureDestinationPanel";
export type { ClinicalMemoryReturnContext } from "./memoryModel";
