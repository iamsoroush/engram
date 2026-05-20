import type { CaptureItem, CaptureSession, SessionFinding, SessionProcessingStatus, SessionReport, SessionSummaries } from "./types";
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

function stringValue(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function normalizeApiReport(raw: Record<string, unknown>, fallbackTitle: string, fallbackBody: string): SessionReport {
  const report = raw.report && typeof raw.report === "object" ? (raw.report as Record<string, unknown>) : {};
  return {
    schemaVersion: typeof report.schemaVersion === "string" ? report.schemaVersion : undefined,
    status: stringValue(report.status, fallbackBody ? "partial" : "empty"),
    format: stringValue(report.format, "markdown"),
    title: stringValue(report.title, fallbackTitle),
    body: stringValue(report.body, fallbackBody),
    sections: Array.isArray(report.sections)
      ? report.sections
          .filter((section): section is Record<string, unknown> => Boolean(section && typeof section === "object"))
          .map((section, index) => ({
            id: stringValue(section.id, `section-${index + 1}`),
            title: stringValue(section.title, "Clinical report"),
            body: stringValue(section.body, ""),
          }))
      : [{ id: "body", title: "Clinical report", body: fallbackBody }],
    source: typeof report.source === "string" ? report.source : null,
    generatedAt: typeof report.generatedAt === "string" ? report.generatedAt : null,
    updatedAt: typeof report.updatedAt === "string" ? report.updatedAt : null,
    isStale: Boolean(report.isStale),
  };
}

function normalizeApiSummaries(raw: Record<string, unknown>, fallbackSummary: string): SessionSummaries {
  const summaries = raw.summaries && typeof raw.summaries === "object" ? (raw.summaries as Record<string, unknown>) : {};
  const short = stringValue(summaries.short, fallbackSummary);
  return {
    schemaVersion: typeof summaries.schemaVersion === "string" ? summaries.schemaVersion : undefined,
    status: stringValue(summaries.status, short ? "partial" : "empty"),
    short,
    clinical: typeof summaries.clinical === "string" ? summaries.clinical : short,
    patientHistory: typeof summaries.patientHistory === "string" ? summaries.patientHistory : null,
    source: typeof summaries.source === "string" ? summaries.source : null,
    generatedAt: typeof summaries.generatedAt === "string" ? summaries.generatedAt : null,
    updatedAt: typeof summaries.updatedAt === "string" ? summaries.updatedAt : null,
  };
}

function normalizeApiFindings(raw: Record<string, unknown>): SessionFinding[] {
  if (!Array.isArray(raw.findings)) return [];
  return raw.findings
    .filter((finding): finding is Record<string, unknown> => Boolean(finding && typeof finding === "object"))
    .map((finding, index) => ({
      id: stringValue(finding.id, `finding-${index + 1}`),
      label: stringValue(finding.label, "Finding"),
      value: stringValue(finding.value, "Pending"),
      category: typeof finding.category === "string" ? finding.category : undefined,
      confidence: typeof finding.confidence === "number" ? finding.confidence : null,
      sourceCaptureIds: Array.isArray(finding.sourceCaptureIds)
        ? finding.sourceCaptureIds.filter((sourceId): sourceId is string => typeof sourceId === "string")
        : [],
      status: typeof finding.status === "string" ? finding.status : undefined,
    }));
}

function normalizeApiProcessingStatus(raw: Record<string, unknown>, status: CaptureSession["status"]): SessionProcessingStatus {
  const processingStatus =
    raw.processingStatus && typeof raw.processingStatus === "object" ? (raw.processingStatus as Record<string, unknown>) : {};
  const state = stringValue(
    processingStatus.state,
    status === "failed" ? "failed" : status === "processing" ? "processing" : "idle",
  );
  return {
    schemaVersion: typeof processingStatus.schemaVersion === "string" ? processingStatus.schemaVersion : undefined,
    state,
    label: stringValue(processingStatus.label, state === "idle" ? "Ready" : state),
    detail: typeof processingStatus.detail === "string" ? processingStatus.detail : null,
    stage: typeof processingStatus.stage === "string" ? processingStatus.stage : null,
    progress: typeof processingStatus.progress === "number" ? processingStatus.progress : null,
    canEdit: processingStatus.canEdit !== false,
    canReview: processingStatus.canReview !== false,
    source: typeof processingStatus.source === "string" ? processingStatus.source : null,
    updatedAt: typeof processingStatus.updatedAt === "string" ? processingStatus.updatedAt : null,
  };
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
  const label = raw.label || (typeof raw.title === "string" && raw.title ? raw.title : `${time} - Capture session`);
  const generatedReport = typeof raw.generatedReport === "string" ? raw.generatedReport : null;
  const summary =
    raw.summary ||
    (typeof raw.generatedSummary === "string" && raw.generatedSummary ? raw.generatedSummary : "Captured material saved to the backend.");
  const report = normalizeApiReport(raw, label, generatedReport || "");
  const summaries = normalizeApiSummaries(raw, summary);
  return {
    id: String(raw.id),
    label,
    time,
    dateLabel: raw.dateLabel || "Today",
    duration: raw.duration || "saved",
    summary: summaries.short || summary,
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
    generatedReport,
    report,
    summaries,
    findings: normalizeApiFindings(raw),
    processingStatus: normalizeApiProcessingStatus(raw, status),
    extractedMetadata:
      raw.extractedMetadata && typeof raw.extractedMetadata === "object" ? (raw.extractedMetadata as Record<string, unknown>) : {},
    reportTemplateKey: typeof raw.reportTemplateKey === "string" ? raw.reportTemplateKey : null,
    reviewReason:
      raw.reviewReason ||
      (status === "draft"
        ? "Capturing"
        : status === "unassigned"
        ? "Unassigned"
        : status === "needs_review"
        ? "Needs review"
        : status === "verified"
          ? "Verified"
          : status === "failed"
            ? "Failed"
        : "Review anytime"),
  };
}

export function normalizeUploadResult(raw: { session: Record<string, unknown>; item: Record<string, unknown> }) {
  const item = normalizeApiCaptureItem(raw.item);
  const session = normalizeApiSession(raw.session);
  return { session: { ...session, items: [...session.items.filter((current) => current.id !== item.id), item] }, item };
}
