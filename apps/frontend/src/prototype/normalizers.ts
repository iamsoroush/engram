import type { CaptureItem, CaptureSession, Patient } from "./types";
import { titleByType, nowLabel } from "./captureModel";

export const sessionStatusFromApi = (status?: string): CaptureSession["status"] => {
  if (
    status === "unassigned" ||
    status === "draft" ||
    status === "needs_review" ||
    status === "processing" ||
    status === "organized" ||
    status === "reviewing" ||
    status === "verified" ||
    status === "reopened" ||
    status === "failed"
  ) {
    return status;
  }
  return "needs_review";
};

export const captureStatusFromApi = (status?: string): CaptureItem["status"] => {
  if (status === "received") return "uploaded";
  if (status === "processed") return "processed";
  if (status === "processing") return "processing";
  if (status === "needs_attention") return "needsReview";
  if (status === "deleted") return "missing";
  return "ready";
};

export function formatApiTime(value?: string | null) {
  if (!value) return nowLabel();
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

/**
 * Maps backend capture payloads into the frontend card model while preserving
 * raw metadata needed for generated transcript/caption display.
 */
export function normalizeApiCaptureItem(raw: Partial<CaptureItem> & Record<string, unknown>): CaptureItem {
  const metadata = raw.metadata && typeof raw.metadata === "object" ? (raw.metadata as Record<string, unknown>) : {};
  const sourceName = typeof metadata.original_filename === "string" ? metadata.original_filename : raw.sourceName;
  const contentType = typeof metadata.content_type === "string" ? metadata.content_type : raw.contentType;
  const assignmentSource =
    typeof raw.assignmentSource === "string"
      ? raw.assignmentSource
      : typeof metadata.patient_assignment_source === "string"
        ? metadata.patient_assignment_source
        : null;
  return {
    id: String(raw.id),
    type: raw.type === "audio" || raw.type === "photo" || raw.type === "note" || raw.type === "voice" ? raw.type : "note",
    title: raw.title || titleByType[raw.type === "audio" || raw.type === "photo" ? raw.type : "note"],
    detail: raw.detail || (typeof metadata.detail === "string" ? metadata.detail : "Captured source saved to the backend."),
    time: raw.time || formatApiTime(typeof raw.capturedAt === "string" ? raw.capturedAt : null),
    sourceName: sourceName || "capture",
    status: raw.status ? captureStatusFromApi(String(raw.status)) : "uploaded",
    contentType: contentType || raw.mimeType,
    sourceUrl: typeof raw.sourceUrl === "string" ? raw.sourceUrl : undefined,
    fileEndpoint: typeof raw.fileEndpoint === "string" ? raw.fileEndpoint : undefined,
    patientId: typeof raw.patientId === "string" ? raw.patientId : null,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource,
    metadata,
  };
}

/**
 * Converts API sessions into the prototype session shape and supplies defensive
 * fallback copy for partially populated processing responses.
 */
export function normalizeApiSession(raw: Partial<CaptureSession> & Record<string, unknown>): CaptureSession {
  const status = sessionStatusFromApi(typeof raw.status === "string" ? raw.status : undefined);
  const capturedAt = typeof raw.capturedAt === "string" ? raw.capturedAt : typeof raw.createdAt === "string" ? raw.createdAt : null;
  const time = raw.time || formatApiTime(capturedAt);
  const items = Array.isArray(raw.items) ? raw.items.map((item) => normalizeApiCaptureItem(item as Record<string, unknown>)) : [];
  return {
    id: String(raw.id),
    label: raw.label || (typeof raw.title === "string" && raw.title ? raw.title : `${time} - Capture session`),
    time,
    dateLabel: raw.dateLabel || "Today",
    duration: raw.duration || "saved",
    summary:
      raw.summary ||
      (typeof raw.generatedSummary === "string" && raw.generatedSummary ? raw.generatedSummary : "Captured material saved to the backend."),
    status,
    items,
    patientId: typeof raw.patientId === "string" ? raw.patientId : raw.patientId ?? undefined,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource:
      typeof raw.assignmentSource === "string"
        ? raw.assignmentSource
        : typeof raw.organizationSource === "string" && raw.organizationSource === "ai-engine" && raw.patientId
          ? "ai-engine"
          : undefined,
    organizationSource: typeof raw.organizationSource === "string" ? raw.organizationSource : null,
    generatedReport: typeof raw.generatedReport === "string" ? raw.generatedReport : null,
    extractedMetadata:
      raw.extractedMetadata && typeof raw.extractedMetadata === "object" ? (raw.extractedMetadata as Record<string, unknown>) : {},
    reportTemplateKey: typeof raw.reportTemplateKey === "string" ? raw.reportTemplateKey : null,
    reviewReason:
      raw.reviewReason ||
      (status === "draft"
        ? "Draft, not saved"
        : status === "unassigned"
        ? "Needs patient assignment"
        : status === "needs_review"
        ? "Ready for verification"
        : status === "verified"
          ? "Human reviewed"
          : status === "failed"
            ? "Processing failed"
        : "Ready for review"),
  };
}

export function normalizePatient(raw: Record<string, unknown>): Patient {
  return {
    id: String(raw.id),
    displayName: String(raw.displayName || "Unnamed patient"),
    nationalId: typeof raw.nationalId === "string" ? raw.nationalId : null,
    dateOfBirth: typeof raw.dateOfBirth === "string" ? raw.dateOfBirth : null,
    phone: typeof raw.phone === "string" ? raw.phone : null,
    email: typeof raw.email === "string" ? raw.email : null,
  };
}

export function normalizeUploadResult(raw: { session: Record<string, unknown>; item: Record<string, unknown> }) {
  const item = normalizeApiCaptureItem(raw.item);
  const session = normalizeApiSession(raw.session);
  return { session: { ...session, items: [...session.items.filter((current) => current.id !== item.id), item] }, item };
}
