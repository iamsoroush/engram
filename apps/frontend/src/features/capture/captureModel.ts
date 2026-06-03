import type { CaptureDraft, PendingCapture } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession } from "../../domain/types";

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
  new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());

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
  return { ...incoming, ...patientContext, ...reportContext, items: merged };
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
