import { describe, expect, it } from "vitest";
import { stripDefaultExpanded } from "./PatientStrip";

// The session-layout-diet auto-collapse decision (AES-1302), derived from current signals so it is
// correct however the screen arrives at a state: pre-capture expanded → in-progress collapsed →
// a patient with un-surfaced history stays expanded (the (re)assignment auto-surface) → collapse waits
// for report-has-content AND history-surfaced → historical collapsed.

const base = { isHistorical: false, hasCaptures: false, reportHasContent: false, hasHistory: false, surfaced: false };

describe("stripDefaultExpanded", () => {
  it("is expanded pre-capture (a glance aid before capturing)", () => {
    expect(stripDefaultExpanded(base)).toBe(true);
  });

  it("collapses once the report has content and there is no history to surface", () => {
    expect(stripDefaultExpanded({ ...base, reportHasContent: true })).toBe(false);
  });

  it("collapses once captures exist and there is no history", () => {
    expect(stripDefaultExpanded({ ...base, hasCaptures: true })).toBe(false);
  });

  it("stays expanded to surface an un-surfaced history even with content (the (re)assignment surface)", () => {
    expect(stripDefaultExpanded({ ...base, reportHasContent: true, hasHistory: true, surfaced: false })).toBe(true);
  });

  it("collapses once that history has been surfaced (report-has-content AND surfaced)", () => {
    expect(stripDefaultExpanded({ ...base, reportHasContent: true, hasHistory: true, surfaced: true })).toBe(false);
  });

  it("is collapsed for historical review regardless of content", () => {
    expect(stripDefaultExpanded({ ...base, isHistorical: true, reportHasContent: true })).toBe(false);
  });
});
