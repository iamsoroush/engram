import React from "react";
import { flushSync } from "react-dom";
import { Badge, Button, Card, Dialog, Input, Sheet, Skeleton, Textarea, Toast } from "./ui";
import type { CaptureItem, CaptureItemType, CaptureSession, CaptureStatus, Patient, Screen, SessionStatus } from "./types";

const statusCopy: Record<CaptureStatus, string> = {
  saved: "Saved on device",
  syncing: "Syncing",
  uploaded: "Uploaded",
  processing: "Processing",
  processed: "Processed",
  needsReview: "Needs review",
  failed: "Failed/Retry",
};

const statusTone: Record<CaptureStatus, "neutral" | "blue" | "green" | "amber" | "red"> = {
  saved: "neutral",
  syncing: "blue",
  uploaded: "blue",
  processing: "amber",
  processed: "green",
  needsReview: "amber",
  failed: "red",
};

const configuredApiBase = import.meta.env.VITE_API_URL || "/api/v1";
const API_BASE =
  typeof window !== "undefined" && window.location.hostname !== "localhost" && configuredApiBase.includes("localhost")
    ? "/api/v1"
    : configuredApiBase;

type CaptureDraft = {
  kind: Extract<CaptureItemType, "audio" | "photo" | "note">;
  detail?: string;
  file: Blob;
  filename: string;
  metadata?: Record<string, unknown>;
};

type PendingCapture = {
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

type Persona = "doctor" | "assistant" | "admin" | "patient-preview";

type AuthUser = {
  id: string;
  email: string;
  displayName: string | null;
  persona?: Persona | string | null;
};

type AuthTenant = {
  id: string;
  name: string;
};

type AuthMembership = {
  tenantId: string;
  role: string;
};

type AuthSession = {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
  tenant: AuthTenant;
  memberships: AuthMembership[];
};

type StoredAuthProfile = Pick<AuthSession, "refreshToken" | "user" | "tenant" | "memberships">;

type ApiFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

type PatientAssignmentTarget = {
  patientId: string | null;
  patientName?: string;
  source?: "staff" | "fake_processing" | "fake-processing" | string;
};

type CachedCapture = {
  id: string;
  blob: Blob;
  sourceName: string;
  contentType: string;
  size: number;
  createdAt: number;
  lastAccessedAt: number;
};

type IdMapping = {
  id: string;
  kind: "capture" | "session";
  localId: string;
  backendId: string;
  tenantId: string;
  createdAt: number;
};

const OUTBOX_DB = "aesmem-capture-outbox";
const OUTBOX_STORE = "pendingCaptures";
const CACHE_STORE = "cachedCaptures";
const ID_MAPPING_STORE = "idMappings";
const CACHE_LIMIT_BYTES = 50 * 1024 * 1024;
const DEV_AUTH_STORAGE_KEY = "aesmem-dev-auth";
const IS_DEV = import.meta.env.DEV;

function screenFromLocation(): Screen {
  if (typeof window !== "undefined" && window.location.hash === "#organize") return "organize";
  return "capture";
}

function replaceScreenLocation(screen: Screen) {
  if (typeof window === "undefined" || (screen !== "capture" && screen !== "organize")) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${screen}`);
}

const nowLabel = () =>
  new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());

function createClientId() {
  const browserCrypto = globalThis.crypto;
  if (browserCrypto?.randomUUID) return browserCrypto.randomUUID();
  if (!browserCrypto?.getRandomValues) return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  const bytes = new Uint8Array(16);
  browserCrypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

const titleByType: Record<CaptureDraft["kind"], string> = {
  audio: "Audio note",
  photo: "Photo",
  note: "Written note",
};

const detailByType: Record<CaptureDraft["kind"], string> = {
  audio: "Clinical audio saved on this device. Waiting for safe transfer.",
  photo: "Clinical photo saved on this device. Waiting for safe transfer.",
  note: "Typed note saved on this device. Waiting for safe transfer.",
};

const sessionStatusCopy: Record<SessionStatus, string> = {
  unassigned: "Unassigned",
  needs_review: "Needs review",
  processing: "Processing",
  organized: "Organized",
  reviewing: "In review",
  verified: "Verified",
  reopened: "Reopened",
  failed: "Failed/Retry",
  current: "Current session",
  matched: "Matched",
};

const sessionStatusTone: Record<SessionStatus, "neutral" | "blue" | "green" | "amber" | "red"> = {
  unassigned: "neutral",
  needs_review: "amber",
  processing: "blue",
  organized: "blue",
  reviewing: "amber",
  verified: "green",
  reopened: "amber",
  failed: "red",
  current: "blue",
  matched: "green",
};

const sessionStatusFromApi = (status?: string): CaptureSession["status"] => {
  if (
    status === "unassigned" ||
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

const captureStatusFromApi = (status?: string): CaptureItem["status"] => {
  if (status === "received") return "uploaded";
  if (status === "processed") return "processed";
  if (status === "processing") return "processing";
  if (status === "needs_attention") return "needsReview";
  if (status === "deleted") return "missing";
  return "ready";
};

function formatApiTime(value?: string | null) {
  if (!value) return nowLabel();
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function normalizeApiCaptureItem(raw: Partial<CaptureItem> & Record<string, unknown>): CaptureItem {
  const metadata = raw.metadata && typeof raw.metadata === "object" ? (raw.metadata as Record<string, unknown>) : {};
  const sourceName = typeof metadata.original_filename === "string" ? metadata.original_filename : raw.sourceName;
  const contentType = typeof metadata.content_type === "string" ? metadata.content_type : raw.contentType;
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
    sourceName: sourceName || "capture",
    status: raw.status ? captureStatusFromApi(String(raw.status)) : "uploaded",
    contentType: contentType || raw.mimeType,
    sourceUrl: typeof raw.sourceUrl === "string" ? raw.sourceUrl : undefined,
    fileEndpoint: typeof raw.fileEndpoint === "string" ? raw.fileEndpoint : undefined,
    patientId: typeof raw.patientId === "string" ? raw.patientId : null,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource,
    metadata,
  };
}

function normalizeApiSession(raw: Partial<CaptureSession> & Record<string, unknown>): CaptureSession {
  const status = sessionStatusFromApi(typeof raw.status === "string" ? raw.status : undefined);
  const capturedAt = typeof raw.capturedAt === "string" ? raw.capturedAt : typeof raw.createdAt === "string" ? raw.createdAt : null;
  const time = raw.time || formatApiTime(capturedAt);
  const items = Array.isArray(raw.items) ? raw.items.map((item) => normalizeApiCaptureItem(item as Record<string, unknown>)) : [];
  return {
    id: String(raw.id),
    label: raw.label || (typeof raw.title === "string" && raw.title ? raw.title : `${time} - Capture session`),
    time,
    dateLabel: raw.dateLabel || "Today",
    duration: raw.duration || "saved",
    summary:
      raw.summary ||
      (typeof raw.generatedSummary === "string" && raw.generatedSummary ? raw.generatedSummary : "Captured material saved to the backend."),
    status,
    items,
    patientId: typeof raw.patientId === "string" ? raw.patientId : raw.patientId ?? undefined,
    patientName: typeof raw.patientName === "string" ? raw.patientName : undefined,
    assignmentSource:
      typeof raw.assignmentSource === "string"
        ? raw.assignmentSource
        : typeof raw.organizationSource === "string" && raw.organizationSource === "fake-processing" && raw.patientId
          ? "fake-processing"
          : undefined,
    organizationSource: typeof raw.organizationSource === "string" ? raw.organizationSource : null,
    reviewReason:
      raw.reviewReason ||
      (status === "organized"
        ? "Organized output, not yet verified"
        : status === "verified"
          ? "Human reviewed"
          : "Ready for review"),
  };
}

function normalizePatient(raw: Record<string, unknown>): Patient {
  return {
    id: String(raw.id),
    displayName: String(raw.displayName || "Unnamed patient"),
    dateOfBirth: typeof raw.dateOfBirth === "string" ? raw.dateOfBirth : null,
    phone: typeof raw.phone === "string" ? raw.phone : null,
    email: typeof raw.email === "string" ? raw.email : null,
  };
}

function normalizeUploadResult(raw: { session: Record<string, unknown>; item: Record<string, unknown> }) {
  const item = normalizeApiCaptureItem(raw.item);
  const session = normalizeApiSession(raw.session);
  return { session: { ...session, items: [...session.items.filter((current) => current.id !== item.id), item] }, item };
}

function mergeSessionItems(existing: CaptureSession | null | undefined, incoming: CaptureSession, replaceLocalItemId?: string) {
  const incomingItems = incoming.items;
  if (!existing?.items.length) return { ...incoming, items: incomingItems };

  const replacements = new Map<string, CaptureItem>();
  incomingItems.forEach((item) => replacements.set(item.id, item));
  const replacementItem = incomingItems[0];
  const merged = existing.items.map((item) => {
    if (replaceLocalItemId && item.id === replaceLocalItemId && replacementItem) {
      return {
        ...replacementItem,
        sourceUrl: item.sourceUrl || replacementItem.sourceUrl,
        contentType: item.contentType || replacementItem.contentType,
      };
    }
    return replacements.get(item.id) || item;
  });
  incomingItems.forEach((item) => {
    if (!merged.some((current) => current.id === item.id)) merged.push(item);
  });
  return { ...incoming, items: merged };
}

function mergeCaptureItemsPreservingPreview(existingItems: CaptureItem[], incomingItems: CaptureItem[]) {
  return incomingItems.map((incomingItem) => {
    const existingItem = existingItems.find((item) => item.id === incomingItem.id);
    if (!existingItem?.sourceUrl) return incomingItem;
    return {
      ...incomingItem,
      sourceUrl: existingItem.sourceUrl,
      contentType: existingItem.contentType || incomingItem.contentType,
    };
  });
}

function openOutboxDb() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(OUTBOX_DB, 3);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OUTBOX_STORE)) db.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(CACHE_STORE)) db.createObjectStore(CACHE_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(ID_MAPPING_STORE)) db.createObjectStore(ID_MAPPING_STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function dbTransaction<T>(
  storeName: typeof OUTBOX_STORE | typeof CACHE_STORE | typeof ID_MAPPING_STORE,
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
) {
  const db = await openOutboxDb();
  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const request = run(transaction.objectStore(storeName));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

const outboxTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(OUTBOX_STORE, mode, run);

const cacheTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(CACHE_STORE, mode, run);

const idMappingTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(ID_MAPPING_STORE, mode, run);

const savePendingCapture = (capture: PendingCapture) => outboxTransaction("readwrite", (store) => store.put(capture));

const removePendingCapture = (id: string) => outboxTransaction("readwrite", (store) => store.delete(id));

const saveIdMapping = (mapping: IdMapping) => idMappingTransaction("readwrite", (store) => store.put(mapping));

const loadPendingCaptures = () =>
  outboxTransaction<PendingCapture[]>("readonly", (store) => store.getAll()).then((captures) =>
    captures.map(normalizePendingCapture).sort((a, b) => a.createdAt - b.createdAt),
  );

const loadPendingCapture = (id: string) =>
  outboxTransaction<PendingCapture | undefined>("readonly", (store) => store.get(id)).then((capture) =>
    capture ? normalizePendingCapture(capture) : undefined,
  );

const loadCachedCaptures = () => cacheTransaction<CachedCapture[]>("readonly", (store) => store.getAll());

async function getCachedCapture(id: string) {
  const cached = await cacheTransaction<CachedCapture | undefined>("readonly", (store) => store.get(id));
  if (cached) void cacheTransaction("readwrite", (store) => store.put({ ...cached, lastAccessedAt: Date.now() }));
  return cached;
}

async function enforceCacheLimit() {
  const cachedCaptures = await loadCachedCaptures();
  let total = cachedCaptures.reduce((sum, capture) => sum + capture.size, 0);
  const oldestFirst = [...cachedCaptures].sort((a, b) => a.lastAccessedAt - b.lastAccessedAt || a.createdAt - b.createdAt);

  for (const capture of oldestFirst) {
    if (total <= CACHE_LIMIT_BYTES) break;
    await cacheTransaction("readwrite", (store) => store.delete(capture.id));
    total -= capture.size;
  }
}

async function saveSyncedCaptureCache(item: CaptureItem, blob: Blob) {
  await cacheTransaction("readwrite", (store) =>
    store.put({
      id: item.id,
      blob,
      sourceName: item.sourceName,
      contentType: item.contentType || blob.type || "application/octet-stream",
      size: blob.size,
      createdAt: Date.now(),
      lastAccessedAt: Date.now(),
    } satisfies CachedCapture),
  );
  await enforceCacheLimit();
}

async function updatePendingCapture(id: string, update: (capture: PendingCapture) => PendingCapture) {
  const db = await openOutboxDb();
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(OUTBOX_STORE, "readwrite");
    const store = transaction.objectStore(OUTBOX_STORE);
    const getRequest = store.get(id);
    getRequest.onsuccess = () => {
      if (!getRequest.result) return;
      store.put(update(getRequest.result as PendingCapture));
    };
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

async function bindPendingSession(localSessionId: string, sessionId: string) {
  const captures = await loadPendingCaptures();
  await Promise.all(
    captures
      .filter((capture) => capture.localSessionId === localSessionId)
      .map((capture) =>
        updatePendingCapture(capture.id, (current) => ({
          ...current,
          sessionId,
          backendSessionId: sessionId,
          intoNew: false,
        })),
      ),
  );
}

function normalizePendingCapture(capture: PendingCapture) {
  return {
    ...capture,
    localCaptureId: capture.localCaptureId || capture.id,
    clientCaptureId: capture.clientCaptureId || capture.id,
    backendSessionId: capture.backendSessionId || capture.sessionId,
  };
}

function isLocalSessionId(sessionId: string) {
  return sessionId.startsWith("local-session-");
}

function backendSessionIdFromCurrent(currentSession: CaptureSession | null, intoNew: boolean) {
  if (intoNew || !currentSession || isLocalSessionId(currentSession.id)) return undefined;
  return currentSession.id;
}

function withoutLocalPreview(item: CaptureItem) {
  const { sourceUrl, ...rest } = item;
  return sourceUrl?.startsWith("blob:") ? rest : item;
}

function makeLocalCapture(
  draft: CaptureDraft,
  currentSession: CaptureSession | null,
  intoNew: boolean,
  tenantId?: string,
): PendingCapture {
  const time = nowLabel();
  const localCaptureId = `local-capture-${createClientId()}`;
  const clientCaptureId = `client-capture-${createClientId()}`;
  const backendSessionId = backendSessionIdFromCurrent(currentSession, intoNew);
  const localSessionId = intoNew || !currentSession ? `local-session-${createClientId()}` : currentSession.id;
  const item: CaptureItem = {
    id: localCaptureId,
    type: draft.kind,
    title: titleByType[draft.kind],
    detail: draft.detail || detailByType[draft.kind],
    time,
    sourceName: draft.filename,
    status: "saved",
    contentType: draft.file.type || "application/octet-stream",
  };
  const session: CaptureSession =
    !intoNew && currentSession
      ? {
          ...currentSession,
          items: [...currentSession.items.map(withoutLocalPreview), item],
        }
      : {
          id: localSessionId,
          label: `Session ${time}`,
          time,
          dateLabel: "Today",
          duration: "just now",
          summary: "Saved on this device. Waiting for safe transfer.",
          status: "needs_review",
          reviewReason: "Not synced yet",
          items: [item],
        };

  return {
    id: localCaptureId,
    localCaptureId,
    localSessionId,
    clientCaptureId,
    sessionId: backendSessionId,
    backendSessionId,
    tenantId,
    intoNew: intoNew || !currentSession,
    retryCount: 0,
    createdAt: Date.now(),
    draft,
    item,
    session,
  };
}

function sessionWithLocalPreview(session: CaptureSession, itemId: string, file: Blob) {
  const sourceUrl = URL.createObjectURL(file);
  return {
    ...session,
    items: session.items.map((item) => (item.id === itemId ? { ...item, sourceUrl } : item)),
  };
}

function sessionsFromPending(captures: PendingCapture[]) {
  const grouped = new Map<string, CaptureSession>();
  captures.forEach((capture) => {
    const existing = grouped.get(capture.localSessionId);
    const item = {
      ...capture.item,
      status: capture.retryCount > 0 ? ("failed" as const) : capture.item.status,
      sourceUrl: URL.createObjectURL(capture.draft.file),
    };
    grouped.set(
      capture.localSessionId,
      existing
        ? { ...existing, items: [...existing.items, item] }
        : { ...capture.session, id: capture.localSessionId, items: [item] },
    );
  });
  return Array.from(grouped.values());
}

function persistAuthProfile(auth: AuthSession) {
  if (!IS_DEV) return;
  const profile: StoredAuthProfile = {
    refreshToken: auth.refreshToken,
    user: auth.user,
    tenant: auth.tenant,
    memberships: auth.memberships,
  };
  window.localStorage.setItem(DEV_AUTH_STORAGE_KEY, JSON.stringify(profile));
}

function loadStoredAuthProfile() {
  if (!IS_DEV) return null;
  try {
    const raw = window.localStorage.getItem(DEV_AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuthProfile) : null;
  } catch {
    window.localStorage.removeItem(DEV_AUTH_STORAGE_KEY);
    return null;
  }
}

function clearStoredAuthProfile() {
  window.localStorage.removeItem(DEV_AUTH_STORAGE_KEY);
}

async function loginWithPersona(persona: Persona) {
  const response = await fetch(`${API_BASE}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as AuthSession;
}

async function loginWithPassword(email: string, password: string) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new Error("Login failed");
  return (await response.json()) as AuthSession;
}

