import { describe, expect, it } from "vitest";
import type { PatientSummary } from "../domain/appTypes";
import type { CaptureItem, CaptureSession, SessionReport } from "../domain/types";
import {
  applyStaffAssignment,
  setItemStatusInSession,
  setItemStatusInSessions,
  stripPatientFromSession,
  stripStalePatientAcross,
  upsertSessionList,
} from "./sessionStoreReducers";

// Unit tests for the pure session-list transitions the SessionStore (seam C, increment 5) performs.
// They pin the subtle reducer semantics the extraction moved out of the App god-component: upsert id
// swaps, item-status propagation, and — the load-bearing one — the 404 self-heal that clears a stale
// patient and marks a synthesized report stale rather than freezing (see docs/frontend/overview.md).

function item(id: string, overrides: Partial<CaptureItem> = {}): CaptureItem {
  return { id, type: "note", title: "", detail: "", time: "10:00", sourceName: "", status: "uploaded", ...overrides };
}

function processedReport(overrides: Partial<SessionReport> = {}): SessionReport {
  return { status: "processed", format: "markdown", title: "Report", body: "Body", isStale: false, ...overrides };
}

function session(overrides: Partial<CaptureSession> = {}): CaptureSession {
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

describe("upsertSessionList", () => {
  it("prepends a new session", () => {
    const list = [session({ id: "a" }), session({ id: "b" })];
    const next = upsertSessionList(list, session({ id: "c" }));
    expect(next.map((s) => s.id)).toEqual(["c", "a", "b"]);
  });

  it("replaces an existing session by id and keeps it at the front (no duplicate)", () => {
    const list = [session({ id: "a", label: "old" }), session({ id: "b" })];
    const next = upsertSessionList(list, session({ id: "a", label: "new" }));
    expect(next.map((s) => s.id)).toEqual(["a", "b"]);
    expect(next[0].label).toBe("new");
  });

  it("drops removeIds — the offline local→backend id swap", () => {
    const list = [session({ id: "local-session-1" }), session({ id: "keep" })];
    const next = upsertSessionList(list, session({ id: "backend-1" }), ["local-session-1"]);
    expect(next.map((s) => s.id)).toEqual(["backend-1", "keep"]);
  });
});

describe("setItemStatus", () => {
  it("updates the matching item's status across every session, leaving others untouched", () => {
    const list = [
      session({ id: "a", items: [item("i1"), item("i2")] }),
      session({ id: "b", items: [item("i1")] }),
    ];
    const next = setItemStatusInSessions(list, "i1", "processing");
    expect(next[0].items[0].status).toBe("processing");
    expect(next[0].items[1].status).toBe("uploaded");
    expect(next[1].items[0].status).toBe("processing");
  });

  it("updates the active session and is null-safe", () => {
    const active = session({ items: [item("i1")] });
    expect(setItemStatusInSession(active, "i1", "uploaded")?.items[0].status).toBe("uploaded");
    expect(setItemStatusInSession(null, "i1", "uploaded")).toBeNull();
  });
});

describe("stripPatientFromSession (self-heal / unassign)", () => {
  it("clears patient identity", () => {
    const stripped = stripPatientFromSession(session({ patientId: "p1", patientName: "Sara", assignmentSource: "staff" }));
    expect(stripped.patientId).toBeUndefined();
    expect(stripped.patientName).toBeUndefined();
    expect(stripped.assignmentSource).toBeUndefined();
  });

  it("marks a processed report stale (keeps prior report visible as partial, never freezes/drops it)", () => {
    const stripped = stripPatientFromSession(
      session({ patientId: "p1", patientName: "Sara", assignmentSource: "staff", report: processedReport() }),
    );
    expect(stripped.report?.isStale).toBe(true);
    expect(stripped.report?.status).toBe("partial");
  });

  it("leaves a session with no report untouched apart from the patient clear", () => {
    const stripped = stripPatientFromSession(session({ patientId: "p1", patientName: "Sara" }));
    expect(stripped.report).toBeUndefined();
  });
});

describe("stripStalePatientAcross", () => {
  it("strips the target session by id", () => {
    const list = [session({ id: "a", patientId: "p1", patientName: "Sara" }), session({ id: "b", patientId: "p1", patientName: "Sara" })];
    const next = stripStalePatientAcross(list, "a");
    expect(next[0].patientId).toBeUndefined();
    expect(next[1].patientId).toBe("p1");
  });

  it("also strips every OTHER session still pointing at the dead patient id", () => {
    const list = [
      session({ id: "a", patientId: "dead", patientName: "Ghost" }),
      session({ id: "b", patientId: "dead", patientName: "Ghost" }),
      session({ id: "c", patientId: "alive", patientName: "Nima" }),
    ];
    const next = stripStalePatientAcross(list, "a", "dead");
    expect(next[0].patientId).toBeUndefined();
    expect(next[1].patientId).toBeUndefined();
    expect(next[2].patientId).toBe("alive");
  });
});

describe("applyStaffAssignment", () => {
  const patient: PatientSummary = { id: "p9", displayName: "Reza", nationalId: null };

  it("enriches the session with the patient and a staff source", () => {
    const assigned = applyStaffAssignment(session(), patient);
    expect(assigned.patientId).toBe("p9");
    expect(assigned.patientName).toBe("Reza");
    expect(assigned.assignmentSource).toBe("staff");
  });

  it("marks a previously-synthesized report stale when the patient changes", () => {
    const assigned = applyStaffAssignment(
      session({ patientId: "p1", patientName: "Sara", report: processedReport() }),
      patient,
    );
    expect(assigned.report?.isStale).toBe(true);
  });
});
