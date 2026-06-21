// Pure data/model helpers and types for the Clinical Memory screens.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import type { CaptureDraft, PatientMemoryDetailResponse, PatientMemoryTimelineSession, PatientMemoryRow as ApiPatientMemoryRow, PatientSummary, SmartPatientMatch, SyncHealth } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { appDateTimeFormat } from "../../../shared/lib/datetime";

export type ClinicalMemoryTab = "today" | "patients" | "needs-input";
export type PatientFilter = "recent" | "active" | "all";
export type ClinicalTone = "blue" | "green" | "amber";

export type ClinicalMemoryReturnContext = {
  tab: ClinicalMemoryTab;
  patientId?: string;
};

export type TodayCardModel = {
  session: CaptureSession;
  statusLabel: string;
  title: string;
  summary: string;
  tone: ClinicalTone;
};

export type TodayModel = {
  currentVisit?: TodayCardModel;
  isOffline: boolean;
  needsInputPreview?: TodayCardModel;
  needsInputSessions: CaptureSession[];
  recentMemory: TodayCardModel[];
  recentMemoryBadge: string;
};

export type PatientRowModel = {
  id: string;
  name: string;
  summary: string;
  memoryStatus: "ready" | "updating" | string;
  badges: string[];
  action: PatientPrimaryAction;
  actionLabel: "Continue" | "View history" | "Review summary" | "Assign patient" | "Choose patient" | "Resolve conflict" | "Verify patient" | "Review items";
  isActive: boolean;
  needsInput: boolean;
  needsInputItems: PatientNeedsInputItem[];
  latestVisitLabel: string | null;
  latestSessionId: string | null;
  activeSessionId: string | null;
  sessionCount: number;
};

export type PatientPrimaryAction = "continue" | "open-memory" | "review-summary" | "assign-patient" | "choose-patient" | "resolve-conflict" | "verify" | "review-items";

export type PatientNeedsInputItem = {
  id: string;
  sessionId: string | null;
  label: "Needs input: review summary" | "Needs input: assign patient" | "Needs input: choose patient" | "Needs input: resolve conflict" | "Needs input: verify patient";
  action: Exclude<PatientPrimaryAction, "continue" | "open-memory" | "review-items">;
  title: string;
  detail: string;
  sessionLabel: string;
  reason: string;
  sortTime: number;
};

export type NeedsInputAction = PatientNeedsInputItem["action"] | "review-storage";
export type NeedsInputKind = "assign-patient" | "choose-patient" | "verify" | "review-summary" | "review-storage" | "resolve-conflict" | "missing-field";

export type NeedsInputCardItem = {
  id: string;
  kind: NeedsInputKind;
  title: string;
  contextLabel?: string;
  session?: CaptureSession;
  sessionId?: string | null;
  sessionLabel?: string;
  needsInputSinceLabel?: string;
  explanation: string;
  action: NeedsInputAction;
  actionLabel: string;
  possiblePatients?: string[];
  tone: "amber" | "blue" | "purple";
  icon: "assign" | "match" | "summary" | "storage" | "conflict";
  sortTime: number;
};

export type StorageWarningDecision = {
  remainingBytes: number;
  usageRatio: number;
};

export function buildNeedsInputItems({
  activeSession,
  resolvedDecisionIds,
  sessions,
  storageWarning,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  storageWarning: StorageWarningDecision | null;
}): NeedsInputCardItem[] {
  const sessionItems = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session)))
    .map(needsInputCardFromSession)
    .filter((item): item is NeedsInputCardItem => Boolean(item));
  const storageItem = storageWarning
    ? [
        {
          id: "storage-warning",
          kind: "review-storage" as const,
          title: "Storage getting full",
          contextLabel: "Offline safety warning",
          explanation: "Storage is getting full. New offline captures may not be safely saved soon.",
          action: "review-storage" as const,
          actionLabel: "Review storage",
          tone: "amber" as const,
          icon: "storage" as const,
          sortTime: Date.now(),
        },
      ]
    : [];
  return [...storageItem, ...sessionItems].sort((a, b) => b.sortTime - a.sortTime);
}

export function needsInputCardFromSession(session: CaptureSession): NeedsInputCardItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const sortTime = latestSessionTime(session);
  const patientLabel = session.patientName || session.patientId;
  const base = {
    id: `${session.id}-${action}`,
    session,
    sessionId: session.id,
    sessionLabel: `Session: ${sessionTimeLabel(session)}`,
    needsInputSinceLabel: `Needs input since: ${formatSessionTime(sortTime)}`,
    sortTime,
  };
  if (action === "verify") {
    return {
      ...base,
      kind: "verify",
      title: "Verify AI-created patient",
      contextLabel: patientLabel ? `Patient: ${patientLabel}` : undefined,
      explanation: "I created this patient from the visit. Confirm the details before it enters memory.",
      action,
      actionLabel: "Verify patient",
      tone: "blue",
      icon: "match",
    };
  }
  if (action === "assign-patient") {
    return {
      ...base,
      kind: "assign-patient",
      title: "Unassigned visit",
      explanation: needsInputSummary(session),
      action,
      actionLabel: "Assign patient",
      tone: "amber",
      icon: "assign",
    };
  }
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return {
      ...base,
      kind: "choose-patient",
      title: "Patient match uncertain",
      explanation: possiblePatients.length >= 2
        ? `This visit may belong to ${formatNameList(possiblePatients)}. Please choose the correct patient.`
        : "I found a possible patient match before updating memory. Please choose the correct patient.",
      action,
      actionLabel: "Choose patient",
      possiblePatients,
      tone: "purple",
      icon: "match",
    };
  }
  if (action === "resolve-conflict") {
    return {
      ...base,
      kind: "resolve-conflict",
      title: "Conflicting patient information",
      contextLabel: patientLabel ? `Patient: ${patientLabel}` : undefined,
      explanation: "I found patient details that conflict with existing memory. Please review before I update it.",
      action,
      actionLabel: "Resolve conflict",
      tone: "amber",
      icon: "conflict",
    };
  }
  return null;
}

