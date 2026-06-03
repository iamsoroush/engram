import type {
  ApiFetch,
  AuthSession,
  CaptureDraft,
  PatientAssignmentDraft,
  PatientMemoryDetailResponse,
  PatientMemoryFilter,
  PatientMemoryListResponse,
  PatientMemoryRow,
  PatientMemoryTimelineSession,
  PatientSummary,
  PendingCapture,
  Persona,
} from "../../domain/appTypes";
import type { CaptureItem, CaptureSession } from "../../domain/types";
import { API_BASE } from "../../shared/lib/config";
import { normalizeApiCaptureItem, normalizeApiSession, normalizeUploadResult } from "./normalizers";
import { saveIdMapping } from "../storage/captureStorage";

export async function loginWithPersona(persona: Persona) {
  const response = await fetch(`${API_BASE}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as AuthSession;
}

export async function loginWithPassword(email: string, password: string) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as AuthSession;
}

export async function refreshAuthToken(refreshToken: string) {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  if (!response.ok) throw new Error("Refresh failed");
  return (await response.json()) as Pick<AuthSession, "accessToken" | "refreshToken">;
}

export async function logoutSession(accessToken: string, refreshToken: string) {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
}

export async function fetchSessions(apiFetch: ApiFetch) {
  const response = await apiFetch(`${API_BASE}/sessions`);
  if (!response.ok) throw new Error("Could not load sessions");
  const sessions = (await response.json()) as Array<Record<string, unknown>>;
  return sessions.map(normalizeApiSession);
}

export async function fetchSession(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`);
  if (!response.ok) throw new Error("Could not load session");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function uploadCapture(apiFetch: ApiFetch, clientCaptureId: string, draft: CaptureDraft, sessionId?: string, intoNew = false) {
  const form = new FormData();
  form.append("capture_type", draft.kind);
  form.append("detail", draft.detail ?? "");
  form.append("new_session", String(intoNew || !sessionId));
  form.append("client_capture_id", clientCaptureId);
  if (draft.metadata) form.append("metadata", JSON.stringify(draft.metadata));
  if (sessionId && !intoNew) form.append("session_id", sessionId);
  form.append("file", draft.file, draft.filename);

  const response = await apiFetch(`${API_BASE}/captures`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error("Capture upload failed");
  return normalizeUploadResult((await response.json()) as { session: Record<string, unknown>; item: Record<string, unknown> });
}

/**
 * Persists local/backend ID relationships so future recovery work can reconcile
 * optimistic captures with uploaded backend records.
 */
export async function storeBackendMappings(
  capture: PendingCapture,
  result: { session: CaptureSession; item: CaptureItem },
  tenantId: string,
) {
  const createdAt = Date.now();
  await Promise.all([
    saveIdMapping({
      id: `${tenantId}:capture:${capture.localCaptureId}`,
      kind: "capture",
      localId: capture.localCaptureId,
      backendId: result.item.id,
      tenantId,
      createdAt,
    }),
    saveIdMapping({
      id: `${tenantId}:session:${capture.localSessionId}`,
      kind: "session",
      localId: capture.localSessionId,
      backendId: result.session.id,
      tenantId,
      createdAt,
    }),
  ]);
}

export async function saveSessionForProcessing(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reportTemplateKey: "default" }),
  });
  if (!response.ok) throw new Error("Could not save session");
  const payload = (await response.json()) as { session?: Record<string, unknown> };
  return normalizeApiSession(payload.session || {});
}

export async function searchPatients(apiFetch: ApiFetch, query: string) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const response = await apiFetch(`${API_BASE}/patients?${params.toString()}`);
  if (!response.ok) throw new Error("Could not search patients");
  const patients = (await response.json()) as Array<Record<string, unknown>>;
  return patients.map(normalizePatientSummary);
}

export async function fetchPatientMemory(
  apiFetch: ApiFetch,
  {
    query,
    filter,
    limit = 50,
    offset = 0,
  }: {
    query?: string;
    filter: PatientMemoryFilter;
    limit?: number;
    offset?: number;
  },
): Promise<PatientMemoryListResponse> {
  const params = new URLSearchParams({ filter, limit: String(limit), offset: String(offset) });
  if (query?.trim()) params.set("query", query.trim());
  const response = await apiFetch(`${API_BASE}/patient-memory?${params.toString()}`);
  if (!response.ok) throw new Error("Could not load patient memory");
  const payload = (await response.json()) as Record<string, unknown>;
  const items = Array.isArray(payload.items) ? payload.items : [];
  return {
    items: items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")).map(normalizePatientMemoryRow),
    limit: numberValue(payload.limit, limit),
    offset: numberValue(payload.offset, offset),
    total: numberValue(payload.total, items.length),
  };
}

