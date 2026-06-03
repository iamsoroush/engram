export type Screen = "active-session" | "patients" | "search";

export type CaptureStatus = "saved" | "syncing" | "uploaded" | "processing" | "processed" | "needsReview" | "failed";

export type SessionStatus =
  | "draft"
  | "unassigned"
  | "needs_review"
  | "processing"
  | "organized"
  | "reviewing"
  | "verified"
  | "reopened"
  | "failed"
  | "current"
  | "matched";

export type CaptureItemType = "audio" | "voice" | "photo" | "note";

export type CaptureItem = {
  id: string;
  type: CaptureItemType;
  title: string;
  detail: string;
  time: string;
  sourceName: string;
  clientCaptureId?: string;
  status?: CaptureStatus | "ready" | "uploading" | "missing";
  capturedAt?: string;
  fileName?: string;
  duration?: string;
  transcript?: string;
  caption?: string;
  mimeType?: string;
  sourceUrl?: string;
  fileEndpoint?: string;
  storagePath?: string;
  url?: string;
  contentType?: string;
  patientId?: string | null;
  patientName?: string;
  assignmentSource?: "staff" | "ai_engine" | "ai-engine" | string | null;
  metadata?: Record<string, unknown>;
};

export type SessionReport = {
  schemaVersion?: string;
  status: "empty" | "partial" | "generating" | "processed" | "verified" | "failed" | string;
  format: "markdown" | "text" | string;
  title: string;
  body: string;
  sections?: Array<{ id: string; title: string; body: string }>;
  structuredModel?: StructuredReportModel | null;
  patientInformation?: StructuredPatientInformation | null;
  patientInformationSource?: string | null;
  template?: SessionReportTemplate | null;
  source?: string | null;
  generatedAt?: string | null;
  updatedAt?: string | null;
  isStale?: boolean;
};

export type SessionReportTemplate = {
  key?: string;
  clinic?: {
    name?: string;
    information?: string[];
  };
};

export type StructuredReportBlock = {
  type: "paragraph" | "image" | "artifact" | string;
  text?: string;
  artifactId?: string;
  captureId?: string;
  caption?: string;
};

export type StructuredReportSection = {
  id: string;
  title: string;
  blocks: StructuredReportBlock[];
};

export type StructuredReportModel = {
  schemaVersion?: string;
  templateKey?: string;
  title?: string;
  sections: StructuredReportSection[];
  findings?: Array<Record<string, unknown>>;
  sourceReferences?: Array<Record<string, unknown>>;
  generatedAt?: string | null;
};

export type StructuredPatientInformation = {
  source?: string;
  status?: string;
  patientId?: string | null;
  displayName?: string | null;
  legalFirstName?: string | null;
  legalLastName?: string | null;
  nationalId?: string | null;
  dateOfBirth?: string | null;
  sex?: string | null;
  phone?: string | null;
  email?: string | null;
};

export type SessionFinding = {
  id: string;
  label: string;
  value: string;
  category?: string;
  confidence?: number | null;
  sourceCaptureIds?: string[];
  status?: string;
};

export type SessionSummaries = {
  schemaVersion?: string;
  status: "empty" | "partial" | "processed" | "verified" | string;
  short: string;
  clinical?: string | null;
  patientHistory?: string | null;
  source?: string | null;
  generatedAt?: string | null;
  updatedAt?: string | null;
};

export type SessionProcessingStatus = {
  schemaVersion?: string;
  state: "idle" | "queued" | "processing" | "complete" | "failed" | string;
  label: string;
  detail?: string | null;
  stage?: string | null;
  progress?: number | null;
  canEdit: boolean;
  canReview: boolean;
  source?: string | null;
  updatedAt?: string | null;
};

export type CaptureSession = {
  id: string;
  label: string;
  time: string;
  dateLabel: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  capturedAt?: string | null;
  duration: string;
  summary: string;
  status: SessionStatus;
  items: CaptureItem[];
  patientName?: string;
  reviewReason?: string;
  patientId?: string;
  assignmentSource?: "staff" | "ai_engine" | "ai-engine" | string | null;
  organizationSource?: string | null;
  generatedReport?: string | null;
  reportModel?: StructuredReportModel | null;
  report?: SessionReport;
  findings?: SessionFinding[];
  summaries?: SessionSummaries;
  processingStatus?: SessionProcessingStatus;
  extractedMetadata?: Record<string, unknown>;
  reportTemplateKey?: string | null;
};
