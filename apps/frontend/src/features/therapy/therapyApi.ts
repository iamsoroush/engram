// Therapy vertical API client (Spine A, therapy). Self-contained so it never disturbs the
// aesthetics capture/client client. Reuses the auth-aware `apiFetch` and the shared backend
// contracts; the therapy synthesis lives on `session.extractedMetadata.therapy`.
import type { ApiFetch, CaptureDraft } from "../../domain/appTypes";
import { API_BASE } from "../../shared/lib/config";

export type TherapyFormat = "dap" | "soap" | "birp";

export type TherapyTheme = { label: string; mentions: number };
export type ThreadCoverage = { label: string; covered: boolean };
export type ShareableSection = { id: string; title: string; body: string };

export type TherapyRisk = {
  active: boolean;
  suggested: boolean;
  level?: string | null;
  cue?: string | null;
  note?: string | null;
  confirmedAt?: string | null;
  confirmedBy?: string | null;
};

export type TherapyBlock = {
  schemaVersion: string;
  format: TherapyFormat;
  availableFormats: TherapyFormat[];
  sessionSoFar: { line: string; narrative: string; threadCoverage: ThreadCoverage[] };
  themes: TherapyTheme[];
  risk: TherapyRisk;
  release: { released: boolean; releasedAt?: string | null };
  planes: {
    shareable: { format: TherapyFormat; sections: ShareableSection[] };
    private: { reflections: string | null; audioTranscripts: Array<{ captureId: string; text: string }> };
  };
  noteCount: number;
  audioCount: number;
  photoCount: number;
  generatedAt?: string | null;
};

export type TherapySession = {
  id: string;
  patientId: string | null;
  patientName: string | null;
  status: string;
  complete: boolean;
  title: string | null;
  generatedReport: string | null;
  therapy: TherapyBlock | null;
};

export type TherapyCaptureNote = {
  id: string;
  type: string;
  status: string;
  text: string;
  raw: string | null;
  capturedAt: string | null;
};

export type TherapyClient = {
  patientId: string;
  displayName: string;
  summary: string;
  sessionCount: number;
  latestSessionId: string | null;
  latestVisitAt: string | null;
  memoryStatus?: string;
};

export type TherapyTimelineSession = {
  sessionId: string;
  title: string | null;
  status: string;
  summary: string;
  captureCount: number;
  complete: boolean;
  capturedAt: string | null;
  updatedAt: string | null;
};

export type TherapyClientDetail = {
  client: TherapyClient;
  sessions: TherapyTimelineSession[];
  history: { snapshot: string; sections: Array<{ label: string; body: string }> } | null;
};

const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);

function parseTherapyBlock(raw: unknown): TherapyBlock | null {
  if (!raw || typeof raw !== "object") return null;
  return raw as TherapyBlock;
}

export function parseTherapySession(raw: Record<string, unknown>): TherapySession {
  const metadata = (raw.extractedMetadata && typeof raw.extractedMetadata === "object" ? raw.extractedMetadata : {}) as Record<string, unknown>;
  return {
    id: String(raw.id || ""),
    patientId: str(raw.patientId),
    patientName: str(raw.patientName),
    status: String(raw.status || "draft"),
    complete: Boolean(raw.complete),
    title: str(raw.title),
    generatedReport: str(raw.generatedReport),
    therapy: parseTherapyBlock(metadata.therapy),
  };
}

export async function getTherapySession(apiFetch: ApiFetch, sessionId: string): Promise<TherapySession> {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}`);
  if (!response.ok) throw new Error("Could not load session");
  return parseTherapySession((await response.json()) as Record<string, unknown>);
}

function noteText(metadata: Record<string, unknown>): { text: string; raw: string | null } {
  // Notes are a pure passthrough (decoration removed): a staff-edited note wins, else the raw note.
  const note = metadata.note as Record<string, unknown> | undefined;
  const detail = typeof metadata.detail === "string" ? metadata.detail : null;
  const text = (note && typeof note.text === "string" && note.text) || detail || "";
  return { text: String(text), raw: detail };
}

function transcriptText(metadata: Record<string, unknown>): string {
  const t = metadata.transcript as Record<string, unknown> | undefined;
  return (t && typeof t.text === "string" && t.text) || "";
}

export async function listTherapySessionCaptures(apiFetch: ApiFetch, sessionId: string): Promise<TherapyCaptureNote[]> {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/captures`);
  if (!response.ok) throw new Error("Could not load captures");
  const items = (await response.json()) as Array<Record<string, unknown>>;
  return items.map((item) => {
    const metadata = (item.metadata && typeof item.metadata === "object" ? item.metadata : {}) as Record<string, unknown>;
    const type = String(item.type || "note");
    const { text, raw } = type === "audio" ? { text: transcriptText(metadata), raw: null } : noteText(metadata);
    return {
      id: String(item.id || ""),
      type,
      status: String(item.status || ""),
      text,
      raw,
      capturedAt: str(item.capturedAt),
    };
  });
}