export async function fetchPatientMemoryDetail(apiFetch: ApiFetch, patientId: string): Promise<PatientMemoryDetailResponse> {
  const response = await apiFetch(`${API_BASE}/patients/${patientId}/memory`);
  if (!response.ok) throw new Error("Could not load patient memory");
  const payload = (await response.json()) as Record<string, unknown>;
  const rawSessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  const sessions = rawSessions
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map(normalizePatientMemoryTimelineSession);
  const rawGroups = Array.isArray(payload.groups) ? payload.groups : [];
  return {
    patient:
      payload.patient && typeof payload.patient === "object"
        ? normalizePatientMemoryRow(payload.patient as Record<string, unknown>)
        : normalizePatientMemoryRow({ patientId, displayName: "Unnamed patient" }),
    sessions,
    groups: rawGroups
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((group) => ({
        label: String(group.label || "Older"),
        sessions: (Array.isArray(group.sessions) ? group.sessions : [])
          .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
          .map(normalizePatientMemoryTimelineSession),
      })),
  };
}

export async function createPatient(apiFetch: ApiFetch, draft: PatientAssignmentDraft, idempotencyKey?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  const response = await apiFetch(`${API_BASE}/patients`, {
    method: "POST",
    headers,
    body: JSON.stringify({ displayName: draft.displayName, nationalId: draft.nationalId || null }),
  });
  if (!response.ok) throw new Error("Could not create patient");
  return normalizePatientSummary((await response.json()) as Record<string, unknown>);
}

export async function updatePatient(
  apiFetch: ApiFetch,
  patientId: string,
  draft: {
    displayName?: string;
    nationalId?: string | null;
    phone?: string | null;
    dateOfBirth?: string | null;
  },
) {
  // Partial PATCH: only send keys that were provided, so an untouched field is never
  // overwritten (e.g. editing a phone must not clear an existing national ID).
  const body: Record<string, unknown> = {};
  if (draft.displayName !== undefined) body.displayName = draft.displayName;
  if (draft.nationalId !== undefined) body.nationalId = draft.nationalId;
  if (draft.phone !== undefined) body.phone = draft.phone;
  if (draft.dateOfBirth !== undefined) body.dateOfBirth = draft.dateOfBirth;
  const response = await apiFetch(`${API_BASE}/patients/${patientId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Could not update patient");
  return normalizePatientSummary((await response.json()) as Record<string, unknown>);
}

export async function verifyAiPatientCreation(apiFetch: ApiFetch, sessionId: string, action: Record<string, unknown>) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      extractedMetadata: {
        ai_patient_action: {
          ...action,
          status: "verified",
          needsVerification: false,
          verifiedAt: new Date().toISOString(),
        },
      },
    }),
  });
  if (!response.ok) throw new Error("Could not verify patient creation");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function assignSessionPatient(apiFetch: ApiFetch, sessionId: string, patientId: string, idempotencyKey?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assign-patient`, {
    method: "POST",
    headers,
    body: JSON.stringify({ patientId, source: "staff", reason: "Lightweight assignment" }),
  });
  if (!response.ok) throw new Error("Could not assign patient");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function unassignSessionPatient(apiFetch: ApiFetch, sessionId: string, idempotencyKey?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assign-patient`, {
    method: "POST",
    headers,
    body: JSON.stringify({ patientId: null, source: "staff", reason: "Unassigned by staff" }),
  });
  if (!response.ok) throw new Error("Could not unassign patient");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function verifySession(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/verify`, { method: "POST" });
  if (!response.ok) throw new Error("Could not verify session");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function reopenSession(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/reopen`, { method: "POST" });
  if (!response.ok) throw new Error("Could not reopen session");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function updateSessionTitle(apiFetch: ApiFetch, sessionId: string, title: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error("Could not update session title");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function updateCaptureTitle(apiFetch: ApiFetch, captureId: string, title: string) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metadata: { title } }),
  });
  if (!response.ok) throw new Error("Could not update capture title");
  return normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
}

export async function updateCaptureCaption(apiFetch: ApiFetch, captureId: string, caption: string) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metadata: {
        caption: {
          text: caption,
          source: "staff_edit",
          updated_at: new Date().toISOString(),
        },
      },
    }),
  });
  if (!response.ok) throw new Error("Could not update capture caption");
  return normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
}

export async function updateCaptureTranscript(apiFetch: ApiFetch, captureId: string, transcript: string) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metadata: {
        transcript: {
          text: transcript,
          source: "staff_edit",
          updated_at: new Date().toISOString(),
        },
      },
    }),
  });
  if (!response.ok) throw new Error("Could not update capture transcript");
  return normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
}

export async function deleteCapture(apiFetch: ApiFetch, captureId: string) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not delete capture");
  const payload = (await response.json()) as { session?: Record<string, unknown> };
  return normalizeApiSession(payload.session || {});
}

export async function retryCaptureProcessing(apiFetch: ApiFetch, captureId: string) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}/retry-processing`, { method: "POST" });
  if (!response.ok) throw new Error("Could not retry capture processing");
  return (await response.json()) as { job?: Record<string, unknown> };
}

