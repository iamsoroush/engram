// Pure data/model helpers and types for the Clinical Memory screens.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import type { CaptureDraft, PatientMemoryDetailResponse, PatientMemoryTimelineSession, PatientMemoryRow as ApiPatientMemoryRow, PatientSummary, SmartPatientMatch, SyncHealth } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { appDateTimeFormat } from "../../../shared/lib/datetime";
import type { Translator } from "../../../shared/i18n";

/** Stable, language-independent tone for a patient-card badge (drives its CSS class, not its text). */
export type PatientBadgeKind = "needs-input" | "complete" | "neutral";

/** A patient-card badge: localized text + a stable kind the UI branches on for styling. */
export type PatientBadge = { label: string; kind: PatientBadgeKind };

// The Needs-input tab evolved into the severity-tiered "Attention" sweep (Close-the-day / AES-1004).
export type ClinicalMemoryTab = "today" | "patients" | "lists" | "attention";
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
  /** Up to 3 needs-input visits previewed inline on Today; the rest overflow to the Needs input tab. */
  needsInputPreviews: TodayCardModel[];
  needsInputSessions: CaptureSession[];
  recentMemory: TodayCardModel[];
  recentMemoryBadge: string;
};

export type PatientRowModel = {
  id: string;
  name: string;
  summary: string;
  memoryStatus: "ready" | "updating" | string;
  // `usage_limit` when a fair-use-parked capture job froze the rebuild (M-P6) — the pill then shows
  // the usage-limit state instead of an open-ended spinner. Null/absent for an ordinary rebuild.
  memoryStatusReason?: string | null;
  badges: PatientBadge[];
  action: PatientPrimaryAction;
  actionLabel: string;
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
  label: string;
  action: Exclude<PatientPrimaryAction, "continue" | "open-memory" | "review-items">;
  title: string;
  detail: string;
  /** Session time as data (no "Session:" prefix — the component renders its own localized label). */
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
  /** Patient display name as data (no "Patient:" prefix — the component renders its own label). */
  contextLabel?: string;
  session?: CaptureSession;
  sessionId?: string | null;
  /** Session time as data (no "Session:" prefix). */
  sessionLabel?: string;
  /** "Needs input since" time as data (no prefix). */
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
  t,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  storageWarning: StorageWarningDecision | null;
  t: Translator;
}): NeedsInputCardItem[] {
  const sessionItems = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session)))
    .map((session) => needsInputCardFromSession(session, t))
    .filter((item): item is NeedsInputCardItem => Boolean(item));
  const storageItem = storageWarning
    ? [
        {
          id: "storage-warning",
          kind: "review-storage" as const,
          title: t("memmodel.storage.title"),
          contextLabel: t("memmodel.storage.context"),
          explanation: t("memmodel.storage.explanation"),
          action: "review-storage" as const,
          actionLabel: t("memmodel.action.reviewStorage"),
          tone: "amber" as const,
          icon: "storage" as const,
          sortTime: Date.now(),
        },
      ]
    : [];
  return [...storageItem, ...sessionItems].sort((a, b) => b.sortTime - a.sortTime);
}

export function needsInputCardFromSession(session: CaptureSession, t: Translator): NeedsInputCardItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const sortTime = latestSessionTime(session);
  const patientLabel = session.patientName || session.patientId;
  const base = {
    id: `${session.id}-${action}`,
    session,
    sessionId: session.id,
    sessionLabel: sessionTimeLabel(session, t),
    needsInputSinceLabel: formatSessionTime(sortTime, t),
    sortTime,
  };
  if (action === "verify") {
    return {
      ...base,
      kind: "verify",
      title: t("memmodel.title.verify"),
      contextLabel: patientLabel || undefined,
      explanation: t("memmodel.reason.verify"),
      action,
      actionLabel: t("memmodel.action.verify"),
      tone: "blue",
      icon: "match",
    };
  }
  if (action === "assign-patient") {
    return {
      ...base,
      kind: "assign-patient",
      title: t("memmodel.title.assignPatient"),
      explanation: needsInputSummary(session, t),
      action,
      actionLabel: t("memmodel.action.assignPatient"),
      tone: "amber",
      icon: "assign",
    };
  }
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return {
      ...base,
      kind: "choose-patient",
      title: t("memmodel.title.choosePatient"),
      explanation: possiblePatients.length >= 2
        ? t("memmodel.reason.choosePatientNamed", { names: formatNameList(possiblePatients, t) })
        : t("memmodel.reason.choosePatient"),
      action,
      actionLabel: t("memmodel.action.choosePatient"),
      possiblePatients,
      tone: "purple",
      icon: "match",
    };
  }
  if (action === "resolve-conflict") {
    return {
      ...base,
      kind: "resolve-conflict",
      title: t("memmodel.title.resolveConflict"),
      contextLabel: patientLabel || undefined,
      explanation: t("memmodel.reason.resolveConflict"),
      action,
      actionLabel: t("memmodel.action.resolveConflict"),
      tone: "amber",
      icon: "conflict",
    };
  }
  return null;
}

