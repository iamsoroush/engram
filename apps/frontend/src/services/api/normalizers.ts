import type {
  CaptureItem,
  CaptureSession,
  SessionFinding,
  SessionProcessingStatus,
  SessionReport,
  SessionSummaries,
  StructuredPatientInformation,
  StructuredReportBlock,
  StructuredReportModel,
} from "../../domain/types";
import { titleByType, nowLabel } from "../../features/capture/captureModel";

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

function formatApiDateLabel(value?: string | null) {
  if (!value) return "Today";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Today";
  const now = new Date();
  if (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  ) {
    return "Today";
  }
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

function stringValue(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function normalizeApiReport(raw: Record<string, unknown>, fallbackTitle: string, fallbackBody: string): SessionReport {
  const report = raw.report && typeof raw.report === "object" ? (raw.report as Record<string, unknown>) : {};
  const structuredModel = normalizeStructuredReportModel(report.structuredModel || raw.reportModel);
  const patientInformation = normalizeStructuredPatientInformation(report.patientInformation);
  const template = normalizeReportTemplate(report.template);
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
    structuredModel,
    patientInformation,
    patientInformationSource: typeof report.patientInformationSource === "string" ? report.patientInformationSource : null,
    template,
    source: typeof report.source === "string" ? report.source : null,
    generatedAt: typeof report.generatedAt === "string" ? report.generatedAt : null,
    updatedAt: typeof report.updatedAt === "string" ? report.updatedAt : null,
    isStale: Boolean(report.isStale),
  };
}

function normalizeReportTemplate(value: unknown): SessionReport["template"] {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const clinic = raw.clinic && typeof raw.clinic === "object" ? (raw.clinic as Record<string, unknown>) : {};
  return {
    key: typeof raw.key === "string" ? raw.key : undefined,
    clinic: {
      name: typeof clinic.name === "string" ? clinic.name : undefined,
      information: Array.isArray(clinic.information)
        ? clinic.information.filter((item): item is string => typeof item === "string")
        : [],
    },
  };
}

function normalizeStructuredReportModel(value: unknown): StructuredReportModel | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const sections = Array.isArray(raw.sections)
    ? raw.sections
        .filter((section): section is Record<string, unknown> => Boolean(section && typeof section === "object"))
        .map((section, index) => ({
          id: stringValue(section.id, `section-${index + 1}`),
          title: stringValue(section.title, "Clinical report"),
          blocks: Array.isArray(section.blocks)
            ? section.blocks
                .filter((block): block is Record<string, unknown> => Boolean(block && typeof block === "object"))
                .map(normalizeStructuredReportBlock)
            : [],
        }))
    : [];
  return {
    schemaVersion: typeof raw.schemaVersion === "string" ? raw.schemaVersion : undefined,
    templateKey: typeof raw.templateKey === "string" ? raw.templateKey : undefined,
    title: typeof raw.title === "string" ? raw.title : undefined,
    sections,
    findings: Array.isArray(raw.findings) ? raw.findings.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")) : [],
    sourceReferences: Array.isArray(raw.sourceReferences)
      ? raw.sourceReferences.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      : [],
    generatedAt: typeof raw.generatedAt === "string" ? raw.generatedAt : null,
  };
}

function normalizeStructuredReportBlock(block: Record<string, unknown>): StructuredReportBlock {
  return {
    type: stringValue(block.type, "paragraph"),
    text: typeof block.text === "string" ? block.text : undefined,
    artifactId: typeof block.artifactId === "string" ? block.artifactId : undefined,
    captureId: typeof block.captureId === "string" ? block.captureId : undefined,
    caption: typeof block.caption === "string" ? block.caption : undefined,
  };
}

function normalizeStructuredPatientInformation(value: unknown): StructuredPatientInformation | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  return {
    source: typeof raw.source === "string" ? raw.source : undefined,
    status: typeof raw.status === "string" ? raw.status : undefined,
    patientId: typeof raw.patientId === "string" ? raw.patientId : null,
    displayName: typeof raw.displayName === "string" ? raw.displayName : null,
    legalFirstName: typeof raw.legalFirstName === "string" ? raw.legalFirstName : null,
    legalLastName: typeof raw.legalLastName === "string" ? raw.legalLastName : null,
    nationalId: typeof raw.nationalId === "string" ? raw.nationalId : null,
    dateOfBirth: typeof raw.dateOfBirth === "string" ? raw.dateOfBirth : null,
    sex: typeof raw.sex === "string" ? raw.sex : null,
    phone: typeof raw.phone === "string" ? raw.phone : null,
    email: typeof raw.email === "string" ? raw.email : null,
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
  const transcript = metadataTextFrom(metadata.transcript) || metadataTextFrom(metadata.ai_transcript);
  const caption = metadataTextFrom(metadata.caption || metadata.ocr) || metadataTextFrom(metadata.ai_caption);
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
    clientCaptureId: typeof raw.clientCaptureId === "string" ? raw.clientCaptureId : undefined,
    capturedAt: typeof raw.capturedAt === "string" ? raw.capturedAt : undefined,
    fileName: typeof raw.fileName === "string" ? raw.fileName : typeof sourceName === "string" ? sourceName : undefined,
    sourceName: sourceName || "capture",
    status: raw.status ? captureStatusFromApi(String(raw.status)) : "uploaded",
    duration: typeof metadata.duration === "string" ? metadata.duration : undefined,
    transcript: transcript || undefined,
    caption: caption || undefined,
    contentType: contentType || raw.mimeType,
    sourceUrl: typeof raw.sourceUrl === "string" ? raw.sourceUrl : undefined,
    fileEndpoint: typeof raw.fileEndpoint === "string" ? raw.fileEndpoint : undefined,
    patientId: typeof raw.patientId === "string" ? raw.patientId : null,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource,
    metadata,
  };
}

function metadataTextFrom(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.text === "string") return record.text.trim();
    if (typeof record.transcript === "string") return record.transcript.trim();
    if (typeof record.caption === "string") return record.caption.trim();
  }
  return "";
}

/**
 * Converts API sessions into the frontend session shape and supplies defensive
 * fallback copy for partially populated processing responses.
 */
export function normalizeApiSession(raw: Partial<CaptureSession> & Record<string, unknown>): CaptureSession {
  const status = sessionStatusFromApi(typeof raw.status === "string" ? raw.status : undefined);
  const createdAt = typeof raw.createdAt === "string" ? raw.createdAt : null;
  const updatedAt = typeof raw.updatedAt === "string" ? raw.updatedAt : null;
  const capturedAt = typeof raw.capturedAt === "string" ? raw.capturedAt : createdAt;
  const displayTimestamp = updatedAt || capturedAt || createdAt;
  const time = raw.time || formatApiTime(displayTimestamp);
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
    dateLabel: raw.dateLabel || formatApiDateLabel(displayTimestamp),
    createdAt,
    updatedAt,
    capturedAt,
    duration: raw.duration || "saved",
    summary: summaries.short || summary,
    status,
    items,
    patientId: typeof raw.patientId === "string" ? raw.patientId : raw.patientId ?? undefined,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource: typeof raw.assignmentSource === "string" ? raw.assignmentSource : undefined,
    organizationSource: typeof raw.organizationSource === "string" ? raw.organizationSource : null,
    generatedReport,
    reportModel: normalizeStructuredReportModel(raw.reportModel),
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