export function needsInputCardPresentation(action: PatientNeedsInputItem["action"]): {
  kind: NeedsInputKind;
  title: string;
  tone: NeedsInputCardItem["tone"];
  icon: NeedsInputCardItem["icon"];
  actionLabel: string;
} {
  if (action === "assign-patient") return { kind: "assign-patient", title: "Unassigned visit", tone: "amber", icon: "assign", actionLabel: "Assign patient" };
  if (action === "choose-patient") return { kind: "choose-patient", title: "Patient match uncertain", tone: "purple", icon: "match", actionLabel: "Choose patient" };
  if (action === "resolve-conflict") return { kind: "resolve-conflict", title: "Conflicting patient information", tone: "amber", icon: "conflict", actionLabel: "Resolve conflict" };
  if (action === "verify") return { kind: "verify", title: "Verify AI-created patient", tone: "blue", icon: "match", actionLabel: "Verify patient" };
  return { kind: "review-summary", title: "Summary ready for confirmation", tone: "blue", icon: "summary", actionLabel: "Review summary" };
}

export function needsInputCardFromApi(row: ApiPatientMemoryRow, item: PatientNeedsInputItem): NeedsInputCardItem {
  const presentation = needsInputCardPresentation(item.action);
  return {
    id: item.id,
    kind: presentation.kind,
    title: presentation.title,
    contextLabel: row.displayName ? `Patient: ${row.displayName}` : undefined,
    sessionId: item.sessionId,
    sessionLabel: item.sessionLabel,
    needsInputSinceLabel: item.sortTime ? `Needs input since: ${formatSessionTime(item.sortTime)}` : undefined,
    explanation: item.reason,
    action: item.action,
    actionLabel: presentation.actionLabel,
    tone: presentation.tone,
    icon: presentation.icon,
    sortTime: item.sortTime,
  };
}

export function buildTodayModel({
  activeSession,
  resolvedDecisionIds,
  sessions,
  syncHealth,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
}): TodayModel {
  const isOffline = !syncHealth.online;
  const todaySessions = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session))).filter(
    sessionTouchedToday,
  );
  const currentSession =
    (activeSession && sessionTouchedToday(activeSession) ? activeSession : null) ||
    todaySessions.find((session) => session.status === "current" || session.status === "draft" || session.status === "reopened");
  const needsInputSessions = todaySessions.filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session))).filter(needsHumanInput);
  const needsInputPreview = needsInputSessions.find((session) => session.id !== currentSession?.id) || needsInputSessions[0];
  const recentMemory = todaySessions
    .filter((session) => session.id !== currentSession?.id)
    .filter((session) => session.id !== needsInputPreview?.id)
    .filter((session) => session.patientName || session.patientId)
    .slice(0, 3)
    .map((session) => ({
      session,
      statusLabel: updatedTodayStatus(session, isOffline),
      title: sessionVisitTitle(session),
      summary: updatedTodaySummary(session),
      tone: "blue" as const,
    }));

  return {
    currentVisit: currentSession
      ? {
          session: currentSession,
          statusLabel: isOffline ? "Saved on this device" : "In progress",
          title: sessionVisitTitle(currentSession),
          summary: currentVisitSummary(currentSession, isOffline),
          tone: currentSession.patientName || currentSession.patientId ? "green" : "amber",
        }
      : undefined,
    isOffline,
    needsInputPreview: needsInputPreview
      ? {
          session: needsInputPreview,
          statusLabel: "Needs your input",
          title: needsInputTitle(needsInputPreview),
          summary: needsInputSummary(needsInputPreview),
          tone: "amber",
        }
      : undefined,
    needsInputSessions,
    recentMemory,
    recentMemoryBadge: isOffline ? `${recentMemory.length} saved on this device` : `${recentMemory.length} updated today`,
  };
}