export function needsInputCardPresentation(action: PatientNeedsInputItem["action"], t: Translator): {
  kind: NeedsInputKind;
  title: string;
  tone: NeedsInputCardItem["tone"];
  icon: NeedsInputCardItem["icon"];
  actionLabel: string;
} {
  if (action === "assign-patient") return { kind: "assign-patient", title: t("memmodel.title.assignPatient"), tone: "amber", icon: "assign", actionLabel: t("memmodel.action.assignPatient") };
  if (action === "choose-patient") return { kind: "choose-patient", title: t("memmodel.title.choosePatient"), tone: "purple", icon: "match", actionLabel: t("memmodel.action.choosePatient") };
  if (action === "resolve-conflict") return { kind: "resolve-conflict", title: t("memmodel.title.resolveConflict"), tone: "amber", icon: "conflict", actionLabel: t("memmodel.action.resolveConflict") };
  if (action === "verify") return { kind: "verify", title: t("memmodel.title.verify"), tone: "blue", icon: "match", actionLabel: t("memmodel.action.verify") };
  return { kind: "review-summary", title: t("memmodel.title.reviewSummary"), tone: "blue", icon: "summary", actionLabel: t("memmodel.action.reviewSummary") };
}

export function needsInputCardFromApi(row: ApiPatientMemoryRow, item: PatientNeedsInputItem, t: Translator): NeedsInputCardItem {
  const presentation = needsInputCardPresentation(item.action, t);
  return {
    id: item.id,
    kind: presentation.kind,
    title: presentation.title,
    contextLabel: row.displayName || undefined,
    sessionId: item.sessionId,
    sessionLabel: item.sessionLabel,
    needsInputSinceLabel: item.sortTime ? formatSessionTime(item.sortTime, t) : undefined,
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
  t,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  t: Translator;
}): TodayModel {
  const isOffline = !syncHealth.online;
  const todaySessions = uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session))).filter(
    sessionTouchedToday,
  );
  const currentSession =
    (activeSession && sessionTouchedToday(activeSession) ? activeSession : null) ||
    todaySessions.find((session) => session.status === "current" || session.status === "draft" || session.status === "reopened");
  const needsInputSessions = todaySessions.filter((session) => !resolvedDecisionIds.has(decisionIdForSession(session))).filter(needsHumanInput);
  // Preview up to 3 needs-input visits inline (preferring ones other than the current visit); any
  // beyond that overflow to the Needs input tab via the section's "see all" pill.
  const preferredPreviews = needsInputSessions.filter((session) => session.id !== currentSession?.id);
  const previewSessions = (preferredPreviews.length ? preferredPreviews : needsInputSessions).slice(0, 3);
  const previewIds = new Set(previewSessions.map((session) => session.id));
  const recentMemory = todaySessions
    .filter((session) => session.id !== currentSession?.id)
    .filter((session) => !previewIds.has(session.id))
    .filter((session) => session.patientName || session.patientId)
    .slice(0, 3)
    .map((session) => ({
      session,
      statusLabel: updatedTodayStatus(session, isOffline, t),
      title: sessionVisitTitle(session, t),
      summary: updatedTodaySummary(session, t),
      tone: "blue" as const,
    }));

  return {
    currentVisit: currentSession
      ? {
          session: currentSession,
          statusLabel: isOffline ? t("memmodel.status.savedOnDevice") : t("memmodel.status.inProgress"),
          title: sessionVisitTitle(currentSession, t),
          summary: currentVisitSummary(currentSession, isOffline, t),
          tone: currentSession.patientName || currentSession.patientId ? "green" : "amber",
        }
      : undefined,
    isOffline,
    needsInputPreviews: previewSessions.map((session) => ({
      session,
      statusLabel: t("memmodel.status.needsYourInput"),
      title: needsInputTitle(session, t),
      summary: needsInputSummary(session, t),
      tone: "amber" as const,
    })),
    needsInputSessions,
    recentMemory,
    recentMemoryBadge: isOffline ? t("memmodel.badge.savedOnDevice", { n: recentMemory.length }) : t("memmodel.badge.updatedToday", { n: recentMemory.length }),
  };
}

