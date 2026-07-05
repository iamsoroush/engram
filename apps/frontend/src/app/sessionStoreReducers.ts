import type { PatientSummary } from "../domain/appTypes";
import type { CaptureSession, CaptureStatus } from "../domain/types";
import { markReportStaleForPatientChange } from "./sessionState";

// Pure session-list transitions the SessionStore (seam C, increment 5) performs. Kept out of the React
// provider so they are unit-testable in the Node test harness (no DOM) — the store's setState updaters
// just call these. The subtle report-staleness + patient-preservation rules live in `sessionState.ts`
// (already covered by sessionState.test.ts); this module composes them at the list level.

/**
 * Prepend `session` to the list, replacing any existing entry with the same id and dropping any ids in
 * `removeIds` — used when an offline local session is replaced by its backend counterpart (id swap).
 */
export function upsertSessionList(
  sessions: CaptureSession[],
  session: CaptureSession,
  removeIds: string[] = [],
): CaptureSession[] {
  return [session, ...sessions.filter((current) => current.id !== session.id && !removeIds.includes(current.id))];
}

/** Set one capture item's status across every session (the list write; mirror of the active-session one). */
export function setItemStatusInSessions(
  sessions: CaptureSession[],
  itemId: string,
  status: CaptureStatus,
): CaptureSession[] {
  return sessions.map((session) => ({
    ...session,
    items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
  }));
}

/** Set one capture item's status in the active session (null-safe). */
export function setItemStatusInSession(
  session: CaptureSession | null,
  itemId: string,
  status: CaptureStatus,
): CaptureSession | null {
  if (!session) return session;
  return { ...session, items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)) };
}

/**
 * Clear a session's patient reference (server already SET NULL the FK) and mark its report stale. Used
 * both by explicit unassign and by the 404 self-heal (a patient deleted/merged out from under a panel).
 */
export function stripPatientFromSession(session: CaptureSession): CaptureSession {
  return markReportStaleForPatientChange(session, {
    ...session,
    patientId: undefined,
    patientName: undefined,
    assignmentSource: undefined,
  });
}

/**
 * Self-heal map: strip the stale patient from the session with `sessionId` AND from any session still
 * pointing at a now-dead `deadPatientId` (a merged/deleted patient can back several cached sessions).
 */
export function stripStalePatientAcross(
  sessions: CaptureSession[],
  sessionId: string | undefined,
  deadPatientId?: string,
): CaptureSession[] {
  return sessions.map((session) =>
    session.id === sessionId || (deadPatientId && session.patientId === deadPatientId) ? stripPatientFromSession(session) : session,
  );
}

/** Optimistic (offline/local) staff assignment: enrich the session with the patient + mark report stale. */
export function applyStaffAssignment(session: CaptureSession, patient: PatientSummary): CaptureSession {
  return markReportStaleForPatientChange(session, {
    ...session,
    patientId: patient.id,
    patientName: patient.displayName,
    assignmentSource: "staff",
  });
}