export function buildPatientRows({
  activeSession,
  resolvedDecisionIds,
  sessions,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
}): PatientRowModel[] {
  const groups = new Map<string, CaptureSession[]>();
  uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => session.patientName || session.patientId)
    .forEach((session) => {
      const key = session.patientId || session.patientName || "Patient";
      groups.set(key, [...(groups.get(key) || []), session]);
    });

  return [...groups.entries()]
    .map(([id, patientSessions]) => {
      const sortedSessions = [...patientSessions].sort((a, b) => latestSessionTime(b) - latestSessionTime(a));
      const primarySession = sortedSessions[0];
      const name = primarySession.patientName || sortedSessions.find((session) => session.patientName)?.patientName || id;
      const activeSessions = sortedSessions.filter(isActiveVisit);
      const activeCount = activeSessions.length;
      const needsInputItems = sortedSessions
        .filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session)))
        .map(patientNeedsInputItem)
        .filter((item): item is PatientNeedsInputItem => Boolean(item));
      const needsInput = needsInputItems.length > 0;
      const complete = sortedSessions.some((session) => Boolean(session.complete));
      const primary = patientPrimaryAction({ activeCount, needsInputItems });
      return {
        id,
        name,
        summary: patientCardSummary(sortedSessions),
        memoryStatus: "ready" as const, // local fallback rows are deterministic, never "updating"
        badges: [
          // "Active session" is intentionally not shown on patient cards — live work lives in Today.
          visitCountLabel(sortedSessions.length),
          complete && !needsInput ? "Complete" : undefined,
          needsInputBadgeLabel(needsInputItems),
        ].filter((badge): badge is string => Boolean(badge)),
        action: primary.action,
        actionLabel: primary.label,
        isActive: Boolean(activeCount),
        needsInput,
        needsInputItems,
        latestVisitLabel: latestVisitLabelFromTimestamp(sessionVisitTimestamp(primarySession)),
        latestSessionId: primarySession.id,
        activeSessionId: activeSessions[0]?.id || null,
        sessionCount: sortedSessions.length,
      };
    })
    .sort((a, b) => latestSessionTimeById(b.latestSessionId, sessions, activeSession) - latestSessionTimeById(a.latestSessionId, sessions, activeSession));
}

export function patientRowFromApi(row: ApiPatientMemoryRow): PatientRowModel {
  const isActive = row.activeSessionCount > 0;
  const needsInputItems = patientNeedsInputItemsFromApi(row);
  const primary = patientPrimaryAction({ activeCount: row.activeSessionCount, needsInputItems });
  return {
    id: row.patientId,
    name: row.displayName,
    summary: row.summary || "No memory summary yet.",
    memoryStatus: row.memoryStatus === "updating" ? "updating" : "ready",
    badges: [
      // "Active session" is intentionally not shown on patient cards — live work lives in Today.
      visitCountLabel(row.sessionCount),
      row.complete && needsInputItems.length === 0 ? "Complete" : undefined,
      needsInputBadgeLabel(needsInputItems),
    ].filter((badge): badge is string => Boolean(badge)),
    action: primary.action,
    actionLabel: primary.label,
    isActive,
    needsInput: needsInputItems.length > 0,
    needsInputItems,
    latestVisitLabel: latestVisitLabelFromApi(row),
    latestSessionId: row.latestSessionId || null,
    activeSessionId: row.activeSessionId || null,
    sessionCount: row.sessionCount,
  };
}