export function buildPatientRows({
  activeSession,
  resolvedDecisionIds,
  sessions,
  t,
}: {
  activeSession: CaptureSession | null;
  resolvedDecisionIds: Set<string>;
  sessions: CaptureSession[];
  t: Translator;
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
        .map((session) => patientNeedsInputItem(session, t))
        .filter((item): item is PatientNeedsInputItem => Boolean(item));
      const needsInput = needsInputItems.length > 0;
      const complete = sortedSessions.some((session) => Boolean(session.complete));
      const primary = patientPrimaryAction({ activeCount, needsInputItems }, t);
      return {
        id,
        name,
        summary: patientCardSummary(sortedSessions, t),
        memoryStatus: "ready" as const, // local fallback rows are deterministic, never "updating"
        // "Active session" is intentionally not shown on patient cards — live work lives in Today.
        badges: patientBadges({ sessionCount: sortedSessions.length, complete, needsInput, needsInputItems, t }),
        action: primary.action,
        actionLabel: primary.label,
        isActive: Boolean(activeCount),
        needsInput,
        needsInputItems,
        latestVisitLabel: latestVisitLabelFromTimestamp(sessionVisitTimestamp(primarySession), t),
        latestSessionId: primarySession.id,
        activeSessionId: activeSessions[0]?.id || null,
        sessionCount: sortedSessions.length,
      };
    })
    .sort((a, b) => latestSessionTimeById(b.latestSessionId, sessions, activeSession) - latestSessionTimeById(a.latestSessionId, sessions, activeSession));
}

export function patientRowFromApi(row: ApiPatientMemoryRow, t: Translator): PatientRowModel {
  const isActive = row.activeSessionCount > 0;
  const needsInputItems = patientNeedsInputItemsFromApi(row, t);
  const needsInput = needsInputItems.length > 0;
  const primary = patientPrimaryAction({ activeCount: row.activeSessionCount, needsInputItems }, t);
  return {
    id: row.patientId,
    name: row.displayName,
    summary: row.summary || t("memmodel.summary.none"),
    memoryStatus: row.memoryStatus === "updating" ? "updating" : "ready",
    memoryStatusReason: row.memoryStatusReason ?? null,
    // "Active session" is intentionally not shown on patient cards — live work lives in Today.
    badges: patientBadges({ sessionCount: row.sessionCount, complete: Boolean(row.complete), needsInput, needsInputItems, t }),
    action: primary.action,
    actionLabel: primary.label,
    isActive,
    needsInput,
    needsInputItems,
    latestVisitLabel: latestVisitLabelFromApi(row, t),
    latestSessionId: row.latestSessionId || null,
    activeSessionId: row.activeSessionId || null,
    sessionCount: row.sessionCount,
  };
}

/**
 * Build the patient-card badges (visit count + optional Complete + optional needs-input). Each badge
 * carries a stable `kind` so the UI styles by enum, never by parsing the localized text.
 */
export function patientBadges({
  sessionCount,
  complete,
  needsInput,
  needsInputItems,
  t,
}: {
  sessionCount: number;
  complete: boolean;
  needsInput: boolean;
  needsInputItems: PatientNeedsInputItem[];
  t: Translator;
}): PatientBadge[] {
  const badges: PatientBadge[] = [{ label: visitCountLabel(sessionCount, t), kind: "neutral" }];
  if (complete && !needsInput) badges.push({ label: t("memmodel.badge.complete"), kind: "complete" });
  const needsInputLabel = needsInputBadgeLabel(needsInputItems, t);
  if (needsInputLabel) badges.push({ label: needsInputLabel, kind: "needs-input" });
  return badges;
}

