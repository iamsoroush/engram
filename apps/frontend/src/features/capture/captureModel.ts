import type { CaptureDraft, PatientSummary, PendingCapture, SafetyFlag, SafetyFlagKind } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, SessionProcessingStatus, SessionTreatment, SessionTreatmentReview, StructuredPatientInformation, TreatmentOverlayEntry } from "../../domain/types";
import type { AftercareTemplate } from "../../domain/appTypes";
import { appDateTimeFormat } from "../../shared/lib/datetime";
import { metadataDisplay, metadataRecord, metadataText } from "./metadata";
import { sessionUxState } from "../../domain/status";
import type { Translator } from "../../shared/i18n";

// English default capture titles. These are the STORAGE defaults written into `item.title` when no
// real title exists (makeLocalCapture / normalizers). They are NOT sent to the backend (the upload
// uses `draft.detail`/the file only). The rendered, translatable title is produced by
// `captureDraftLabel(item, sequence, t)`, which detects these defaults and re-keys them via `t`.
export const titleByType: Record<CaptureDraft["kind"], string> = {
  audio: "Audio note",
  photo: "Photo",
  note: "Written note",
};

/** Translator key for a default capture title, so a stored English default renders in the UI language. */
const TITLE_KEY_BY_TYPE: Record<CaptureDraft["kind"], string> = {
  audio: "model.title.audio",
  photo: "model.title.photo",
  note: "model.title.note",
};

/** Map an English default `titleByType` value back to its translator key (else "" if it's a real title). */
function defaultTitleKey(title: string): string {
  const trimmed = title.trim();
  for (const kind of Object.keys(titleByType) as Array<CaptureDraft["kind"]>) {
    if (titleByType[kind] === trimmed) return TITLE_KEY_BY_TYPE[kind];
  }
  return "";
}

export const detailByType: Record<CaptureDraft["kind"], string> = {
  audio: "Clinical audio saved on this device. I'll organize it when connection returns.",
  photo: "Clinical photo saved on this device. I'll organize it when connection returns.",
  note: "Typed note saved on this device. I'll organize it when connection returns.",
};