// Upload any capture (note / audio / photo) into a therapy session — the shared aesthetics capture
// dialogs hand back a CaptureDraft; we add patient_id on first capture so the new session is owned
// by the selected client. Audio is uploaded as recorded; the backend transcodes it to the canonical
// stored format on ingest (audio.ts standardizeCaptureDraft no longer re-encodes).
export async function uploadTherapyCapture(
  apiFetch: ApiFetch,
  { draft, sessionId, patientId }: { draft: CaptureDraft; sessionId?: string; patientId?: string },
): Promise<{ sessionId: string }> {
  const form = new FormData();
  form.append("capture_type", draft.kind);
  form.append("detail", draft.detail ?? "");
  form.append("new_session", String(!sessionId));
  form.append("client_capture_id", `th-${(crypto as Crypto).randomUUID?.() || Date.now()}`);
  if (draft.metadata) form.append("metadata", JSON.stringify(draft.metadata));
  if (sessionId) form.append("session_id", sessionId);
  if (patientId && !sessionId) form.append("patient_id", patientId);
  form.append("file", draft.file, draft.filename);
  const response = await apiFetch(`${API_BASE}/captures`, { method: "POST", body: form });
  if (!response.ok) throw new Error("Could not save capture");
  const payload = (await response.json()) as { session?: Record<string, unknown> };
  return { sessionId: String(payload.session?.id || sessionId || "") };
}

async function postTherapyAction(apiFetch: ApiFetch, sessionId: string, action: string, body: Record<string, unknown>): Promise<TherapySession> {
  const response = await apiFetch(`${API_BASE}/sessions/${sessionId}/therapy/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Could not update therapy ${action}`);
  return parseTherapySession((await response.json()) as Record<string, unknown>);
}

export const setTherapyFormat = (apiFetch: ApiFetch, sessionId: string, format: TherapyFormat) =>
  postTherapyAction(apiFetch, sessionId, "format", { format });
export const setTherapyRelease = (apiFetch: ApiFetch, sessionId: string, released: boolean) =>
  postTherapyAction(apiFetch, sessionId, "release", { released });
export const setTherapyRisk = (apiFetch: ApiFetch, sessionId: string, body: { active: boolean; level?: string; note?: string }) =>
  postTherapyAction(apiFetch, sessionId, "risk", body);
export const setTherapyReflections = (apiFetch: ApiFetch, sessionId: string, reflections: string) =>
  postTherapyAction(apiFetch, sessionId, "reflections", { reflections });

export async function listTherapyClients(apiFetch: ApiFetch): Promise<TherapyClient[]> {
  const response = await apiFetch(`${API_BASE}/patient-memory?filter=all&limit=100`);
  if (!response.ok) throw new Error("Could not load clients");
  const payload = (await response.json()) as { items?: Array<Record<string, unknown>> };
  return (payload.items || []).map((item) => ({
    patientId: String(item.patientId || ""),
    displayName: String(item.displayName || "Client"),
    summary: String(item.summary || ""),
    sessionCount: typeof item.sessionCount === "number" ? item.sessionCount : 0,
    latestSessionId: str(item.latestSessionId),
    latestVisitAt: str(item.latestVisitAt),
    memoryStatus: str(item.memoryStatus) || undefined,
  }));
}

export async function getTherapyClient(apiFetch: ApiFetch, patientId: string): Promise<TherapyClientDetail> {
  const response = await apiFetch(`${API_BASE}/patients/${patientId}/memory`);
  if (!response.ok) throw new Error("Could not load client");
  const payload = (await response.json()) as Record<string, unknown>;
  const patient = (payload.patient && typeof payload.patient === "object" ? payload.patient : {}) as Record<string, unknown>;
  const history = (payload.history && typeof payload.history === "object" ? payload.history : null) as Record<string, unknown> | null;
  return {
    client: {
      patientId: String(patient.patientId || patientId),
      displayName: String(patient.displayName || "Client"),
      summary: String(patient.summary || ""),
      sessionCount: typeof patient.sessionCount === "number" ? patient.sessionCount : 0,
      latestSessionId: str(patient.latestSessionId),
      latestVisitAt: str(patient.latestVisitAt),
    },
    sessions: ((payload.sessions as Array<Record<string, unknown>>) || []).map((s) => ({
      sessionId: String(s.sessionId || ""),
      title: str(s.title),
      status: String(s.status || ""),
      summary: String(s.summary || ""),
      captureCount: typeof s.captureCount === "number" ? s.captureCount : 0,
      complete: Boolean(s.complete),
      capturedAt: str(s.capturedAt),
      updatedAt: str(s.updatedAt),
    })),
    history: history
      ? {
          snapshot: String(history.snapshot || ""),
          sections: ((history.sections as Array<Record<string, unknown>>) || []).map((sec) => ({
            label: String(sec.label || ""),
            body: String(sec.body || ""),
          })),
        }
      : null,
  };
}
