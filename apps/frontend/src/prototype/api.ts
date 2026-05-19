import type { ApiFetch, CaptureDraft, PendingCapture, Persona, PatientAssignmentTarget } from "./appTypes";
import type { CaptureItem, CaptureSession } from "./types";
import { API_BASE } from "./config";
import { normalizeApiCaptureItem, normalizeApiSession, normalizePatient, normalizeUploadResult } from "./normalizers";
import { saveIdMapping } from "./storage";

export async function loginWithPersona(persona: Persona) {
  const response = await fetch(`${API_BASE}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as import("./appTypes").AuthSession;
}

export async function loginWithPassword(email: string, password: string) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as import("./appTypes").AuthSession;
}

export async function refreshAuthToken(refreshToken: string) {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  if (!response.ok) throw new Error("Refresh failed");
  return (await response.json()) as Pick<import("./appTypes").AuthSession, "accessToken" | "refreshToken">;
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

export async function retrySessionProcessing(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/retry-processing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reportTemplateKey: "default" }),
  });
  if (!response.ok) throw new Error("Could not retry session processing");
  const payload = (await response.json()) as { session?: Record<string, unknown> };
  return normalizeApiSession(payload.session || {});
}

export async function verifySession(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error("Could not verify session");
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

export async function updateSessionMetadata(apiFetch: ApiFetch, sessionId: string, extractedMetadata: Record<string, unknown>) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ extractedMetadata }),
  });
  if (!response.ok) throw new Error("Could not update session metadata");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function fetchSessionCaptures(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/captures`);
  if (!response.ok) throw new Error("Could not load captures");
  const captures = (await response.json()) as Array<Record<string, unknown>>;
  return captures.map(normalizeApiCaptureItem);
}

export async function searchPatients(apiFetch: ApiFetch, query: string) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const response = await apiFetch(`${API_BASE}/patients?${params.toString()}`);
  if (!response.ok) throw new Error("Could not search patients");
  const patients = (await response.json()) as Array<Record<string, unknown>>;
  return patients.map(normalizePatient);
}

export async function createPatient(apiFetch: ApiFetch, displayName: string, nationalId?: string) {
  const response = await apiFetch(`${API_BASE}/patients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName, nationalId: nationalId || undefined }),
  });
  if (!response.ok) throw new Error("Could not create patient");
  return normalizePatient((await response.json()) as Record<string, unknown>);
}

export async function assignSessionPatient(apiFetch: ApiFetch, sessionId: string, target: PatientAssignmentTarget) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assign-patient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId: target.patientId, source: target.source || "staff" }),
  });
  if (!response.ok) throw new Error("Could not assign patient");
  const session = normalizeApiSession((await response.json()) as Record<string, unknown>);
  return { ...session, patientName: target.patientName, assignmentSource: target.source || "staff" };
}

export async function assignCapturePatient(apiFetch: ApiFetch, captureId: string, target: PatientAssignmentTarget) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}/assign-patient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId: target.patientId, source: target.source || "staff" }),
  });
  if (!response.ok) throw new Error("Could not assign capture");
  const item = normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
  return { ...item, patientName: target.patientName, assignmentSource: target.source || "staff" };
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
