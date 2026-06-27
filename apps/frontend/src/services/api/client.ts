import type {
  ApiFetch,
  AuthSession,
  CaptureDraft,
  DevTier,
  PatientAssignmentDraft,
  AiModelConfig,
  AftercareTemplate,
  AftercareTemplateDraft,
  AssignmentSuggestionResponse,
  CreatePatientShareInput,
  DuplicateCheckResponse,
  LastVisitInfo,
  LastVisitMedia,
  LineupCard,
  PatientMemoryDetailResponse,
  PatientMemoryFilter,
  PatientMemoryHistory,
  PatientMemoryListResponse,
  PatientMemoryRow,
  PatientMemoryTimelineSession,
  PatientShare,
  PatientSummary,
  PendingCapture,
  Persona,
  ClinicMember,
  RolePermissions,
  SessionContext,
  SmartPatientSearchResponse,
  WorklistEntry,
  WorklistResponse,
} from "../../domain/appTypes";
import type { Attribution, CaptureItem, CaptureSession, StructuredPatientInformation } from "../../domain/types";
import { API_BASE } from "../../shared/lib/config";
import { normalizeApiCaptureItem, normalizeApiSession, normalizeUploadResult } from "./normalizers";
import { saveIdMapping } from "../storage/captureStorage";

/**
 * An HTTP error that carries the response status, so callers can distinguish a "the resource is
 * gone" 404 (self-heal: clear the stale reference) from a transient/network error (retry/queue).
 */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when an error is a 404 — the referenced patient/session no longer exists (deleted/merged). */
export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export async function loginWithPersona(persona: Persona, tier: DevTier = "pro") {
  const response = await fetch(`${API_BASE}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, tier }),
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

export interface RegisterClinicInput {
  clinicName: string;
  fullName: string;
  email: string;
  password: string;
  appLanguage: string;
}

/** Self-serve clinic sign-up. Throws an Error tagged with `.status` so the form can map 409/422. */
export async function registerClinic(input: RegisterClinicInput) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const error = new Error("Registration failed") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return (await response.json()) as AuthSession;
}

/** Switch the signed-in user's active clinic (re-issues a session for another of their tenants). */
export async function switchTenant(apiFetch: ApiFetch, tenantId: string) {
  const response = await apiFetch(`${API_BASE}/auth/switch-tenant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenantId }),
  });
  if (!response.ok) throw new Error("Could not switch clinic");
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

