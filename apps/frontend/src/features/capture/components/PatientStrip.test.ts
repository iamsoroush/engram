import { describe, expect, it } from "vitest";
import { stripInitialExpanded, stripTransition, type StripSignals } from "./PatientStrip";

// The session-layout-diet auto-collapse state machine (AES-1302): pre-capture expanded → report-has-
// content collapsed → unassigned keeps Assign → undo-all re-expands → (re)assignment of a patient with
// history re-surfaces it, and collapse waits for report-has-content AND history-surfaced.

const base: StripSignals = { assignmentSignal: "p1:staff", reportHasContent: false, hasCaptures: false };

describe("stripInitialExpanded", () => {
  it("is expanded pre-capture (a glance aid before capturing)", () => {
    expect(stripInitialExpanded(false, false)).toBe(true);
  });
  it("is collapsed once there are captures", () => {
    expect(stripInitialExpanded(false, true)).toBe(false);
  });
  it("is collapsed for historical review (no pending actions)", () => {
    expect(stripInitialExpanded(true, false)).toBe(false);
  });
});

describe("stripTransition", () => {
  it("re-expands when every capture is undone (returns to the pre-capture glance)", () => {
    const prev = { ...base, hasCaptures: true };
    const next = { ...base, hasCaptures: false };
    expect(stripTransition(prev, next, { hasHistory: false, surfaced: true }).expanded).toBe(true);
  });

  it("collapses when the report gains content and history is already surfaced", () => {
    const prev = { ...base, hasCaptures: true, reportHasContent: false };
    const next = { ...base, hasCaptures: true, reportHasContent: true };
    expect(stripTransition(prev, next, { hasHistory: true, surfaced: true }).expanded).toBe(false);
  });

  it("collapses when the report gains content and there is no history to surface", () => {
    const prev = { ...base, hasCaptures: true, reportHasContent: false };
    const next = { ...base, hasCaptures: true, reportHasContent: true };
    expect(stripTransition(prev, next, { hasHistory: false, surfaced: false }).expanded).toBe(false);
  });

  it("does NOT collapse on report content while an un-surfaced history is still pending", () => {
    const prev = { ...base, hasCaptures: true, reportHasContent: false };
    const next = { ...base, hasCaptures: true, reportHasContent: true };
    expect(stripTransition(prev, next, { hasHistory: true, surfaced: false }).expanded).toBeNull();
  });

  it("re-surfaces history on a (re)assignment, winning over a simultaneous collapse", () => {
    const prev = { assignmentSignal: "p1:staff", hasCaptures: true, reportHasContent: false };
    const next = { assignmentSignal: "p2:ai_match", hasCaptures: true, reportHasContent: true };
    const result = stripTransition(prev, next, { hasHistory: true, surfaced: true });
    expect(result.expanded).toBe(true); // assignment wins → expand (surface p2's history)
    expect(result.surfaced).toBe(true);
  });

  it("leaves a manual toggle intact when nothing transitions", () => {
    expect(stripTransition(base, base, { hasHistory: true, surfaced: false }).expanded).toBeNull();
  });
});