// AES-204 — a smart-search match rendered as a minimal patient row (so it can open the detail by id).
/** Minimal placeholder row used while a patient opened by id (e.g. from the worklist) loads. */
export function patientRowStub(id: string, name: string): PatientRowModel {
  return {
    id,
    name,
    summary: "Loading patient…",
    memoryStatus: "ready",
    badges: [],
    action: "open-memory",
    actionLabel: "View history",
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

export function patientRowFromSmartMatch(match: SmartPatientMatch): PatientRowModel {
  return {
    id: match.id,
    name: match.displayName,
    summary: match.reason || "Matched patient record.",
    memoryStatus: "ready",
    badges: smartMatchBadges(match),
    action: "open-memory",
    actionLabel: "View history",
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: match.lastVisit ? `Last visit ${formatPatientLastVisit(match.lastVisit)}` : null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

export function smartMatchBadges(match: SmartPatientMatch): string[] {
  const labels: Record<string, string> = {
    national_id: "✓ national ID",
    phone: "✓ phone",
    email: "✓ email",
    name: "✓ name",
    name_prefix: "name prefix",
    name_fuzzy: "fuzzy name",
    contact_partial: "partial contact",
  };
  return match.matchedOn.map((key) => labels[key] || key).slice(0, 3);
}

export function patientPrimaryAction({
  activeCount,
  needsInputItems,
}: {
  activeCount: number;
  needsInputItems: PatientNeedsInputItem[];
}): { action: PatientPrimaryAction; label: PatientRowModel["actionLabel"] } {
  if (needsInputItems.length > 1) return { action: "review-items", label: "Review items" };
  const item = needsInputItems[0];
  if (item) return { action: item.action, label: labelForDecisionAction(item.action) };
  if (activeCount > 0) return { action: "continue", label: "Continue" };
  return { action: "open-memory", label: "View history" };
}

export function labelForDecisionAction(action: PatientNeedsInputItem["action"]): PatientRowModel["actionLabel"] {
  if (action === "review-summary") return "Review summary";
  if (action === "assign-patient") return "Assign patient";
  if (action === "choose-patient") return "Choose patient";
  if (action === "verify") return "Verify patient";
  return "Resolve conflict";
}

export function todayNeedsInputActionLabel(session: CaptureSession) {
  const action = decisionActionForSession(session);
  return action ? labelForDecisionAction(action) : "Open visit";
}

export function activeSectionBadge(session: CaptureSession) {
  const action = decisionActionForSession(session);
  return action ? needsInputLabelForAction(action) : "In progress";
}

export function needsInputBadgeLabel(items: PatientNeedsInputItem[]) {
  if (items.length > 1) return `${items.length} decisions need input`;
  return items[0]?.label;
}

export function patientNeedsInputItemsFromApi(row: ApiPatientMemoryRow): PatientNeedsInputItem[] {
  // The backend is the single source of truth for typed needs-input items. No synthesized
  // fallback: if there are no items, the patient needs nothing.
  return (row.needsInputItems || []).map((item, index) => {
    const action = decisionActionFromKind(item.kind || item.label || "");
    if (!action) return null;
    return {
      id: item.id || `${row.patientId}-needs-input-${index}`,
      sessionId: item.sessionId || row.latestSessionId || row.activeSessionId || null,
      label: needsInputLabelForAction(action),
      action,
      title: titleForDecisionAction(action),
      detail: item.reason || reasonForDecisionAction(action),
      sessionLabel: apiNeedsInputSessionLabel(row, item.createdAt),
      reason: item.reason || reasonForDecisionAction(action),
      sortTime: item.createdAt ? new Date(item.createdAt).getTime() || 0 : 0,
    };
  }).filter((item): item is PatientNeedsInputItem => Boolean(item)).sort((a, b) => b.sortTime - a.sortTime);
}

export function patientNeedsInputItem(session: CaptureSession): PatientNeedsInputItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const label = needsInputLabelForAction(action);
  return {
    id: `${session.id}-${action}`,
    sessionId: session.id,
    label,
    action,
    title: titleForSessionDecision(session, action),
    detail: needsInputSummary(session),
    sessionLabel: `Session: ${sessionTimeLabel(session)}`,
    reason: reasonForSessionDecision(session, action),
    sortTime: latestSessionTime(session),
  };
}

export function titleForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"]) {
  if (action === "review-summary") return hasMissingClinicalField(session) ? "Clinically important field missing" : "Summary ready for confirmation";
  return titleForDecisionAction(action);
}

export function titleForDecisionAction(action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "Unassigned visit";
  if (action === "choose-patient") return "Patient match uncertain";
  if (action === "resolve-conflict") return "Conflicting patient information";
  if (action === "verify") return "Verify AI-created patient";
  return "Summary ready for confirmation";
}

export function reasonForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "This visit is saved, but I do not know which patient it belongs to.";
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return possiblePatients.length >= 2
      ? `This visit may belong to ${formatNameList(possiblePatients)}. Please choose the correct patient.`
      : "I found a possible patient match before updating memory. Please choose the correct patient.";
  }
  if (action === "resolve-conflict") return "I found patient details that conflict with existing memory. Please review before I update it.";
  if (hasMissingClinicalField(session)) return "This visit is missing a clinically important detail before it becomes patient memory.";
  return "Review before it becomes part of patient memory.";
}

export function reasonForDecisionAction(action: PatientNeedsInputItem["action"]) {
  if (action === "assign-patient") return "This visit is saved, but I do not know which patient it belongs to.";
  if (action === "choose-patient") return "I found more than one possible patient match before updating memory.";
  if (action === "resolve-conflict") return "I found patient details that conflict with existing memory.";
  if (action === "verify") return "I created this patient from the visit. Confirm the details before it enters memory.";
  return "Review before it becomes part of patient memory.";
}

export function decisionActionForSession(session: CaptureSession): PatientNeedsInputItem["action"] | null {
  // Local (offline) fallback mirroring the backend's three critical needs-input categories:
  // verify (AI-created patient awaiting confirmation), choose-patient / resolve-conflict
  // (ambiguous auto-match on an unassigned visit), and assign-patient (unassigned, no candidate).
  const metadata = session.extractedMetadata as Record<string, unknown> | undefined;
  const aiAction = metadata?.ai_patient_action;
  if (aiAction && typeof aiAction === "object" && (aiAction as Record<string, unknown>).needsVerification === true) {
    return "verify";
  }
  if (session.patientId || session.patientName) return null; // assigned + confirmed → no input
  const patientMatch = metadata?.patient_match;
  const matchStatus =
    patientMatch && typeof patientMatch === "object" && "status" in patientMatch ? String((patientMatch as Record<string, unknown>).status) : "";
  if (matchStatus === "possible_match") {
    const risks = patientMatch && typeof patientMatch === "object" ? (patientMatch as Record<string, unknown>).risks : undefined;
    const hasConflict = Array.isArray(risks) && risks.some((risk) => `${risk}`.toLowerCase().includes("conflict") || `${risk}`.toLowerCase().includes("national id"));
    return hasConflict ? "resolve-conflict" : "choose-patient";
  }
  if (session.status === "unassigned") return "assign-patient";
  return null;
}

export function decisionIdForSession(session: CaptureSession) {
  return `${session.id}-${decisionActionForSession(session) || "none"}`;
}

export function decisionActionFromKind(value: string): PatientNeedsInputItem["action"] | null {
  const normalized = value.toLowerCase();
  if (isTechnicalNeedsInputText(normalized)) return null;
  if (normalized.includes("verify") || normalized.includes("verification")) return "verify";
  if (normalized.includes("conflict")) return "resolve-conflict";
  if (normalized.includes("assign") || normalized.includes("unassigned")) return "assign-patient";
  if (normalized.includes("choose") || normalized.includes("uncertain") || normalized.includes("match")) return "choose-patient";
  // Routine summary confirmation / missing-field are no longer needs-input categories.
  return null;
}