// AES-204 — a smart-search match rendered as a minimal patient row (so it can open the detail by id).
/** Minimal placeholder row used while a patient opened by id (e.g. from the worklist) loads. */
export function patientRowStub(id: string, name: string, t: Translator): PatientRowModel {
  return {
    id,
    name,
    summary: t("memmodel.summary.loading"),
    memoryStatus: "ready",
    badges: [],
    action: "open-memory",
    actionLabel: t("memmodel.action.viewHistory"),
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

export function patientRowFromSmartMatch(match: SmartPatientMatch, t: Translator): PatientRowModel {
  return {
    id: match.id,
    name: match.displayName,
    summary: match.reason || t("memmodel.summary.matchedRecord"),
    memoryStatus: "ready",
    badges: smartMatchBadges(match, t),
    action: "open-memory",
    actionLabel: t("memmodel.action.viewHistory"),
    isActive: false,
    needsInput: false,
    needsInputItems: [],
    latestVisitLabel: match.lastVisit ? t("memmodel.label.lastVisit", { date: formatPatientLastVisit(match.lastVisit, t) }) : null,
    latestSessionId: null,
    activeSessionId: null,
    sessionCount: 0,
  };
}

export function smartMatchBadges(match: SmartPatientMatch, t: Translator): PatientBadge[] {
  const labels: Record<string, string> = {
    national_id: t("memmodel.match.nationalId"),
    phone: t("memmodel.match.phone"),
    email: t("memmodel.match.email"),
    name: t("memmodel.match.name"),
    name_prefix: t("memmodel.match.namePrefix"),
    name_fuzzy: t("memmodel.match.nameFuzzy"),
    contact_partial: t("memmodel.match.contactPartial"),
  };
  return match.matchedOn.map((key) => ({ label: labels[key] || key, kind: "neutral" as const })).slice(0, 3);
}

export function patientPrimaryAction({
  activeCount,
  needsInputItems,
}: {
  activeCount: number;
  needsInputItems: PatientNeedsInputItem[];
}, t: Translator): { action: PatientPrimaryAction; label: string } {
  if (needsInputItems.length > 1) return { action: "review-items", label: t("memmodel.action.reviewItems") };
  const item = needsInputItems[0];
  if (item) return { action: item.action, label: labelForDecisionAction(item.action, t) };
  if (activeCount > 0) return { action: "continue", label: t("memmodel.action.continue") };
  return { action: "open-memory", label: t("memmodel.action.viewHistory") };
}

export function labelForDecisionAction(action: PatientNeedsInputItem["action"], t: Translator): string {
  if (action === "review-summary") return t("memmodel.action.reviewSummary");
  if (action === "assign-patient") return t("memmodel.action.assignPatient");
  if (action === "choose-patient") return t("memmodel.action.choosePatient");
  if (action === "verify") return t("memmodel.action.verify");
  return t("memmodel.action.resolveConflict");
}

export function todayNeedsInputActionLabel(session: CaptureSession, t: Translator) {
  const action = decisionActionForSession(session);
  return action ? labelForDecisionAction(action, t) : t("memmodel.action.openVisit");
}

export function activeSectionBadge(session: CaptureSession, t: Translator) {
  const action = decisionActionForSession(session);
  return action ? needsInputLabelForAction(action, t) : t("memmodel.status.inProgress");
}

export function needsInputBadgeLabel(items: PatientNeedsInputItem[], t: Translator) {
  if (items.length > 1) return t("memmodel.badge.decisionsNeedInput", { n: items.length });
  return items[0]?.label;
}

export function patientNeedsInputItemsFromApi(row: ApiPatientMemoryRow, t: Translator): PatientNeedsInputItem[] {
  // The backend is the single source of truth for typed needs-input items. No synthesized
  // fallback: if there are no items, the patient needs nothing.
  return (row.needsInputItems || []).map((item, index) => {
    const action = decisionActionFromKind(item.kind || item.label || "");
    if (!action) return null;
    return {
      id: item.id || `${row.patientId}-needs-input-${index}`,
      sessionId: item.sessionId || row.latestSessionId || row.activeSessionId || null,
      label: needsInputLabelForAction(action, t),
      action,
      title: titleForDecisionAction(action, t),
      detail: item.reason || reasonForDecisionAction(action, t),
      sessionLabel: apiNeedsInputSessionLabel(row, t, item.createdAt),
      reason: item.reason || reasonForDecisionAction(action, t),
      sortTime: item.createdAt ? new Date(item.createdAt).getTime() || 0 : 0,
    };
  }).filter((item): item is PatientNeedsInputItem => Boolean(item)).sort((a, b) => b.sortTime - a.sortTime);
}

export function patientNeedsInputItem(session: CaptureSession, t: Translator): PatientNeedsInputItem | null {
  const action = decisionActionForSession(session);
  if (!action) return null;
  const label = needsInputLabelForAction(action, t);
  return {
    id: `${session.id}-${action}`,
    sessionId: session.id,
    label,
    action,
    title: titleForSessionDecision(session, action, t),
    detail: needsInputSummary(session, t),
    sessionLabel: sessionTimeLabel(session, t),
    reason: reasonForSessionDecision(session, action, t),
    sortTime: latestSessionTime(session),
  };
}

export function titleForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"], t: Translator) {
  if (action === "review-summary") return hasMissingClinicalField(session) ? t("memmodel.title.missingField") : t("memmodel.title.reviewSummary");
  return titleForDecisionAction(action, t);
}

export function titleForDecisionAction(action: PatientNeedsInputItem["action"], t: Translator) {
  if (action === "assign-patient") return t("memmodel.title.assignPatient");
  if (action === "choose-patient") return t("memmodel.title.choosePatient");
  if (action === "resolve-conflict") return t("memmodel.title.resolveConflict");
  if (action === "verify") return t("memmodel.title.verify");
  return t("memmodel.title.reviewSummary");
}

export function reasonForSessionDecision(session: CaptureSession, action: PatientNeedsInputItem["action"], t: Translator) {
  if (action === "assign-patient") return t("memmodel.reason.assignPatient");
  if (action === "choose-patient") {
    const possiblePatients = possiblePatientNames(session);
    return possiblePatients.length >= 2
      ? t("memmodel.reason.choosePatientNamed", { names: formatNameList(possiblePatients, t) })
      : t("memmodel.reason.choosePatient");
  }
  if (action === "resolve-conflict") return t("memmodel.reason.resolveConflict");
  if (hasMissingClinicalField(session)) return t("memmodel.reason.missingField");
  return t("memmodel.reason.reviewSummary");
}

export function reasonForDecisionAction(action: PatientNeedsInputItem["action"], t: Translator) {
  if (action === "assign-patient") return t("memmodel.reason.assignPatient");
  if (action === "choose-patient") return t("memmodel.reason.choosePatientApi");
  if (action === "resolve-conflict") return t("memmodel.reason.resolveConflictApi");
  if (action === "verify") return t("memmodel.reason.verify");
  return t("memmodel.reason.reviewSummary");
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

export function needsInputLabelForAction(action: PatientNeedsInputItem["action"], t: Translator): string {
  if (action === "assign-patient") return t("memmodel.needsInput.assignPatient");
  if (action === "choose-patient") return t("memmodel.needsInput.choosePatient");
  if (action === "resolve-conflict") return t("memmodel.needsInput.resolveConflict");
  if (action === "verify") return t("memmodel.needsInput.verify");
  return t("memmodel.needsInput.reviewSummary");
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

export function extractedPatientMatchHint(session: CaptureSession, t: Translator) {
  const metadata = session.extractedMetadata || {};
  const patientMatch = metadata.patient_match;
  if (patientMatch && typeof patientMatch === "object") {
    const record = patientMatch as Record<string, unknown>;
    const hint = [record.hint, record.reason, record.summary].find((value): value is string => typeof value === "string" && Boolean(value.trim()));
    if (hint) return sanitizePatientMatchHint(hint);
  }
  if (session.items.some((item) => item.type === "audio" || item.type === "voice")) {
    return t("memmodel.hint.audioMentionsName");
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

export function formatNameList(names: string[], t: Translator) {
  if (names.length <= 1) return names[0] || t("memmodel.names.aPossiblePatient");
  if (names.length === 2) return t("memmodel.names.pair", { a: names[0], b: names[1] });
  return t("memmodel.names.many", { list: names.slice(0, -1).join(", "), last: names[names.length - 1] });
}

export function filterPatientMatches(patients: PatientSummary[], query: string) {
  if (!query) return patients;
  const normalizedQuery = query.toLowerCase();
  return patients.filter((patient) =>
    [patient.displayName, patient.nationalId || "", patient.phone || ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
  );
}

export function resolverCaptureSummary(session: CaptureSession, t: Translator) {
  const counts = captureCounts(session, t);
  if (!counts.length) return t("memmodel.capture.none");
  return counts
    .map((item) => {
      const label = item.type === "audio" ? item.label : item.count === 1 ? item.singular : item.label;
      return `${item.count} ${label}`;
    })
    .join(t("memmodel.capture.separator"));
}

export function patientHint(patient: PatientSummary, index: number, t: Translator) {
  if (patient.lastVisit) return t("memmodel.hint.recentlyActiveOn", { date: formatPatientLastVisit(patient.lastVisit, t) });
  if (index === 0) return t("memmodel.hint.recentlyActive");
  if (index === 1) return t("memmodel.hint.similarName");
  return t("memmodel.hint.existingPatient");
}

export function formatPatientLastVisit(value: string, t: Translator) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (isToday(date.toISOString())) return t("memmodel.date.today");
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

export function needsInputTitle(session: CaptureSession, t: Translator) {
  const action = decisionActionForSession(session);
  if (action === "choose-patient") return t("memmodel.title.choosePatient");
  if (action === "resolve-conflict") return t("memmodel.title.resolveConflict");
  if (action === "review-summary") return hasMissingClinicalField(session) ? t("memmodel.title.missingField") : t("memmodel.title.reviewSummary");
  if (!session.patientName && !session.patientId) return t("memmodel.title.unassignedVisit");
  return sessionVisitTitle(session, t);
}

export function needsInputSummary(session: CaptureSession, t: Translator) {
  if (!session.patientName && !session.patientId) {
    const count = session.items.length;
    return count === 1 ? t("memmodel.summary.unassignedOne") : t("memmodel.summary.unassignedMany", { n: count || t("memmodel.count.no") });
  }
  return t("memmodel.summary.reviewBeforeMemory");
}

export function sessionVisitTitle(session: CaptureSession, t: Translator) {
  const title = session.report?.title || session.reportModel?.title || sanitizeSessionLabel(session.label, t);
  if (title && title.toLowerCase() === "unassigned visit" && (session.patientName || session.patientId)) return t("memmodel.title.visit");
  if (title) return title;
  if (!session.patientName && !session.patientId) return t("memmodel.title.unassignedVisit");
  return isActiveVisit(session) ? t("memmodel.title.followUpVisit") : t("memmodel.title.visit");
}

export function sanitizeSessionLabel(label: string | null | undefined, t: Translator) {
  const trimmed = label?.trim();
  if (!trimmed) return "";
  if (/^session\s+\d{1,2}:\d{2}/i.test(trimmed)) return t("memmodel.title.followUpVisit");
  if (/^\d{1,2}:\d{2}\s*(am|pm)?\s*-\s*capture session$/i.test(trimmed)) return t("memmodel.title.followUpVisit");
  if (/^session$/i.test(trimmed)) return "";
  return trimmed;
}

export function updatedTodayStatus(session: CaptureSession, isOffline: boolean, t: Translator) {
  if (isOffline) return t("memmodel.status.savedOnDevice");
  if (session.assignmentSource || session.patientName || session.patientId) return t("memmodel.status.updatedTodayAssigned");
  return t("memmodel.status.memoryUpdatedToday");
}

export function updatedTodaySummary(session: CaptureSession, t: Translator) {
  const counts = captureCounts(session, t);
  const typeSummary = captureTypeSummary(counts, t);
  if (typeSummary) {
    return countsTotal(counts) === 1
      ? t("memmodel.summary.attachedTodayOne", { captures: capitalize(typeSummary) })
      : t("memmodel.summary.attachedTodayMany", { captures: capitalize(typeSummary) });
  }
  const summary = naturalSessionSummary(session, t);
  return summary || t("memmodel.summary.updatedToday");
}

export function visitCountLabel(count: number, t: Translator) {
  return count === 1 ? t("memmodel.label.visitCountOne", { n: count }) : t("memmodel.label.visitCountMany", { n: count });
}

export function currentVisitSummary(session: CaptureSession, isOffline: boolean, t: Translator) {
  const counts = captureCounts(session, t);
  const captureTotal = session.items.length;
  if (isOffline) {
    return captureTotal === 1
      ? t("memmodel.summary.offlineOne")
      : t("memmodel.summary.offlineMany", { n: captureTotal || t("memmodel.count.no") });
  }
  if (!captureTotal) return t("memmodel.summary.noCapturesYet");
  const typeSummary = captureTypeSummary(counts, t);
  if (typeSummary) {
    return captureTotal === 1
      ? t("memmodel.summary.capturesSavedWithTypesOne", { n: captureTotal, types: typeSummary })
      : t("memmodel.summary.capturesSavedWithTypesMany", { n: captureTotal, types: typeSummary });
  }
  return captureTotal === 1 ? t("memmodel.summary.capturesSavedOne", { n: captureTotal }) : t("memmodel.summary.capturesSavedMany", { n: captureTotal });
}

export function patientCardSummary(sessions: CaptureSession[], t: Translator) {
  const orderedSessions = [...sessions].sort((a, b) => latestSessionTime(b) - latestSessionTime(a));
  const aiSummary = orderedSessions
    .map((session) => session.summaries)
    .find((summary) => {
      if (!summary?.short) return false;
      const source = (summary.source || "").toLowerCase();
      return !source.includes("rule") && !source.includes("deterministic");
    });
  if (aiSummary?.short) return aiSummary.short;

  const ruleBased = orderedSessions.map((session) => naturalSessionSummary(session, t)).find(Boolean);
  if (ruleBased) return ruleBased;

  const latest = orderedSessions[0];
  if (latest && (sessionTouchTimestamps(latest).length || latest.items.length)) {
    const updated = naturalUpdatedDate(latest, t);
    const captureCount = latest.items.length;
    if (captureCount) {
      return captureCount === 1
        ? t("memmodel.summary.lastUpdatedWithCapturesOne", { date: updated })
        : t("memmodel.summary.lastUpdatedWithCapturesMany", { date: updated, n: captureCount });
    }
    return t("memmodel.summary.lastUpdated", { date: updated });
  }

  return t("memmodel.summary.none");
}

export function patientSessionsForDetail(patient: PatientRowModel, sessions: CaptureSession[], activeSession: CaptureSession | null) {
  return uniqueSessions([activeSession, ...sessions].filter((session): session is CaptureSession => Boolean(session)))
    .filter((session) => session.patientId === patient.id || session.patientName === patient.name)
    .sort((a, b) => sessionVisitTimestamp(b) - sessionVisitTimestamp(a));
}

export function buildTimelineGroups(detail: PatientMemoryDetailResponse | undefined, localSessions: CaptureSession[], t: Translator): TimelineGroupModel[] {
  const localById = new Map(localSessions.map((session) => [session.id, session]));
  const detailSessions = detail?.sessions.length
    ? detail.sessions.map((session) => ({ ...session, groupLabel: normalizeTimelineGroupLabel(session.groupLabel), localSession: localById.get(session.sessionId) }))
    : localSessions.map((session) => timelineSessionFromLocal(session, t));
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

export function timelineSessionFromLocal(session: CaptureSession, t: Translator): TimelineSessionModel {
  const visitTime = sessionVisitTimestamp(session);
  return {
    sessionId: session.id,
    title: sessionVisitTitle(session, t),
    status: session.status,
    summary: naturalSessionSummary(session, t) || t("memmodel.summary.savedInMemory"),
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

export function timelineSessionTimeLabel(session: TimelineSessionModel, t: Translator, localSession?: CaptureSession) {
  if (localSession) return sessionTimeLabel(localSession, t);
  const timestamp = timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  return explicitDateTimeLabel(timestamp, t);
}

/**
 * "Updated …" metadata for a timeline card. Returns the localized text plus a stable `assignedToday`
 * flag so the card can branch on the flag (success styling / hide its own "Updated" heading) instead
 * of string-matching the now-localized label. Empty `label` means "no meaningful update to show".
 */
export function timelineUpdatedLabel(session: TimelineSessionModel, t: Translator, localSession?: CaptureSession): { label: string; assignedToday: boolean } {
  const sessionTime = localSession ? sessionVisitTimestamp(localSession) : timelineSortTime({ sortDate: session.capturedAt || session.sortDate, capturedAt: session.capturedAt, updatedAt: null });
  const updatedTime = localSession ? latestSessionTime(localSession) : timelineSortTime({ sortDate: session.updatedAt, capturedAt: null, updatedAt: session.updatedAt });
  if (!updatedTime || !sessionTime || updatedTime - sessionTime < 60000) return { label: "", assignedToday: false };
  if (isToday(new Date(updatedTime).toISOString()) && (localSession?.assignmentSource || localSession?.patientId)) {
    return { label: t("memmodel.status.updatedTodayAssigned"), assignedToday: true };
  }
  return { label: formatSessionTime(updatedTime, t), assignedToday: false };
}

/**
 * Status badge for a timeline card: localized `label` + a stable `tone` the card styles on (it used to
 * re-derive the tone by string-matching the label, which breaks once the label is translated).
 */
export function timelineSessionStatus(session: TimelineSessionModel, t: Translator, localSession?: CaptureSession): { label: string; tone: "amber" | "blue" | "green" } {
  const action = timelineDecisionAction(session, localSession);
  if (action) return { label: needsInputLabelForAction(action, t), tone: "amber" };
  if (localSession && isActiveVisit(localSession)) return { label: t("memmodel.status.inProgress"), tone: "green" };
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return { label: t("memmodel.status.inProgress"), tone: "green" };
  if (session.complete || localSession?.complete) return { label: t("memmodel.status.complete"), tone: "blue" };
  return { label: t("memmodel.status.savedOnDevice"), tone: "green" };
}

export function timelineSessionAction(session: TimelineSessionModel, t: Translator, localSession?: CaptureSession): { kind: "continue" | "open" | "review" | "assign"; label: string } {
  const action = timelineDecisionAction(session, localSession);
  if (action === "assign-patient" || action === "choose-patient" || action === "resolve-conflict") return { kind: "assign", label: labelForDecisionAction(action, t) };
  if (action === "verify") return { kind: "open", label: t("memmodel.action.verify") };
  if (localSession && isActiveVisit(localSession)) return { kind: "continue", label: t("memmodel.action.continueVisit") };
  if (!localSession && ["current", "draft", "reopened", "processing"].includes(session.status)) return { kind: "continue", label: t("memmodel.action.continueVisit") };
  if (session.complete || localSession?.complete) return { kind: "open", label: t("memmodel.action.openVisit") };
  return { kind: "open", label: t("memmodel.action.openVisit") };
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

export function naturalSessionSummary(session: CaptureSession, t: Translator) {
  if (session.summaries?.short) return session.summaries.short;
  if (session.summaries?.patientHistory) return session.summaries.patientHistory;
  const summary = sanitizeSummary(session.summary);
  if (summary) return summary;
  const counts = captureCounts(session, t);
  const captureSummary = captureTypeSummary(counts, t);
  return captureSummary ? t("memmodel.summary.latestVisitIncludes", { captures: captureSummary }) : "";
}

export function reviewSummaryText(session: CaptureSession, t: Translator) {
  return (
    naturalSessionSummary(session, t) ||
    t("memmodel.summary.reviewPlaceholder")
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

export function latestVisitLabelFromApi(row: ApiPatientMemoryRow, t: Translator) {
  const timestamp = latestApiVisitTimestamp(row);
  return latestVisitLabelFromTimestamp(timestamp, t);
}

/** Session time as data (no "Session:" prefix — callers render their own localized label). */
export function apiNeedsInputSessionLabel(row: ApiPatientMemoryRow, t: Translator, fallbackTimestamp?: string | null) {
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
  if (!timestamp) return t("memmodel.date.recentVisit");
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? t("memmodel.date.today") : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  const timeLabel = appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(date);
  return `${dateLabel} · ${timeLabel}`;
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

export function latestVisitLabelFromTimestamp(timestamp: number, t: Translator) {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? t("memmodel.date.today") : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  const timeLabel = appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(date);
  return t("memmodel.label.latestVisit", { when: `${dateLabel} · ${timeLabel}` });
}

export function naturalUpdatedDate(session: CaptureSession, t: Translator) {
  const timestamp = latestSessionTime(session);
  if (!timestamp) return t("memmodel.date.recently");
  const date = new Date(timestamp);
  if (isToday(date.toISOString())) return t("memmodel.date.today");
  return appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
}

export function captureCounts(session: CaptureSession, t: Translator) {
  return [
    { label: t("memmodel.capture.photosPlural"), singular: t("memmodel.capture.photoSingular"), type: "photo" as const, count: session.items.filter((item) => item.type === "photo").length },
    { label: t("memmodel.capture.audioPlural"), singular: t("memmodel.capture.audioSingular"), type: "audio" as const, count: session.items.filter((item) => item.type === "audio" || item.type === "voice").length },
    { label: t("memmodel.capture.notesPlural"), singular: t("memmodel.capture.noteSingular"), type: "note" as const, count: session.items.filter((item) => item.type === "note").length },
  ].filter((item) => item.count);
}

export function captureTypeSummary(counts: ReturnType<typeof captureCounts>, t: Translator) {
  const parts = counts.map((item) => `${item.count} ${item.count === 1 ? item.singular : item.label}`);
  if (parts.length <= 1) return parts[0] || "";
  return t("memmodel.capture.joinAnd", { list: parts.slice(0, -1).join(", "), last: parts[parts.length - 1] });
}

export function countsTotal(counts: ReturnType<typeof captureCounts>) {
  return counts.reduce((total, item) => total + item.count, 0);
}

export function capitalize(value: string) {
  if (!value) return value;
  return `${value[0].toUpperCase()}${value.slice(1)}`;
}

export function sessionTimeLabel(session: CaptureSession, t: Translator) {
  return [session.dateLabel, session.time].filter(Boolean).join(" · ") || t("memmodel.date.recentVisit");
}

export function formatSessionTime(timestamp: number, t: Translator) {
  if (!timestamp) return t("memmodel.date.recently");
  return appDateTimeFormat({ hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

export function explicitDateTimeLabel(timestamp: number, t: Translator) {
  if (!timestamp) return t("memmodel.date.recentVisit");
  const date = new Date(timestamp);
  const dateLabel = isToday(date.toISOString()) ? t("memmodel.date.today") : appDateTimeFormat({ month: "short", day: "numeric" }).format(date);
  return `${dateLabel} · ${formatSessionTime(timestamp, t)}`;
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

export function captureKindLabel(kind: CaptureDraft["kind"], t: Translator) {
  if (kind === "audio") return t("memmodel.captureKind.audio");
  if (kind === "photo") return t("memmodel.captureKind.takePhoto");
  return t("memmodel.captureKind.writeNote");
}