export async function fetchSessions(apiFetch: ApiFetch, options?: { clinicianId?: string }) {
  // AES-904 "Mine vs Clinic": pass the caller's own id as clinicianId for the Mine view.
  const params = new URLSearchParams();
  if (options?.clinicianId) params.set("clinicianId", options.clinicianId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/sessions${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load sessions");
  const sessions = (await response.json()) as Array<Record<string, unknown>>;
  return sessions.map(normalizeApiSession);
}

export async function fetchSession(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`);
  if (!response.ok) throw new Error("Could not load session");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

/** AES-903 — start a fresh visit assigned to a patient (the worklist "Start visit" quick action). */
export async function createSession(apiFetch: ApiFetch, patientId: string, title?: string) {
  const response = await apiFetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId, title }),
  });
  if (!response.ok) throw new Error("Could not start the visit");
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

// --- Aesthetics-Basic deterministic services (docs/backend/aes-basic-api.md) ---

const arrayOfStrings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : []);
const stringOrNull = (value: unknown): string | null => (typeof value === "string" && value.trim() ? value : null);

/** AES-204 — deterministic, Persian-orthography-aware, ranked smart patient search. */
export async function searchPatientsSmart(apiFetch: ApiFetch, query: string, limit = 20): Promise<SmartPatientSearchResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) params.set("q", query.trim());
  const response = await apiFetch(`${API_BASE}/patients/search?${params.toString()}`);
  if (!response.ok) throw new Error("Could not search patients");
  const payload = (await response.json()) as Record<string, unknown>;
  const items = Array.isArray(payload.items) ? payload.items : [];
  return {
    query: String(payload.query || query.trim()),
    total: numberValue(payload.total, items.length),
    items: items
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({
        ...normalizePatientSummary(item),
        email: stringOrNull(item.email),
        status: stringOrNull(item.status),
        createdAt: stringOrNull(item.createdAt),
        updatedAt: stringOrNull(item.updatedAt),
        score: typeof item.score === "number" ? item.score : null,
        matchedOn: arrayOfStrings(item.matchedOn),
        reason: String(item.reason || ""),
      })),
  };
}

/** AES-205 — duplicate-patient guard; run before creating a new patient. */
export async function checkDuplicatePatient(
  apiFetch: ApiFetch,
  body: { displayName?: string; nationalId?: string; phone?: string; email?: string },
): Promise<DuplicateCheckResponse> {
  const response = await apiFetch(`${API_BASE}/patients/duplicate-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Could not run duplicate check");
  const payload = (await response.json()) as Record<string, unknown>;
  const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
  return {
    hasLikelyDuplicate: Boolean(payload.hasLikelyDuplicate),
    candidates: candidates
      .filter((candidate): candidate is Record<string, unknown> => Boolean(candidate && typeof candidate === "object"))
      .map((candidate) => ({
        patientId: String(candidate.patientId || ""),
        displayName: String(candidate.displayName || "Unnamed patient"),
        confidence: numberValue(candidate.confidence, 0),
        matchedOn: arrayOfStrings(candidate.matchedOn),
        reason: String(candidate.reason || ""),
        risks: arrayOfStrings(candidate.risks),
      })),
  };
}

/** AES-301 — deterministic assign-later suggestion for an unassigned visit. */
export async function fetchAssignmentSuggestion(apiFetch: ApiFetch, sessionId: string): Promise<AssignmentSuggestionResponse> {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assignment-suggestion`);
  if (!response.ok) throw new Error("Could not load assignment suggestion");
  const payload = (await response.json()) as Record<string, unknown>;
  const mapCandidate = (raw: Record<string, unknown>) => ({
    patientId: String(raw.patientId || ""),
    displayName: String(raw.displayName || "Unnamed patient"),
    basis: String(raw.basis || ""),
    reason: String(raw.reason || ""),
    lastVisitAt: stringOrNull(raw.lastVisitAt),
  });
  const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
  return {
    sessionId: String(payload.sessionId || sessionId),
    alreadyAssigned: Boolean(payload.alreadyAssigned),
    suggestion:
      payload.suggestion && typeof payload.suggestion === "object" ? mapCandidate(payload.suggestion as Record<string, unknown>) : null,
    candidates: candidates
      .filter((candidate): candidate is Record<string, unknown> => Boolean(candidate && typeof candidate === "object"))
      .map(mapCandidate),
  };
}

/** AES-106/203 — the prior visit's note + photos (how Basic answers "what did we use last time"). */
function normalizeVisitMedia(raw: unknown): LastVisitMedia[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((media): media is Record<string, unknown> => Boolean(media && typeof media === "object"))
    .map((media) => ({
      captureId: String(media.captureId || ""),
      type: String(media.type || "photo"),
      fileEndpoint: String(media.fileEndpoint || ""),
      contentEndpoint: String(media.contentEndpoint || ""),
      capturedAt: stringOrNull(media.capturedAt),
      caption: stringOrNull(media.caption),
    }));
}

function normalizeLastVisit(payload: Record<string, unknown>, fallbackPatientId: string): LastVisitInfo {
  const rawVisit = payload.visit && typeof payload.visit === "object" ? (payload.visit as Record<string, unknown>) : null;
  const rawSame = payload.sameAsLastTime && typeof payload.sameAsLastTime === "object" ? (payload.sameAsLastTime as Record<string, unknown>) : null;
  return {
    patientId: String(payload.patientId || fallbackPatientId),
    hasPriorVisit: Boolean(payload.hasPriorVisit),
    visit: rawVisit
      ? {
          sessionId: String(rawVisit.sessionId || ""),
          title: String(rawVisit.title || "Visit"),
          status: String(rawVisit.status || ""),
          capturedAt: stringOrNull(rawVisit.capturedAt),
          updatedAt: stringOrNull(rawVisit.updatedAt),
          captureCount: numberValue(rawVisit.captureCount, 0),
          note: stringOrNull(rawVisit.note),
          noteSource: stringOrNull(rawVisit.noteSource),
          media: normalizeVisitMedia(rawVisit.media),
          audio: normalizeVisitMedia(rawVisit.audio),
          audioCount: numberValue(rawVisit.audioCount, 0),
        }
      : null,
    sameAsLastTime: rawSame
      ? {
          note: String(rawSame.note || ""),
          fromSessionId: String(rawSame.fromSessionId || ""),
          fromVisitAt: stringOrNull(rawSame.fromVisitAt),
          label: String(rawSame.label || "from last visit"),
        }
      : null,
  };
}

export async function fetchLastVisit(apiFetch: ApiFetch, patientId: string, excludeSessionId?: string): Promise<LastVisitInfo> {
  const params = new URLSearchParams();
  if (excludeSessionId) params.set("excludeSessionId", excludeSessionId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/patients/${patientId}/last-visit${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load last visit");
  return normalizeLastVisit((await response.json()) as Record<string, unknown>, patientId);
}

export async function fetchSessionContext(apiFetch: ApiFetch, patientId: string, excludeSessionId?: string): Promise<SessionContext> {
  const params = new URLSearchParams();
  if (excludeSessionId) params.set("excludeSessionId", excludeSessionId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/patients/${patientId}/session-context${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load session context");
  const payload = (await response.json()) as Record<string, unknown>;
  const rawLast = payload.lastVisit && typeof payload.lastVisit === "object" ? (payload.lastVisit as Record<string, unknown>) : {};
  const rawRecent = Array.isArray(payload.recentVisits) ? payload.recentVisits : [];
  return {
    patientId: String(payload.patientId || patientId),
    lastVisit: normalizeLastVisit(rawLast, patientId),
    recentVisits: rawRecent
      .filter((visit): visit is Record<string, unknown> => Boolean(visit && typeof visit === "object"))
      .map((visit) => ({
        sessionId: String(visit.sessionId || ""),
        title: String(visit.title || "Visit"),
        capturedAt: stringOrNull(visit.capturedAt),
        photoCount: numberValue(visit.photoCount, 0),
        photos: normalizeVisitMedia(visit.photos),
      })),
    totalPriorVisits: numberValue(payload.totalPriorVisits, 0),
    visitOrdinal: numberValue(payload.visitOrdinal, 1),
    keyFacts: stringOrNull(payload.keyFacts),
  };
}

function normalizeAftercareTemplate(raw: Record<string, unknown>): AftercareTemplate {
  return {
    id: String(raw.id || ""),
    tenantId: stringOrNull(raw.tenantId),
    name: String(raw.name || "Untitled template"),
    procedureType: stringOrNull(raw.procedureType),
    body: String(raw.body || ""),
    isActive: raw.isActive !== false,
    createdAt: stringOrNull(raw.createdAt),
    updatedAt: stringOrNull(raw.updatedAt),
  };
}

/** AES-702 — aftercare templates managed in Settings, attached to a curated share (AES-304). */
export async function listAftercareTemplates(apiFetch: ApiFetch, includeInactive = false): Promise<AftercareTemplate[]> {
  const params = new URLSearchParams();
  if (includeInactive) params.set("includeInactive", "true");
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/aftercare-templates${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load aftercare templates");
  const payload = (await response.json()) as Array<Record<string, unknown>>;
  return (Array.isArray(payload) ? payload : []).map(normalizeAftercareTemplate);
}

export async function createAftercareTemplate(apiFetch: ApiFetch, draft: AftercareTemplateDraft): Promise<AftercareTemplate> {
  const response = await apiFetch(`${API_BASE}/aftercare-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) throw new Error("Could not create aftercare template");
  return normalizeAftercareTemplate((await response.json()) as Record<string, unknown>);
}

export async function updateAftercareTemplate(apiFetch: ApiFetch, id: string, draft: Partial<AftercareTemplateDraft>): Promise<AftercareTemplate> {
  const response = await apiFetch(`${API_BASE}/aftercare-templates/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) throw new Error("Could not update aftercare template");
  return normalizeAftercareTemplate((await response.json()) as Record<string, unknown>);
}

export async function deleteAftercareTemplate(apiFetch: ApiFetch, id: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/aftercare-templates/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not delete aftercare template");
}

function normalizePatientShare(raw: Record<string, unknown>): PatientShare {
  const rawPreview = raw.preview && typeof raw.preview === "object" ? (raw.preview as Record<string, unknown>) : null;
  const rawSections = rawPreview && Array.isArray(rawPreview.sections) ? rawPreview.sections : [];
  const rawMedia = rawPreview && Array.isArray(rawPreview.media) ? rawPreview.media : [];
  const rawAftercare = rawPreview && rawPreview.aftercare && typeof rawPreview.aftercare === "object" ? (rawPreview.aftercare as Record<string, unknown>) : null;
  const rawClinic = rawPreview && rawPreview.clinic && typeof rawPreview.clinic === "object" ? (rawPreview.clinic as Record<string, unknown>) : null;
  return {
    id: String(raw.id || ""),
    patientId: String(raw.patientId || ""),
    sessionId: stringOrNull(raw.sessionId),
    token: String(raw.token || ""),
    publicPath: String(raw.publicPath || ""),
    payloadType: String(raw.payloadType || "report_aftercare"),
    status: String(raw.status || "active"),
    title: String(raw.title || "Patient report"),
    mediaCount: numberValue(raw.mediaCount, 0),
    createdAt: stringOrNull(raw.createdAt),
    updatedAt: stringOrNull(raw.updatedAt),
    expiresAt: stringOrNull(raw.expiresAt),
    revokedAt: stringOrNull(raw.revokedAt),
    preview: rawPreview
      ? {
          payloadType: String(rawPreview.payloadType || "report_aftercare"),
          status: String(rawPreview.status || "active"),
          clinic: { name: String((rawClinic && rawClinic.name) || "Clinic") },
          patientName: String(rawPreview.patientName || ""),
          title: String(rawPreview.title || ""),
          visitDate: stringOrNull(rawPreview.visitDate),
          sections: rawSections
            .filter((section): section is Record<string, unknown> => Boolean(section && typeof section === "object"))
            .map((section) => ({ label: String(section.label || ""), body: String(section.body || "") })),
          media: rawMedia
            .filter((media): media is Record<string, unknown> => Boolean(media && typeof media === "object"))
            .map((media) => ({ captureId: String(media.captureId || ""), caption: stringOrNull(media.caption), url: String(media.url || "") })),
          aftercare: rawAftercare
            ? { templateId: stringOrNull(rawAftercare.templateId), name: String(rawAftercare.name || ""), body: String(rawAftercare.body || "") }
            : null,
          createdAt: stringOrNull(rawPreview.createdAt),
          expiresAt: stringOrNull(rawPreview.expiresAt),
        }
      : null,
  };
}

/** AES-303/304/403/401 — create a curated, revocable clinic→patient share. */
export async function createPatientShare(apiFetch: ApiFetch, input: CreatePatientShareInput): Promise<PatientShare> {
  const response = await apiFetch(`${API_BASE}/patient-shares`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("Could not create patient share");
  return normalizePatientShare((await response.json()) as Record<string, unknown>);
}

export async function listPatientShares(apiFetch: ApiFetch, patientId?: string): Promise<PatientShare[]> {
  const params = new URLSearchParams();
  if (patientId) params.set("patientId", patientId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/patient-shares${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load patient shares");
  const payload = (await response.json()) as Array<Record<string, unknown>>;
  return (Array.isArray(payload) ? payload : []).map(normalizePatientShare);
}

export async function revokePatientShare(apiFetch: ApiFetch, id: string): Promise<PatientShare> {
  const response = await apiFetch(`${API_BASE}/patient-shares/${id}/revoke`, { method: "POST" });
  if (!response.ok) throw new Error("Could not revoke patient share");
  return normalizePatientShare((await response.json()) as Record<string, unknown>);
}

export async function fetchPatientMemory(
  apiFetch: ApiFetch,
  {
    query,
    filter,
    limit = 50,
    offset = 0,
    clinicianId,
  }: {
    query?: string;
    filter: PatientMemoryFilter;
    limit?: number;
    offset?: number;
    /** AES-904 "Mine vs Clinic": the caller's own id → only their patients; omit → whole clinic. */
    clinicianId?: string;
  },
): Promise<PatientMemoryListResponse> {
  const params = new URLSearchParams({ filter, limit: String(limit), offset: String(offset) });
  if (query?.trim()) params.set("query", query.trim());
  if (clinicianId) params.set("clinicianId", clinicianId);
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
    history:
      payload.history && typeof payload.history === "object"
        ? normalizePatientMemoryHistory(payload.history as Record<string, unknown>)
        : null,
    lineupCard:
      payload.lineupCard && typeof payload.lineupCard === "object"
        ? normalizeLineupCard(payload.lineupCard as Record<string, unknown>)
        : null,
  };
}

function normalizeLineupCard(raw: Record<string, unknown>): LineupCard {
  const rawFlags = Array.isArray(raw.flags) ? raw.flags : [];
  const rawHero = raw.hero && typeof raw.hero === "object" ? (raw.hero as Record<string, unknown>) : null;
  return {
    storySoFar: String(raw.storySoFar || ""),
    rightNow: String(raw.rightNow || ""),
    flags: rawFlags
      .filter((flag): flag is Record<string, unknown> => Boolean(flag && typeof flag === "object"))
      .map((flag) => ({ kind: String(flag.kind || "caution"), label: String(flag.label || "") }))
      .filter((flag) => flag.label),
    sinceLastVisit: stringOrNull(raw.sinceLastVisit),
    hero: rawHero
      ? {
          captureId: String(rawHero.captureId || ""),
          fileEndpoint: String(rawHero.fileEndpoint || ""),
          contentEndpoint: String(rawHero.contentEndpoint || ""),
          capturedAt: stringOrNull(rawHero.capturedAt),
          caption: stringOrNull(rawHero.caption),
        }
      : null,
    status: raw.status === "updating" ? "updating" : "ready",
    updatedAt: stringOrNull(raw.updatedAt),
  };
}

function normalizePatientMemoryHistory(raw: Record<string, unknown>): PatientMemoryHistory {
  const rawSections = Array.isArray(raw.sections) ? raw.sections : [];
  const rawVisits = Array.isArray(raw.visits) ? raw.visits : [];
  return {
    mode: raw.mode === "basic" ? "basic" : "pro",
    status: raw.status === "updating" ? "updating" : "ready",
    snapshot: String(raw.snapshot || ""),
    sections: rawSections
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({ label: String(item.label || ""), body: String(item.body || "") })),
    visits: rawVisits.filter((item): item is string => typeof item === "string"),
    source: String(raw.source || ""),
    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : null,
  };
}

export async function createPatient(apiFetch: ApiFetch, draft: PatientAssignmentDraft, idempotencyKey?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  // Persist every demographic field the unified create form collected (B3), not just the name.
  const response = await apiFetch(`${API_BASE}/patients`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      displayName: draft.displayName,
      nationalId: draft.nationalId || null,
      phone: draft.phone || null,
      dateOfBirth: draft.dateOfBirth || null,
      sex: draft.sex || null,
      notes: draft.notes || null,
    }),
  });
  if (!response.ok) throw new Error("Could not create patient");
  return normalizePatientSummary((await response.json()) as Record<string, unknown>);
}

function mapAiModelConfig(payload: Record<string, unknown>): AiModelConfig {
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
  return {
    tasks: tasks
      .filter((task): task is Record<string, unknown> => Boolean(task && typeof task === "object"))
      .map((task) => ({
        task: String(task.task || ""),
        label: String(task.label || task.task || ""),
        model: typeof task.model === "string" ? task.model : "",
      })),
  };
}

export async function fetchAiModels(apiFetch: ApiFetch): Promise<AiModelConfig> {
  const response = await apiFetch(`${API_BASE}/ai-config/models`);
  if (!response.ok) throw new Error("Could not load AI model config");
  return mapAiModelConfig((await response.json()) as Record<string, unknown>);
}

export async function updateAiModels(apiFetch: ApiFetch, models: Record<string, string>): Promise<AiModelConfig> {
  const response = await apiFetch(`${API_BASE}/ai-config/models`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ models }),
  });
  if (!response.ok) throw new Error("Could not update AI model config");
  return mapAiModelConfig((await response.json()) as Record<string, unknown>);
}

export async function updateTenantSettings(
  apiFetch: ApiFetch,
  settings: {
    transcriptionLanguage?: string;
    reportLanguage?: string | null;
    matchStrictness?: string;
    // AES-905 — per non-owner role preset, e.g. { assistant: "reassign" }. Admin-only on the backend.
    rolePermissions?: RolePermissions;
  },
) {
  const response = await apiFetch(`${API_BASE}/tenant/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error("Could not update tenant settings");
  return (await response.json()) as {
    id: string;
    name: string;
    tier?: string;
    transcriptionLanguage?: string;
    reportLanguage?: string | null;
    matchStrictness?: string;
    rolePermissions?: RolePermissions;
  };
}

export interface TeamMember {
  userId: string;
  displayName: string;
  email: string;
  role: string;
  status: string;
  isSelf: boolean;
  isOwner: boolean;
}

export interface CreateMemberInput {
  fullName: string;
  email: string;
  // Required for a brand-new person; omit for an existing Memara account (added across clinics).
  password?: string;
  role: string;
}

export async function fetchTeamMembers(apiFetch: ApiFetch): Promise<TeamMember[]> {
  const response = await apiFetch(`${API_BASE}/clinic/team`);
  if (!response.ok) throw new Error("Could not load members");
  return ((await response.json()) as { items: TeamMember[] }).items;
}

/** Create or attach a clinic member (`created` is false when an existing account was added across
 * clinics). Throws an Error tagged with `.status` so the form can map 409/422. */
export async function createTeamMember(apiFetch: ApiFetch, input: CreateMemberInput): Promise<TeamMember & { created: boolean }> {
  const response = await apiFetch(`${API_BASE}/clinic/team`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const error = new Error("Could not add member") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return (await response.json()) as TeamMember & { created: boolean };
}

/** Switch the clinic plan/tier (basic | pro). Returns the updated tenant profile. */
export async function setClinicPlan(apiFetch: ApiFetch, tier: string): Promise<{ tier: string }> {
  const response = await apiFetch(`${API_BASE}/clinic/plan`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier }),
  });
  if (!response.ok) throw new Error("Could not change plan");
  return (await response.json()) as { tier: string };
}

