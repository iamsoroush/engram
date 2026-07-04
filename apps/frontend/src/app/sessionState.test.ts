import { describe, expect, it } from "vitest";
import type { CaptureItem, CaptureSession, SessionReport } from "../domain/types";
import {
  makeEmptyLocalSession,
  markReportStaleForCaptureChange,
  markReportStaleForPatientChange,
  mergeSessionUpdate,
  resolveRestoredSession,
} from "./sessionState";

// Characterization tests for the load-bearing session-state rules the store extraction (Increment 5)
// moves callers around (frontend-refactor plan §6). These are the subtle report-staleness and
// patient-preservation behaviors that keep a prior synthesized report visible while a new one
// organizes — pin them BEFORE the refactor so a regression is caught by a fast unit test, not by
// spotting a downgraded report in the UI.

function baseSession(overrides: Partial<CaptureSession> = {}): CaptureSession {
  return {
    id: "session-1",
    label: "Session",
    time: "10:00",
    dateLabel: "Today",
    duration: "5m",
    summary: "",
    status: "processing",
    items: [],
    ...overrides,
  };
}

function processedReport(overrides: Partial<SessionReport> = {}): SessionReport {
  return {
    status: "processed",
    format: "markdown",
    title: "Report",
    body: "Body",
    isStale: false,
    ...overrides,
  };
}

function item(id: string, overrides: Partial<CaptureItem> = {}): CaptureItem {
  return { id, type: "note", title: "", detail: "", time: "10:00", sourceName: "", ...overrides };
}

describe("mergeSessionUpdate", () => {
  it("preserves the existing patient when the update drops patient identity", () => {
    const existing = baseSession({ patientId: "p1", patientName: "Sara", assignmentSource: "staff" });
    const updated = baseSession({ patientId: undefined, patientName: undefined });
    const merged = mergeSessionUpdate(existing, updated);
    expect(merged.patientId).toBe("p1");
    expect(merged.patientName).toBe("Sara");
    expect(merged.assignmentSource).toBe("staff");
  });

  it("adopts the updated patient when the patient genuinely changed", () => {
    const existing = baseSession({ patientId: "p1", patientName: "Sara", assignmentSource: "staff" });
    const updated = baseSession({ patientId: "p2", patientName: "Nima", assignmentSource: "ai_engine" });
    const merged = mergeSessionUpdate(existing, updated);
    expect(merged.patientId).toBe("p2");
    expect(merged.patientName).toBe("Nima");
  });

  it("keeps a staff assignment source when the update re-confirms the same patient", () => {
    const existing = baseSession({ patientId: "p1", patientName: "Sara", assignmentSource: "staff" });
    const updated = baseSession({ patientId: "p1", patientName: "Sara", assignmentSource: "ai_engine" });
    const merged = mergeSessionUpdate(existing, updated);
    expect(merged.assignmentSource).toBe("staff");
  });

  it("holds the prior report while a stale->processed update lands without a regenerating job", () => {
    const existing = baseSession({ status: "organized", report: processedReport({ isStale: true, body: "OLD" }) });
    const updated = baseSession({ status: "organized", report: processedReport({ isStale: false, body: "NEW" }) });
    const merged = mergeSessionUpdate(existing, updated);
    // The stale existing report is held (not replaced) so the polished report never blanks.
    expect(merged.report?.body).toBe("OLD");
  });

  it("does NOT hold the prior report when the existing session is actively regenerating", () => {
    const existing = baseSession({
      report: processedReport({ isStale: true, body: "OLD", status: "generating" }),
      processingStatus: { state: "processing" } as CaptureSession["processingStatus"],
    });
    const updated = baseSession({ report: processedReport({ isStale: false, body: "NEW" }) });
    const merged = mergeSessionUpdate(existing, updated);
    expect(merged.report?.body).toBe("NEW");
  });

  it("defaults items to the existing items when none are provided", () => {
    const existing = baseSession({ items: [item("a")] });
    const updated = baseSession({ items: [item("b")] });
    expect(mergeSessionUpdate(existing, updated).items).toEqual([item("a")]);
  });

  it("uses explicitly-passed items over both existing and updated", () => {
    const existing = baseSession({ items: [item("a")] });
    const updated = baseSession({ items: [item("b")] });
    expect(mergeSessionUpdate(existing, updated, [item("c")]).items).toEqual([item("c")]);
  });
});