export function needsInputLabelForAction(action: PatientNeedsInputItem["action"]): PatientNeedsInputItem["label"] {
  if (action === "assign-patient") return "Needs input: assign patient";
  if (action === "choose-patient") return "Needs input: choose patient";
  if (action === "resolve-conflict") return "Needs input: resolve conflict";
  if (action === "verify") return "Needs input: verify patient";
  return "Needs input: review summary";
}

export function uniqueSessions(sessions: CaptureSession[]) {
  const seen = new Set<string>();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

export function sessionTouchedToday(session: CaptureSession) {
  return sessionTouchTimestamps(session).some(isToday);
}

export function sessionTouchTimestamps(session: CaptureSession) {
  return [
    session.updatedAt,
    session.createdAt,
    session.capturedAt,
    session.report?.updatedAt,
    session.processingStatus?.updatedAt,
    session.summaries?.updatedAt,
    session.summaries?.generatedAt,
    ...session.items.map((item) => item.capturedAt),
  ].filter((value): value is string => Boolean(value));
}

export function isToday(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

export type TimelineSessionModel = PatientMemoryTimelineSession & {
  localSession?: CaptureSession;
};

export type TimelineGroupModel = {
  label: "Today" | "Earlier this week" | "Older";
  sessions: TimelineSessionModel[];
};

export function memoryTextDirection(text: string): "rtl" | "ltr" {
  const rtl = (text.match(/[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

// ✨ provenance mark: present whenever an AI-maintained (Pro) memory artifact is shown; it pulses
// while the artifact is refreshing. Basic memory is deterministic and carries no spark.
export function possiblePatientNames(session: CaptureSession) {
  const metadata = session.extractedMetadata || {};
  const patientMatch = metadata.patient_match;
  const candidates = [
    ...namesFromUnknown((patientMatch && typeof patientMatch === "object" ? (patientMatch as Record<string, unknown>).candidates : null) || metadata.possible_patients),
    ...namesFromUnknown(metadata.patient_options),
  ];
  const matchedName =
    patientMatch && typeof patientMatch === "object" && typeof (patientMatch as Record<string, unknown>).display_name === "string"
      ? String((patientMatch as Record<string, unknown>).display_name)
      : "";
  return uniqueNames([matchedName, ...candidates]);
}

export function patientChoiceCandidates(session: CaptureSession): PatientSummary[] {
  return uniqueNames(possiblePatientNames(session)).slice(0, 6).map((name) => ({
    id: `candidate-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    displayName: name,
  }));
}

export function extractedPatientMatchHint(session: CaptureSession) {
  const metadata = session.extractedMetadata || {};
  const patientMatch = metadata.patient_match;
  if (patientMatch && typeof patientMatch === "object") {
    const record = patientMatch as Record<string, unknown>;
    const hint = [record.hint, record.reason, record.summary].find((value): value is string => typeof value === "string" && Boolean(value.trim()));
    if (hint) return sanitizePatientMatchHint(hint);
  }
  if (session.items.some((item) => item.type === "audio" || item.type === "voice")) {
    return "Audio from this visit mentions a patient name.";
  }
  return "";
}

export function sanitizePatientMatchHint(value: string) {
  return value
    .replace(/\b(confidence|score|probability)\b\s*[:=]?\s*\d+(\.\d+)?%?/gi, "")
    .replace(/\b(ai|model|job|pipeline)\b/gi, "assistant")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function namesFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        return typeof record.display_name === "string" ? record.display_name : typeof record.name === "string" ? record.name : "";
      }
      return "";
    })
    .filter(Boolean);
}

export function uniqueNames(names: string[]) {
  const seen = new Set<string>();
  return names.filter((name) => {
    const normalized = name.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

export function formatNameList(names: string[]) {
  if (names.length <= 1) return names[0] || "a possible patient";
  if (names.length === 2) return `${names[0]} or ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, or ${names[names.length - 1]}`;
}

export function filterPatientMatches(patients: PatientSummary[], query: string) {
  if (!query) return patients;
  const normalizedQuery = query.toLowerCase();
  return patients.filter((patient) =>
    [patient.displayName, patient.nationalId || "", patient.phone || ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
  );
}

export function resolverCaptureSummary(session: CaptureSession) {
  const counts = captureCounts(session);
  if (!counts.length) return "No captures";
  return counts
    .map((item) => {
      const label = item.type === "audio" ? "audio" : item.count === 1 ? item.singular : item.label;
      return `${item.count} ${label}`;
    })
    .join(", ");
}

export function patientHint(patient: PatientSummary, index: number) {
  if (patient.lastVisit) return `Recently active · ${formatPatientLastVisit(patient.lastVisit)}`;
  if (index === 0) return "Recently active";
  if (index === 1) return "Similar name mentioned";
  return "Existing patient";
}

export function formatPatientLastVisit(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (isToday(date.toISOString())) return "today";
  return appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
}

export function hasMissingClinicalField(session: CaptureSession) {
  const text = `${session.reviewReason || ""} ${JSON.stringify(session.extractedMetadata || {})}`.toLowerCase();
  return text.includes("missing") && (text.includes("clinical") || text.includes("field") || text.includes("required"));
}

export function isTechnicalNeedsInputText(value: string) {
  return [
    "ai failed",
    "ai unavailable",
    "backend unavailable",
    "backend",
    "job pending",
    "object storage",
    "retry sync",
    "retry transcription",
    "sync",
    "transcription failed",
    "upload queue",
  ].some((token) => value.includes(token));
}

export function needsHumanInput(session: CaptureSession) {
  return Boolean(decisionActionForSession(session));
}

export function needsInputTitle(session: CaptureSession) {
  const action = decisionActionForSession(session);
  if (action === "choose-patient") return "Patient match uncertain";
  if (action === "resolve-conflict") return "Conflicting patient information";
  if (action === "review-summary") return hasMissingClinicalField(session) ? "Clinically important field missing" : "Summary ready for confirmation";
  if (!session.patientName && !session.patientId) return "Unassigned visit";
  return sessionVisitTitle(session);
}

export function needsInputSummary(session: CaptureSession) {
  if (!session.patientName && !session.patientId) {
    const count = session.items.length;
    return `${count || "No"} capture${count === 1 ? "" : "s"} saved. I could not confidently attach this visit to a patient.`;
  }
  return "Review this visit before it becomes part of patient memory.";
}

export function sessionVisitTitle(session: CaptureSession) {
  const title = session.report?.title || session.reportModel?.title || sanitizeSessionLabel(session.label);
  if (title && title.toLowerCase() === "unassigned visit" && (session.patientName || session.patientId)) return "Visit";
  if (title) return title;
  if (!session.patientName && !session.patientId) return "Unassigned visit";
  return isActiveVisit(session) ? "Follow-up visit" : "Visit";
}

export function sanitizeSessionLabel(label?: string | null) {
  const trimmed = label?.trim();
  if (!trimmed) return "";
  if (/^session\s+\d{1,2}:\d{2}/i.test(trimmed)) return "Follow-up visit";
  if (/^\d{1,2}:\d{2}\s*(am|pm)?\s*-\s*capture session$/i.test(trimmed)) return "Follow-up visit";
  if (/^session$/i.test(trimmed)) return "";
  return trimmed;
}

export function updatedTodayStatus(session: CaptureSession, isOffline: boolean) {
  if (isOffline) return "Saved on this device";
  if (session.assignmentSource || session.patientName || session.patientId) return "Updated today · Patient assigned";
  return "Memory updated today";
}

export function updatedTodaySummary(session: CaptureSession) {
  const counts = captureCounts(session);
  const typeSummary = captureTypeSummary(counts);
  if (typeSummary) return `${capitalize(typeSummary)} ${countsTotal(counts) === 1 ? "was" : "were"} attached to this visit today.`;
  const summary = naturalSessionSummary(session);
  return summary || "This visit was updated today.";
}

export function visitCountLabel(count: number) {
  return `${count} visit${count === 1 ? "" : "s"}`;
}

export function currentVisitSummary(session: CaptureSession, isOffline: boolean) {
  const counts = captureCounts(session);
  const captureTotal = session.items.length;
  if (isOffline) {
    return `${captureTotal || "No"} capture${captureTotal === 1 ? "" : "s"} saved on this device. I'll organize ${captureTotal === 1 ? "it" : "them"} when connection returns.`;
  }
  if (!captureTotal) return "No captures yet. Start with audio, photo, or note.";
  const typeSummary = captureTypeSummary(counts);
  return `${captureTotal} capture${captureTotal === 1 ? "" : "s"} saved${typeSummary ? `: ${typeSummary}` : ""}. I'm preparing the visit summary.`;
}

export function patientCardSummary(sessions: CaptureSession[]) {
  const orderedSessions = [...sessions].sort((a, b) => latestSessionTime(b) - latestSessionTime(a));
  const aiSummary = orderedSessions
    .map((session) => session.summaries)
    .find((summary) => {
      if (!summary?.short) return false;
      const source = (summary.source || "").toLowerCase();
      return !source.includes("rule") && !source.includes("deterministic");
    });
  if (aiSummary?.short) return aiSummary.short;

  const ruleBased = orderedSessions.map((session) => naturalSessionSummary(session)).find(Boolean);
  if (ruleBased) return ruleBased;

  const latest = orderedSessions[0];
  if (latest && (sessionTouchTimestamps(latest).length || latest.items.length)) {
    const updated = naturalUpdatedDate(latest);
    const captureCount = latest.items.length;
    if (captureCount) return `Last updated ${updated}. ${captureCount} capture${captureCount === 1 ? "" : "s"} in the latest visit.`;
    return `Last updated ${updated}.`;
  }

  return "No memory summary yet.";
}

export function patientSessionsForDetail(patient: PatientRowModel, sessions: CaptureSession[], activeSession: CaptureSession | null) {
  return uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => session.patientId === patient.id || session.patientName === patient.name)
    .sort((a, b) => sessionVisitTimestamp(b) - sessionVisitTimestamp(a));
}

export function buildTimelineGroups(detail: PatientMemoryDetailResponse | undefined, localSessions: CaptureSession[]): TimelineGroupModel[] {
  const localById = new Map(localSessions.map((session) => [session.id, session]));
  const detailSessions = detail?.sessions.length
    ? detail.sessions.map((session) => ({ ...session, groupLabel: normalizeTimelineGroupLabel(session.groupLabel), localSession: localById.get(session.sessionId) }))
    : localSessions.map(timelineSessionFromLocal);
  const groups = new Map<TimelineGroupModel["label"], TimelineSessionModel[]>();
  detailSessions
    .sort((a, b) => timelineSortTime(b) - timelineSortTime(a))
    .forEach((session) => {
      const label = normalizeTimelineGroupLabel(session.groupLabel || timelineGroupLabel(timelineSortTime(session)));
      groups.set(label, [...(groups.get(label) || []), session]);
    });
  return (["Today", "Earlier this week", "Older"] as const)
    .map((label) => ({ label, sessions: groups.get(label) || [] }))
    .filter((group) => group.sessions.length);
}

export function timelineSessionFromLocal(session: CaptureSession): TimelineSessionModel {
  const visitTime = sessionVisitTimestamp(session);
  return {
    sessionId: session.id,
    title: sessionVisitTitle(session),
    status: session.status,
    summary: naturalSessionSummary(session) || "This visit is saved in patient memory.",
    generatedSummary: session.summaries?.short || null,
    ruleBasedSummary: null,
    captureCount: session.items.length,
    complete: Boolean(session.complete),
    needsInput: needsHumanInput(session),
    groupLabel: timelineGroupLabel(visitTime),
    sortDate: visitTime ? new Date(visitTime).toISOString() : null,
    capturedAt: session.capturedAt || session.createdAt || null,
    updatedAt: session.updatedAt || session.report?.updatedAt || session.processingStatus?.updatedAt || null,
    localSession: session,
  };
}

export function normalizeTimelineGroupLabel(label: string): TimelineGroupModel["label"] {
  if (label === "Today" || label === "Earlier this week") return label;
  return "Older";
}

export function timelineGroupLabel(timestamp: number): TimelineGroupModel["label"] {
  if (!timestamp) return "Older";
  const date = new Date(timestamp);
  if (isToday(date.toISOString())) return "Today";
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const ageDays = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) / 86400000);
  return ageDays > 0 && ageDays < 7 ? "Earlier this week" : "Older";
}

export function timelineSortTime(session: Pick<TimelineSessionModel, "sortDate" | "capturedAt" | "updatedAt">) {
  return [session.sortDate, session.capturedAt, session.updatedAt]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0] || 0;
}

export function timelineSessionTimeLabel(session: TimelineSessionModel, localSession?: CaptureSession) {
  if (localSession) return sessionTimeLabel(localSession);
  const timestamp = timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  return explicitDateTimeLabel(timestamp);
}

export function timelineUpdatedLabel(session: TimelineSessionModel, localSession?: CaptureSession) {
  const sessionTime = localSession ? sessionVisitTimestamp(localSession) : timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  const updatedTime = localSession ? latestSessionTime(localSession) : timelineSortTime({ sortDate: session.updatedAt, capturedAt: null, updatedAt: session.updatedAt });
  if (!updatedTime || !sessionTime || updatedTime - sessionTime < 60000) return "";
  if (isToday(new Date(updatedTime).toISOString()) && (localSession?.assignmentSource || localSession?.patientId)) return "Updated today · Patient assigned";
  return formatSessionTime(updatedTime);
}

export function timelineSessionStatus(session: TimelineSessionModel, localSession?: CaptureSession) {
  const action = timelineDecisionAction(session, localSession);
  if (action) return needsInputLabelForAction(action);
  if (localSession && isActiveVisit(localSession)) return "In progress";
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return "In progress";
  if (session.complete || localSession?.complete) return "Complete";
  if (localSession?.id.startsWith("local-session-")) return "Saved on this device";
  return "Saved on this device";
}

export function timelineSessionAction(session: TimelineSessionModel, localSession?: CaptureSession): { kind: "continue" | "open" | "review" | "assign"; label: string } {
  const action = timelineDecisionAction(session, localSession);
  if (action === "assign-patient" || action === "choose-patient" || action === "resolve-conflict") return { kind: "assign", label: labelForDecisionAction(action) };
  if (action === "verify") return { kind: "open", label: "Verify patient" };
  if (localSession && isActiveVisit(localSession)) return { kind: "continue", label: "Continue visit" };
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return { kind: "continue", label: "Continue visit" };
  if (session.complete || localSession?.complete) return { kind: "open", label: "Open visit" };
  return { kind: "open", label: "Open visit" };
}

export function timelineDecisionAction(session: TimelineSessionModel, localSession?: CaptureSession): PatientNeedsInputItem["action"] | null {
  if (localSession) return decisionActionForSession(localSession);
  const status = session.status.toLowerCase();
  if (status === "unassigned") return "assign-patient";
  // The backend `needsInput` flag is the 3-category source of truth; on an assigned timeline
  // session that still needs input, the only remaining category is verify.
  if (session.needsInput) return "verify";
  return null;
}

export function firstSeenLabel(detailSessions: PatientMemoryTimelineSession[] | undefined, localSessions: CaptureSession[]) {
  const timestamps = [
    ...(detailSessions || []).map((session) => timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null })),
    ...localSessions.map(sessionVisitTimestamp),
  ].filter(Boolean);
  if (!timestamps.length) return "";
  return appDateTimeFormat({ month: "short", day: "numeric", year: "numeric" }).format(new Date(Math.min(...timestamps)));
}

export function naturalSessionSummary(session: CaptureSession) {
  if (session.summaries?.short) return session.summaries.short;
  if (session.summaries?.patientHistory) return session.summaries.patientHistory;
  const summary = sanitizeSummary(session.summary);
  if (summary) return summary;
  const counts = captureCounts(session);
  const captureSummary = captureTypeSummary(counts);
  return captureSummary ? `Latest visit includes ${captureSummary}.` : "";
}

export function reviewSummaryText(session: CaptureSession) {
  return (
    naturalSessionSummary(session) ||
    "Follow-up visit focused on headache patterns, sleep quality, and next steps. Photos and an audio note were captured. Education and follow-up plan are being prepared."
  );
}

export function sanitizeSummary(summary?: string | null) {
  const trimmed = summary?.trim();
  if (!trimmed) return "";
  return trimmed.replace(/^Mock session summary:\s*/i, "");
}

export function isActiveVisit(session: CaptureSession) {
  return ["current", "draft", "reopened", "processing"].includes(session.status);
}

export function latestSessionTime(session: CaptureSession) {
  const timestamp = sessionTouchTimestamps(session)
    .map((value) => new Date(value).getTime())
    .filter((value) => !Number.isNaN(value))
    .sort((a, b) => b - a)[0];
  return timestamp || 0;
}

export function sessionVisitTimestamp(session: CaptureSession) {
  const timestamp = [session.capturedAt, session.createdAt]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))[0];
  return timestamp || latestSessionTime(session);
}