export const nowLabel = () =>
  appDateTimeFormat({ hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());

export function createClientId() {
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

export function mergeSessionItems(existing: CaptureSession | null | undefined, incoming: CaptureSession, replaceLocalItemId?: string) {
  const incomingItems = incoming.items;
  const patientContext = existing && shouldPreservePatientContext(existing, incoming) ? patientContextFrom(existing) : {};
  const reportContext = existing && shouldKeepStaleReport(existing, incoming) ? { report: existing.report } : {};
  if (!existing?.items.length) return { ...incoming, ...patientContext, ...reportContext, items: incomingItems };

  const modelContext = preservedReportModelContext(existing, incoming);
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
  return { ...incoming, ...patientContext, ...reportContext, ...modelContext, items: merged };
}

export function mergeCaptureItemsPreservingPreview(existingItems: CaptureItem[], incomingItems: CaptureItem[]) {
  const mergedItems = incomingItems.map((incomingItem) => {
    const existingItem = existingItems.find(
      (item) =>
        item.id === incomingItem.id ||
        (incomingItem.clientCaptureId && item.clientCaptureId === incomingItem.clientCaptureId),
    );
    if (!existingItem?.sourceUrl) return incomingItem;
    return {
      ...incomingItem,
      sourceUrl: existingItem.sourceUrl,
      contentType: existingItem.contentType || incomingItem.contentType,
    };
  });
  existingItems.forEach((existingItem) => {
    const stillLocal = isLocalCaptureItem(existingItem) || existingItem.status === "saved" || existingItem.status === "syncing";
    const replacedByBackend = mergedItems.some(
      (item) =>
        item.id === existingItem.id ||
        (existingItem.clientCaptureId && item.clientCaptureId === existingItem.clientCaptureId),
    );
    if (stillLocal && !replacedByBackend) mergedItems.push(existingItem);
  });
  return mergedItems;
}

function hasPatientContext(session: CaptureSession) {
  return Boolean(session.patientId || session.patientName || session.assignmentSource);
}

function shouldPreservePatientContext(existing: CaptureSession, incoming: CaptureSession) {
  if (!hasPatientContext(existing)) return false;
  if (!hasPatientContext(incoming)) return true;
  if (!existing.patientId || incoming.patientId !== existing.patientId) return false;
  return !incoming.patientName || !incoming.assignmentSource || existing.assignmentSource === "staff";
}

function patientContextFrom(session: CaptureSession) {
  return {
    patientId: session.patientId,
    patientName: session.patientName,
    assignmentSource: session.assignmentSource,
  };
}

function isLocalCaptureItem(item: CaptureItem) {
  return item.id.startsWith("local-capture-");
}

function shouldKeepStaleReport(existing: CaptureSession, incoming: CaptureSession) {
  return Boolean(
    existing.processingStatus?.state !== "processing" &&
      existing.report?.status !== "generating" &&
      existing.report?.isStale &&
      incoming.report?.status === "processed" &&
      !incoming.report.isStale,
  );
}

// The fixed Pro-synthesis section ids (mirrors the ai_engine's SYNTHESIS_SECTIONS). A report model
// carrying any of these IS the polished synthesis; anything else (by-type "Audio notes / Written
// notes", a "Draft report", an empty model) is the deterministic baseline / a transient draft.
const SYNTHESIZED_SECTION_IDS = new Set([
  "visit-summary",
  "concern-goals",
  "assessment",
  "treatment-performed",
  "media",
  "plan-followup",
  "aftercare",
]);

function isSynthesizedReportModel(session: CaptureSession): boolean {
  return Boolean(session.reportModel?.sections?.some((section) => SYNTHESIZED_SECTION_IDS.has(section.id) && section.blocks?.length));
}

/**
 * Keep showing the previous **synthesized** report while a freshly-added capture is still being
 * organized. Adding a capture marks the report stale and the session churns through a draft/baseline
 * model (empty → "Draft report" → by-type "Audio notes / Written notes") before the new synthesis
 * lands — rendering any of those makes the polished report visibly vanish/downgrade. So while the
 * session is still working AND `incoming` is not yet a synthesis, we hold the prior synthesized model
 * (the freshness/shimmer indicators still mark it as updating) and only swap in `incoming` once it
 * carries a fresh synthesis again. Only guards a real synthesis, so the Basic baseline is untouched.
 */
function shouldKeepPreviousReportModel(existing: CaptureSession, incoming: CaptureSession): boolean {
  if (!isSynthesizedReportModel(existing)) return false;
  if (isSynthesizedReportModel(incoming)) return false;
  const working =
    incoming.processingStatus?.state === "processing" ||
    incoming.report?.status === "generating" ||
    incoming.report?.status === "pending" ||
    incoming.report?.status === "partial" ||
    incoming.report?.isStale === true;
  return working;
}

/**
 * Report-model fields to carry over from the previous session when a freshly-added capture is still
 * processing (see {@link shouldKeepPreviousReportModel}). Used by BOTH the optimistic capture-add
 * merge and the background processing-poll merge, so the report never blanks to "Preparing…" between
 * "capture added" and "new synthesis ready". Empty object (no override) otherwise.
 */
export function preservedReportModelContext(
  existing: CaptureSession | null | undefined,
  incoming: CaptureSession,
): Partial<CaptureSession> {
  if (!existing || !shouldKeepPreviousReportModel(existing, incoming)) return {};
  // Hold the prior synthesis + its treatments — but NEVER drop a user action recorded in the incoming
  // metadata. A just-confirmed carried-forward dose (Q3) lives in `confirmed_carried_forward`; merge
  // the two sets (confirmations only accumulate) so confirming during the editing window survives the
  // hold instead of reverting to "needs confirmation".
  const existingMeta = (existing.extractedMetadata as Record<string, unknown> | null | undefined) || {};
  const incomingMeta = (incoming.extractedMetadata as Record<string, unknown> | null | undefined) || {};
  const existingConfirmed = Array.isArray(existingMeta.confirmed_carried_forward) ? existingMeta.confirmed_carried_forward : [];
  const incomingConfirmed = Array.isArray(incomingMeta.confirmed_carried_forward) ? incomingMeta.confirmed_carried_forward : [];
  const confirmed = Array.from(new Set([...existingConfirmed, ...incomingConfirmed]));
  return {
    reportModel: existing.reportModel,
    extractedMetadata: { ...existingMeta, confirmed_carried_forward: confirmed } as CaptureSession["extractedMetadata"],
  };
}

export function isLocalSessionId(sessionId: string) {
  return sessionId.startsWith("local-session-");
}

// A patient id that only exists client-side (offline-created, AI-mock, or the current-session
// placeholder) — it has no backend row yet, so the outbox must resolve/create a real one before
// assigning. Shared by the outbox engine and the session-action layer.
export function isLocalAssignmentPatient(patientId: string) {
  return patientId.startsWith("mock-") || patientId.startsWith("local-patient-") || patientId === "current-session-patient";
}

export function backendSessionIdFromCurrent(currentSession: CaptureSession | null, intoNew: boolean) {
  if (intoNew || !currentSession || isLocalSessionId(currentSession.id)) return undefined;
  return currentSession.id;
}

export function withoutLocalPreview(item: CaptureItem) {
  const { sourceUrl, ...rest } = item;
  return sourceUrl?.startsWith("blob:") ? rest : item;
}

/**
 * Creates the durable local representation used for optimistic UI and later
 * upload. Local IDs remain stable until the backend mapping is known.
 */
export function makeLocalCapture(
  draft: CaptureDraft,
  currentSession: CaptureSession | null,
  intoNew: boolean,
  tenantId?: string,
): PendingCapture {
  const time = nowLabel();
  const now = new Date().toISOString();
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
    clientCaptureId,
    capturedAt: now,
    fileName: draft.filename,
    sourceName: draft.filename,
    status: "saved",
    duration: draft.kind === "audio" ? metadataString(draft.metadata?.duration) : undefined,
    transcript: draft.kind === "audio" ? metadataString(draft.metadata?.transcript) : undefined,
    caption: draft.kind === "photo" ? metadataString(draft.metadata?.caption) : undefined,
    contentType: draft.file.type || "application/octet-stream",
  };
  const session: CaptureSession =
    !intoNew && currentSession
      ? {
          ...currentSession,
          updatedAt: now,
          capturedAt: currentSession.capturedAt || now,
          status: currentSession.status === "verified" ? "reopened" : currentSession.status,
          report: currentSession.report
            ? {
                ...currentSession.report,
                status: "partial",
                isStale: true,
              }
            : currentSession.report,
          items: [...currentSession.items.map(withoutLocalPreview), item],
        }
      : {
          id: localSessionId,
          label: `Session ${time}`,
          time,
          dateLabel: "Today",
          createdAt: now,
          updatedAt: now,
          capturedAt: now,
          duration: "just now",
          summary: "Saved on this device. I'll organize it when connection returns.",
          status: "draft",
          reviewReason: "Saved on this device",
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

function metadataString(value: unknown) {
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function sessionWithLocalPreview(session: CaptureSession, itemId: string, file: Blob) {
  const sourceUrl = URL.createObjectURL(file);
  return {
    ...session,
    items: session.items.map((item) => (item.id === itemId ? { ...item, sourceUrl } : item)),
  };
}

/**
 * Rehydrates browser-only sessions from the outbox so captures survive reloads
 * before they have backend IDs.
 */
export function sessionsFromPending(captures: PendingCapture[]) {
  const grouped = new Map<string, CaptureSession>();
  captures.forEach((capture) => {
    const existing = grouped.get(capture.localSessionId);
    const item = {
      ...capture.item,
      status: capture.retryCount > 0 ? ("saved" as const) : capture.item.status,
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

// --- Pure capture/report/assignment helpers (moved verbatim from components/CaptureScreen.tsx) ---
export function patientDetailRows(info: StructuredPatientInformation | null | undefined, t: Translator): Array<[string, string]> {
  if (!info || info.status !== "assigned") return [];
  // Field labels reuse the existing report.field.* catalog (the same labels the report's patient rows
  // use); the VALUES are patient content shown verbatim.
  return ([
    [t("report.field.nationalId"), info.nationalId],
    [t("report.field.phone"), info.phone],
    [t("report.field.dob"), info.dateOfBirth],
  ] as Array<[string, string | null | undefined]>).filter((row): row is [string, string] => Boolean(row[1]));
}

export function detectedSessionPatients(session: CaptureSession, excludeId?: string): PatientSummary[] {
  // Patients that surfaced in this session (assigned, matched, suggested, or candidate) — the
  // "smart" suggestions to show first, instead of an arbitrary search list.
  const out: PatientSummary[] = [];
  const seen = new Set<string>();
  const push = (id: string, displayName: string, nationalId?: string) => {
    if (!id || !displayName || id === excludeId || seen.has(id)) return;
    seen.add(id);
    out.push({ id, displayName, nationalId: nationalId || null, lastVisit: null });
  };
  const timeline = metadataRecord(session.extractedMetadata).patient_assignment_timeline;
  if (Array.isArray(timeline)) {
    for (const raw of timeline) {
      const event = metadataRecord(raw);
      push(metadataDisplay(event.patientId), metadataDisplay(event.displayName));
    }
  }
  for (const item of session.items || []) {
    const meta = metadataRecord(item.metadata);
    const candidate = metadataRecord(meta.patient_match_candidate);
    push(metadataDisplay(candidate.patientId), metadataDisplay(candidate.displayName) || suggestionNameFromInformation(candidate), suggestionNationalId(candidate));
    if (Array.isArray(candidate.candidateSet)) {
      for (const raw of candidate.candidateSet) {
        const entry = metadataRecord(raw);
        push(metadataDisplay(entry.patientId), metadataDisplay(entry.displayName));
      }
    }
    const action = metadataRecord(meta.ai_patient_action);
    push(metadataDisplay(action.patientId), metadataDisplay(action.displayName));
  }
  return out;
}

export function currentSessionPatient(session: CaptureSession, t: Translator) {
  if (!session.patientName && !session.patientId) return [];
  return [
    {
      id: session.patientId || "current-session-patient",
      displayName: session.patientName || t("model.patient.assigned"),
      nationalId: session.patientId || null,
      lastVisit: session.report?.updatedAt || null,
    },
  ];
}

export function filterPatientMatches(patients: PatientSummary[], query: string) {
  if (!query) return patients;
  const normalizedQuery = query.toLowerCase();
  return patients.filter((patient) =>
    [patient.displayName, patient.nationalId || "", patient.phone || ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
  );
}

export function mergePatientMatches(primary: PatientSummary[], secondary: PatientSummary[]) {
  const seen = new Set<string>();
  return [...primary, ...secondary].filter((patient) => {
    const key = patient.id || `${patient.displayName}:${patient.nationalId || patient.phone || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function samePatientSummary(left: PatientSummary, right: PatientSummary) {
  if (left.id && right.id && left.id === right.id) return true;
  const leftName = left.displayName.trim().toLowerCase();
  const rightName = right.displayName.trim().toLowerCase();
  if (leftName && rightName && leftName === rightName) return true;
  return Boolean(left.nationalId && right.nationalId && left.nationalId === right.nationalId);
}

export function patientIdentifierLabel(patient: PatientSummary, t: Translator) {
  if (patient.phone) return maskPhone(patient.phone);
  if (patient.nationalId) return t("model.patient.idMasked", { id: maskIdentifier(patient.nationalId) });
  return t("model.patient.existing");
}

export function maskIdentifier(value: string) {
  const digits = value.replace(/\D/g, "");
  if (digits.length < 8) return value;
  return `${digits.slice(0, 4)}....${digits.slice(-4)}`;
}

export function maskPhone(value: string) {
  const visible = value.slice(0, Math.max(0, value.length - 4));
  return `${visible}....`;
}

export function formatLastVisit(value: string | null | undefined, t: Translator) {
  if (!value) return t("model.patient.notRecorded");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return appDateTimeFormat({ month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function captureOutOfContext(item: CaptureItem): boolean {
  const meta = metadataRecord(item.metadata);
  const marker = metadataRecord(meta.out_of_context);
  // A staff "Mark relevant" override clears the AI marker (see backend update_capture).
  if (marker.overridden_by_staff === true) return false;
  if (marker.present === true) return true;
  if ("present" in marker) return false;
  const intents = metadataRecord(metadataRecord(meta.ai_processing).intents);
  return metadataRecord(intents.out_of_context).present === true;
}

export function suggestionNameFromInformation(candidate: Record<string, unknown>): string {
  const info = metadataRecord(candidate.patientInformation);
  return metadataDisplay(info.standardized_display_name || info.raw_mentioned_name || info.full_name);
}

export function suggestionNationalId(candidate: Record<string, unknown>): string | undefined {
  const info = metadataRecord(candidate.patientInformation);
  return metadataDisplay(info.national_id) || undefined;
}

export function reportFreshness(
  session: CaptureSession | null,
  isPro?: boolean,
): { current: boolean; included: number; pending: number; setAside: number } | null {
  if (!isPro) return null;
  const inContext = (session?.items || []).filter((item) => !captureOutOfContext(item));
  if (!inContext.length) return null;
  const pending = inContext.filter(
    (item) => metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status) !== "added",
  );
  const summary = metadataRecord(metadataRecord(session?.extractedMetadata).report_contribution_summary);
  const setAside = Number(summary.set_aside);
  return {
    current: pending.length === 0,
    included: inContext.length - pending.length,
    pending: pending.length,
    setAside: Number.isFinite(setAside) && setAside > 0 ? setAside : 0,
  };
}

/**
 * Calm, persistent "AI is still organizing" notice for Pro. The backend flips the session's
 * processingStatus to `state="processing"` + `stage="organizing"` while a real Pro synthesis job is
 * in flight (even though the deterministic baseline already reads complete), so the report stays
 * readable while we signal AI is still working. Never set for Basic / gateway-less (no such job).
 */
export function aiOrganizingNotice(t: Translator): string {
  return t("model.status.aiOrganizing");
}

export function sessionAiOrganizing(session: CaptureSession | null): boolean {
  return session?.processingStatus?.state === "processing" && session?.processingStatus?.stage === "organizing";
}

export function reportUpdatingLabel(session: CaptureSession | null, t: Translator): string {
  // While AI is organizing, the captures are already in the baseline — the work is the synthesis,
  // not folding captures in — so show the calm AI notice instead of a per-capture "Updating for…".
  if (sessionAiOrganizing(session)) return aiOrganizingNotice(t);
  const pending = (session?.items || []).filter((item) => {
    const status = metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status);
    return status === "pending" || status === "updating" || item.status === "processing" || item.status === "uploaded";
  });
  if (!pending.length) return t("model.status.updatingReport");
  const labels = pending.slice(0, 2).map((item, index) => captureDraftLabel(item, index + 1, t));
  const suffix = pending.length > 2 ? ` +${pending.length - 2}` : "";
  return t("model.status.updatingFor", { labels: `${labels.join(", ")}${suffix}` });
}

export function patientInformationFromSession(session: CaptureSession | null, t: Translator): StructuredPatientInformation | null {
  if (!session?.patientId && !session?.patientName) return { status: "unassigned" };
  return {
    status: "assigned",
    patientId: session.patientId || null,
    displayName: session.patientName || session.patientId || t("model.patient.assigned"),
  };
}

export function workspaceReportState(
  session: CaptureSession | null,
  t: Translator,
): { badge: string; detail: string; kind: "partial" | "structured" | "verified"; label: string; tone: "neutral" | "blue" | "green" | "amber" } {
  const stageLabel = nonTechnicalStageLabel(session?.processingStatus, t);
  if (!session) {
    return {
      badge: t("model.report.emptyBadge"),
      detail: t("model.report.emptyDetail"),
      kind: "partial",
      label: t("model.report.emptyLabel"),
      tone: "neutral",
    };
  }
  if (session.report?.isStale) {
    return {
      badge: t("model.report.draftBadge"),
      detail: t("model.report.draftUpdatedDetail"),
      kind: "partial",
      label: t("model.report.draftUpdatedLabel"),
      tone: "blue",
    };
  }
  if (session.report?.status === "generating" || session.processingStatus?.state === "processing") {
    return { badge: t("model.report.updatingBadge"), detail: stageLabel, kind: "partial", label: t("model.report.updatingLabel"), tone: "blue" };
  }
  if (session.complete) {
    return { badge: t("model.report.completeBadge"), detail: t("model.report.completeDetail"), kind: "verified", label: t("model.report.completeLabel"), tone: "green" };
  }
  if (session.report?.status === "processed") {
    return {
      badge: t("model.report.structuredBadge"),
      detail: t("model.report.structuredDetail"),
      kind: "structured",
      label: t("model.report.structuredLabel"),
      tone: "green",
    };
  }
  if (session.report?.status === "failed" || sessionUxState(session.status) === "failed") {
    return { badge: t("model.report.attentionBadge"), detail: t("model.report.attentionDetail"), kind: "partial", label: t("model.report.attentionLabel"), tone: "amber" };
  }
  if (isLocalSessionId(session.id) || sessionUxState(session.status) === "capturing") {
    return {
      badge: session.items.length ? t("model.report.partialBadge") : t("model.report.emptyBadge"),
      detail: session.items.length ? t("model.report.partialDetail") : t("model.report.emptyDetailShort"),
      kind: "partial",
      label: session.items.length ? t("model.report.partialLabel") : t("model.report.emptyLabel"),
      tone: session.items.length ? "blue" : "neutral",
    };
  }
  return { badge: t("model.report.structuredBadge"), detail: t("model.report.structuredDetail"), kind: "structured", label: t("model.report.structuredLabel"), tone: "green" };
}

export function workspaceStructuredReportCopy(session: CaptureSession | null) {
  const reportBody = session?.report?.body || session?.generatedReport;
  if (reportBody) return reportBody.split(/\n{2,}/).map((line) => line.trim()).filter(Boolean);
  return [];
}

export function captureDraftLabel(item: CaptureItem, sequence: number, t: Translator) {
  if (item.title?.trim()) {
    // A stored default title ("Audio note"/"Photo"/"Written note") renders in the UI language; a
    // real/custom title (clinician- or backend-authored content) is shown verbatim.
    const key = defaultTitleKey(item.title);
    return key ? t(key) : item.title.trim();
  }
  if (item.type === "audio" || item.type === "voice") return t("model.label.audioN", { n: sequence });
  if (item.type === "photo") return t("model.label.photoN", { n: sequence });
  return t("model.label.noteN", { n: sequence });
}

export function draftCaptureText(item: CaptureItem) {
  const generated = generatedTextForReport(item);
  if (generated) return generated;
  if (item.type === "audio" || item.type === "voice") return "Transcribing audio...";
  if (item.type === "photo") return "Photo added, analyzing...";
  return item.detail || "Text note added to the draft.";
}

export function generatedTextForReport(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  // Notes are a pure passthrough (no AI decoration): a staff-edited note wins, else the raw note.
  if (item.type === "note") {
    return metadataText(metadataRecord(metadata.note).text) || item.detail;
  }
  const generated = item.type === "audio" || item.type === "voice" ? metadata.transcript : metadata.caption || metadata.ocr;
  const generatedRecord = metadataRecord(generated);
  const status = metadataDisplay(generatedRecord.status || generatedRecord.state).toLowerCase();
  if (status === "processing" || status === "queued" || status === "running") return "";
  const text =
    metadataText(generated) ||
    metadataText(generatedRecord.text) ||
    metadataText(generatedRecord.transcript) ||
    metadataText(generatedRecord.caption);
  if (text) return text;
  // Photos carry no AI caption in Basic (or when captioning is unavailable) — return nothing so the
  // UI offers a manual "Add caption" instead of a placeholder.
  return "";
}

/** Display direction for transcript/caption/note text: RTL when it's predominantly
 * Persian/Arabic script (covers farsi and mixed-farsi), otherwise LTR. */
export function textDirection(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

/** A low-confidence / flagged photo caption the backend raised for review (§7): the reason to show
 * on the capture's "Needs review" chip, or "" when there's nothing to review. */
export function captureNeedsReview(item: CaptureItem, t: Translator): string {
  if (item.type !== "photo") return "";
  const marker = metadataRecord(metadataRecord(item.metadata).needs_review);
  if (marker.present !== true) return "";
  // A backend-provided reason is content (shown verbatim); the generic fallback is chrome.
  return metadataText(marker.reason) || t("model.review.lowConfidenceCaption");
}

/** The model-authored Markdown display variant of a photo caption (the clean `text` is for AI jobs;
 * this `display` has the important words **bold** for the UI). "" when there's no distinct display. */
export function captionDisplay(item: CaptureItem): string {
  if (item.type !== "photo") return "";
  return metadataText(metadataRecord(metadataRecord(item.metadata).caption).display);
}

export function nonTechnicalStageLabel(status: SessionProcessingStatus | undefined, t: Translator) {
  if (!status || status.state !== "processing") return t("model.stage.current");
  if (status.stage === "organizing") return aiOrganizingNotice(t);
  if (status.stage === "transcripts") return t("model.stage.transcripts");
  if (status.stage === "report") return t("model.stage.report");
  if (status.stage === "findings") return t("model.stage.findings");
  if (status.stage === "summary") return t("model.stage.summary");
  // status.label is a backend-authored fallback (content), shown verbatim when present.
  return status.label || t("model.stage.default");
}

export function workspaceReportMilestones(session: CaptureSession | null, state: ReturnType<typeof workspaceReportState>, t: Translator) {
  const milestones: Array<{ key: "draft" | "structured" | "complete"; label: string }> = [
    { key: "draft", label: t("model.milestone.draft") },
    { key: "structured", label: t("model.milestone.structured") },
    { key: "complete", label: t("model.milestone.complete") },
  ];
  if (state.kind === "verified") {
    return milestones.map(({ key, label }) => ({
      label,
      state: "done",
      className: key === "complete" ? "done verified" : "done",
    }));
  }
  if (state.kind === "structured") {
    return [
      { label: milestones[0].label, state: "done", className: "done" },
      { label: milestones[1].label, state: "done", className: "done" },
      { label: milestones[2].label, state: "current", className: "current" },
    ];
  }
  return milestones.map(({ label }, index) => ({
    label,
    state: index === 0 ? "current" : "next",
    className: index === 0 ? "current" : "next",
  }));
}

export function workspaceReportUpdatedLabel(value: string | null | undefined, t: Translator) {
  if (!value) return t("model.report.liveDraftUpdates");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("model.report.recentlyUpdated");
  return t("model.report.updatedAt", { time: appDateTimeFormat({ hour: "2-digit", minute: "2-digit", hour12: false }).format(date) });
}

export function sessionSummaryStatusChip(session: CaptureSession | null, t: Translator) {
  // AI still organizing wins over "Complete": the deterministic baseline is current, but the
  // synthesized report is still on its way, so the header reads "Organizing" (not a false Complete).
  if (sessionAiOrganizing(session)) {
    return { checked: false, label: t("model.chip.organizing"), tone: "info" };
  }
  if (session?.complete) {
    return { checked: true, label: t("model.chip.complete"), tone: "success" };
  }
  if (session?.report?.status === "processed" && !session.report.isStale) {
    return { checked: false, label: t("model.chip.generated"), tone: "success" };
  }
  if (session?.processingStatus?.state === "processing" || session?.report?.status === "generating") {
    return { checked: false, label: t("model.chip.generating"), tone: "info" };
  }
  return { checked: false, label: session?.items.length ? t("model.chip.draft") : t("model.chip.ready"), tone: "neutral" };
}

/** True when a session title is the generic "no real title yet" placeholder (drives the Pro fallback
 * to {@link lightSessionTitle}). Language-independent: detects the empty/local case the same way
 * {@link sessionSummaryTitle} produces its placeholder, so it survives translation. */
export function isPlaceholderSessionTitle(session: CaptureSession | null, isHistorical: boolean): boolean {
  if (isHistorical) return !session?.label;
  const title = (session?.report?.title || session?.label || "").trim();
  return !(title && session && !isLocalSessionId(session.id));
}

export function sessionSummaryTitle(session: CaptureSession | null, isHistorical: boolean, t: Translator) {
  if (isHistorical) return session?.label || t("model.title.sessionReview");
  const title = (session?.report?.title || session?.label || "").trim();
  if (title && session && !isLocalSessionId(session.id)) return title;
  return t("model.title.currentSession");
}

export const ORDINAL_WORDS = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];
export function ordinalWord(n: number, t: Translator) {
  if (!n || n <= 0) return "";
  if (n >= 1 && n <= 10) return t(`model.ordinal.${ORDINAL_WORDS[n]}`);
  return t("model.ordinal.nth", { n });
}

/** Basic light-header title: "{patient}'s {Nth} session" when assigned, else the session date+time. */
export function lightSessionTitle(session: CaptureSession | null, ordinal: number | null, t: Translator) {
  if (!session) return t("model.title.newSession");
  if (session.patientName || session.patientId) {
    const name = session.patientName || t("model.patient.fallback");
    const word = ordinal ? ordinalWord(ordinal, t) : "";
    return word ? t("model.title.patientNthSession", { name, ordinal: word }) : t("model.title.patientSession", { name });
  }
  return sessionDateTimeLabel(session.capturedAt || session.createdAt, session.time) || t("model.title.newSession");
}

/** A capture not yet confirmed on the backend (queued, in-flight, or failed). */
export function captureNotSynced(status?: CaptureItem["status"]) {
  return status === "saved" || status === "syncing" || status === "uploading" || status === "failed";
}

export function sessionPatientName(session: CaptureSession | null, t: Translator) {
  return session?.patientName || t("model.patient.unassigned");
}

export function aiPatientActionForSession(session: CaptureSession | null) {
  if (!session?.extractedMetadata) return null;
  const action = metadataRecord(session.extractedMetadata.ai_patient_action);
  return Object.keys(action).length ? action : null;
}

/**
 * Whether an `ai_patient_action` is a blocker awaiting identity verification — i.e. an AI-*created*
 * patient still flagged `needsVerification`. The SINGLE source of truth for both the verify-bar count
 * (`patientVerifyNeeded`) and the resolver that renders it (`AiCreatedPatientPanel`), so the count can
 * never diverge from a reachable resolver (INV-SILENT: every counted blocker has a resolver on screen).
 * A merely *matched* action, or a created patient already `verified`, is NOT a blocker — it must not
 * inflate the count (the phantom-verify-count bug: the count read "an action exists", the panel read
 * "created + unverified"). Mirrors `AiCreatedPatientPanel`'s render guard exactly.
 */
export function aiCreatedPatientNeedsVerification(
  action: Record<string, unknown> | null,
  session: CaptureSession | null,
): boolean {
  if (!action) return false;
  const patientId = metadataDisplay(action.patientId) || session?.patientId || "";
  if (!patientId || action.action !== "created_and_assigned") return false;
  const status = metadataDisplay(action.status);
  return action.needsVerification !== false && status !== "verified";
}

export function activePatientAssignmentActionForSession(session: CaptureSession | null) {
  if (!session?.extractedMetadata) return null;
  const action = metadataRecord(session.extractedMetadata.active_patient_assignment_action || session.extractedMetadata.ai_patient_action);
  return Object.keys(action).length ? action : null;
}

export type AssignmentCandidate = { patientId: string; displayName: string };

/** Derive each capture's assignment candidate from the session's assignment timeline. */
export function sessionAssignmentCandidates(session: CaptureSession | null): {
  activeCaptureId: string;
  activePatientId: string;
  byCapture: Record<string, AssignmentCandidate>;
} {
  const action = metadataRecord(activePatientAssignmentActionForSession(session));
  const actionMeta = metadataRecord(action.actionMetadata);
  const activeCaptureId = metadataDisplay(action.captureId || action.basisCaptureId || actionMeta.basisCaptureId);
  const activePatientId = metadataDisplay(action.patientId || actionMeta.patientId);
  const byCapture: Record<string, AssignmentCandidate> = {};
  const timeline = metadataRecord(session?.extractedMetadata).patient_assignment_timeline;
  if (Array.isArray(timeline)) {
    for (const raw of timeline) {
      const event = metadataRecord(raw);
      const captureId = metadataDisplay(event.captureId);
      const patientId = metadataDisplay(event.patientId);
      if (captureId && patientId) byCapture[captureId] = { patientId, displayName: metadataDisplay(event.displayName) };
    }
  }
  return { activeCaptureId, activePatientId, byCapture };
}

/** The reassignment a capture offers when it is not the current source (a switchable alternate). */
export function alternateCandidateForCapture(
  candidates: ReturnType<typeof sessionAssignmentCandidates>,
  captureId: string,
): AssignmentCandidate | null {
  const candidate = candidates.byCapture[captureId];
  if (!candidate) return null;
  if (captureId === candidates.activeCaptureId) return null;
  if (candidate.patientId === candidates.activePatientId) return null;
  return candidate;
}

export function sessionSummaryCreatedLabel(session: CaptureSession | null, t: Translator) {
  if (!session) return t("model.session.createdNow");
  const source = session.capturedAt || session.createdAt || session.dateLabel || session.time;
  const label = sessionDateTimeLabel(source, session.time);
  return label ? t("model.session.createdAt", { label }) : t("model.session.createdRecently");
}

export function sessionSummaryUpdatedLabel(session: CaptureSession | null, t: Translator) {
  const source = session?.report?.updatedAt || session?.processingStatus?.updatedAt || session?.time;
  const label = sessionDateTimeLabel(source);
  return label ? t("model.session.updatedAt", { label }) : t("model.session.updatedRecently");
}

export function sessionDateTimeLabel(source?: string | null, fallbackTime?: string | null) {
  if (!source && !fallbackTime) return "";
  const date = source ? new Date(source) : null;
  if (date && !Number.isNaN(date.getTime())) {
    const dateLabel = appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
    const timeLabel = appDateTimeFormat({ hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
    return `${dateLabel} · ${timeLabel}`;
  }
  const datePart = source && !source.match(/\b\d{1,2}:\d{2}\b/) ? source : "";
  const time = source?.match(/\b\d{1,2}:\d{2}\b/)?.[0] || fallbackTime || "";
  return [datePart, time].filter(Boolean).join(" · ");
}

/** Performed treatments extracted by the Pro synthesis (extractedMetadata.treatments), display-shaped. */
export function workspaceTreatments(session: CaptureSession | null): SessionTreatment[] {
  const raw = metadataRecord(session?.extractedMetadata).treatments;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === "object"))
    .map((entry) => ({
      area: metadataText(entry.area) || null,
      product: metadataText(entry.product) || null,
      brand: metadataText(entry.brand) || null,
      quantity: typeof entry.quantity === "number" ? entry.quantity : null,
      unit: metadataText(entry.unit) || null,
      quantityText: metadataText(entry.quantityText) || null,
      lot: metadataText(entry.lot) || null,
      confidence: typeof entry.confidence === "number" ? entry.confidence : null,
      carriedForward: entry.carriedForward === true,
      attributes: entry.attributes && typeof entry.attributes === "object" ? (entry.attributes as Record<string, unknown>) : null,
      sourceCaptureIds: Array.isArray(entry.sourceCaptureIds)
        ? entry.sourceCaptureIds.filter((id): id is string => typeof id === "string")
        : undefined,
      // AES-1101: the stable key a human field-edit binds to + which fields were overridden (the
      // payload already folds the human values into the row via effective_treatments).
      treatmentKey: metadataText(entry.treatmentKey) || null,
      overlayEditedFields: Array.isArray(entry.overlayEditedFields)
        ? entry.overlayEditedFields.filter((field): field is string => typeof field === "string")
        : undefined,
    }))
    .filter((treatment) => treatment.area || treatment.product);
}

/** Human field-edit overlay entries on this session's treatments (AES-1101) — the aiValue/attribution
 *  lookup behind the "Edited by you" chip, provenance subline, and Revert-to-AI. */
export function sessionTreatmentOverlay(session: CaptureSession | null): TreatmentOverlayEntry[] {
  const raw = metadataRecord(session?.extractedMetadata).treatment_overlay;
  if (!Array.isArray(raw)) return [];
  const entries: TreatmentOverlayEntry[] = [];
  for (const value of raw) {
    const record = metadataRecord(value);
    const treatmentKey = metadataText(record.treatmentKey);
    const field = metadataText(record.field);
    const val = metadataText(record.value);
    if (!treatmentKey || !field || !val || (record.op && record.op !== "edit")) continue;
    entries.push({
      treatmentKey,
      field,
      value: val,
      aiValue: metadataText(record.aiValue) || null,
      editedByUserId: metadataText(record.editedByUserId) || null,
      editedAt: metadataText(record.editedAt) || null,
      parked: record.parked === true,
    });
  }
  return entries;
}

/** Parked overlay orphans (AES-1101): edits a re-synthesis couldn't re-bind — surfaced as a review
 *  chip so a human correction is never silently lost, and re-bound when its row reappears. */
export function sessionTreatmentOverlayOrphans(session: CaptureSession | null): TreatmentOverlayEntry[] {
  const raw = metadataRecord(session?.extractedMetadata).treatment_overlay_orphans;
  if (!Array.isArray(raw)) return [];
  const entries: TreatmentOverlayEntry[] = [];
  for (const value of raw) {
    const record = metadataRecord(value);
    const treatmentKey = metadataText(record.treatmentKey);
    const field = metadataText(record.field);
    const val = metadataText(record.value);
    if (!treatmentKey || !field || !val) continue;
    entries.push({
      treatmentKey,
      field,
      value: val,
      aiValue: metadataText(record.aiValue) || null,
      editedByUserId: metadataText(record.editedByUserId) || null,
      editedAt: metadataText(record.editedAt) || null,
      parked: true,
    });
  }
  return entries;
}

// The genuine open TECHNIQUE-attribute keys a treatment row may surface as calm "label: value" lines.
// The synthesis attaches an open `attributes` map to each treatment (needleGauge, depth, device, …),
// but schema-v3 also lets the model drop STATUS / semantic keys in there (e.g. `planned_vs_performed`)
// or coded uncertainties. Those must NEVER render as a raw technique line — they flow through the calm
// review-note path (treatment_review / uncertaintyReasons) instead. So we whitelist technique keys and
// drop everything else, which keeps a normal row clean and can never leak a raw status key (R2).
const TECHNIQUE_ATTRIBUTE_KEYS = new Set<string>([
  "needlegauge", "gauge", "needle",
  "depth", "plane", "layer", "level",
  "technique", "method", "approach", "device", "tool",
  "cannula", "angle", "direction", "vector",
  "sessions", "session", "passes", "threads", "thread",
  "entrypoint", "entrypoints", "points", "injectionpoints", "injectionpoint",
  "pattern", "dilution", "concentration", "anesthesia", "anesthetic",
]);

/** Whether an open-attribute key names a genuine technique attribute (vs a status / uncertainty code). */
function isTechniqueAttributeKey(key: string): boolean {
  return TECHNIQUE_ATTRIBUTE_KEYS.has(key.replace(/[_\s-]/g, "").toLowerCase());
}

/** Human "key·value" lines for a treatment's open TECHNIQUE attributes only (needleGauge, depth, …).
 *  Status / uncertainty keys the model may place in `attributes` (planned_vs_performed, low_confidence,
 *  …) are filtered out — they are surfaced through the calm review-note path, never as a raw line (R2). */
export function treatmentAttributeLines(treatment: SessionTreatment): string[] {
  const attributes = treatment.attributes;
  if (!attributes || typeof attributes !== "object") return [];
  return Object.entries(attributes)
    .filter(([key, value]) => value != null && String(value).trim() !== "" && isTechniqueAttributeKey(key))
    .map(([key, value]) => `${key.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase()}: ${String(value)}`);
}

/** A treatment whose extraction confidence is below the trust threshold (surfaced, not hidden). */
export function isLowConfidenceTreatment(treatment: SessionTreatment): boolean {
  return typeof treatment.confidence === "number" && treatment.confidence < 0.6;
}

/**
 * Clinician-confirmation items from the Pro synthesis (extractedMetadata.treatment_review), which
 * already folds in synthesis-level uncertainties[]. Drives the report's "Needs your confirmation"
 * chips. Empty for Basic / when synthesis produced nothing to confirm.
 */
export function sessionTreatmentReview(session: CaptureSession | null): SessionTreatmentReview[] {
  const raw = metadataRecord(session?.extractedMetadata).treatment_review;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === "object"))
    .map((entry) => ({
      category: metadataText(entry.category) || "ambiguous",
      reason: metadataText(entry.reason),
      product: metadataText(entry.product) || null,
      key: metadataText(entry.key) || null,
      sourceCaptureIds: Array.isArray(entry.sourceCaptureIds)
        ? entry.sourceCaptureIds.filter((id): id is string => typeof id === "string")
        : undefined,
    }))
    .filter((item) => item.reason);
}

/** Keys (area|product) of carried-forward doses the clinician has already confirmed (Q3). */
export function sessionConfirmedCarriedForward(session: CaptureSession | null): string[] {
  const raw = metadataRecord(session?.extractedMetadata).confirmed_carried_forward;
  if (!Array.isArray(raw)) return [];
  return raw.map((entry) => metadataText(entry)).filter(Boolean);
}

/** Template ids of auto-included clinic aftercare the clinician opted OUT of for this visit. */
export function sessionDismissedAftercare(session: CaptureSession | null): string[] {
  const raw = metadataRecord(session?.extractedMetadata).dismissed_aftercare;
  if (!Array.isArray(raw)) return [];
  return raw.map((entry) => metadataText(entry)).filter(Boolean);
}

export type AftercareSelection = { templateId: string; status: "applies" | "conflicts" | "superseded"; note: string | null };

/**
 * The synthesis's intelligent aftercare matches — which clinic protocols apply this visit, and whether
 * the clinician's dictation conflicts with one. `aiRan` distinguishes "the AI matched none" (empty
 * list) from "the AI hasn't run yet" (caller falls back to the deterministic procedure match).
 */
export function sessionAftercareSelections(session: CaptureSession | null): { aiRan: boolean; selections: AftercareSelection[] } {
  const raw = metadataRecord(session?.extractedMetadata).aftercare_selections;
  if (!Array.isArray(raw)) return { aiRan: false, selections: [] };
  const selections: AftercareSelection[] = [];
  for (const entry of raw) {
    const record = metadataRecord(entry);
    const templateId = metadataText(record.templateId);
    const status = metadataText(record.status);
    if (!templateId || (status !== "applies" && status !== "conflicts" && status !== "superseded")) continue;
    selections.push({ templateId, status, note: metadataText(record.note) || null });
  }
  return { aiRan: true, selections };
}

const SAFETY_FLAG_KINDS: SafetyFlagKind[] = ["allergy", "contraindication", "consent"];

/** Stable key for a detected safety flag — MUST match the backend `patient_safety.safety_flag_key`. */
export function safetyFlagKey(kind: string, text: string): string {
  return `${kind}|${text.trim().toLowerCase().replace(/\s+/g, " ")}`;
}

/** Safety flags (allergy/contraindication/consent) the synthesis detected for this visit, keyed. */
export function sessionSafetyFlags(session: CaptureSession | null): SafetyFlag[] {
  const raw = metadataRecord(session?.extractedMetadata).safety_flags;
  if (!Array.isArray(raw)) return [];
  const flags: SafetyFlag[] = [];
  for (const entry of raw) {
    const record = metadataRecord(entry);
    const kind = metadataText(record.kind);
    const text = metadataText(record.text);
    if (!text || !SAFETY_FLAG_KINDS.includes(kind as SafetyFlagKind)) continue;
    const sourceCaptureIds = Array.isArray(record.sourceCaptureIds)
      ? record.sourceCaptureIds.map((value) => metadataText(value)).filter(Boolean)
      : [];
    flags.push({ key: safetyFlagKey(kind, text), kind: kind as SafetyFlagKind, text, sourceCaptureIds });
  }
  return flags;
}

/** Keys of safety flags the clinician rejected this visit (opt-out user state). */
export function sessionRejectedSafetyFlags(session: CaptureSession | null): string[] {
  const raw = metadataRecord(session?.extractedMetadata).rejected_safety_flags;
  if (!Array.isArray(raw)) return [];
  return raw.map((entry) => metadataText(entry)).filter(Boolean);
}

/** Detected minus rejected — the safety flags shown by default (auto-kept). */
export function sessionKeptSafetyFlags(session: CaptureSession | null): SafetyFlag[] {
  const rejected = new Set(sessionRejectedSafetyFlags(session));
  return sessionSafetyFlags(session).filter((flag) => !rejected.has(flag.key));
}

// Cross-language synonyms per aesthetics procedure, for matching the visit's extracted treatments
// to the clinic's aftercare templates. Deterministic — the AI never authors aftercare; it only
// surfaces WHICH of the clinic's own templates fit the procedure actually performed.
const AFTERCARE_PROCEDURE_SYNONYMS: Record<string, string[]> = {
  botox: ["botox", "بوتاکس", "dysport", "دیسپورت", "xeomin", "زئومین", "neurotoxin", "نوروتاکسین"],
  filler: ["filler", "فیلر", "ژل", "gel", "juvederm", "ژوویدرم", "restylane", "رستیلین", "hyaluronic", "هیالورونیک", "voluma", "ولوما"],
  prp: ["prp", "پی آر پی", "پی‌آر‌پی", "plasma", "پلاسما"],
  mesotherapy: ["meso", "مزو", "mesotherapy", "مزوتراپی"],
  laser: ["laser", "لیزر"],
};

/**
 * IDs of the clinic's aftercare templates that match the procedures performed this visit (Pro). A
 * template matches when its procedure type or name shares a synonym with a detected treatment's
 * product/brand. Empty when nothing is detected (then the UI just shows the flat template list).
 */
export function suggestedAftercareTemplateIds(templates: AftercareTemplate[], treatments: SessionTreatment[]): Set<string> {
  const haystacks = treatments.map((treatment) => `${treatment.product || ""} ${treatment.brand || ""}`.toLowerCase());
  const detected = Object.entries(AFTERCARE_PROCEDURE_SYNONYMS)
    .filter(([, synonyms]) => haystacks.some((hay) => synonyms.some((synonym) => hay.includes(synonym))))
    .map(([key]) => key);
  const ids = new Set<string>();
  if (!detected.length) return ids;
  for (const template of templates) {
    const fields = `${template.procedureType || ""} ${template.name || ""}`.toLowerCase();
    const matched = detected.some((key) => (AFTERCARE_PROCEDURE_SYNONYMS[key] || [key]).some((synonym) => fields.includes(synonym)));
    if (matched) ids.add(template.id);
  }
  return ids;
}

/** A one-line label for a treatment (verbatim quantity/brand/lot preserved). */
export function treatmentLabel(treatment: SessionTreatment): string {
  const head = treatment.area && treatment.product ? `${treatment.area}: ${treatment.product}` : treatment.area || treatment.product || "";
  const withBrand = treatment.brand ? `${head} (${treatment.brand})` : head;
  const amount = treatment.quantityText || (treatment.quantity != null && treatment.unit ? `${treatment.quantity} ${treatment.unit}` : "");
  const withAmount = amount ? `${withBrand} — ${amount}` : withBrand;
  return treatment.lot ? `${withAmount} · lot ${treatment.lot}` : withAmount;
}

export function workspaceFindings(session: CaptureSession | null) {
  if (session?.findings?.length) return session.findings;
  const metadata = metadataRecord(session?.extractedMetadata);
  const clinical = metadataRecord(metadata.clinical_metadata);
  const patient = metadataRecord(metadata.patient_information);
  const candidates = [
    ["Patient", session?.patientName || metadataDisplay(patient.full_name)],
    ["Procedure", metadataDisplay(clinical.procedure || clinical.visit_type || metadata.visit_type)],
    ["Body area", metadataDisplay(clinical.body_area || clinical.area || metadata.body_area)],
    ["Product", metadataDisplay(clinical.product || metadata.product)],
    ["Template", metadataDisplay(session?.reportTemplateKey)],
  ];
  return candidates
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([label, value]) => ({ label, value }));
}