describe("markReportStaleForPatientChange", () => {
  it("marks a processed report stale when the patient changes", () => {
    const existing = baseSession({ status: "organized", patientId: "p1", report: processedReport() });
    const updated = baseSession({ status: "organized", patientId: "p2", report: processedReport() });
    const result = markReportStaleForPatientChange(existing, updated);
    expect(result.report?.status).toBe("partial");
    expect(result.report?.isStale).toBe(true);
  });

  it("reopens a verified session on patient change", () => {
    const existing = baseSession({ status: "verified", patientId: "p1", report: processedReport({ status: "verified" }) });
    const updated = baseSession({ status: "verified", patientId: "p2", report: processedReport({ status: "verified" }) });
    expect(markReportStaleForPatientChange(existing, updated).status).toBe("reopened");
  });

  it("returns the update untouched when the patient did not change", () => {
    const existing = baseSession({ patientId: "p1", report: processedReport() });
    const updated = baseSession({ patientId: "p1", report: processedReport(), summary: "x" });
    expect(markReportStaleForPatientChange(existing, updated)).toBe(updated);
  });

  it("does nothing when there is no processed/verified report to stale", () => {
    const existing = baseSession({ status: "draft", patientId: "p1", report: processedReport({ status: "partial" }) });
    const updated = baseSession({ status: "draft", patientId: "p2", report: processedReport({ status: "partial" }) });
    expect(markReportStaleForPatientChange(existing, updated)).toBe(updated);
  });

  it("does not re-stale an already-stale report", () => {
    const existing = baseSession({ patientId: "p1", report: processedReport({ isStale: true }) });
    const updated = baseSession({ patientId: "p2", report: processedReport({ isStale: true }) });
    expect(markReportStaleForPatientChange(existing, updated)).toBe(updated);
  });
});

describe("markReportStaleForCaptureChange", () => {
  it("marks a processed report partial+stale after a capture edit", () => {
    const session = baseSession({ status: "organized", report: processedReport() });
    const result = markReportStaleForCaptureChange(session);
    expect(result.report?.status).toBe("partial");
    expect(result.report?.isStale).toBe(true);
  });

  it("reopens a verified session", () => {
    const session = baseSession({ status: "verified", report: processedReport({ status: "verified" }) });
    expect(markReportStaleForCaptureChange(session).status).toBe("reopened");
  });

  it("returns the session unchanged when there is no report", () => {
    const session = baseSession({ report: undefined });
    expect(markReportStaleForCaptureChange(session)).toBe(session);
  });

  it("does not re-stale an already-stale report", () => {
    const session = baseSession({ report: processedReport({ isStale: true }) });
    expect(markReportStaleForCaptureChange(session)).toBe(session);
  });
});

describe("resolveRestoredSession", () => {
  it("returns null when there is no stored session", () => {
    expect(resolveRestoredSession(null, [])).toBeNull();
  });

  it("returns the stored session verbatim when it is not among the live sessions", () => {
    const stored = baseSession({ id: "gone" });
    expect(resolveRestoredSession(stored, [baseSession({ id: "other" })])).toBe(stored);
  });

  it("merges live session fields over the stored one, preferring live items when present", () => {
    const stored = baseSession({ id: "s", summary: "old", items: [item("stored")] });
    const live = baseSession({ id: "s", summary: "new", items: [item("live")] });
    const merged = resolveRestoredSession(stored, [live]);
    expect(merged?.summary).toBe("new");
    expect(merged?.items).toEqual([item("live")]);
  });

  it("keeps the stored items when the live session has none (avoids blanking a restored preview)", () => {
    const stored = baseSession({ id: "s", items: [item("stored")] });
    const live = baseSession({ id: "s", items: [] });
    expect(resolveRestoredSession(stored, [live])?.items).toEqual([item("stored")]);
  });
});

describe("makeEmptyLocalSession", () => {
  it("produces a fresh draft local session with no items", () => {
    const session = makeEmptyLocalSession();
    expect(session.id.startsWith("local-session-")).toBe(true);
    expect(session.status).toBe("draft");
    expect(session.items).toEqual([]);
  });
});
