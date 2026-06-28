// Capture screen shell (orchestration); presentational pieces live in sibling files.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { AftercareTemplate, LineupCard, PatientAssignmentDraft, PatientSummary, SessionContext } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import { assignmentSourceLabel } from "../metadata";
import { Button, Card } from "../../../shared/ui/primitives";
import { SessionContextCard } from "../../aesthetics/SessionContextCard";
import { SourcePreviewDialog } from "./SourcePreview";
import { PatientAssignmentSheet } from "./PatientAssignmentSheet";
import { LiveDraftReport } from "./LiveDraftReport";
import { LiveReportView } from "./LiveReport";
import { ReportFeedbackBar } from "./ReportFeedbackBar";
import { SessionVerifyBar } from "./SessionVerifyBar";
import { AiCreatedPatientPanel, CaptureTimelineIcon, AiSpark, PatientConflictResolver, captureConflictSuggestion } from "./CaptureBadges";
import { reportUpdatingLabel, workspaceReportState, textDirection, sessionSummaryStatusChip, sessionSummaryTitle, isPlaceholderSessionTitle, lightSessionTitle, captureNotSynced, sessionPatientName, aiPatientActionForSession, sessionSummaryCreatedLabel, sessionSummaryUpdatedLabel, workspaceTreatments, suggestedAftercareTemplateIds, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionDismissedAftercare, sessionAftercareSelections, sessionKeptSafetyFlags, workspaceStructuredReportCopy, activePatientAssignmentActionForSession, sessionAssignmentCandidates, alternateCandidateForCapture } from "../captureModel";
import type { AftercareSelection } from "../captureModel";
import { PatientIcon, BackIcon, ClipboardIcon, EditIcon, AddPatientIcon, SyncIcon, ClockHistoryIcon, ShareIcon } from "./CaptureIcons";
import { isPersianLocale } from "../../../shared/lib/datetime";
import { useT } from "../../../shared/i18n";

