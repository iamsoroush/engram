import type { CaptureSession } from "../domain/types";
import { createClientId, nowLabel } from "../features/capture/captureModel";

export const PROCESSING_REFRESH_DELAYS = [1200, 3000, 5200, 7600, 11000, 16000];

export function mergeSessionUpdate(existing: CaptureSession, updated: CaptureSession, items = existing.items) {
  const patientChanged = Boolean(updated.patientId && existing.patientId && updated.patientId !== existing.patientId);
  const preservedPatient =
    !patientChanged && (existing.patientId || existing.patientName || existing.assignmentSource) && (!updated.patientId || !updated.patientName)
      ? {
          patientId: existing.patientId,
          patientName: existing.patientName,
          assignmentSource: existing.assignmentSource,
        }
      : !patientChanged && existing.assignmentSource === "staff" && updated.patientId === existing.patientId
        ? { assignmentSource: "staff" }
        : {};
  const isReplacingGeneratedReport = existing.processingStatus?.state === "processing" || existing.report?.status === "generating";
  const preservedReport =
    !isReplacingGeneratedReport && existing.report?.isStale && updated.report?.status === "processed" && !updated.report.isStale
      ? { report: existing.report }
      : {};
  return { ...existing, ...updated, ...preservedPatient, ...preservedReport, items };
}

export function markReportStaleForPatientChange(existing: CaptureSession, updated: CaptureSession) {
  const patientChanged = existing.patientId !== updated.patientId || existing.patientName !== updated.patientName;
  if (!patientChanged || !existing.report || existing.report.isStale) return updated;
  if (existing.report.status !== "processed" && existing.report.status !== "verified" && existing.status !== "verified") return updated;
  return {
    ...updated,
    status: updated.status === "verified" ? "reopened" : updated.status,
    report: {
      ...existing.report,
      status: "partial",
      isStale: true,
    },
  };
}

export function markReportStaleForCaptureChange(session: CaptureSession): CaptureSession {
  if (!session.report || session.report.isStale) return session;
  if (session.report.status !== "processed" && session.report.status !== "verified" && session.status !== "verified") return session;
  return {
    ...session,
    status: session.status === "verified" ? "reopened" : session.status,
    report: {
      ...session.report,
      status: "partial",
      isStale: true,
    },
  };
}

export function makeEmptyLocalSession(): CaptureSession {
  const time = nowLabel();
  const now = new Date().toISOString();
  return {
    id: `local-session-${createClientId()}`,
    label: `Session ${time}`,
    time,
    dateLabel: "Today",
    createdAt: now,
    updatedAt: now,
    capturedAt: now,
    duration: "not started",
    summary: "Ready for the first capture.",
    status: "draft",
    reviewReason: "No captures yet",
    items: [],
  };
}

export function resolveRestoredSession(storedSession: CaptureSession | null, sessions: CaptureSession[]) {
  if (!storedSession) return null;
  const current = sessions.find((session) => session.id === storedSession.id);
  if (!current) return storedSession;
  return {
    ...storedSession,
    ...current,
    items: current.items.length ? current.items : storedSession.items,
  };
}
