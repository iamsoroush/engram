import type { CaptureItem, CaptureItemType, CaptureSession } from "./types";

export type CaptureDraft = {
  kind: Extract<CaptureItemType, "audio" | "photo" | "note">;
  detail?: string;
  file: Blob;
  filename: string;
  metadata?: Record<string, unknown>;
};

export type PendingCapture = {
  id: string;
  localCaptureId: string;
  localSessionId: string;
  clientCaptureId: string;
  sessionId?: string;
  backendSessionId?: string;
  backendCaptureId?: string;
  tenantId?: string;
  intoNew: boolean;
  retryCount: number;
  createdAt: number;
  draft: CaptureDraft;
  item: CaptureItem;
  session: CaptureSession;
};

export type PendingOperationType = "sessionTitle" | "patientAssignment" | "sessionProcessing";

export type PendingOperationStatus = "pending" | "syncing" | "failed";

export type PendingOperation = {
  id: string;
  type: PendingOperationType;
  localSessionId?: string;
  backendSessionId?: string;
  localPatientId?: string;
  backendPatientId?: string;
  tenantId?: string;
  payload: Record<string, unknown>;
  retryCount: number;
  status: PendingOperationStatus;
  createdAt: number;
  updatedAt: number;
  lastError?: string;
};

export type SyncHealth = {
  online: boolean;
  backendReachable: boolean | null;
  pendingCaptures: number;
  pendingOperations: number;
  syncing: boolean;
  lastError?: string;
};

export type Persona = "doctor" | "assistant" | "admin" | "patient-preview";

export type AuthUser = {
  id: string;
  email: string;
  displayName: string | null;
  persona?: Persona | string | null;
};

export type AuthTenant = {
  id: string;
  name: string;
  tier?: "basic" | "pro" | string;
  transcriptionLanguage?: string;
  reportLanguage?: string | null;
  matchStrictness?: "strict" | "balanced" | "lenient" | string;
  /** A0 — vertical ("clinic" today) + the presentation label for its work-unit ("Session"). */
  vertical?: string;
  encounterLabel?: string;
};

export type AuthMembership = {
  tenantId: string;
  role: string;
};

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
  tenant: AuthTenant;
  memberships: AuthMembership[];
};

export type StoredAuthProfile = Pick<AuthSession, "refreshToken" | "user" | "tenant" | "memberships">;

export type ApiFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type PatientSummary = {
  id: string;
  displayName: string;
  nationalId?: string | null;
  phone?: string | null;
  lastVisit?: string | null;
};

export type PatientMemoryFilter = "recent" | "active" | "all" | "needs-input";

// Live per-task AI model selection (Settings → AI models). Blank model = worker env default.
export type AiModelTask = { task: string; label: string; model: string };
export type AiModelConfig = { tasks: AiModelTask[] };

export type PatientMemoryRow = {
  patientId: string;
  displayName: string;
  summary: string;
  summarySource: string;
  // Mock patient-memory lifecycle: "ready" once the (tier-aware) summary is generated,
  // "updating" while a recent change is being processed.
  memoryStatus?: "ready" | "updating" | string;
  memoryUpdatedAt?: string | null;
  generatedSummary?: string | null;
  ruleBasedSummary?: string | null;
  metadataSentence?: string | null;
  latestSessionMetadata?: {
    sessionId?: string | null;
    title?: string | null;
    status?: string | null;
    summary?: string | null;
    captureCount: number;
    capturedAt?: string | null;
    updatedAt?: string | null;
  } | null;
  latestSessionId?: string | null;
  activeSessionId?: string | null;
  activeSessionCount: number;
  sessionCount: number;
  complete: boolean;
  needsInput: boolean;
  needsInputItems?: Array<{
    id: string;
    sessionId?: string | null;
    kind: string;
    label?: string | null;
    reason?: string | null;
    createdAt?: string | null;
  }>;
  latestVisitAt?: string | null;
  updatedAt?: string | null;
};

export type PatientMemoryListResponse = {
  items: PatientMemoryRow[];
  limit: number;
  offset: number;
  total: number;
};

export type PatientMemoryTimelineSession = {
  sessionId: string;
  title?: string | null;
  status: string;
  summary: string;
  generatedSummary?: string | null;
  ruleBasedSummary?: string | null;
  captureCount: number;
  complete: boolean;
  needsInput: boolean;
  groupLabel: string;
  sortDate?: string | null;
  capturedAt?: string | null;
  updatedAt?: string | null;
};

export type PatientMemorySessionGroup = {
  label: string;
  sessions: PatientMemoryTimelineSession[];
};

export type PatientMemoryHistorySection = {
  label: string;
  body: string;
};

// The richer "patient history" brief shown atop the timeline. Pro fills `sections`
// (Story so far / Worth remembering / Right now); Basic fills `visits` (a structural recap).
export type PatientMemoryHistory = {
  mode: "pro" | "basic" | string;
  status: "ready" | "updating" | string;
  snapshot: string;
  sections: PatientMemoryHistorySection[];
  visits: string[];
  source: string;
  updatedAt?: string | null;
};

export type PatientMemoryDetailResponse = {
  patient: PatientMemoryRow;
  sessions: PatientMemoryTimelineSession[];
  groups: PatientMemorySessionGroup[];
  history?: PatientMemoryHistory | null;
};

export type PatientAssignmentDraft = {
  patientId?: string;
  displayName: string;
  nationalId?: string;
  /** Demographic fields carried when creating a new patient from the unified create form (B3). */
  phone?: string;
  dateOfBirth?: string;
  sex?: string;
  notes?: string;
  unassign?: boolean;
  /** The capture that justifies this (re)assignment — set when applying a per-capture suggestion. */
  basisCaptureId?: string;
};

export type CachedCapture = {
  id: string;
  blob: Blob;
  sourceName: string;
  contentType: string;
  size: number;
  createdAt: number;
  lastAccessedAt: number;
};

export type IdMapping = {
  id: string;
  kind: "capture" | "session";
  localId: string;
  backendId: string;
  tenantId: string;
  createdAt: number;
};

export type StoredWorkspaceState = {
  schemaVersion: 1;
  tenantId?: string;
  screen: string;
  activeSession: CaptureSession | null;
  selectedSessionId: string;
  assignmentSessionId: string;
  pendingCaptureKind: CaptureDraft["kind"] | null;
  updatedAt: number;
};