export function CaptureScreen({
  activeSession,
  onResolveFile,
  onUpdateTitle,
  onRenameCapture,
  onUpdateCaptureCaption,
  onUpdateCaptureTranscript,
  onUpdateNote,
  onDeleteCapture,
  mode = "active",
  onBack,
  backLabel,
  onResumeCapture,
  assignmentOpen,
  onAssignPatient,
  onCloseAssignment,
  onOpenResolver,
  onSearchPatients,
  onCompleteAiCreatedPatient,
  onStartNewSession,
  onMarkRelevant,
  onConfirmCarriedForward,
  onRateReport,
  onFetchPatient,
  onFetchCapture,
  tier,
  reportLanguage,
  sessionContext,
  lineupCard,
  onOpenVisit,
  onViewPatientHistory,
  onShareVisit,
  onUseAsNote,
  aftercareTemplates,
  onDismissAftercare,
  onRejectSafetyFlag,
  offline = false,
  sessionOrdinal = null,
  currentUserId = null,
  readOnly = false,
  nextLinedUpPatient = null,
  onAssignActiveToNext,
  onStartNextVisit,
}: {
  activeSession: CaptureSession | null;
  /** Deprecated: the live report regenerates automatically (Epic E); kept for the retry path. */
  onSaveSession?: (sessionId: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
  onRenameCapture?: (sessionId: string, captureId: string, title: string) => Promise<void>;
  onUpdateCaptureCaption?: (sessionId: string, captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateCaptureTranscript?: (sessionId: string, captureId: string, transcript: string) => Promise<CaptureItem | null>;
  onUpdateNote?: (sessionId: string, captureId: string, text: string) => Promise<void>;
  onDeleteCapture?: (sessionId: string, captureId: string) => Promise<void>;
  mode?: "active" | "historical";
  onBack?: () => void;
  backLabel?: string;
  onResumeCapture?: () => void;
  assignmentOpen?: boolean;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onCloseAssignment?: () => void;
  /** Open the assignment resolver from a capture-card "Choose another" quick action (H4). */
  onOpenResolver?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onCompleteAiCreatedPatient?: (
    sessionId: string,
    patientId: string,
    draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
    action: Record<string, unknown>,
  ) => Promise<void>;
  onStartNewSession?: () => void;
  onMarkRelevant?: (sessionId: string, captureId: string) => Promise<void>;
  /** Q3 — confirm a carried-forward dose (by area|product key) so the Pro report can complete. */
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
  /** Record a lightweight thumbs rating on the Pro report (eval golden-set harvester; eval-epic §1b). */
  onRateReport?: (sessionId: string, rating: number) => void;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  /** Resolve a citation's source capture not in the loaded set (cross-visit) — for "tap a claim → source". */
  onFetchCapture?: (captureId: string) => Promise<CaptureItem | null>;
  tier?: string | null;
  /** Tenant report-content language (distinct from app UI language) — localizes the report's section
   * titles so a Persian report doesn't show English headings. */
  reportLanguage?: string | null;
  /** Deterministic session context (last-visit digest + cross-visit photo strip), surfaced at
   * capture in both tiers once the patient is determined. */
  sessionContext?: SessionContext | null;
  /** Pro: the active patient's Job-4 curated brief, rendered in place of the raw digest. */
  lineupCard?: LineupCard | null;
  onOpenVisit?: (sessionId: string) => void;
  /** Jump to the assigned patient's full timeline, with a one-tap "back to this visit". */
  onViewPatientHistory?: (patientId: string) => void;
  /** Curate + share THIS visit's report with the patient (Pro), from the session screen. */
  onShareVisit?: () => void;
  onUseAsNote?: (text: string) => void;
  /** Clinic aftercare templates — one-tap deterministic follow-up instructions (both tiers). */
  aftercareTemplates?: AftercareTemplate[];
  /** Opt an auto-included clinic aftercare template in/out of this visit (persisted). */
  onDismissAftercare?: (sessionId: string, templateId: string, dismissed: boolean) => Promise<void>;
  /** Reject (×) an auto-kept session safety flag (opt-out, persisted). Not a verify-bar blocker. */
  onRejectSafetyFlag?: (sessionId: string, flagKey: string) => Promise<void>;
  /** No connection / backend unreachable — gates the only sync indicators we show. */
  offline?: boolean;
  /** This session's 1-based rank among the patient's sessions (for "{patient}'s Nth session"). */
  sessionOrdinal?: number | null;
  /** AES-901 — the signed-in user's id, so capture attribution can read "by you". */
  currentUserId?: string | null;
  /** AES-902 — the viewer doesn't own this visit and their role can't edit it: read-only. */
  readOnly?: boolean;
  /** AES-903/301 — the doctor's next lined-up patient, to file an unassigned visit to them. */
  nextLinedUpPatient?: { patientName: string } | null;
  onAssignActiveToNext?: () => void;
  onStartNextVisit?: () => void;
}) {
  const t = useT();
  const isPro = tier !== "basic";
  // Pro smart aftercare: promote the clinic's templates that match the procedures performed this
  // visit (deterministic match against the extracted treatments). Basic shows the flat list.
  // Aftercare matching is AI-driven when the synthesis has run (it judges clinical relevance, not a
  // keyword, and flags when the clinician's dictation conflicts with a protocol); it falls back to the
  // deterministic procedure-synonym match until then (gateway-less Pro / pre-synthesis), so it's never
  // blank.
  const { aiRan: aftercareAiRan, selections: aftercareSelections } = sessionAftercareSelections(activeSession);
  const deterministicAftercareIds =
    isPro && aftercareTemplates?.length ? suggestedAftercareTemplateIds(aftercareTemplates, workspaceTreatments(activeSession)) : new Set<string>();
  const appliedAftercareIds = aftercareAiRan
    ? new Set(aftercareSelections.filter((selection) => selection.status === "applies").map((selection) => selection.templateId))
    : deterministicAftercareIds;
  const dismissedAftercare = new Set(sessionDismissedAftercare(activeSession));
  // Auto-include matched aftercare in the report by default (opt-out), minus anything the doctor removed.
  const includedAftercare = (aftercareTemplates || []).filter((template) => appliedAftercareIds.has(template.id) && !dismissedAftercare.has(template.id));
  // Conflicts: the AI found the clinician dictated aftercare that differs from a clinic protocol — show
  // it (the dictation wins) instead of silently including the contradicting protocol.
  const aftercareConflicts = aftercareAiRan
    ? aftercareSelections
        .filter((selection) => (selection.status === "conflicts" || selection.status === "superseded") && !dismissedAftercare.has(selection.templateId))
        .map((selection) => ({
          template: (aftercareTemplates || []).find((template) => template.id === selection.templateId),
          note: selection.note,
          status: selection.status,
        }))
        .filter((conflict): conflict is { template: AftercareTemplate; note: string | null; status: AftercareSelection["status"] } => Boolean(conflict.template))
    : [];
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [reportView, setReportView] = React.useState<"draft" | "structured">("draft");
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const isHistorical = mode === "historical";
  // Basic active visits get a lightweight header — no "Complete" badge, no raw "Session <time>"
  // name. Title = the patient's Nth session when assigned, else the session date+time. Sync state
  // only shows when offline/unreachable (calm when everything is fine).
  const lightHeader = !isPro && !isHistorical;
  const lightTitle = lightSessionTitle(activeSession, sessionOrdinal, t);
  const sessionPending = !isHistorical && Boolean(activeSession?.items.some((item) => captureNotSynced(item.status)));
  const processingState = activeSession?.processingStatus?.state;
  // A just-added capture is "in flight" the instant it lands (local → syncing → uploaded → processing)
  // — before the backend's synthesis job flips processingStatus. Treat that as "editing" too, so the
  // updating animation fires IMMEDIATELY on capture-add (the doctor feels their capture being included),
  // not only once the server starts processing. Gated on connectivity: offline, nothing is organizing.
  const captureBeingIncluded =
    !offline &&
    Boolean(
      activeSession?.items?.some(
        (item) =>
          item.status === "saved" ||
          item.status === "syncing" ||
          item.status === "uploading" ||
          item.status === "uploaded" ||
          item.status === "processing",
      ),
    );
  // The live report regenerates automatically as captures land (Epic E); "updating" is a calm
  // inline state, never a gate. Pro = synthesized; Basic = chronological.
  const isUpdatingReport =
    isPro && (processingState === "processing" || activeSession?.report?.status === "generating" || captureBeingIncluded);
  // Surface-by-exception: instead of a persistent "everything's fine" line, show a calm "Organizing…"
  // pulse on the Sources header only while captures are still being processed into the report.
  const sourcesProcessing = isUpdatingReport || (activeSession?.items || []).some((item) => item.status === "processing");
  const reportState = workspaceReportState(activeSession, t);
  const selectedReportView = reportView;
  const sessionTitle = sessionSummaryTitle(activeSession, isHistorical, t);
  // Pro keeps its status chip + meta, but the title gets the same meaningful naming as Basic — a
  // real AI report title when there is one, otherwise "{patient}'s Nth session" / the date+time
  // (instead of a raw "Session <timestamp>" label). The generic-title test is language-independent
  // (isPlaceholderSessionTitle) so it survives translation; the raw "Session <ts>" label case is a
  // local/backend label, still matched textually.
  const proTitle =
    !isHistorical && (isPlaceholderSessionTitle(activeSession, isHistorical) || /^session\s/i.test(sessionTitle))
      ? lightSessionTitle(activeSession, sessionOrdinal, t)
      : sessionTitle;
  const patientName = sessionPatientName(activeSession, t);
  const aiPatientAction = aiPatientActionForSession(activeSession);
  const captureCount = activeSession?.items.length || 0;
  const captureCountLabel = t(captureCount === 1 ? "capture.captureCountOne" : "capture.captureCountOther", { count: captureCount });
  // The most-recently-added capture — the target of the one-tap "Undo last capture" shortcut (a more
  // accessible entry to the same de-effecting removal as the per-capture Delete). Newest by capture time.
  const lastCapture = React.useMemo(() => {
    const items = [...(activeSession?.items || [])];
    if (!items.length) return null;
    // Newest by capture time; a just-added local capture without a timestamp yet is treated as newest
    // (it's exactly the one a quick undo targets). Stable sort keeps array order among ties.
    const ts = (c: CaptureItem) => (c.capturedAt ? new Date(c.capturedAt).getTime() : Number.MAX_SAFE_INTEGER);
    items.sort((a, b) => ts(a) - ts(b));
    return items[items.length - 1];
  }, [activeSession?.items]);
  const sessionStatusChip = sessionSummaryStatusChip(activeSession, t);
  const sessionCreatedLabel = sessionSummaryCreatedLabel(activeSession, t);
  const sessionUpdatedLabel = sessionSummaryUpdatedLabel(activeSession, t);

  // FB8 unified Pro layout: the synthesized report is the primary surface, the raw captures become a
  // collapsible "Sources" drawer, and a sticky bar drives verification. Basic keeps its Captures /
  // Live-report tabs (it has no synthesized report to make primary).
  const useUnifiedLayout = isPro;
  // Sticky verify driver counts ONLY blockers — unconfirmed carried-forward doses + an AI-created
  // patient awaiting identity verification. Soft warnings (missing lot, low confidence) stay inline
  // in the report and never feed this count, keeping the bar calm ("warnings over blocking").
  const treatmentReview = sessionTreatmentReview(activeSession);
  const confirmedCarriedForward = new Set(sessionConfirmedCarriedForward(activeSession));
  const openDoseConfirmations = treatmentReview.filter(
    (item) => item.category === "carried_forward" && item.key && !confirmedCarriedForward.has(item.key),
  );
  const patientVerifyNeeded = Boolean(aiPatientAction && onCompleteAiCreatedPatient);
  // Patient CONFLICTS (a capture dictated a different/partial-match patient than the assigned one) are
  // a session-level blocker too — surfaced in the verify region + counted, not buried in the Sources
  // drawer (FB8). Resolution is in place via the shared PatientConflictResolver. Local dismiss only.
  const [dismissedConflicts, setDismissedConflicts] = React.useState<Set<string>>(new Set());
  React.useEffect(() => setDismissedConflicts(new Set()), [activeSession?.id]);
  const assignmentCandidates = sessionAssignmentCandidates(activeSession);
  const activeAssignmentAction = activePatientAssignmentActionForSession(activeSession);
  const patientConflicts =
    !isHistorical && onAssignPatient
      ? (activeSession?.items || [])
          .map((item) => ({
            captureId: item.id,
            suggestion: captureConflictSuggestion(item, alternateCandidateForCapture(assignmentCandidates, item.id), activeAssignmentAction),
          }))
          .filter((conflict) => conflict.suggestion && !dismissedConflicts.has(conflict.captureId))
      : [];
  const verifyCount = openDoseConfirmations.length + (patientVerifyNeeded ? 1 : 0) + patientConflicts.length;
  // Session-level SAFETY flags (allergy/contraindication/consent) detected this visit. Auto-kept
  // (opt-out): shown by default, the clinician acts only to reject a wrong one. Deliberately NOT part
  // of `verifyCount` — safety is surfaced/prominent but requires no action, so it never gates the
  // report ("warnings over blocking"). Errs toward inclusion: kept unless the clinician rejects it.
  const keptSafetyFlags = !isHistorical ? sessionKeptSafetyFlags(activeSession) : [];
  const verifyRegionRef = React.useRef<HTMLDivElement>(null);
  // "Review" jumps to the TOPMOST unresolved item. Every counted blocker is reachable without opening
  // the Sources drawer: patient conflicts + AI-created-patient identity live in the verify region
  // (above the report), and a carried-forward dose lives inline on its treatment row in the report. The
  // region (when present) is highest on the page, so it wins; otherwise the first inline dose row.
  const scrollToVerify = () => {
    const region = verifyRegionRef.current;
    const target = region || document.querySelector(".treatment-item.needs-confirm");
    target?.scrollIntoView({ behavior: "smooth", block: region ? "start" : "center" });
  };
  // The Sources drawer opens by default while the report has no content yet (early capture, before
  // synthesis), so a fresh session never looks empty; once the report has body the drawer collapses.
  const reportHasContent = Boolean(
    activeSession?.reportModel?.sections?.some((section) => section.blocks?.length) ||
      workspaceStructuredReportCopy(activeSession).length ||
      workspaceTreatments(activeSession).length,
  );
  const [sourcesOpen, setSourcesOpen] = React.useState(false);
  const sourcesShown = sourcesOpen || !reportHasContent;
  const sourcesDrawerRef = React.useRef<HTMLElement>(null);
  // "Fix at source" on a flagged treatment row: open the Sources drawer and scroll to it, so the
  // doctor corrects the originating capture (transcript/caption) and the AI re-extracts.
  const onFixAtSource = () => {
    setSourcesOpen(true);
    window.requestAnimationFrame(() => sourcesDrawerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  // "Tap a claim → its source capture" (the redesign's assistive+cited principle): open the cited
  // capture in the source preview. It is usually one of this session's captures; a carried-forward
  // claim cites a prior visit, so fall back to fetching the capture by id when it isn't loaded here.
  const openSourceCapture = async (captureId: string) => {
    const local = (activeSession?.items || []).find((item) => item.id === captureId);
    if (local) {
      setSelectedCapture(local);
      return;
    }
    if (onFetchCapture) {
      const fetched = await onFetchCapture(captureId);
      if (fetched) setSelectedCapture(fetched);
    }
  };
  // Capture-type breakdown for the Sources drawer chips (voice folds into audio).
  const captureTypeCounts = (activeSession?.items || []).reduce<Record<string, number>>((counts, item) => {
    const key = item.type === "voice" ? "audio" : item.type;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});

  // The report is always live; default to the Captures feed and let the user toggle tabs.
  React.useEffect(() => {
    setReportView("draft");
  }, [activeSession?.id]);

  React.useEffect(() => {
    if (!activeSession) previousCaptureCountRef.current = 0;
  }, [activeSession]);

  React.useEffect(() => {
    const currentCaptureCount = activeSession?.items.length || 0;
    if (!currentCaptureCount) {
      previousCaptureCountRef.current = 0;
      return;
    }
    const previousCaptureCount = previousCaptureCountRef.current;
    previousCaptureCountRef.current = currentCaptureCount;
    if (currentCaptureCount > previousCaptureCount && previousCaptureCount === 0) {
      window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "instant" }));
    }
  }, [activeSession?.items.length]);

  // The raw capture feed — Basic's "Captures" tab and Pro's "Sources" drawer render the same element.
  const captureFeed = (
    <LiveDraftReport
      isPro={isPro}
      offline={offline}
      session={activeSession}
      currentUserId={currentUserId}
      onApplyRelevant={onMarkRelevant}
      onAssignPatient={onAssignPatient}
      onDeleteCapture={onDeleteCapture}
      onOpenCapture={setSelectedCapture}
      onOpenResolver={onOpenResolver}
      onRenameCapture={onRenameCapture}
      onResolveFile={onResolveFile}
      onUpdateCaptureCaption={onUpdateCaptureCaption}
      onUpdateCaptureTranscript={onUpdateCaptureTranscript}
      onUpdateNote={onUpdateNote}
    />
  );

  return (
    <section className="capture-current session-workspace" aria-label={isHistorical ? t("capture.historicalSessionReview") : t("capture.activeSessionWorkspace")}>
      {onBack ? (
        <button className="context-back-button" onClick={onBack} type="button">
          <BackIcon />
          {backLabel ?? t("capture.backToMemory")}
        </button>
      ) : null}
      <div className={`active-session-summary${lightHeader ? " light" : ""}`}>
        <div className="session-summary-copy">
          {lightHeader ? (
            <>
              <div className="session-summary-heading">
                <span className="session-live-dot" aria-hidden="true" />
                <h1 dir={textDirection(lightTitle)}>{lightTitle}</h1>
              </div>
              <p>
                {captureCountLabel}
                {offline && sessionPending ? (
                  <span className="session-sync-pending"><SyncIcon /> {t("capture.tryingToSyncSession")}</span>
                ) : null}
              </p>
            </>
          ) : (
            <>
              <div className="session-summary-heading">
                <h1 dir={textDirection(proTitle)}>{proTitle}</h1>
                <span className={`status-chip ${sessionStatusChip.tone} ${sessionStatusChip.checked ? "checked" : ""}`}>
                  <span aria-hidden="true" />
                  {sessionStatusChip.label}
                </span>
              </div>
              <p data-testid="session-meta">{sessionCreatedLabel} <span aria-hidden="true">&bull;</span> {captureCountLabel} <span aria-hidden="true">&bull;</span> {sessionUpdatedLabel}</p>
            </>
          )}
        </div>
        <div className="workspace-header-actions">
          {isHistorical && onResumeCapture ? (
            <Button disabled={!activeSession} onClick={onResumeCapture} size="sm" type="button" variant="secondary">
              {t("capture.addCapture")}
            </Button>
          ) : null}
          {!isHistorical && onStartNewSession ? (
            <Button className="current-new-session" onClick={onStartNewSession} size="sm" type="button" variant="secondary">
              <span aria-hidden="true">+</span>
              {t("capture.newSession")}
            </Button>
          ) : null}
        </div>
      </div>
      {readOnly && activeSession ? (
        <div className="session-readonly-banner" role="note">
          <span aria-hidden="true">🔒</span>
          <span>
            {activeSession.createdBy?.displayName
              ? t("capture.readOnlyStartedBy", { name: activeSession.createdBy.displayName })
              : t("capture.readOnlyOwnedByOther")}
          </span>
        </div>
      ) : null}
      {useUnifiedLayout && !isHistorical ? (
        <SessionVerifyBar count={verifyCount} onReview={scrollToVerify} />
      ) : null}
      <Card className={`patient-context-card${activeSession?.patientId || activeSession?.patientName ? " assigned" : " unassigned"}`}>
        <span className="patient-context-avatar" aria-hidden="true">
          <PatientIcon />
        </span>
        <div className="patient-context-copy">
          <strong dir={textDirection(patientName)}>{patientName}</strong>
          <p>
            {activeSession?.patientId || activeSession?.patientName
              ? activeSession.assignmentSource
                ? assignmentSourceLabel(activeSession.assignmentSource, t)
                : t("capture.assignedManually")
              : t("capture.captureFirstAssignWhenReady")}
          </p>
        </div>
        <div className="patient-context-actions">
          {activeSession?.patientId && onViewPatientHistory ? (
            <button
              className="patient-context-action"
              onClick={() => onViewPatientHistory(activeSession.patientId as string)}
              type="button"
            >
              <ClockHistoryIcon />
              {t("capture.history")}
            </button>
          ) : null}
          {onAssignPatient ? (
            <button
              className={`patient-context-action${activeSession?.patientId || activeSession?.patientName ? "" : " primary"}`}
              onClick={onCloseAssignment}
              type="button"
            >
              {activeSession?.patientId || activeSession?.patientName ? (
                <>
                  <EditIcon />
                  {t("capture.change")}
                </>
              ) : (
                <>
                  <AddPatientIcon />
                  {t("capture.assign")}
                </>
              )}
            </button>
          ) : null}
        </div>
      </Card>
      {!isHistorical && nextLinedUpPatient && activeSession && !activeSession.patientId && !activeSession.patientName ? (
        <div className="next-lined-up" role="note">
          <span className="next-lined-up-copy">
            {t("capture.nextInYourList")} <strong dir={textDirection(nextLinedUpPatient.patientName)}>{nextLinedUpPatient.patientName}</strong>
          </span>
          <span className="next-lined-up-actions">
            {activeSession.items.length && onAssignActiveToNext ? (
              <Button size="sm" type="button" onClick={onAssignActiveToNext}>
                {t("capture.assignThisVisit")}
              </Button>
            ) : null}
            {onStartNextVisit ? (
              <Button size="sm" variant="secondary" type="button" onClick={onStartNextVisit}>
                {t("capture.startTheirVisit")}
              </Button>
            ) : null}
          </span>
        </div>
      ) : null}
      {/* Session-level safety panel — highest priority, so it sits ABOVE the context card and the
          verify region. Opt-out: every detected flag is shown by default; the × rejects a wrong one.
          NOT a verify-bar blocker (not in verifyRegionRef, not counted). Flag body is report-language
          clinical content (dir auto, never translated); only the chrome routes through appT. */}
      {keptSafetyFlags.length ? (
        <section className="session-safety-panel" aria-label={t("capture.safety.label")}>
          <div className="session-safety-head">
            <span className="session-safety-label">{t("capture.safety.label")}</span>
            <span className="session-safety-hint">{t("capture.safety.hint")}</span>
          </div>
          {keptSafetyFlags.map((flag) => (
            <div className={`session-safety-flag safety-${flag.kind}`} key={flag.key}>
              <span className="session-safety-kind">{t(`safety.kind.${flag.kind}`)}</span>
              <p className="session-safety-text" dir={textDirection(flag.text)}>
                {flag.text}
              </p>
              {onRejectSafetyFlag && !readOnly && activeSession ? (
                <button
                  className="session-safety-remove"
                  type="button"
                  aria-label={t("capture.safety.reject")}
                  title={t("capture.safety.reject")}
                  onClick={() => onRejectSafetyFlag(activeSession.id, flag.key)}
                >
                  ✕
                </button>
              ) : null}
            </div>
          ))}
        </section>
      ) : null}
      {!isHistorical && activeSession?.patientId && sessionContext ? (
        <SessionContextCard
          context={sessionContext}
          isPro={isPro}
          lineupCard={lineupCard}
          onOpenVisit={onOpenVisit}
          onUseAsNote={onUseAsNote}
          onResolveFile={onResolveFile}
        />
      ) : null}
      {!isHistorical && activeSession && ((aiPatientAction && onCompleteAiCreatedPatient) || patientConflicts.length) ? (
        <div className="session-verify-region" ref={verifyRegionRef}>
          {patientConflicts.length ? (
            <section className="session-patient-conflicts" aria-label={t("capture.patientNeedsConfirmation")}>
              <span className="session-patient-conflicts-label">{t("capture.patientNeedsConfirmation")}</span>
              {patientConflicts.map((conflict) => (
                <PatientConflictResolver
                  key={conflict.captureId}
                  suggestion={conflict.suggestion as Exclude<typeof conflict.suggestion, null>}
                  basisCaptureId={conflict.captureId}
                  onApply={onAssignPatient ? (draft) => onAssignPatient(activeSession.id, draft) : undefined}
                  onChooseAnother={onOpenResolver}
                  onDismiss={() => setDismissedConflicts((current) => new Set(current).add(conflict.captureId))}
                />
              ))}
            </section>
          ) : null}
          {aiPatientAction && onCompleteAiCreatedPatient ? (
            <AiCreatedPatientPanel action={aiPatientAction} session={activeSession} onComplete={onCompleteAiCreatedPatient} />
          ) : null}
        </div>
      ) : null}
      <Card className={`workspace-report-card ${isUpdatingReport ? "processing" : ""}`}>
        <div className="report-heading">
          <div className="report-title-lockup">
            <span className="report-title-icon" aria-hidden="true">
              <ClipboardIcon />
            </span>
            <h2>{t("capture.clinicalReport")}</h2>
            {/* AI-provenance mark: the Pro report is AI-synthesized; the spark twinkles while the
                synthesis is organizing (the "editing" phase), so the icon itself signals AI is at work. */}
            {isPro ? (
              <span className="report-ai-mark" role="img" aria-label={t("capture.aiSynthesizedReport")} title={t("capture.aiSynthesizedReport")}>
                <AiSpark working={isUpdatingReport} />
              </span>
            ) : null}
          </div>
          <div className="report-heading-actions">
            {isUpdatingReport ? (
              <span className="report-updating" aria-live="polite">
                <span className="report-updating-spinner" aria-hidden="true" />
                {reportUpdatingLabel(activeSession, t)}
              </span>
            ) : null}
            {/* Compact share affordance in the header (a share icon, not a full sentence on its own
                row) — a curated clinic→patient action; opens the curate+preview sheet. */}
            {isPro && !isHistorical && activeSession?.patientId && activeSession.items.length && onShareVisit ? (
              <button className="report-share-button" type="button" onClick={onShareVisit} aria-label={t("capture.shareWithPatient")} title={t("capture.shareWithPatient")}>
                <ShareIcon />
                <span className="report-share-button-label">{t("capture.share")}</span>
              </button>
            ) : null}
          </div>
        </div>
        {/* Basic keeps the Captures / Live-report tab switch; Pro's unified layout has no toolbar row. */}
        {!useUnifiedLayout ? (
          <div className="report-toolbar">
            <div className="report-toolbar-actions">
              <div className="report-view-switch" aria-label={t("capture.reportView")}>
                <button className={selectedReportView === "draft" ? "active" : ""} onClick={() => setReportView("draft")} type="button">
                  {t("capture.capturesTab")}
                </button>
                <button
                  className={selectedReportView === "structured" ? "active" : ""}
                  onClick={() => setReportView("structured")}
                  type="button"
                >
                  {t("capture.liveReportTab")}
                </button>
              </div>
            </div>
          </div>
        ) : null}
        {assignmentOpen && activeSession && onAssignPatient ? (
          <PatientAssignmentSheet
            session={activeSession}
            onAssign={(draft) => onAssignPatient(activeSession.id, draft)}
            onCancel={onCloseAssignment}
            onFetchPatient={onFetchPatient}
            onSearchPatients={onSearchPatients}
          />
        ) : null}
        <div className={`workspace-report-body ${reportState.kind}`}>
          {/* Unified Pro layout: the synthesized report IS the surface (no Captures/Live-report tabs).
              Basic keeps the tabs — its "Live report" is a chronological doc, not a synthesis. */}
          {useUnifiedLayout || selectedReportView === "structured" ? (
            <LiveReportView
              isPro={isPro}
              session={activeSession}
              onResolveFile={onResolveFile}
              onConfirmCarriedForward={onConfirmCarriedForward}
              onFixAtSource={useUnifiedLayout ? onFixAtSource : undefined}
              onOpenSource={openSourceCapture}
              reportLanguage={reportLanguage}
            />
          ) : (
            captureFeed
          )}
        </div>
        {/* Content-driven aftercare, AI-matched and auto-included in the report (opt-out): the synthesis
            decides which clinic protocols apply this visit; each is added by default — the doctor only
            acts to remove it. Persisted dismissals survive re-synthesis; it flows into the patient share.
            When the doctor DICTATED aftercare that differs from a protocol, the dictation wins and a
            conflict note is shown instead of silently including the contradicting protocol. */}
        {useUnifiedLayout && !isHistorical && !readOnly && (includedAftercare.length || aftercareConflicts.length) ? (
          <section className="report-aftercare-included" aria-label={t("capture.aftercareForThisVisit")}>
            <span className="report-aftercare-included-label">{t("capture.aftercareForThisVisitFromProtocol")}</span>
            {includedAftercare.map((template) => (
              <div className="aftercare-included-card" key={template.id}>
                <div className="aftercare-included-body">
                  <strong dir="auto">{template.name}</strong>
                  <p dir="auto">{template.body}</p>
                </div>
                {onDismissAftercare && activeSession ? (
                  <button
                    className="aftercare-included-remove"
                    type="button"
                    aria-label={t("capture.removeTemplate", { name: template.name })}
                    title={t("capture.removeFromThisVisit")}
                    onClick={() => onDismissAftercare(activeSession.id, template.id, true)}
                  >
                    ✕
                  </button>
                ) : null}
              </div>
            ))}
            {aftercareConflicts.map((conflict) => (
              <div className="aftercare-conflict-note" key={conflict.template.id} dir={textDirection(conflict.note || conflict.template.name)}>
                <span className="aftercare-conflict-icon" aria-hidden="true">⚠</span>
                <span>
                  {conflict.note ? (
                    <>
                      {conflict.note} <span className="aftercare-conflict-source">{t("capture.aftercareConflictSource", { name: conflict.template.name })}</span>
                    </>
                  ) : (
                    <>{t("capture.aftercareConflictDefault", { name: conflict.template.name })}</>
                  )}
                </span>
              </div>
            ))}
          </section>
        ) : null}
        {/* Report thumbs rating (eval golden-set harvester; eval-epic §1b) — a quiet end-cap AFTER the
            aftercare section so it reads "rate-after-reading" and never splits the clinical content;
            on mobile it's the last thing before the collapsible raw Sources. Pro report only. */}
        {useUnifiedLayout && onRateReport && activeSession && reportHasContent ? (
          // The rating prompt is app chrome, so it follows the APP UI language (isPersianLocale),
          // not the report's CONTENT language — a Persian report under an English app shows English.
          <ReportFeedbackBar isPersian={isPersianLocale()} onRate={(rating) => onRateReport(activeSession.id, rating)} />
        ) : null}
        {useUnifiedLayout && captureCount > 0 ? (
          // The raw captures, demoted to a collapsible "Sources" drawer beneath the report. Editing,
          // deleting, re-assigning and tapping into a capture all still live here (and via the report's
          // own source links). Auto-expanded while the report has no content yet.
          <section className="sources-drawer" ref={sourcesDrawerRef}>
            <button
              className="sources-drawer-summary"
              type="button"
              aria-expanded={sourcesShown}
              onClick={() => setSourcesOpen((open) => !open)}
            >
              <span className="sources-drawer-lead">
                <span className="sources-drawer-chev" aria-hidden="true">{sourcesShown ? "▾" : "▸"}</span>
                <span className="sources-drawer-title">{t("capture.sources")}</span>
                <span className="sources-drawer-count">{captureCount}</span>
                {sourcesProcessing ? (
                  <span className="sources-drawer-organizing" aria-live="polite">
                    <span className="sources-organizing-dot" aria-hidden="true" />
                    {t("capture.organizing")}
                  </span>
                ) : null}
              </span>
              <span className="sources-drawer-types" aria-hidden="true">
                {(["audio", "photo", "note"] as const).map((type) =>
                  captureTypeCounts[type] ? (
                    <span className="sources-type-chip" key={type}>
                      <CaptureTimelineIcon type={type} />
                      {captureTypeCounts[type]}
                    </span>
                  ) : null,
                )}
              </span>
            </button>
            {/* One-tap undo: remove the most-recent capture (the de-effecting removal) without having
                to expand Sources and find it. Owner-only; same operation as the per-capture Delete. */}
            {!isHistorical && !readOnly && onDeleteCapture && activeSession && lastCapture ? (
              <div className="sources-drawer-undo-row">
                <button
                  className="sources-drawer-undo"
                  type="button"
                  onClick={() => onDeleteCapture(activeSession.id, lastCapture.id)}
                  title={t("capture.undoLastHint")}
                >
                  {t("capture.undoLast")}
                </button>
              </div>
            ) : null}
            {sourcesShown ? <div className="sources-drawer-body">{captureFeed}</div> : null}
          </section>
        ) : null}
      </Card>
      <SourcePreviewDialog
        item={selectedCapture}
        isPro={isPro}
        onClose={() => setSelectedCapture(null)}
        onResolveFile={onResolveFile}
        onUpdateCaption={
          activeSession && onUpdateCaptureCaption
            ? async (captureId, caption) => {
                const updated = await onUpdateCaptureCaption(activeSession.id, captureId, caption);
                if (updated) setSelectedCapture(updated);
                return updated;
              }
            : undefined
        }
        onUpdateTranscript={
          activeSession && onUpdateCaptureTranscript
            ? async (captureId, transcript) => {
                const updated = await onUpdateCaptureTranscript(activeSession.id, captureId, transcript);
                if (updated) setSelectedCapture(updated);
                return updated;
              }
            : undefined
        }
      />
    </section>
  );
}