function normalizePatientSummary(raw: Record<string, unknown>): PatientSummary {
  return {
    id: String(raw.id),
    displayName: String(raw.displayName || "Unnamed patient"),
    nationalId: typeof raw.nationalId === "string" ? raw.nationalId : null,
    phone: typeof raw.phone === "string" ? raw.phone : null,
    lastVisit: typeof raw.lastVisit === "string" ? raw.lastVisit : null,
  };
}

function normalizePatientMemoryRow(raw: Record<string, unknown>): PatientMemoryRow {
  const latestSessionMetadata =
    raw.latestSessionMetadata && typeof raw.latestSessionMetadata === "object"
      ? (raw.latestSessionMetadata as Record<string, unknown>)
      : null;
  const rawNeedsInputItems = Array.isArray(raw.needsInputItems) ? raw.needsInputItems : [];
  return {
    patientId: String(raw.patientId || raw.id || ""),
    displayName: String(raw.displayName || "Unnamed patient"),
    summary: String(raw.summary || "No memory summary yet."),
    summarySource: String(raw.summarySource || "fallback"),
    generatedSummary: typeof raw.generatedSummary === "string" ? raw.generatedSummary : null,
    ruleBasedSummary: typeof raw.ruleBasedSummary === "string" ? raw.ruleBasedSummary : null,
    metadataSentence: typeof raw.metadataSentence === "string" ? raw.metadataSentence : null,
    latestSessionMetadata: latestSessionMetadata
      ? {
          sessionId: typeof latestSessionMetadata.sessionId === "string" ? latestSessionMetadata.sessionId : null,
          title: typeof latestSessionMetadata.title === "string" ? latestSessionMetadata.title : null,
          status: typeof latestSessionMetadata.status === "string" ? latestSessionMetadata.status : null,
          summary: typeof latestSessionMetadata.summary === "string" ? latestSessionMetadata.summary : null,
          captureCount: numberValue(latestSessionMetadata.captureCount, 0),
          capturedAt: typeof latestSessionMetadata.capturedAt === "string" ? latestSessionMetadata.capturedAt : null,
          updatedAt: typeof latestSessionMetadata.updatedAt === "string" ? latestSessionMetadata.updatedAt : null,
        }
      : null,
    latestSessionId: typeof raw.latestSessionId === "string" ? raw.latestSessionId : null,
    activeSessionId: typeof raw.activeSessionId === "string" ? raw.activeSessionId : null,
    activeSessionCount: numberValue(raw.activeSessionCount, 0),
    sessionCount: numberValue(raw.sessionCount, 0),
    verified: Boolean(raw.verified),
    needsInput: Boolean(raw.needsInput),
    needsInputItems: rawNeedsInputItems
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item, index) => ({
        id: String(item.id || item.sessionId || `needs-input-${index}`),
        sessionId: typeof item.sessionId === "string" ? item.sessionId : null,
        kind: String(item.kind || item.type || ""),
        label: typeof item.label === "string" ? item.label : null,
        createdAt: typeof item.createdAt === "string" ? item.createdAt : null,
      })),
    latestVisitAt: typeof raw.latestVisitAt === "string" ? raw.latestVisitAt : null,
    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : null,
  };
}

function normalizePatientMemoryTimelineSession(raw: Record<string, unknown>): PatientMemoryTimelineSession {
  return {
    sessionId: String(raw.sessionId || raw.session_id || ""),
    title: typeof raw.title === "string" ? raw.title : null,
    status: String(raw.status || "organized"),
    summary: String(raw.summary || "No session summary yet."),
    generatedSummary: typeof raw.generatedSummary === "string" ? raw.generatedSummary : null,
    ruleBasedSummary: typeof raw.ruleBasedSummary === "string" ? raw.ruleBasedSummary : null,
    captureCount: numberValue(raw.captureCount, 0),
    verified: Boolean(raw.verified),
    needsInput: Boolean(raw.needsInput),
    groupLabel: String(raw.groupLabel || "Older"),
    sortDate: typeof raw.sortDate === "string" ? raw.sortDate : null,
    capturedAt: typeof raw.capturedAt === "string" ? raw.capturedAt : null,
    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : null,
  };
}

function numberValue(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export async function fetchSessionCaptures(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/captures`);
  if (!response.ok) throw new Error("Could not load captures");
  const captures = (await response.json()) as Array<Record<string, unknown>>;
  return captures.map(normalizeApiCaptureItem);
}

/**
 * Uses the file-content endpoint for in-app previews because `/file` may be a
 * download route rather than a blob response.
 */
export async function resolveCaptureFileUrl(apiFetch: ApiFetch, endpoint: string) {
  const contentEndpoint = endpoint.endsWith("/file") ? endpoint.replace(/\/file$/, "/file-content") : endpoint;
  const response = await apiFetch(contentEndpoint);
  if (!response.ok) throw new Error("Could not load source file");
  return URL.createObjectURL(await response.blob());
}