async function refreshAuthToken(refreshToken: string) {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  if (!response.ok) throw new Error("Refresh failed");
  return (await response.json()) as Pick<AuthSession, "accessToken" | "refreshToken">;
}

async function logoutSession(accessToken: string, refreshToken: string) {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
}

async function fetchSessions(apiFetch: ApiFetch) {
  const response = await apiFetch(`${API_BASE}/sessions`);
  if (!response.ok) throw new Error("Could not load sessions");
  const sessions = (await response.json()) as Array<Record<string, unknown>>;
  return sessions.map(normalizeApiSession);
}

async function uploadCapture(apiFetch: ApiFetch, clientCaptureId: string, draft: CaptureDraft, sessionId?: string, intoNew = false) {
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

async function storeBackendMappings(capture: PendingCapture, result: { session: CaptureSession; item: CaptureItem }, tenantId: string) {
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

async function markSessionOrganized(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/organize`, { method: "PATCH" });
  if (!response.ok) throw new Error("Could not organize session");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

async function updateSessionTitle(apiFetch: ApiFetch, sessionId: string, title: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error("Could not update session title");
  return normalizeApiSession((await response.json()) as Record<string, unknown>);
}

async function fetchSessionCaptures(apiFetch: ApiFetch, sessionId: string) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/captures`);
  if (!response.ok) throw new Error("Could not load captures");
  const captures = (await response.json()) as Array<Record<string, unknown>>;
  return captures.map(normalizeApiCaptureItem);
}

async function searchPatients(apiFetch: ApiFetch, query: string) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const response = await apiFetch(`${API_BASE}/patients?${params.toString()}`);
  if (!response.ok) throw new Error("Could not search patients");
  const patients = (await response.json()) as Array<Record<string, unknown>>;
  return patients.map(normalizePatient);
}

