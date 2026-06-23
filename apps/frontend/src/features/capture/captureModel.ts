import type { CaptureDraft, PatientSummary, PendingCapture } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, SessionProcessingStatus, SessionTreatment, SessionTreatmentReview, StructuredPatientInformation } from "../../domain/types";
import type { AftercareTemplate } from "../../domain/appTypes";
import { appDateTimeFormat } from "../../shared/lib/datetime";
import { metadataDisplay, metadataRecord, metadataText } from "./metadata";
import { sessionUxState } from "../../domain/status";

export const titleByType: Record<CaptureDraft["kind"], string> = {
  audio: "Audio note",
  photo: "Photo",
  note: "Written note",
};

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
export function patientDetailRows(info?: StructuredPatientInformation | null): Array<[string, string]> {
  if (!info || info.status !== "assigned") return [];
  return ([
    ["National ID", info.nationalId],
    ["Phone", info.phone],
    ["Date of birth", info.dateOfBirth],
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

export function currentSessionPatient(session: CaptureSession) {
  if (!session.patientName && !session.patientId) return [];
  return [
    {
      id: session.patientId || "current-session-patient",
      displayName: session.patientName || "Assigned patient",
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

export function patientIdentifierLabel(patient: PatientSummary) {
  if (patient.phone) return maskPhone(patient.phone);
  if (patient.nationalId) return `ID: ${maskIdentifier(patient.nationalId)}`;
  return "Existing patient";
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

export function formatLastVisit(value?: string | null) {
  if (!value) return "Not recorded";
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
export const AI_ORGANIZING_NOTICE = "Organizing with AI — this report will update shortly";

export function sessionAiOrganizing(session: CaptureSession | null): boolean {
  return session?.processingStatus?.state === "processing" && session?.processingStatus?.stage === "organizing";
}

export function reportUpdatingLabel(session: CaptureSession | null): string {
  // While AI is organizing, the captures are already in the baseline — the work is the synthesis,
  // not folding captures in — so show the calm AI notice instead of a per-capture "Updating for…".
  if (sessionAiOrganizing(session)) return AI_ORGANIZING_NOTICE;
  const pending = (session?.items || []).filter((item) => {
    const status = metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status);
    return status === "pending" || status === "updating" || item.status === "processing" || item.status === "uploaded";
  });
  if (!pending.length) return "Updating the report…";
  const labels = pending.slice(0, 2).map((item, index) => captureDraftLabel(item, index + 1));
  const suffix = pending.length > 2 ? ` +${pending.length - 2}` : "";
  return `Updating for ${labels.join(", ")}${suffix}…`;
}

export function patientInformationFromSession(session: CaptureSession | null): StructuredPatientInformation | null {
  if (!session?.patientId && !session?.patientName) return { status: "unassigned" };
  return {
    status: "assigned",
    patientId: session.patientId || null,
    displayName: session.patientName || session.patientId || "Assigned patient",
  };
}

export function workspaceReportState(
  session: CaptureSession | null,
): { badge: string; detail: string; kind: "partial" | "structured" | "verified"; label: string; tone: "neutral" | "blue" | "green" | "amber" } {
  const stageLabel = nonTechnicalStageLabel(session?.processingStatus);
  if (!session) {
    return {
      badge: "Empty",
      detail: "Start with audio, a photo, or a note. The draft will build here without changing screens.",
      kind: "partial",
      label: "Empty draft",
      tone: "neutral",
    };
  }
  if (session.report?.isStale) {
    return {
      badge: "Draft",
      detail: "New material has been added. Generate the structured report again when ready.",
      kind: "partial",
      label: "Draft updated",
      tone: "blue",
    };
  }
  if (session.report?.status === "generating" || session.processingStatus?.state === "processing") {
    return { badge: "Updating", detail: stageLabel, kind: "partial", label: "Report updating", tone: "blue" };
  }
  if (session.complete) {
    return { badge: "Complete", detail: "Captures processed, patient assigned, and the report is up to date.", kind: "verified", label: "Complete report", tone: "green" };
  }
  if (session.report?.status === "processed") {
    return {
      badge: "Structured",
      detail: "Structured draft is ready for review.",
      kind: "structured",
      label: "Structured report",
      tone: "green",
    };
  }
  if (session.report?.status === "failed" || sessionUxState(session.status) === "failed") {
    return { badge: "Needs attention", detail: "The latest report update did not complete. Existing captures remain available below.", kind: "partial", label: "Report needs attention", tone: "amber" };
  }
  if (isLocalSessionId(session.id) || sessionUxState(session.status) === "capturing") {
    return {
      badge: session.items.length ? "Partial" : "Empty",
      detail: session.items.length ? "Early draft from the current captures." : "Start with audio, a photo, or a note.",
      kind: "partial",
      label: session.items.length ? "Partial draft" : "Empty draft",
      tone: session.items.length ? "blue" : "neutral",
    };
  }
  return { badge: "Structured", detail: "Structured draft is ready for review.", kind: "structured", label: "Structured report", tone: "green" };
}

export function workspaceStructuredReportCopy(session: CaptureSession | null) {
  const reportBody = session?.report?.body || session?.generatedReport;
  if (reportBody) return reportBody.split(/\n{2,}/).map((line) => line.trim()).filter(Boolean);
  return [];
}

export function captureDraftLabel(item: CaptureItem, sequence: number) {
  if (item.title?.trim()) return item.title.trim();
  if (item.type === "audio" || item.type === "voice") return `Audio ${sequence}`;
  if (item.type === "photo") return `Photo ${sequence}`;
  return `Note ${sequence}`;
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
export function captureNeedsReview(item: CaptureItem): string {
  if (item.type !== "photo") return "";
  const marker = metadataRecord(metadataRecord(item.metadata).needs_review);
  if (marker.present !== true) return "";
  return metadataText(marker.reason) || "Low-confidence caption — please review.";
}

/** The model-authored Markdown display variant of a photo caption (the clean `text` is for AI jobs;
 * this `display` has the important words **bold** for the UI). "" when there's no distinct display. */
export function captionDisplay(item: CaptureItem): string {
  if (item.type !== "photo") return "";
  return metadataText(metadataRecord(metadataRecord(item.metadata).caption).display);
}

export function nonTechnicalStageLabel(status?: SessionProcessingStatus) {
  if (!status || status.state !== "processing") return "Report is staying current with the latest captures.";
  if (status.stage === "organizing") return AI_ORGANIZING_NOTICE;
  if (status.stage === "transcripts") return "Reading the source captures.";
  if (status.stage === "report") return "Drafting the clinical report.";
  if (status.stage === "findings") return "Organizing key details.";
  if (status.stage === "summary") return "Condensing the session.";
  return status.label || "Updating the report.";
}

export function workspaceReportMilestones(session: CaptureSession | null, state: ReturnType<typeof workspaceReportState>) {
  if (state.kind === "verified") {
    return ["Draft", "Structured", "Complete"].map((label) => ({
      label,
      state: "done",
      className: label === "Complete" ? "done verified" : "done",
    }));
  }
  if (state.kind === "structured") {
    return [
      { label: "Draft", state: "done", className: "done" },
      { label: "Structured", state: "done", className: "done" },
      { label: "Complete", state: "current", className: "current" },
    ];
  }
  return ["Draft", "Structured", "Complete"].map((label, index) => ({
    label,
    state: index === 0 ? "current" : "next",
    className: index === 0 ? "current" : "next",
  }));
}

export function workspaceReportUpdatedLabel(value?: string | null) {
  if (!value) return "Live draft updates as captures arrive";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently updated";
  return `Updated ${appDateTimeFormat({ hour: "2-digit", minute: "2-digit", hour12: false }).format(date)}`;
}

export function sessionSummaryStatusChip(session: CaptureSession | null) {
  // AI still organizing wins over "Complete": the deterministic baseline is current, but the
  // synthesized report is still on its way, so the header reads "Organizing" (not a false Complete).
  if (sessionAiOrganizing(session)) {
    return { checked: false, label: "Organizing", tone: "info" };
  }
  if (session?.complete) {
    return { checked: true, label: "Complete", tone: "success" };
  }
  if (session?.report?.status === "processed" && !session.report.isStale) {
    return { checked: false, label: "Generated", tone: "success" };
  }
  if (session?.processingStatus?.state === "processing" || session?.report?.status === "generating") {
    return { checked: false, label: "Generating", tone: "info" };
  }
  return { checked: false, label: session?.items.length ? "Draft" : "Ready", tone: "neutral" };
}

export function sessionSummaryTitle(session: CaptureSession | null, isHistorical: boolean) {
  if (isHistorical) return session?.label || "Session review";
  const title = (session?.report?.title || session?.label || "").trim();
  if (title && session && !isLocalSessionId(session.id)) return title;
  return "Current session";
}

export const ORDINAL_WORDS = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];
export function ordinalWord(n: number) {
  if (!n || n <= 0) return "";
  return ORDINAL_WORDS[n] || `${n}th`;
}

/** Basic light-header title: "{patient}'s {Nth} session" when assigned, else the session date+time. */
export function lightSessionTitle(session: CaptureSession | null, ordinal: number | null) {
  if (!session) return "New session";
  if (session.patientName || session.patientId) {
    const name = session.patientName || "Patient";
    const word = ordinal ? ordinalWord(ordinal) : "";
    return word ? `${name}'s ${word} session` : `${name}'s session`;
  }
  return sessionDateTimeLabel(session.capturedAt || session.createdAt, session.time) || "New session";
}

/** A capture not yet confirmed on the backend (queued, in-flight, or failed). */
export function captureNotSynced(status?: CaptureItem["status"]) {
  return status === "saved" || status === "syncing" || status === "uploading" || status === "failed";
}

export function sessionPatientName(session: CaptureSession | null) {
  return session?.patientName || "Unassigned patient";
}

export function aiPatientActionForSession(session: CaptureSession | null) {
  if (!session?.extractedMetadata) return null;
  const action = metadataRecord(session.extractedMetadata.ai_patient_action);
  return Object.keys(action).length ? action : null;
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

export function sessionSummaryCreatedLabel(session: CaptureSession | null) {
  if (!session) return "Created now";
  const source = session.capturedAt || session.createdAt || session.dateLabel || session.time;
  const label = sessionDateTimeLabel(source, session.time);
  return label ? `Created ${label}` : "Created recently";
}

export function sessionSummaryUpdatedLabel(session: CaptureSession | null) {
  const source = session?.report?.updatedAt || session?.processingStatus?.updatedAt || session?.time;
  const label = sessionDateTimeLabel(source);
  return `Updated ${label || "recently"}`;
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
    }))
    .filter((treatment) => treatment.area || treatment.product);
}

/** Human "key·value" lines for a treatment's open technique attributes (needleGauge, depth, …). */
export function treatmentAttributeLines(treatment: SessionTreatment): string[] {
  const attributes = treatment.attributes;
  if (!attributes || typeof attributes !== "object") return [];
  return Object.entries(attributes)
    .filter(([, value]) => value != null && String(value).trim() !== "")
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
