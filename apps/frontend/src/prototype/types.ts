export type Screen = "capture" | "organize" | "session" | "today" | "saved" | "inbox" | "match" | "record";

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
  status?: CaptureStatus | "ready" | "uploading" | "missing";
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

export type CaptureSession = {
  id: string;
  label: string;
  time: string;
  dateLabel: string;
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
  extractedMetadata?: Record<string, unknown>;
  reportTemplateKey?: string | null;
};

export type Patient = {
  id: string;
  displayName: string;
  nationalId?: string | null;
  dateOfBirth?: string | null;
  phone?: string | null;
  email?: string | null;
};

export type PatientCandidate = {
  id: string;
  name: string;
  age: number;
  gender: string;
  lastVisit: string;
  hint: string;
  confidence: "High" | "Possible" | "Low";
  duplicateWarning?: boolean;
};
