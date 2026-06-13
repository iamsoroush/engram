import type { ApiFetch } from "../../domain/appTypes";
import { API_BASE } from "../../shared/lib/config";

/**
 * Authenticated doctor Q&A client (AES-402). Thin wrappers over `/patient-qa/*`, mirroring the
 * existing client.ts pattern (each takes `apiFetch`, throws on non-2xx). Pro-gated server-side.
 */

export interface QaAssignedDoctor {
  userId: string;
  name: string;
}

export interface QaInboxItem {
  messageId: string;
  threadId: string;
  patientId: string;
  patientName: string;
  question: string;
  askedAt: string | null;
  suggestedReply: string | null;
  draftStatus: "none" | "pending" | "ready" | "failed" | string;
  assignedDoctor: QaAssignedDoctor | null;
  routingSource: string;
}

export interface QaInboxResponse {
  scope: "mine" | "all";
  items: QaInboxItem[];
  total: number;
}

export interface QaTreatingDoctor {
  userId: string;
  name: string;
  sessionCount: number;
  lastVisitAt: string | null;
}

export interface QaSettings {
  routingMode: "ai_default" | "manual" | string;
}

export interface QaThreadMessage {
  id: string;
  role: "patient" | "doctor" | string;
  body: string;
  status: string;
  inReplyToId: string | null;
  createdAt: string | null;
}

export interface QaThreadDetail {
  id: string;
  patientId: string;
  status: string;
  assignedDoctor: QaAssignedDoctor | null;
  routingSource: string;
  messages: QaThreadMessage[];
}

export async function fetchQaThreadDetail(apiFetch: ApiFetch, threadId: string): Promise<QaThreadDetail> {
  const response = await apiFetch(`${API_BASE}/patient-qa/threads/${threadId}`);
  if (!response.ok) throw new Error("Could not load the conversation");
  const payload = (await response.json()) as QaThreadDetail & { messages?: QaThreadMessage[] };
  return { ...payload, messages: Array.isArray(payload.messages) ? payload.messages : [] };
}

export async function fetchQaInbox(apiFetch: ApiFetch, scope: "mine" | "all" = "mine"): Promise<QaInboxResponse> {
  const response = await apiFetch(`${API_BASE}/patient-qa/inbox?scope=${encodeURIComponent(scope)}`);
  if (!response.ok) throw new Error("Could not load the Q&A inbox");
  const payload = (await response.json()) as QaInboxResponse;
  return { scope: payload.scope ?? scope, total: payload.total ?? 0, items: Array.isArray(payload.items) ? payload.items : [] };
}

export async function sendQaReply(apiFetch: ApiFetch, messageId: string, reply: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/patient-qa/messages/${messageId}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reply }),
  });
  if (!response.ok) throw new Error("Could not send the reply");
}

export async function dismissQaQuestion(apiFetch: ApiFetch, messageId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/patient-qa/messages/${messageId}/dismiss`, { method: "POST" });
  if (!response.ok) throw new Error("Could not dismiss the question");
}

export async function fetchTreatingDoctors(apiFetch: ApiFetch, patientId: string): Promise<QaTreatingDoctor[]> {
  const response = await apiFetch(`${API_BASE}/patient-qa/patients/${patientId}/treating-doctors`);
  if (!response.ok) throw new Error("Could not load treating doctors");
  const payload = (await response.json()) as { treatingDoctors?: QaTreatingDoctor[] };
  return Array.isArray(payload.treatingDoctors) ? payload.treatingDoctors : [];
}

export async function routeQaThread(apiFetch: ApiFetch, threadId: string, doctorUserId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/patient-qa/threads/${threadId}/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctorUserId }),
  });
  if (!response.ok) throw new Error("Could not re-route the thread");
}

export async function fetchQaSettings(apiFetch: ApiFetch): Promise<QaSettings> {
  const response = await apiFetch(`${API_BASE}/patient-qa/settings`);
  if (!response.ok) throw new Error("Could not load Q&A settings");
  return (await response.json()) as QaSettings;
}

export async function setQaRoutingMode(apiFetch: ApiFetch, routingMode: "ai_default" | "manual"): Promise<QaSettings> {
  const response = await apiFetch(`${API_BASE}/patient-qa/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routingMode }),
  });
  if (!response.ok) throw new Error("Could not update Q&A routing");
  return (await response.json()) as QaSettings;
}