async function createPatient(apiFetch: ApiFetch, displayName: string) {
  const response = await apiFetch(`${API_BASE}/patients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName }),
  });
  if (!response.ok) throw new Error("Could not create patient");
  return normalizePatient((await response.json()) as Record<string, unknown>);
}

async function assignSessionPatient(apiFetch: ApiFetch, sessionId: string, target: PatientAssignmentTarget) {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/assign-patient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId: target.patientId, source: target.source || "staff" }),
  });
  if (!response.ok) throw new Error("Could not assign patient");
  const session = normalizeApiSession((await response.json()) as Record<string, unknown>);
  return { ...session, patientName: target.patientName, assignmentSource: target.source || "staff" };
}

async function assignCapturePatient(apiFetch: ApiFetch, captureId: string, target: PatientAssignmentTarget) {
  const response = await apiFetch(`${API_BASE}/captures/${captureId}/assign-patient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patientId: target.patientId, source: target.source || "staff" }),
  });
  if (!response.ok) throw new Error("Could not assign capture");
  const item = normalizeApiCaptureItem((await response.json()) as Record<string, unknown>);
  return { ...item, patientName: target.patientName, assignmentSource: target.source || "staff" };
}

async function resolveCaptureFileUrl(apiFetch: ApiFetch, endpoint: string) {
  const contentEndpoint = endpoint.endsWith("/file") ? endpoint.replace(/\/file$/, "/file-content") : endpoint;
  const response = await apiFetch(contentEndpoint);
  if (!response.ok) throw new Error("Could not load source file");
  return URL.createObjectURL(await response.blob());
}

function StatusBadge({ status }: { status?: CaptureItem["status"] }) {
  const normalized: CaptureStatus =
    status === "syncing" ||
    status === "uploaded" ||
    status === "processing" ||
    status === "processed" ||
    status === "needsReview" ||
    status === "failed"
      ? status
      : "saved";
  return <Badge tone={statusTone[normalized]}>{statusCopy[normalized]}</Badge>;
}

function SessionStatusBadge({ status }: { status: SessionStatus }) {
  return <Badge tone={sessionStatusTone[status]}>{sessionStatusCopy[status]}</Badge>;
}

function assignmentSourceLabel(source?: string | null) {
  if (source === "staff") return "Assigned by staff";
  if (source === "fake_processing" || source === "fake-processing") return "Suggested by fake processing";
  return source ? `Assigned by ${source}` : "";
}