export function latestSessionTimeById(sessionId: string | null, sessions: CaptureSession[], activeSession: CaptureSession | null) {
  const session = [activeSession, ...sessions].find((candidate) => candidate?.id === sessionId);
  return session ? latestSessionTime(session) : 0;
}

export function latestVisitLabelFromApi(row: ApiPatientMemoryRow) {
  const timestamp = latestApiVisitTimestamp(row);
  return latestVisitLabelFromTimestamp(timestamp);
}

export function apiNeedsInputSessionLabel(row: ApiPatientMemoryRow, fallbackTimestamp?: string | null) {
  const timestamp = [
    row.latestSessionMetadata?.capturedAt,
    row.latestVisitAt,
    row.latestSessionMetadata?.updatedAt,
    fallbackTimestamp,
    row.updatedAt,
  ]
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0];
  if (!timestamp) return "Session: Recent visit";
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  const timeLabel = appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(date);
  return `Session: ${dateLabel} · ${timeLabel}`;
}

export function latestApiVisitTimestamp(row: ApiPatientMemoryRow) {
  const candidates = [
    row.latestVisitAt,
    row.latestSessionMetadata?.capturedAt,
    row.latestSessionMetadata?.updatedAt,
    row.updatedAt,
  ];
  return candidates
    .map((value) => (value ? new Date(value).getTime() : 0))
    .filter((value) => value && !Number.isNaN(value))
    .sort((a, b) => b - a)[0] || 0;
}