export async function updateTeamMember(
  apiFetch: ApiFetch,
  userId: string,
  patch: { role?: string; status?: string },
): Promise<TeamMember> {
  const response = await apiFetch(`${API_BASE}/clinic/team/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error("Could not update member");
  return (await response.json()) as TeamMember;
}

// --- E9 multi-seat: clinic directory + worklist (AES-903) ---

const normalizeAttribution = (value: unknown): Attribution | null => {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.userId !== "string") return null;
  return { userId: raw.userId, displayName: typeof raw.displayName === "string" ? raw.displayName : null };
};

/** AES-903 — the clinic's active staff (for the worklist line-up picker). */
export async function fetchClinicMembers(apiFetch: ApiFetch): Promise<ClinicMember[]> {
  const response = await apiFetch(`${API_BASE}/clinic/members`);
  if (!response.ok) throw new Error("Could not load clinic members");
  const payload = (await response.json()) as { items?: Array<Record<string, unknown>> };
  return (Array.isArray(payload.items) ? payload.items : [])
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      userId: String(item.userId || ""),
      displayName: String(item.displayName || "Unnamed"),
      role: String(item.role || ""),
      isClinician: Boolean(item.isClinician),
    }));
}

function normalizeWorklistEntry(raw: Record<string, unknown>): WorklistEntry {
  return {
    id: String(raw.id || ""),
    status: String(raw.status || "waiting"),
    note: stringOrNull(raw.note),
    patientId: String(raw.patientId || ""),
    patientName: stringOrNull(raw.patientName),
    clinicianUserId: String(raw.clinicianUserId || ""),
    clinician: normalizeAttribution(raw.clinician),
    linedUpBy: normalizeAttribution(raw.linedUpBy),
    sessionId: stringOrNull(raw.sessionId),
    createdAt: stringOrNull(raw.createdAt),
    updatedAt: stringOrNull(raw.updatedAt),
    resolvedAt: stringOrNull(raw.resolvedAt),
  };
}

/** AES-903 — a clinician's "Today / up next" worklist (default: the caller's waiting entries). */
export async function fetchWorklist(
  apiFetch: ApiFetch,
  options?: { scope?: "mine" | "clinic"; status?: "waiting" | "seen" | "cancelled" | "all"; clinicianId?: string },
): Promise<WorklistResponse> {
  const params = new URLSearchParams();
  if (options?.scope) params.set("scope", options.scope);
  if (options?.status) params.set("status", options.status);
  if (options?.clinicianId) params.set("clinicianId", options.clinicianId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE}/worklist${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error("Could not load worklist");
  const payload = (await response.json()) as Record<string, unknown>;
  const items = Array.isArray(payload.items) ? payload.items : [];
  return {
    scope: String(payload.scope || options?.scope || "mine"),
    clinicianId: stringOrNull(payload.clinicianId),
    status: String(payload.status || options?.status || "waiting"),
    items: items
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map(normalizeWorklistEntry),
  };
}

/** AES-903 — line a patient up for a clinician. */
export async function createWorklistEntry(
  apiFetch: ApiFetch,
  input: { patientId: string; clinicianUserId: string; note?: string },
): Promise<WorklistEntry> {
  const response = await apiFetch(`${API_BASE}/worklist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("Could not line up patient");
  return normalizeWorklistEntry((await response.json()) as Record<string, unknown>);
}

/** AES-903 — clear a worklist entry as seen (optionally linking the session that was started). */
export async function markWorklistEntrySeen(apiFetch: ApiFetch, entryId: string, sessionId?: string): Promise<WorklistEntry> {
  const response = await apiFetch(`${API_BASE}/worklist/${entryId}/seen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sessionId ? { sessionId } : {}),
  });
  if (!response.ok) throw new Error("Could not update worklist entry");
  return normalizeWorklistEntry((await response.json()) as Record<string, unknown>);
}

/** AES-903 — cancel (remove) a worklist entry. */
export async function cancelWorklistEntry(apiFetch: ApiFetch, entryId: string): Promise<WorklistEntry> {
  const response = await apiFetch(`${API_BASE}/worklist/${entryId}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not cancel worklist entry");
  return normalizeWorklistEntry((await response.json()) as Record<string, unknown>);
}

export async function getPatient(apiFetch: ApiFetch, patientId: string): Promise<StructuredPatientInformation | null> {
  const response = await apiFetch(`${API_BASE}/patients/${patientId}`);
  if (!response.ok) return null;
  const raw = (await response.json()) as Record<string, unknown>;
  const str = (value: unknown) => (typeof value === "string" && value.trim() ? value : null);
  return {
    source: "db",
    status: "assigned",
    patientId: str(raw.id),
    displayName: str(raw.displayName),
    legalFirstName: str(raw.legalFirstName),
    legalLastName: str(raw.legalLastName),
    nationalId: str(raw.nationalId),
    dateOfBirth: str(raw.dateOfBirth),
    sex: str(raw.sex),
    phone: str(raw.phone),
    email: str(raw.email),
    notes: str(raw.notes),
  };
}

export type PatientEditDraft = {
  displayName?: string;
  nationalId?: string | null;
  phone?: string | null;
  dateOfBirth?: string | null;
  sex?: string | null;
  notes?: string | null;
};

export async function updatePatient(apiFetch: ApiFetch, patientId: string, draft: PatientEditDraft) {
  // Partial PATCH: only send keys that were provided, so an untouched field is never
  // overwritten (e.g. editing a phone must not clear an existing national ID).
  const body: Record<string, unknown> = {};
  if (draft.displayName !== undefined) body.displayName = draft.displayName;
  if (draft.nationalId !== undefined) body.nationalId = draft.nationalId;
  if (draft.phone !== undefined) body.phone = draft.phone;
  if (draft.dateOfBirth !== undefined) body.dateOfBirth = draft.dateOfBirth;
  if (draft.sex !== undefined) body.sex = draft.sex;
  if (draft.notes !== undefined) body.notes = draft.notes;
  const response = await apiFetch(`${API_BASE}/patients/${patientId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError("Could not update patient", response.status);
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
  if (!response.ok) throw new ApiError("Could not verify patient creation", response.status);
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

/**
 * Dismiss a stuck AI-created-patient "verify" panel by neutralizing the session's `ai_patient_action`
 * (needsVerification → false). Used by the stale-client self-heal when the referenced patient was
 * deleted/merged out from under the panel — so it stops asking the staff to verify a dead record.
 */
export async function dismissAiPatientAction(apiFetch: ApiFetch, sessionId: string, reason = "patient-unavailable") {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      extractedMetadata: {
        ai_patient_action: {
          status: "stale",
          needsVerification: false,
          dismissedReason: reason,
          dismissedAt: new Date().toISOString(),
        },
      },
    }),
  });
  if (!response.ok) throw new ApiError("Could not dismiss AI patient action", response.status);
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function assignSessionPatient(apiFetch: ApiFetch, sessionId: string, patientId: string, idempotencyKey?: string, basisCaptureId?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assign-patient`, {
    method: "POST",
    headers,
    body: JSON.stringify({ patientId, source: "staff", reason: "Lightweight assignment", basisCaptureId }),
  });
  if (!response.ok) throw new ApiError("Could not assign patient", response.status);
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
  if (!response.ok) throw new ApiError("Could not unassign patient", response.status);
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

/** Q3: confirm a carried-forward dose (by its area|product key) so the Pro report can read Complete. */
export async function confirmCarriedForward(apiFetch: ApiFetch, sessionId: string, key: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/confirm-carried-forward`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  if (!response.ok) throw new Error("Could not confirm carried-forward dose");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

export async function setAftercareDismissed(apiFetch: ApiFetch, sessionId: string, templateId: string, dismissed: boolean) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/aftercare-dismissal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ templateId, dismissed }),
  });
  if (!response.ok) throw new Error("Could not update aftercare");
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

/** Fetch one capture by id (for opening a citation's source capture that isn't in the loaded set). */
export async function fetchCapture(apiFetch: ApiFetch, captureId: string): Promise<CaptureItem | null> {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`);
  if (!response.ok) return null;
  return normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
}

export type FeedbackInput = {
  kind?: "rating" | "correction" | "confirmation";
  aiOutputType?: "report" | "brief" | "transcript" | "caption" | "treatment" | "patient_match";
  rating?: number;
  comment?: string;
  before?: string;
  after?: string;
  sessionId?: string;
  captureId?: string;
  patientId?: string;
  context?: Record<string, unknown>;
};

/**
 * Send an AI-quality signal (eval golden-set harvester; eval-epic §1b). Fire-and-forget: a rating is
 * a nice-to-have, never part of the clinical flow, so failures are swallowed and never surfaced.
 * Staff *corrections* (transcript/caption/treatment/patient-match) are harvested server-side; this is
 * the lightweight report/brief thumbs rating.
 */
export async function postFeedback(apiFetch: ApiFetch, input: FeedbackInput): Promise<void> {
  try {
    await apiFetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  } catch {
    // Feedback instrumentation must never disrupt the user.
  }
}

export async function updateCaptureNote(apiFetch: ApiFetch, captureId: string, text: string) {
  // Basic note body edit — stored as a staff-edited note field (no AI involved).
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metadata: { note: { text, source: "staff_edit", updated_at: new Date().toISOString() } },
    }),
  });
  if (!response.ok) throw new Error("Could not update note");
  return normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
}

export async function markCaptureRelevant(apiFetch: ApiFetch, captureId: string) {
  // Clears the AI out-of-context marker (the backend records the staff override and
  // re-folds the capture into the Pro live report).
  const response = await apiFetch(`${API_BASE}/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metadata: { out_of_context: { present: false } } }),
  });
  if (!response.ok) throw new Error("Could not update capture relevance");
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
    memoryStatus: raw.memoryStatus === "updating" ? "updating" : "ready",
    memoryUpdatedAt: typeof raw.memoryUpdatedAt === "string" ? raw.memoryUpdatedAt : null,
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
    complete: Boolean(raw.complete),
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
    complete: Boolean(raw.complete),
    needsInput: Boolean(raw.needsInput),
    createdByUserId: stringOrNull(raw.createdByUserId),
    createdBy: normalizeAttribution(raw.createdBy),
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
