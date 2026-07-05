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

/**
 * Retrieval provenance for a suggested reply (AES-410): the library exemplar (a saved template or a
 * previously-sent reply) the draft was grounded on. `label` is the exemplar's short title, if any.
 */
export interface QaDraftProvenance {
  kind: "template" | "sent_reply";
  exemplarId: string;
  label: string | null;
}

export interface QaPendingQuestion {
  messageId: string;
  question: string;
  askedAt: string | null;
  suggestedReply: string | null;
  draftStatus: "none" | "pending" | "ready" | "failed" | string;
  /** Which library exemplar grounded this draft, if retrieval found one (AES-410). */
  draftProvenance?: QaDraftProvenance | null;
}

export interface QaVisitMarker {
  sessionId: string;
  title: string;
  date: string | null;
}

/** A thread-centric inbox entry: one patient conversation (Telegram-style), needs-approval first. */
export interface QaInboxItem {
  threadId: string;
  patientId: string;
  patientName: string;
  assignedDoctor: QaAssignedDoctor | null;
  routingSource: string;
  treatingDoctorCount: number;
  needsApproval: boolean;
  pendingQuestion: QaPendingQuestion | null;
  messages: QaThreadMessage[];
  visits: QaVisitMarker[];
  lastActivityAt: string | null;
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

export interface QaThreadSummary {
  threadId: string;
  token: string;
  publicPath: string;
  status: string;
  assignedDoctor: QaAssignedDoctor | null;
  routingSource: string;
}

/** Open (or idempotently reuse) the patient's Q&A channel; returns the tokenized public link. */
export async function openQaChannel(apiFetch: ApiFetch, patientId: string): Promise<QaThreadSummary> {
  const response = await apiFetch(`${API_BASE}/patient-qa/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId }),
  });
  if (!response.ok) throw new Error("Could not open the Q&A channel");
  const payload = (await response.json()) as Record<string, unknown>;
  return {
    threadId: String(payload.id || ""),
    token: String(payload.token || ""),
    publicPath: String(payload.publicPath || ""),
    status: String(payload.status || "active"),
    assignedDoctor: (payload.assignedDoctor as QaAssignedDoctor | null) ?? null,
    routingSource: String(payload.routingSource || ""),
  };
}

export async function fetchQaInbox(apiFetch: ApiFetch, scope: "mine" | "all" = "mine"): Promise<QaInboxResponse> {
  const response = await apiFetch(`${API_BASE}/patient-qa/inbox?scope=${encodeURIComponent(scope)}`);
  if (!response.ok) throw new Error("Could not load the Q&A inbox");
  const payload = (await response.json()) as QaInboxResponse;
  return { scope: payload.scope ?? scope, total: payload.total ?? 0, items: Array.isArray(payload.items) ? payload.items : [] };
}

export interface QaMessageDraft {
  messageId: string;
  status: string;
  draft: string | null;
  draftStatus: "none" | "pending" | "ready" | "failed" | "revising" | string;
  draftSource: string | null;
  draftMode: "revise" | "replace" | null;
  /** Which library exemplar grounded this draft, if retrieval found one (AES-410). */
  draftProvenance?: QaDraftProvenance | null;
}

/** Send the doctor's voice note to revise/replace the reply draft; the AI decides which (AES-402). */
export async function requestQaVoiceEdit(
  apiFetch: ApiFetch,
  messageId: string,
  audio: Blob,
  currentDraft: string,
): Promise<{ messageId: string; draftStatus: string }> {
  const ext = audio.type.includes("mp4") || audio.type.includes("mpeg") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("file", audio, `voice.${ext}`);
  form.append("draft", currentDraft);
  // No explicit Content-Type — the browser sets the multipart boundary; apiFetch adds auth.
  const response = await apiFetch(`${API_BASE}/patient-qa/messages/${messageId}/voice-edit`, { method: "POST", body: form });
  if (!response.ok) throw new Error("Could not send the voice note");
  return (await response.json()) as { messageId: string; draftStatus: string };
}

/** Poll a question's draft state (used while a voice edit / initial draft is running). */
export async function fetchQaMessageDraft(apiFetch: ApiFetch, messageId: string): Promise<QaMessageDraft> {
  const response = await apiFetch(`${API_BASE}/patient-qa/messages/${messageId}/draft`);
  if (!response.ok) throw new Error("Could not load the draft");
  return (await response.json()) as QaMessageDraft;
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

// --- Q&A knowledge library (AES-410) ---------------------------------------------------------------
// The retrieval corpus behind grounded reply drafting: hand-authored templates plus indexed
// previously-sent replies. The doctor curates it here (add/edit/delete templates; exclude a noisy
// sent reply). All chrome is localized in the caller; template/reply text is verbatim clinical content.

/** One library exemplar: a curated template or an indexed sent reply. Shapes mirror the backend. */
export interface LibraryItem {
  id: string;
  kind: "template" | "sent_reply";
  status: "active" | "excluded";
  title: string | null;
  question: string | null;
  answer: string;
  language: string;
  tags: string[];
  sourceMessageId: string | null;
  indexed: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface QaLibraryCounts {
  templates: number;
  sentRepliesActive: number;
  sentRepliesExcluded: number;
}

export interface QaLibraryResponse {
  templates: LibraryItem[];
  sentReplies: LibraryItem[];
  counts: QaLibraryCounts;
}

/** Create/update body for a curated template. `answer` is required; the rest are optional. */
export interface QaTemplateInput {
  title?: string | null;
  question?: string | null;
  answer: string;
  tags?: string[];
}

export async function fetchQaLibrary(
  apiFetch: ApiFetch,
  filters: { kind?: string; status?: string } = {},
): Promise<QaLibraryResponse> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/patient-qa/library${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load the Q&A library");
  const payload = (await response.json()) as Partial<QaLibraryResponse>;
  return {
    templates: Array.isArray(payload.templates) ? payload.templates : [],
    sentReplies: Array.isArray(payload.sentReplies) ? payload.sentReplies : [],
    counts: payload.counts ?? { templates: 0, sentRepliesActive: 0, sentRepliesExcluded: 0 },
  };
}

export async function createQaTemplate(apiFetch: ApiFetch, body: QaTemplateInput): Promise<LibraryItem> {
  const response = await apiFetch(`${API_BASE}/patient-qa/library/templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Could not save the template");
  return (await response.json()) as LibraryItem;
}

export async function updateQaTemplate(apiFetch: ApiFetch, id: string, body: QaTemplateInput): Promise<LibraryItem> {
  const response = await apiFetch(`${API_BASE}/patient-qa/library/templates/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Could not update the template");
  return (await response.json()) as LibraryItem;
}

export async function deleteQaTemplate(apiFetch: ApiFetch, id: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/patient-qa/library/templates/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not delete the template");
}

/** Include/exclude a library exemplar (template or sent reply) from the retrieval corpus. */
export async function setQaExemplarStatus(
  apiFetch: ApiFetch,
  id: string,
  status: "active" | "excluded",
): Promise<LibraryItem> {
  const response = await apiFetch(`${API_BASE}/patient-qa/library/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) throw new Error("Could not update the exemplar");
  return (await response.json()) as LibraryItem;
}

/** Promote a sent doctor reply into a curated, reusable template. */
export async function saveReplyAsTemplate(apiFetch: ApiFetch, messageId: string, title?: string | null): Promise<LibraryItem> {
  const response = await apiFetch(`${API_BASE}/patient-qa/messages/${messageId}/save-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  });
  if (!response.ok) throw new Error("Could not save the reply as a template");
  return (await response.json()) as LibraryItem;
}