export function latestVisitLabelFromTimestamp(timestamp: number) {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  const timeLabel = appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(date);
  return `Latest visit: ${dateLabel} · ${timeLabel}`;
}

export function naturalUpdatedDate(session: CaptureSession) {
  const timestamp = latestSessionTime(session);
  if (!timestamp) return "recently";
  const date = new Date(timestamp);
  if (isToday(date.toISOString())) return "today";
  return appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
}

export function captureCounts(session: CaptureSession) {
  return [
    { label: "photos", singular: "photo", type: "photo" as const, count: session.items.filter((item) => item.type === "photo").length },
    { label: "audio", singular: "audio note", type: "audio" as const, count: session.items.filter((item) => item.type === "audio" || item.type === "voice").length },
    { label: "notes", singular: "note", type: "note" as const, count: session.items.filter((item) => item.type === "note").length },
  ].filter((item) => item.count);
}

export function captureTypeSummary(counts: ReturnType<typeof captureCounts>) {
  const parts = counts.map((item) => `${item.count} ${item.count === 1 ? item.singular : item.label}`);
  if (parts.length <= 1) return parts[0] || "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

export function countsTotal(counts: ReturnType<typeof captureCounts>) {
  return counts.reduce((total, item) => total + item.count, 0);
}

export function capitalize(value: string) {
  if (!value) return value;
  return `${value[0].toUpperCase()}${value.slice(1)}`;
}

export function sessionTimeLabel(session: CaptureSession) {
  return [session.dateLabel, session.time].filter(Boolean).join(" · ") || "Recent visit";
}

export function formatSessionTime(timestamp: number) {
  if (!timestamp) return "recently";
  return appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

export function explicitDateTimeLabel(timestamp: number) {
  if (!timestamp) return "Recent visit";
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? "Today" : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  return `${dateLabel} · ${formatSessionTime(timestamp)}`;
}

export function formatBytes(bytes: number) {
  if (!bytes) return "0 MB";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 10 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

export function avatarInitials(label: string) {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (label.toLowerCase().includes("unassigned")) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("");
}

export function captureKindLabel(kind: CaptureDraft["kind"]) {
  if (kind === "audio") return "Audio";
  if (kind === "photo") return "Take photo";
  return "Write note";
}
