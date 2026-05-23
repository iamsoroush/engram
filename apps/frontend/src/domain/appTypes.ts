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
};

export type PatientAssignmentDraft = {
  displayName: string;
  nationalId?: string;
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