function metadataRecord(value: unknown) {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function metadataText(value: unknown) {
  return typeof value === "string" && value.trim() ? value : "";
}

function metadataDisplay(value: unknown) {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

function audioExtensionForMimeType(mimeType: string) {
  if (mimeType.includes("mp4") || mimeType.includes("mpeg") || mimeType.includes("aac")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

function isSafariBrowser() {
  return /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
}

function preferredAudioRecorderOptions() {
  const mimeTypes = isSafariBrowser()
    ? ["audio/mp4", "audio/mp4;codecs=mp4a.40.2", "audio/aac"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  const mimeType = mimeTypes.find((type) => MediaRecorder.isTypeSupported(type));
  return mimeType ? { mimeType } : undefined;
}

function writeAscii(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

function encodeWavPcm16Mono(audioBuffer: AudioBuffer, sampleRate = 16000) {
  const samples = audioBuffer.getChannelData(0);
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function standardizeAudioBlob(blob: Blob) {
  const AudioContextClass =
    window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass || !window.OfflineAudioContext) throw new Error("Audio conversion is not available");
  const context = new AudioContextClass();
  try {
    const sourceBuffer = await context.decodeAudioData(await blob.arrayBuffer());
    const sampleRate = 16000;
    const length = Math.max(1, Math.ceil(sourceBuffer.duration * sampleRate));
    const offline = new OfflineAudioContext(1, length, sampleRate);
    const source = offline.createBufferSource();
    source.buffer = sourceBuffer;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return { blob: encodeWavPcm16Mono(rendered, sampleRate), duration: rendered.duration };
  } finally {
    void context.close();
  }
}

async function standardizeCaptureDraft(draft: CaptureDraft): Promise<CaptureDraft> {
  if (draft.kind !== "audio") return draft;
  const standardized = await standardizeAudioBlob(draft.file);
  return {
    ...draft,
    file: standardized.blob,
    filename: `audio-${Date.now()}.wav`,
    metadata: {
      ...draft.metadata,
      original_audio_filename: draft.filename,
      original_audio_content_type: draft.file.type || "application/octet-stream",
      content_type: "audio/wav",
      codec: "pcm_s16le",
      sample_rate: 16000,
      channels: 1,
      duration: Number(standardized.duration.toFixed(2)),
    },
  };
}

function generatedMetadataFor(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  if (item.type === "audio" || item.type === "voice") return metadataRecord(metadata.transcript);
  if (item.type === "photo") return metadataRecord(metadata.caption || metadata.ocr);
  return metadataRecord(metadata.decorated_text || metadata.normalized_note);
}

function isGeneratedMetadata(metadata: Record<string, unknown>) {
  return Boolean(metadata.generated_by || metadata.generatedBy || metadata.fake_job_id || metadata.fakeJobId || metadata.artifact_id);
}

function captureGeneratedLabel(item: CaptureItem) {
  if (item.type === "audio" || item.type === "voice") return "Transcription";
  if (item.type === "photo") return "Caption";
  return "Decorated text";
}

function captureGeneratedFallback(item: CaptureItem) {
  if (item.status === "saved" || item.status === "syncing" || item.status === "failed") {
    return "Waiting for safe transfer before processing starts.";
  }
  if (item.status === "processing") return "Processing. Placeholder output is expected after about 5 seconds.";
  if (item.type === "audio" || item.type === "voice") return "Transcript placeholder will appear here.";
  if (item.type === "photo") return "Caption placeholder will appear here.";
  return "Decorated text placeholder will appear here.";
}

function CaptureGeneratedDetails({ item }: { item: CaptureItem }) {
  const generated = generatedMetadataFor(item);
  const text = metadataText(generated.text);
  const isReady = metadataDisplay(generated.status) === "completed" || Boolean(text);
  return (
    <details className={`capture-generated ${isReady ? "" : "processing"}`}>
      <summary>
        <span>{captureGeneratedLabel(item)}</span>
        {isReady ? null : <span className="capture-processing-indicator" aria-label="Processing" />}
      </summary>
      <p>{text || captureGeneratedFallback(item)}</p>
    </details>
  );
}

function CaptureMetadataSummary({ item }: { item: CaptureItem }) {
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedLabel = isGeneratedMetadata(generated) ? "Fake/generated - not verified" : "";
  const rows: Array<{ label: string; value: string }> = [];

  if (item.type === "audio" || item.type === "voice") {
    rows.push(
      { label: "Transcript status", value: metadataDisplay(generated.status || metadata.transcript_status) },
      { label: "Language", value: metadataDisplay(generated.language || metadata.language) },
      { label: "Duration", value: metadataDisplay(generated.duration || metadata.duration) },
    );
  } else if (item.type === "photo") {
    const width = metadataDisplay(generated.width || metadata.width);
    const height = metadataDisplay(generated.height || metadata.height);
    rows.push(
      { label: "Caption status", value: metadataDisplay(generated.status || metadata.caption_status || metadata.ocr_status) },
      { label: "Dimensions", value: width && height ? `${width} x ${height}` : "" },
      { label: "Thumbnail", value: metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl) },
    );
  } else {
    rows.push(
      { label: "Extraction status", value: metadataDisplay(generated.status || metadata.extraction_status) },
    );
  }

  const visibleRows = rows.filter((row) => row.value);
  if (!visibleRows.length && !generatedLabel) return null;

  return (
    <div className="capture-metadata">
      {generatedLabel ? <Badge tone="amber">{generatedLabel}</Badge> : null}
      {visibleRows.map((row) => (
        <div key={row.label}>
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function Shell({
  screen,
  children,
  onNavigate,
  onCapture,
  auth,
  onLogout,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  auth: AuthSession;
  onLogout: () => void;
}) {
  const displayName = auth.user.displayName || auth.user.email;
  const role = auth.memberships[0]?.role || auth.user.persona || "user";

  return (
    <main className="phone-shell">
      <header className="topbar">
        <div className="topbar-left">
          <strong>AesMem</strong>
          <nav className="top-nav" aria-label="Primary">
            <button className={screen === "capture" ? "active" : ""} onClick={() => onNavigate("capture")} type="button">
              Capture
            </button>
            <button className={screen !== "capture" ? "active" : ""} onClick={() => onNavigate("organize")} type="button">
              Organize
            </button>
          </nav>
        </div>
        <details className="user-menu">
          <summary>{displayName}</summary>
          <div className="user-menu-panel">
            <div>
              <span>Profile</span>
              <strong>{displayName}</strong>
              <span>{role} - {auth.tenant.name}</span>
            </div>
            <Button onClick={onLogout} size="sm" variant="secondary">
              Logout
            </Button>
          </div>
        </details>
      </header>
      {children}
      <CaptureActions compact onAction={onCapture} />
      <footer className="app-version">MVP v2</footer>
    </main>
  );
}

function SyncSafetyBanner({
  pendingCount,
  syncing,
  onRetry,
}: {
  pendingCount: number;
  syncing: boolean;
  onRetry: () => void;
}) {
  if (!pendingCount) return null;

  return (
    <Card className="sync-warning">
      <div>
        <strong>{pendingCount} capture{pendingCount === 1 ? "" : "s"} saved on this device</strong>
        <p>Keep this browser data until transfer is complete. Closing or clearing site data could lose unsynced captures.</p>
      </div>
      <Button disabled={syncing} onClick={onRetry} size="sm" variant="secondary">
        {syncing ? "Syncing" : "Retry now"}
      </Button>
    </Card>
  );
}

function LoginGate({
  error,
  pendingCount,
  onLogin,
  onPersonaLogin,
}: {
  error: string;
  pendingCount: number;
  onLogin: (email: string, password: string) => Promise<void>;
  onPersonaLogin: (persona: Persona) => Promise<void>;
}) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busyPersona, setBusyPersona] = React.useState<Persona | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const personas: Array<{ value: Persona; label: string }> = [
    { value: "doctor", label: "Doctor" },
    { value: "assistant", label: "Assistant" },
    { value: "admin", label: "Admin" },
    { value: "patient-preview", label: "Patient preview" },
  ];

  const submitLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onLogin(email, password);
    } finally {
      setSubmitting(false);
    }
  };

  const loginPersona = async (persona: Persona) => {
    setBusyPersona(persona);
    try {
      await onPersonaLogin(persona);
    } finally {
      setBusyPersona(null);
    }
  };

  return (
    <main className="login-shell">
      <Card className="login-card">
        <div className="stack">
          <p className="eyebrow">AesMem</p>
          <h1>Sign in to continue</h1>
          <p>Capture opens after an authenticated tenant session is ready.</p>
        </div>
        {pendingCount ? (
          <div className="alert alert-amber">
            {pendingCount} capture{pendingCount === 1 ? "" : "s"} saved on this device. Sign in to resume sync.
          </div>
        ) : null}
        {IS_DEV ? (
          <div className="persona-grid" aria-label="Development personas">
            {personas.map((persona) => (
              <Button
                disabled={busyPersona !== null}
                key={persona.value}
                onClick={() => void loginPersona(persona.value)}
                type="button"
                variant={persona.value === "patient-preview" ? "secondary" : "default"}
              >
                {busyPersona === persona.value ? "Signing in..." : persona.label}
              </Button>
            ))}
          </div>
        ) : (
          <form className="stack" onSubmit={submitLogin}>
            <label className="field-label">
              Email
              <Input autoComplete="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
            </label>
            <label className="field-label">
              Password
              <Input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <Button disabled={submitting} type="submit">
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        )}
        {error ? <div className="alert alert-red">{error}</div> : null}
      </Card>
    </main>
  );
}

function PatientPreviewGate({ auth, onLogout }: { auth: AuthSession; onLogout: () => void }) {
  return (
    <main className="login-shell">
      <Card className="login-card">
        <div className="stack">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Patient preview</p>
              <h1>Limited access</h1>
            </div>
            <Badge tone="neutral">{auth.tenant.name}</Badge>
          </div>
          <p>
            {auth.user.displayName || auth.user.email} is signed in for patient preview only. Staff capture and review tools are not available in
            this mode.
          </p>
        </div>
        <Button onClick={onLogout} variant="secondary">
          Logout
        </Button>
      </Card>
    </main>
  );
}

function CaptureActions({ compact, onAction }: { compact?: boolean; onAction: (kind: CaptureDraft["kind"]) => void }) {
  return (
    <div className={compact ? "capture-pills" : "capture-actions"}>
      <Button onClick={() => onAction("audio")} size={compact ? "sm" : "lg"}>
        Record audio
      </Button>
      <Button onClick={() => onAction("photo")} size={compact ? "sm" : "lg"} variant={compact ? "secondary" : "default"}>
        Take photo
      </Button>
      <Button onClick={() => onAction("note")} size={compact ? "sm" : "lg"} variant={compact ? "secondary" : "default"}>
        Write note
      </Button>
    </div>
  );
}

function CaptureRawPreview({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const metadata = metadataRecord(item.metadata);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);
  const isAudio = item.type === "audio" || item.type === "voice";

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setNoteText("");
    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);
    return () => {
      revoked = true;
    };
  }, [item]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    const endpoint =
      item.fileEndpoint || (item.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");
    if (!endpoint) return;
    onResolveFile(endpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [item, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url || "";

  if (item.type === "note") {
    return <p className="capture-raw-text">{noteText || item.detail}</p>;
  }

  if (item.type === "photo") {
    return sourceUrl || thumbnail ? (
      <img alt={item.sourceName} className="capture-raw-photo" src={sourceUrl || thumbnail} />
    ) : (
      <div className="capture-raw-placeholder">Photo preview unavailable</div>
    );
  }

  if (isAudio) {
    return sourceUrl ? (
      <audio className="capture-raw-audio" controls src={sourceUrl} />
    ) : (
      <div className="capture-raw-placeholder">Audio preview unavailable</div>
    );
  }

  return null;
}

function CaptureItemCard({
  item,
  onOpen,
  onResolveFile,
}: {
  item: CaptureItem;
  onOpen?: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  return (
    <Card className="v2-capture-item">
      <div className="capture-card-header">
        <button className="capture-title-button" onClick={onOpen} type="button">
          <span>
            <h3>{item.title}</h3>
            <small>{item.time}</small>
          </span>
        </button>
        <StatusBadge status={item.status} />
      </div>
      <div
        className="capture-card-body"
        onClick={isAudio ? undefined : onOpen}
        onKeyDown={(event) => {
          if (!onOpen || isAudio || (event.key !== "Enter" && event.key !== " ")) return;
          event.preventDefault();
          onOpen();
        }}
        role={onOpen && !isAudio ? "button" : undefined}
        tabIndex={onOpen && !isAudio ? 0 : undefined}
      >
        <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
      </div>
      <CaptureGeneratedDetails item={item} />
    </Card>
  );
}

function CaptureScreen({
  activeSession,
  onCapture,
  onNewSession,
  onResolveFile,
  onUpdateTitle,
}: {
  activeSession: CaptureSession | null;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  onNewSession: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [titleDraft, setTitleDraft] = React.useState(activeSession?.label || "");
  const [editingTitle, setEditingTitle] = React.useState(false);
  const [savingTitle, setSavingTitle] = React.useState(false);
  const latestCaptureRef = React.useRef<HTMLDivElement | null>(null);
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const titleFormRef = React.useRef<HTMLFormElement | null>(null);
  const titleChanged = Boolean(activeSession && titleDraft.trim() && titleDraft.trim() !== activeSession.label);

  React.useEffect(() => {
    setTitleDraft(activeSession?.label || "");
    setEditingTitle(false);
  }, [activeSession?.id, activeSession?.label]);

  React.useEffect(() => {
    if (!activeSession) previousCaptureCountRef.current = 0;
  }, [activeSession]);

  React.useEffect(() => {
    if (!activeSession?.items.length) return;
    const previousCaptureCount = previousCaptureCountRef.current;
    previousCaptureCountRef.current = activeSession.items.length;
    window.requestAnimationFrame(() => {
      if (previousCaptureCount === 0) {
        window.scrollTo({ top: 0, behavior: "instant" });
        return;
      }
      latestCaptureRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    });
  }, [activeSession?.items.length]);

  if (!activeSession || activeSession.items.length === 0) {
    return (
      <section className="capture-empty" aria-label="Capture">
        <div className="capture-empty-panel">
          <div className="capture-empty-copy">
            <p className="eyebrow">Capture</p>
            <h1>Nothing captured yet</h1>
            <p>Start with audio, a photo, or a note. Your captures will appear here in order as the current session builds.</p>
          </div>
          <div className="capture-empty-preview" aria-hidden="true">
            <div className="empty-capture-row">
              <span />
              <div>
                <strong>First capture</strong>
                <small>Saved here</small>
              </div>
            </div>
            <div className="empty-capture-row muted">
              <span />
              <div>
                <strong>Next capture</strong>
                <small>Added below</small>
              </div>
            </div>
            <div className="empty-capture-line" />
          </div>
        </div>
        <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
      </section>
    );
  }

  return (
    <section className="capture-current" aria-label="Current session">
      <div className="current-header">
        <form
          className="current-title-form"
          ref={titleFormRef}
          onBlur={(event) => {
            const nextFocus = event.relatedTarget;
            if (nextFocus instanceof Node && titleFormRef.current?.contains(nextFocus)) return;
            if (!savingTitle) setTitleDraft(activeSession.label);
            setEditingTitle(false);
          }}
          onSubmit={(event) => {
            event.preventDefault();
            if (!titleChanged || savingTitle) return;
            setSavingTitle(true);
            void onUpdateTitle(activeSession.id, titleDraft.trim()).finally(() => {
              setSavingTitle(false);
              setEditingTitle(false);
            });
          }}
        >
          <p className="eyebrow">Current session</p>
          <Input
            aria-label="Session title"
            onChange={(event) => {
              setEditingTitle(true);
              setTitleDraft(event.target.value);
            }}
            onFocus={() => setEditingTitle(true)}
            value={titleDraft}
          />
          <small>New captures save here by default.</small>
          {editingTitle ? (
            <div className="current-title-actions">
              <Button disabled={savingTitle || !titleChanged} size="sm" type="submit" variant="secondary">
                {savingTitle ? "Saving" : "Save title"}
              </Button>
            </div>
          ) : null}
        </form>
        <Button className="new-session-button" onClick={onNewSession} size="sm" variant="secondary">
          New session
        </Button>
      </div>
      <div className="feed-focus">
        {activeSession.items.map((item, index) => (
          <div className="capture-feed-item" key={item.id} ref={index === activeSession.items.length - 1 ? latestCaptureRef : undefined}>
            <CaptureItemCard item={item} onOpen={() => setSelectedCapture(item)} onResolveFile={onResolveFile} />
          </div>
        ))}
      </div>
      <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
    </section>
  );
}

function TextCaptureSheet({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [value, setValue] = React.useState("");

  React.useEffect(() => {
    if (open) setValue("");
  }, [open]);

  return (
    <Sheet onClose={onClose} open={open} title="Write note">
      <div className="sheet-stack">
        <Textarea
          autoFocus
          onChange={(event) => setValue(event.target.value)}
          placeholder="Type the note now. Patient matching can wait."
          rows={7}
          value={value}
        />
        <Button
          disabled={!value.trim()}
          onClick={() =>
            void onSave({
              kind: "note",
              detail: value.trim(),
              file: new Blob([value.trim()], { type: "text/plain" }),
              filename: `note-${Date.now()}.txt`,
            })
          }
        >
          Save to current session
        </Button>
        <Button
          disabled={!value.trim()}
          onClick={() =>
            void onSave(
              {
                kind: "note",
                detail: value.trim(),
                file: new Blob([value.trim()], { type: "text/plain" }),
                filename: `note-${Date.now()}.txt`,
              },
              true,
            )
          }
          variant="secondary"
        >
          Save into new session
        </Button>
      </div>
    </Sheet>
  );
}

function PhotoPreviewDialog({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState("");

  React.useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  React.useEffect(() => {
    if (open) setFile(null);
  }, [open]);

  const makeDraft = (): CaptureDraft | null =>
    file
      ? {
          kind: "photo",
          detail: "Clinical photo saved for later review.",
          file,
          filename: file.name || `photo-${Date.now()}.jpg`,
        }
      : null;

  return (
    <Dialog onClose={onClose} open={open} title="Photo preview">
      <div className="photo-preview">
        <input
          accept="image/*"
          capture="environment"
          className="input"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          type="file"
        />
        {previewUrl ? (
          <img alt="Selected capture" className="photo-image-preview" src={previewUrl} />
        ) : (
          <div className="photo-frame">
            <span>Select or take a clinical photo</span>
          </div>
        )}
        <div className="dialog-actions">
          <Button disabled={!file} onClick={() => {
            const draft = makeDraft();
            if (draft) void onSave(draft);
          }}>
            Use photo
          </Button>
          <Button disabled={!file} onClick={() => {
            const draft = makeDraft();
            if (draft) void onSave(draft, true);
          }} variant="secondary">
            Save into new session
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function AudioDialog({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [seconds, setSeconds] = React.useState(0);
  const [recorder, setRecorder] = React.useState<MediaRecorder | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [error, setError] = React.useState("");
  const [recordingState, setRecordingState] = React.useState<"recording" | "paused" | "stopped">("stopped");
  const chunksRef = React.useRef<BlobPart[]>([]);
  const streamRef = React.useRef<MediaStream | null>(null);
  const saveOnStopRef = React.useRef(false);

  React.useEffect(() => {
    if (!open) return;
    setSeconds(0);
    const timer = window.setInterval(() => {
      setSeconds((value) => (recordingState === "recording" ? value + 1 : value));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [open, recordingState]);

  React.useEffect(() => {
    if (!open) return;
    chunksRef.current = [];
    saveOnStopRef.current = false;
    setAudioUrl("");
    setError("");
    setRecordingState("stopped");

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Microphone recording is not available here. Attach an audio file instead.");
      return;
    }

    const recorderOptions = preferredAudioRecorderOptions();
    if (isSafariBrowser() && !recorderOptions) {
      setError("Safari cannot record a playable audio format here. Attach an audio file instead.");
      return;
    }

    navigator.mediaDevices
      ?.getUserMedia({ audio: true })
      .then((mediaStream) => {
        streamRef.current = mediaStream;
        const nextRecorder = new MediaRecorder(mediaStream, recorderOptions);
        nextRecorder.ondataavailable = (event) => {
          if (event.data.size) chunksRef.current.push(event.data);
        };
        nextRecorder.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: nextRecorder.mimeType || "audio/webm" });
          const filename = `audio-${Date.now()}.${audioExtensionForMimeType(blob.type)}`;
          setAudioUrl(URL.createObjectURL(blob));
          setRecordingState("stopped");
          streamRef.current?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          if (saveOnStopRef.current && blob.size) {
            void onSave({
              kind: "audio",
              detail: "Clinical audio captured and saved to the backend.",
              file: blob,
              filename,
            });
          }
        };
        nextRecorder.start();
        setRecorder(nextRecorder);
        setRecordingState("recording");
      })
      .catch(() => setError("Microphone permission is needed to record audio."));

    return () => {
      setRecorder((current) => {
        saveOnStopRef.current = false;
        if (current && current.state !== "inactive") current.stop();
        return null;
      });
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [open, onSave]);

  React.useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const stopAndSaveRecording = () => {
    if (!recorder || recorder.state === "inactive") return;
    saveOnStopRef.current = true;
    recorder.stop();
  };

  const pauseRecording = () => {
    if (recorder?.state !== "recording") return;
    recorder.pause();
    setRecordingState("paused");
  };

  const resumeRecording = () => {
    if (recorder?.state !== "paused") return;
    recorder.resume();
    setRecordingState("recording");
  };

  return (
    <Dialog onClose={onClose} open={open} title="Audio recording">
      <div className="recording-panel">
        <div className="record-dot" />
        <h1>00:{seconds.toString().padStart(2, "0")}</h1>
        <p>{recordingState === "paused" ? "Recording paused." : recordingState === "recording" ? "Recording now." : "Recording saved."}</p>
        {error ? <p className="error-copy">{error}</p> : null}
        <input
          accept="audio/*"
          capture
          className="input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            setAudioUrl(URL.createObjectURL(file));
            const fallbackName = `audio-${Date.now()}.${audioExtensionForMimeType(file.type)}`;
            void onSave({
              kind: "audio",
              detail: "Clinical audio captured and saved to the backend.",
              file,
              filename: file.name || fallbackName,
            });
          }}
          type="file"
        />
        {audioUrl ? <audio controls src={audioUrl} /> : null}
        <div className="dialog-actions">
          <Button disabled={!recorder || recorder.state !== "recording"} onClick={pauseRecording} variant="secondary">
            Pause
          </Button>
          <Button disabled={!recorder || recorder.state !== "paused"} onClick={resumeRecording} variant="secondary">
            Resume
          </Button>
          <Button disabled={!recorder || recorder.state === "inactive"} onClick={stopAndSaveRecording}>
            Stop and save
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function SourcePreviewDialog({
  item,
  onClose,
  onResolveFile,
}: {
  item: CaptureItem | null;
  onClose: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [cacheSourceName, setCacheSourceName] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [previewError, setPreviewError] = React.useState("");

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setCacheSourceName("");
    setNoteText("");
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;

    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        setCacheSourceName(cached.sourceName);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);

    return () => {
      revoked = true;
    };
  }, [item]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;
    const endpoint =
      item.fileEndpoint || (item.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");
    if (!endpoint) return;

    onResolveFile(endpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPreviewError("Source preview is not available right now.");
      });

    return () => {
      cancelled = true;
    };
  }, [item, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  if (!item) return null;

  const isAudio = item.type === "audio" || item.type === "voice";
  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url;
  const sourceName = cacheSourceName || item.sourceName;
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedText = metadataText(generated.text);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);

  return (
    <Dialog onClose={onClose} open title={item.title}>
      <div className="source-viewer">
        {item.type === "photo" ? (
          sourceUrl ? (
            <img alt={item.sourceName} className="photo-image-preview" src={sourceUrl} />
          ) : thumbnail ? (
            <img alt={`${item.sourceName} thumbnail`} className="photo-image-preview" src={thumbnail} />
          ) : (
            <div className="photo-frame">
              <span>{item.sourceName}</span>
            </div>
          )
        ) : null}
        {previewError ? <div className="alert alert-red">{previewError}</div> : null}
        {item.type === "note" ? (
          <Card className="source-note">
            <p>{generatedText || noteText || item.detail}</p>
          </Card>
        ) : null}
        {isAudio ? (
          <div className="audio-source">
            {sourceUrl ? (
              <audio controls src={sourceUrl} />
            ) : (
              <div className="audio-wave">
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        ) : null}
        <div className="source-info-panel">
          <div className="source-info-header">
            <small>{item.time} · File: {sourceName}</small>
            <StatusBadge status={item.status} />
          </div>
          <CaptureMetadataSummary item={item} />
        </div>
        {(item.type === "audio" || item.type === "photo") && generatedText ? (
          <Card className="source-note">
            <p>{generatedText}</p>
          </Card>
        ) : null}
      </div>
    </Dialog>
  );
}

function OrganizeHome({
  sessions,
  onOpenSession,
}: {
  sessions: CaptureSession[];
  onOpenSession: (sessionId: string) => void;
}) {
  const [query, setQuery] = React.useState("");
  const unassigned = sessions.filter((session) => session.status === "unassigned");
  const needsReview = sessions.filter((session) => session.status === "needs_review" || session.status === "reopened");
  const inProgress = sessions.filter((session) => session.status === "processing" || session.status === "reviewing");
  const organized = sessions.filter((session) => session.status === "organized");
  const verified = sessions.filter((session) => session.status === "verified");
  const failed = sessions.filter((session) => session.status === "failed");
  const filtered = sessions.filter((session) =>
    `${session.label} ${session.summary} ${session.patientName ?? ""}`.toLowerCase().includes(query.toLowerCase()),
  );
  const filterByStatuses = (source: CaptureSession[], statuses: SessionStatus[]) =>
    source.filter((session) => statuses.includes(session.status));

  return (
    <section className="organize-home" aria-label="Organize">
      <div>
        <p className="eyebrow">Organize</p>
        <h1>Review when there is a pause</h1>
      </div>
      <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search sessions" value={query} />
      <Card>
        <div className="section-heading">
          <div>
            <h2>Unassigned</h2>
            <p>Captured sessions waiting for patient assignment.</p>
          </div>
          <Badge tone={unassigned.length ? "blue" : "neutral"}>{unassigned.length}</Badge>
        </div>
        <div className="stack">
          {(query ? filtered.filter((session) => session.status === "unassigned") : unassigned).map((session) => (
            <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
          ))}
          {(query ? filtered.filter((session) => session.status === "unassigned") : unassigned).length === 0 ? (
            <p>No unassigned sessions.</p>
          ) : null}
        </div>
      </Card>
      <Card className="review-card">
        <div className="section-heading">
          <div>
            <h2>Needs review</h2>
            <p>{needsReview.length ? "Confirm where these captures belong." : "No sessions need review."}</p>
          </div>
          <Badge tone={needsReview.length ? "amber" : "neutral"}>{needsReview.length}</Badge>
        </div>
        <div className="stack">
          {(query ? filterByStatuses(filtered, ["needs_review", "reopened"]) : needsReview).map((session) => (
            <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
          ))}
          {(query ? filterByStatuses(filtered, ["needs_review", "reopened"]) : needsReview).length === 0 ? (
            <p>No captures waiting here.</p>
          ) : null}
        </div>
      </Card>
      <Card>
        <div className="section-heading">
          <div>
            <h2>Processing</h2>
            <p>Backend work or staff review is still underway.</p>
          </div>
          <Badge tone={inProgress.length ? "blue" : "neutral"}>{inProgress.length}</Badge>
        </div>
        <div className="stack">
          {(query ? filterByStatuses(filtered, ["processing", "reviewing"]) : inProgress).map((session) => (
            <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
          ))}
          {(query ? filterByStatuses(filtered, ["processing", "reviewing"]) : inProgress).length === 0 ? <p>No active processing.</p> : null}
        </div>
      </Card>
      <Card>
        <div className="section-heading">
          <div>
            <h2>Organized</h2>
            <p>Generated or structured output is ready for human review.</p>
          </div>
          <Badge tone="blue">{organized.length}</Badge>
        </div>
        <div className="stack">
          {(query ? filtered.filter((session) => session.status === "organized") : organized).map((session) => (
            <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
          ))}
          {(query ? filtered.filter((session) => session.status === "organized") : organized).length === 0 ? (
            <p>Organized output will appear here before verification.</p>
          ) : null}
        </div>
      </Card>
      <Card>
        <div className="section-heading">
          <div>
            <h2>Verified</h2>
            <p>Sessions reviewed and accepted by staff.</p>
          </div>
          <Badge tone="green">{verified.length}</Badge>
        </div>
        <div className="stack">
          {(query ? filtered.filter((session) => session.status === "verified") : verified).map((session) => (
            <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
          ))}
          {(query ? filtered.filter((session) => session.status === "verified") : verified).length === 0 ? (
            <p>Verified sessions will appear after staff review.</p>
          ) : null}
        </div>
      </Card>
      {failed.length ? (
        <Card>
          <div className="section-heading">
            <div>
              <h2>Failed</h2>
              <p>Retry or reopen these sessions when the source is available.</p>
            </div>
            <Badge tone="red">{failed.length}</Badge>
          </div>
          <div className="stack">
            {(query ? filtered.filter((session) => session.status === "failed") : failed).map((session) => (
              <SessionRow key={session.id} onOpen={() => onOpenSession(session.id)} session={session} />
            ))}
            {(query ? filtered.filter((session) => session.status === "failed") : failed).length === 0 ? (
              <p>No failed sessions match this search.</p>
            ) : null}
          </div>
        </Card>
      ) : null}
    </section>
  );
}

function SessionRow({ session, onOpen }: { session: CaptureSession; onOpen: () => void }) {
  const sourceLabel = assignmentSourceLabel(session.assignmentSource);
  return (
    <button className="session-row" onClick={onOpen} type="button">
      <div>
        <strong>{session.label}</strong>
        <span>
          {session.patientName ?? session.reviewReason ?? "Unassigned"}
          {sourceLabel ? ` - ${sourceLabel}` : ""}
        </span>
      </div>
      <SessionStatusBadge status={session.status} />
      <span className="session-row-arrow" aria-hidden="true">›</span>
    </button>
  );
}

function PatientAssignmentPanel({
  selectedPatient,
  onSelectPatient,
  onSearch,
  onCreate,
}: {
  selectedPatient: Patient | null;
  onSelectPatient: (patient: Patient | null) => void;
  onSearch: (query: string) => Promise<Patient[]>;
  onCreate: (displayName: string) => Promise<Patient>;
}) {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Patient[]>([]);
  const [newName, setNewName] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setBusy(true);
    onSearch(query)
      .then((patients) => {
        if (!cancelled) setResults(patients);
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, onSearch]);

  const create = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const patient = await onCreate(newName.trim());
      onSelectPatient(patient);
      setNewName("");
      setQuery(patient.displayName);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="review-card">
      <div className="section-heading">
        <div>
          <h2>Patient assignment</h2>
          <p>Search or create a patient while reviewing this session.</p>
        </div>
        {selectedPatient ? <Badge tone="blue">{selectedPatient.displayName}</Badge> : <Badge tone="neutral">Unassigned</Badge>}
      </div>
      <div className="stack">
        <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search patients" value={query} />
        <div className="patient-result-list">
          {results.slice(0, 5).map((patient) => (
            <button
              className={selectedPatient?.id === patient.id ? "patient-result selected" : "patient-result"}
              key={patient.id}
              onClick={() => onSelectPatient(patient)}
              type="button"
            >
              <strong>{patient.displayName}</strong>
              <span>{patient.dateOfBirth || patient.phone || patient.email || "No identifiers"}</span>
            </button>
          ))}
          {!busy && results.length === 0 ? <p>No matching patients.</p> : null}
        </div>
        <div className="patient-create-row">
          <Input onChange={(event) => setNewName(event.target.value)} placeholder="New patient name" value={newName} />
          <Button disabled={busy || !newName.trim()} onClick={() => void create()} variant="secondary">
            Create
          </Button>
        </div>
      </div>
    </Card>
  );
}

function SessionDetail({
  session,
  onOrganize,
  onUpdateTitle,
  onLoadCaptures,
  onSearchPatients,
  onCreatePatient,
  onAssignSessionPatient,
  onAssignCapturePatient,
  onResolveFile,
}: {
  session?: CaptureSession;
  onOrganize: (sessionId: string) => void;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
  onLoadCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  onSearchPatients: (query: string) => Promise<Patient[]>;
  onCreatePatient: (displayName: string) => Promise<Patient>;
  onAssignSessionPatient: (sessionId: string, target: PatientAssignmentTarget) => Promise<void>;
  onAssignCapturePatient: (sessionId: string, captureId: string, target: PatientAssignmentTarget) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [selectedPatient, setSelectedPatient] = React.useState<Patient | null>(null);
  const [assigning, setAssigning] = React.useState("");
  const [titleDraft, setTitleDraft] = React.useState(session?.label || "");
  const [savingTitle, setSavingTitle] = React.useState(false);

  React.useEffect(() => {
    if (!session || session.items.length || isLocalSessionId(session.id)) return;
    void onLoadCaptures(session.id);
  }, [session, onLoadCaptures]);

  React.useEffect(() => {
    setSelectedPatient(session?.patientId ? { id: session.patientId, displayName: session.patientName || "Selected patient" } : null);
  }, [session?.id, session?.patientId, session?.patientName]);

  React.useEffect(() => {
    setTitleDraft(session?.label || "");
  }, [session?.id, session?.label]);

  if (!session) {
    return (
      <section className="organize-home">
        <Skeleton className="h-16" />
      </section>
    );
  }

  return (
    <section className="session-detail">
      <Card className="review-card">
        <p className="eyebrow">Session detail / review</p>
        <div className="patient-create-row">
          <Input onChange={(event) => setTitleDraft(event.target.value)} value={titleDraft} />
          <Button
            disabled={savingTitle || !titleDraft.trim() || titleDraft.trim() === session.label || isLocalSessionId(session.id)}
            onClick={() => {
              setSavingTitle(true);
              void onUpdateTitle(session.id, titleDraft.trim()).finally(() => setSavingTitle(false));
            }}
            variant="secondary"
          >
            Save title
          </Button>
        </div>
        <p>{session.summary}</p>
        <div className="detail-meta">
          <SessionStatusBadge status={session.status} />
          <span>
            {session.patientName ?? "No patient selected"}
            {assignmentSourceLabel(session.assignmentSource) ? ` - ${assignmentSourceLabel(session.assignmentSource)}` : ""}
          </span>
        </div>
        {session.status !== "organized" && session.status !== "verified" ? (
          <Button onClick={() => onOrganize(session.id)}>Mark organized</Button>
        ) : null}
      </Card>
      <PatientAssignmentPanel
        onCreate={onCreatePatient}
        onSearch={onSearchPatients}
        onSelectPatient={setSelectedPatient}
        selectedPatient={selectedPatient}
      />
      <div className="action-row">
        <Button
          disabled={!selectedPatient || assigning === "session"}
          onClick={() => {
            if (!selectedPatient) return;
            setAssigning("session");
            void onAssignSessionPatient(session.id, {
              patientId: selectedPatient.id,
              patientName: selectedPatient.displayName,
              source: "staff",
            }).finally(() => setAssigning(""));
          }}
        >
          Assign session
        </Button>
        {session.patientId ? (
          <Button
            disabled={assigning === "session-clear"}
            onClick={() => {
              setAssigning("session-clear");
              void onAssignSessionPatient(session.id, { patientId: null, source: "staff" }).finally(() => setAssigning(""));
            }}
            variant="secondary"
          >
            Clear session patient
          </Button>
        ) : null}
      </div>
      <div className="feed-focus">
        {session.items.map((item) => (
          <div className="capture-assignment-row" key={item.id}>
            <CaptureItemCard item={item} onOpen={() => setSelectedCapture(item)} onResolveFile={onResolveFile} />
            <div className="assignment-actions">
              <small>
                {item.patientName || item.patientId || "No capture patient"}
                {assignmentSourceLabel(item.assignmentSource) ? ` - ${assignmentSourceLabel(item.assignmentSource)}` : ""}
              </small>
              <Button
                disabled={!selectedPatient || assigning === item.id}
                onClick={() => {
                  if (!selectedPatient) return;
                  setAssigning(item.id);
                  void onAssignCapturePatient(session.id, item.id, {
                    patientId: selectedPatient.id,
                    patientName: selectedPatient.displayName,
                    source: "staff",
                  }).finally(() => setAssigning(""));
                }}
                size="sm"
                variant={item.patientId ? "secondary" : "default"}
              >
                {item.patientId ? "Override capture" : "Assign capture"}
              </Button>
            </div>
          </div>
        ))}
        {session.items.length === 0 ? <p>No captures loaded for this session yet.</p> : null}
      </div>
      <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
    </section>
  );
}

export function App() {
  const [auth, setAuth] = React.useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = React.useState(false);
  const [authError, setAuthError] = React.useState("");
  const authRef = React.useRef<AuthSession | null>(null);
  const refreshPromiseRef = React.useRef<Promise<string> | null>(null);
  const bootstrappedAuthRef = React.useRef(false);
  const [screen, setScreen] = React.useState<Screen>(() => screenFromLocation());
  const [sessions, setSessions] = React.useState<CaptureSession[]>([]);
  const [activeSession, setActiveSession] = React.useState<CaptureSession | null>(null);
  const [selectedSessionId, setSelectedSessionId] = React.useState("");
  const [pendingCount, setPendingCount] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [textOpen, setTextOpen] = React.useState(false);
  const [photoOpen, setPhotoOpen] = React.useState(false);
  const [audioOpen, setAudioOpen] = React.useState(false);
  const [toast, setToast] = React.useState("");
  const processingRef = React.useRef(false);

  const navigateScreen = React.useCallback((nextScreen: Screen) => {
    setScreen(nextScreen);
    replaceScreenLocation(nextScreen);
    if (nextScreen === "capture") setSelectedSessionId("");
  }, []);

  const clearAuth = React.useCallback(() => {
    authRef.current = null;
    setAuth(null);
    clearStoredAuthProfile();
    processingRef.current = false;
  }, []);

  const commitAuth = React.useCallback((nextAuth: AuthSession) => {
    authRef.current = nextAuth;
    setAuth(nextAuth);
    persistAuthProfile(nextAuth);
    setAuthError("");
  }, []);

  const refreshAccessToken = React.useCallback(async () => {
    const currentAuth = authRef.current;
    if (!currentAuth) throw new Error("No auth session");
    if (!refreshPromiseRef.current) {
      refreshPromiseRef.current = refreshAuthToken(currentAuth.refreshToken)
        .then((tokens) => {
          const refreshed = { ...currentAuth, ...tokens };
          commitAuth(refreshed);
          return refreshed.accessToken;
        })
        .catch((error) => {
          clearAuth();
          throw error;
        })
        .finally(() => {
          refreshPromiseRef.current = null;
        });
    }
    return refreshPromiseRef.current;
  }, [clearAuth, commitAuth]);

  const apiFetch = React.useCallback<ApiFetch>(
    async (input, init = {}) => {
      const token = authRef.current?.accessToken;
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);

      const response = await fetch(input, { ...init, headers });
      if (response.status !== 401) return response;

      try {
        const nextToken = await refreshAccessToken();
        const retryHeaders = new Headers(init.headers);
        retryHeaders.set("Authorization", `Bearer ${nextToken}`);
        return await fetch(input, { ...init, headers: retryHeaders });
      } catch {
        return response;
      }
    },
    [refreshAccessToken],
  );

  React.useEffect(() => {
    if (bootstrappedAuthRef.current) return;
    bootstrappedAuthRef.current = true;
    const storedAuth = loadStoredAuthProfile();
    if (!storedAuth) {
      setAuthReady(true);
      return;
    }
    refreshAuthToken(storedAuth.refreshToken)
      .then((tokens) => commitAuth({ ...storedAuth, ...tokens }))
      .catch(() => clearAuth())
      .finally(() => setAuthReady(true));
  }, [clearAuth, commitAuth]);

  React.useEffect(() => {
    if (!auth || auth.user.persona === "patient-preview") return;
    void hydrateFromStorage();
    void navigator.storage?.persist?.();
  }, [auth]);

  React.useEffect(() => {
    if (auth) return;
    void refreshPendingCount();
  }, [auth]);

  React.useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  React.useEffect(() => {
    const syncScreenFromLocation = () => {
      setScreen(screenFromLocation());
      if (screenFromLocation() === "capture") setSelectedSessionId("");
    };
    window.addEventListener("hashchange", syncScreenFromLocation);
    return () => window.removeEventListener("hashchange", syncScreenFromLocation);
  }, []);

  React.useEffect(() => {
    const warnIfPending = (event: BeforeUnloadEvent) => {
      if (!pendingCount) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnIfPending);
    return () => window.removeEventListener("beforeunload", warnIfPending);
  }, [pendingCount]);

  React.useEffect(() => {
    const retryWhenOnline = () => void processOutbox();
    window.addEventListener("online", retryWhenOnline);
    return () => window.removeEventListener("online", retryWhenOnline);
  }, []);

  const refreshPendingCount = async () => {
    const pending = await loadPendingCaptures();
    setPendingCount(pending.length);
    return pending;
  };

  const hydrateFromStorage = async () => {
    const pending = await refreshPendingCount();
    const localSessions = sessionsFromPending(pending);
    try {
      const loadedSessions = await fetchSessions(apiFetch);
      setSessions([...localSessions, ...loadedSessions.filter((session) => !localSessions.some((local) => local.id === session.id))]);
    } catch {
      setSessions(localSessions);
      setToast("Backend is not reachable. Captures stay on this device.");
    }
    if (pending.length) window.setTimeout(() => void processOutbox(), 600);
  };

  const updateItemStatus = (itemId: string, status: CaptureStatus) => {
    setActiveSession((session) =>
      session
        ? {
            ...session,
            items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
          }
        : session,
    );
    setSessions((current) =>
      current.map((session) => ({
        ...session,
        items: session.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
      })),
    );
  };

  const upsertSession = (session: CaptureSession, removeIds: string[] = []) => {
    setSessions((current) => [
      session,
      ...current.filter((currentSession) => currentSession.id !== session.id && !removeIds.includes(currentSession.id)),
    ]);
  };

  const rebuildLocalPendingSessions = async () => {
    const pending = await loadPendingCaptures();
    const localSessions = sessionsFromPending(pending);
    setSessions((current) => [
      ...localSessions,
      ...current.filter((session) => !localSessions.some((localSession) => localSession.id === session.id)),
    ]);
  };

  const scheduleCaptureProcessingRefresh = React.useCallback(
    (sessionId: string) => {
      window.setTimeout(() => {
        void fetchSessionCaptures(apiFetch, sessionId)
          .then((captures) => {
            setSessions((current) =>
              current.map((session) =>
                session.id === sessionId ? { ...session, items: mergeCaptureItemsPreservingPreview(session.items, captures) } : session,
              ),
            );
            setActiveSession((current) =>
              current?.id === sessionId ? { ...current, items: mergeCaptureItemsPreservingPreview(current.items, captures) } : current,
            );
          })
          .catch(() => undefined);
      }, 5500);
    },
    [apiFetch],
  );

  const processOutbox = async () => {
    const currentAuth = authRef.current;
    const activeTenantId = currentAuth?.tenant.id;
    if (processingRef.current || !currentAuth || !activeTenantId || currentAuth.user.persona === "patient-preview") return;
    processingRef.current = true;
    setSyncing(true);
    try {
      const pending = await loadPendingCaptures();
      for (const pendingCapture of pending) {
        if (!authRef.current || authRef.current.tenant.id !== activeTenantId) break;
        const capture = (await loadPendingCapture(pendingCapture.id)) || pendingCapture;
        if (capture.tenantId && capture.tenantId !== activeTenantId) continue;
        const backendSessionId = capture.backendSessionId || capture.sessionId;
        await updatePendingCapture(capture.id, (current) => ({
          ...normalizePendingCapture(current),
          tenantId: current.tenantId || activeTenantId,
          backendSessionId,
          sessionId: backendSessionId,
        }));
        updateItemStatus(capture.item.id, "syncing");
        try {
          const uploadDraft = await standardizeCaptureDraft(capture.draft);
          const result = await uploadCapture(apiFetch, capture.clientCaptureId, uploadDraft, backendSessionId, capture.intoNew);
          await updatePendingCapture(capture.id, (current) => ({
            ...normalizePendingCapture(current),
            draft: uploadDraft,
            tenantId: activeTenantId,
            backendSessionId: result.session.id,
            backendCaptureId: result.item.id,
            sessionId: result.session.id,
            intoNew: false,
          }));
          await storeBackendMappings(capture, result, activeTenantId);
          await saveSyncedCaptureCache(result.item, uploadDraft.file);
          await bindPendingSession(capture.localSessionId, result.session.id);
          await removePendingCapture(capture.id);
          const stillPendingForLocalSession = (await loadPendingCaptures()).some(
            (pendingCapture) => pendingCapture.localSessionId === capture.localSessionId,
          );
          if (stillPendingForLocalSession) await rebuildLocalPendingSessions();
          const currentSession = sessions.find((session) => session.id === capture.localSessionId || session.id === result.session.id);
          const mergedSession = mergeSessionItems(currentSession || activeSession, result.session, capture.item.id);
          upsertSession(mergedSession, stillPendingForLocalSession ? [] : [capture.localSessionId]);
          setActiveSession((current) =>
            current?.id === capture.localSessionId || current?.id === result.session.id
              ? mergeSessionItems(current, result.session, capture.item.id)
              : current,
          );
          setSelectedSessionId((current) => (current === capture.localSessionId ? mergedSession.id : current));
          setToast("Capture safely transferred.");
          if (result.item.status === "processing") scheduleCaptureProcessingRefresh(result.session.id);
        } catch {
          await updatePendingCapture(capture.id, (current) => ({ ...current, retryCount: current.retryCount + 1 }));
          updateItemStatus(capture.item.id, "failed");
          await rebuildLocalPendingSessions();
          setToast("Failed/Retry");
          break;
        }
      }
    } finally {
      processingRef.current = false;
      setSyncing(false);
      await refreshPendingCount();
    }
  };

  const saveDraft = async (draft: CaptureDraft, intoNew = false) => {
    let pending: PendingCapture;
    try {
      const safeDraft = await standardizeCaptureDraft(draft);
      pending = makeLocalCapture(safeDraft, activeSession, intoNew, authRef.current?.tenant.id);
      const visibleSession = sessionWithLocalPreview(pending.session, pending.item.id, safeDraft.file);
      flushSync(() => {
        setActiveSession(visibleSession);
        upsertSession(visibleSession);
        navigateScreen("capture");
      });
    } catch {
      setToast(draft.kind === "audio" ? "Audio conversion failed." : "Failed/Retry");
      return;
    }

    try {
      await savePendingCapture(pending);
      void saveSyncedCaptureCache(pending.item, pending.draft.file);
      setToast("Saved on device.");
      void refreshPendingCount();
      if (authRef.current?.tenant.id) void processOutbox();
    } catch {
      setToast("Visible for this visit. Device storage failed.");
    }
  };

  const beginCapture = (kind: CaptureDraft["kind"]) => {
    if (kind === "note") setTextOpen(true);
    if (kind === "photo") setPhotoOpen(true);
    if (kind === "audio") setAudioOpen(true);
  };

  const startNewSession = () => {
    setActiveSession(null);
    setToast("New session ready.");
  };

  const organizeSession = async (sessionId: string) => {
    try {
      const organized = await markSessionOrganized(apiFetch, sessionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? organized : session)));
      setToast("Session organized.");
    } catch {
      setToast("Failed/Retry");
    }
  };

  const renameSession = React.useCallback(
    async (sessionId: string, title: string) => {
      if (isLocalSessionId(sessionId)) {
        const updateSession = (session: CaptureSession) => ({ ...session, label: title });
        setSessions((current) => current.map((session) => (session.id === sessionId ? updateSession(session) : session)));
        setActiveSession((current) => (current?.id === sessionId ? updateSession(current) : current));
        const pending = await loadPendingCaptures();
        await Promise.all(
          pending
            .filter((capture) => capture.localSessionId === sessionId)
            .map((capture) =>
              updatePendingCapture(capture.id, (current) => ({
                ...current,
                session: updateSession(current.session),
              })),
            ),
        );
        setToast("Session title updated.");
        return;
      }
      const updated = await updateSessionTitle(apiFetch, sessionId, title);
      setSessions((current) =>
        current.map((session) => (session.id === sessionId ? { ...session, ...updated, items: session.items } : session)),
      );
      setActiveSession((current) => (current?.id === sessionId ? { ...current, ...updated, items: current.items } : current));
      setToast("Session title updated.");
    },
    [apiFetch],
  );

  const loadCapturesForSession = React.useCallback(
    async (sessionId: string) => {
      const captures = await fetchSessionCaptures(apiFetch, sessionId);
      setSessions((current) => current.map((session) => (session.id === sessionId ? { ...session, items: captures } : session)));
      return captures;
    },
    [apiFetch],
  );

  const searchPatientOptions = React.useCallback((query: string) => searchPatients(apiFetch, query), [apiFetch]);

  const createPatientOption = React.useCallback((displayName: string) => createPatient(apiFetch, displayName), [apiFetch]);

  const assignPatientToSession = React.useCallback(
    async (sessionId: string, target: PatientAssignmentTarget) => {
      const assigned = await assignSessionPatient(apiFetch, sessionId, target);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                ...assigned,
                items: session.items.map((item) =>
                  item.patientId
                    ? item
                    : {
                        ...item,
                        patientId: target.patientId,
                        patientName: target.patientName,
                        assignmentSource: target.source || "staff",
                      },
                ),
              }
            : session,
        ),
      );
      setToast(target.patientId ? "Session assigned." : "Session patient cleared.");
    },
    [apiFetch],
  );

  const assignPatientToCapture = React.useCallback(
    async (sessionId: string, captureId: string, target: PatientAssignmentTarget) => {
      const assigned = await assignCapturePatient(apiFetch, captureId, target);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                items: session.items.map((item) => (item.id === captureId ? { ...item, ...assigned } : item)),
              }
            : session,
        ),
      );
      setToast(target.patientId ? "Capture assigned." : "Capture patient cleared.");
    },
    [apiFetch],
  );

  const resolveSourceFile = React.useCallback((endpoint: string) => resolveCaptureFileUrl(apiFetch, endpoint), [apiFetch]);

  const handlePersonaLogin = async (persona: Persona) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPersona(persona));
      navigateScreen("capture");
    } catch {
      setAuthError("Could not sign in with that persona.");
    }
  };

  const handlePasswordLogin = async (email: string, password: string) => {
    setAuthError("");
    try {
      commitAuth(await loginWithPassword(email, password));
      navigateScreen("capture");
    } catch {
      setAuthError("Invalid email or password.");
    }
  };

  const handleLogout = async () => {
    const currentAuth = authRef.current;
    clearAuth();
    setSessions([]);
    setActiveSession(null);
    setSelectedSessionId("");
    setSyncing(false);
    navigateScreen("capture");
    void refreshPendingCount();
    if (currentAuth) {
      try {
        await logoutSession(currentAuth.accessToken, currentAuth.refreshToken);
      } catch {
        // Local logout still wins when the backend cannot be reached.
      }
    }
  };

  const selectedSession = sessions.find((session) => session.id === selectedSessionId);

  if (!authReady) {
    return (
      <main className="login-shell">
        <Card className="login-card">
          <Skeleton className="h-16" />
          <Skeleton className="h-12" />
        </Card>
      </main>
    );
  }

  if (!auth) {
    return (
      <LoginGate
        error={authError}
        pendingCount={pendingCount}
        onLogin={handlePasswordLogin}
        onPersonaLogin={handlePersonaLogin}
      />
    );
  }

  if (auth.user.persona === "patient-preview") {
    return <PatientPreviewGate auth={auth} onLogout={handleLogout} />;
  }

  return (
    <>
      <Shell auth={auth} onCapture={beginCapture} onLogout={handleLogout} screen={screen} onNavigate={navigateScreen}>
        <SyncSafetyBanner pendingCount={pendingCount} syncing={syncing} onRetry={() => void processOutbox()} />
        {screen === "capture" ? (
          <CaptureScreen
            activeSession={activeSession}
            onCapture={beginCapture}
            onNewSession={startNewSession}
            onResolveFile={resolveSourceFile}
            onUpdateTitle={renameSession}
          />
        ) : (
          <OrganizeHome
            onOpenSession={(sessionId) => {
              setSelectedSessionId(sessionId);
              navigateScreen("organize");
            }}
            sessions={sessions}
          />
        )}
      </Shell>
      <Dialog
        className="session-dialog"
        onClose={() => setSelectedSessionId("")}
        open={screen !== "capture" && Boolean(selectedSession)}
        title={selectedSession?.label || "Session review"}
      >
        <SessionDetail
          onAssignCapturePatient={assignPatientToCapture}
          onAssignSessionPatient={assignPatientToSession}
          onCreatePatient={createPatientOption}
          onLoadCaptures={loadCapturesForSession}
          onOrganize={organizeSession}
          onResolveFile={resolveSourceFile}
          onSearchPatients={searchPatientOptions}
          onUpdateTitle={renameSession}
          session={selectedSession}
        />
      </Dialog>
      <TextCaptureSheet
        onClose={() => setTextOpen(false)}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setTextOpen(false);
        }}
        open={textOpen}
      />
      <PhotoPreviewDialog
        onClose={() => setPhotoOpen(false)}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setPhotoOpen(false);
        }}
        open={photoOpen}
      />
      <AudioDialog
        onClose={() => setAudioOpen(false)}
        onSave={async (draft, intoNew) => {
          await saveDraft(draft, intoNew);
          setAudioOpen(false);
        }}
        open={audioOpen}
      />
      <Toast message={toast} />
    </>
  );
}
