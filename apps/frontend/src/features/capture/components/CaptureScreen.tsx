// Capture screen shell (orchestration); presentational pieces live in sibling files.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import "../sessionSurface.css";
import type { AftercareTemplate, LineupCard, PatientAssignmentDraft, PatientSummary, SessionContext } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import { assignmentSourceLabel } from "../metadata";
import { Button, Card } from "../../../shared/ui/primitives";
import { SessionContextCard } from "../../aesthetics/SessionContextCard";
import { SourcePreviewDialog } from "./SourcePreview";
import { PatientAssignmentSheet } from "./PatientAssignmentSheet";
import { LiveDraftReport } from "./LiveDraftReport";
import { LiveReportView, BasicLiveReport } from "./LiveReport";
import { ReportFeedbackBar } from "./ReportFeedbackBar";
import { CaptureTimelineIcon, AiSpark, captureConflictSuggestion, AiCreatedPatientPanel, PatientConflictResolver } from "./CaptureBadges";
import { NextLinedUpBar, SessionSafetyPanel } from "./CaptureRegions";
import { PatientStrip } from "./PatientStrip";
import { ReportHistoryButton } from "../reportHistory";
import { reportUpdatingLabel, workspaceReportState, textDirection, sessionSummaryStatusChip, sessionSummaryTitle, isPlaceholderSessionTitle, lightSessionTitle, captureNotSynced, sessionPatientName, aiPatientActionForSession, aiCreatedPatientNeedsVerification, sessionSummaryCreatedLabel, sessionSummaryUpdatedLabel, workspaceTreatments, suggestedAftercareTemplateIds, sessionTreatmentReview, sessionConfirmedCarriedForward, sessionDismissedAftercare, sessionAftercareSelections, sessionKeptSafetyFlags, workspaceStructuredReportCopy, activePatientAssignmentActionForSession, sessionAssignmentCandidates, alternateCandidateForCapture, ordinalWord } from "../captureModel";
import type { AftercareSelection } from "../captureModel";
import { PatientIcon, BackIcon, ClipboardIcon, EditIcon, AddPatientIcon, SyncIcon, ClockHistoryIcon, ShareIcon } from "./CaptureIcons";
import { isPersianLocale } from "../../../shared/lib/datetime";
import { useT } from "../../../shared/i18n";
import { useMemoryApi } from "../../memory/useMemoryApi";
import { useAuth } from "../../../app/providers/AuthProvider";
import { useCapabilities } from "../../../app/providers/CapabilitiesProvider";
import { useSync } from "../../../app/providers/SyncProvider";
import { useSessionActions } from "../../../app/providers/SessionStoreProvider";

export function CaptureScreen({
  activeSession,
  mode = "active",
  onBack,
  backLabel,
  onResumeCapture,
  assignmentOpen,
  onCloseAssignment,
  onOpenResolver,
  onStartNewSession,
  sessionContext,
  lineupCard,
  onOpenVisit,
  onViewPatientHistory,
  onShareVisit,
  onUseAsNote,
  aftercareTemplates,
  sessionOrdinal = null,
  currentUserId = null,
  readOnly = false,
  nextLinedUpPatient = null,
  onAssignActiveToNext,
  onStartNextVisit,
  usageNotice = null,
}: {
  activeSession: CaptureSession | null;
  mode?: "active" | "historical";
  onBack?: () => void;
  backLabel?: string;
  onResumeCapture?: () => void;
  assignmentOpen?: boolean;
  onCloseAssignment?: () => void;
  /** Open the assignment resolver from a capture-card "Choose another" quick action (H4). */
  onOpenResolver?: () => void;
  onStartNewSession?: () => void;
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
  /** Calm, non-blocking fair-use AI notice (approaching / limit reached). Informational only. */
  usageNotice?: React.ReactNode;
}) {
  const t = useT();
  // Seam consumption (frontend-refactor plan §3, increment 6): the session-mutation callbacks +
  // resolve-file + tier/reportLanguage/offline this screen used to receive collapse into
  // useSessionActions() + useMemoryApi() + capability/sync/auth context, aliased to the local names the
  // body uses. Per-render-site props (activeSession/mode/assignmentOpen), the App-computed display
  // slices (sessionContext/lineupCard/aftercareTemplates/nextLinedUpPatient/usageNotice/sessionOrdinal/
  // readOnly) and navigation callbacks stay as props — they move to region components + the router seam
  // (increments 7/8).
  const { resolveSourceFile: onResolveFile } = useMemoryApi();
  const { tier } = useCapabilities();
  const { offline } = useSync();
  const tenant = useAuth().auth?.tenant;
  const reportLanguage = tenant?.reportLanguage ?? null;
  // Coarse fallback for the report section-title language when the tenant's report_language is NULL:
  // the report body follows the transcript, so titles infer from content, then this app language (R1).
  const appLanguage = tenant?.appLanguage ?? null;
  // Session-layout-diet: a high-risk clinic pins the full safety panel open (never a collapsed chip).
  const highRiskClinic = tenant?.highRiskClinic ?? false;
  const {
    renameSession: onUpdateTitle,
    renameCapture: onRenameCapture,
    editCaptureNote: onUpdateNote,
    removeCaptureFromSession: onDeleteCapture,
    assignPatientToSession: onAssignPatient,
    searchPatientsForAssignment: onSearchPatients,
    completeAiCreatedPatient: onCompleteAiCreatedPatient,
    markCaptureRelevantInSession: onMarkRelevant,
    confirmCarriedForwardDose: onConfirmCarriedForward,
    rateReport: onRateReport,
    fetchAssignedPatientDetails: onFetchPatient,
    fetchCaptureById: onFetchCapture,
    dismissAftercareTemplate: onDismissAftercare,
    rejectSafetyFlagFromSession: onRejectSafetyFlag,
    applyPatientNameCorrection: onApplyNameCorrection,
    unassignPatientFromSession: onUnassignPatient,
    editTreatmentField: onEditTreatmentField,
    revertTreatmentField: onRevertTreatmentField,
    editCaptureSourceText,
  } = useSessionActions();
  const onUpdateCaptureCaption = (sessionId: string, captureId: string, caption: string) =>
    editCaptureSourceText(sessionId, captureId, caption, "caption");
  const onUpdateCaptureTranscript = (sessionId: string, captureId: string, transcript: string) =>
    editCaptureSourceText(sessionId, captureId, transcript, "transcript");
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

  // Tier-convergence (AES-1401): both tiers now share ONE tabless skeleton —
  // patient strip → primary working surface → secondary collapsible view → capture bar. What sits in
  // "primary" differs by tier because the valuable artifact differs: Pro's primary is the synthesized
  // REPORT (raw captures demoted to the collapsible "Sources" drawer); Basic's primary is the captures
  // FEED itself (the tidy chronological document is the secondary "View as document" panel below). The
  // legacy Captures/Live-report tab switch is deleted in both tiers; the AI zones stay capability-gated
  // on `isPro`, so Basic omits them cleanly (no empty bands) rather than disabling them.
  // Sticky verify driver counts ONLY blockers — unconfirmed carried-forward doses + an AI-created
  // patient awaiting identity verification. Soft warnings (missing lot, low confidence) stay inline
  // in the report and never feed this count, keeping the bar calm ("warnings over blocking").
  const treatmentReview = sessionTreatmentReview(activeSession);
  const confirmedCarriedForward = new Set(sessionConfirmedCarriedForward(activeSession));
  // Keys (area|product) of the treatment rows actually rendered — the inline "Confirm dose" box lives
  // on one of these rows, so only a carried-forward item WITH a matching row has a reachable resolver.
  // (Reachability invariant: a counted dose confirm that had no row would be a phantom count.)
  const workspaceTreatmentRows = workspaceTreatments(activeSession);
  const renderedTreatmentKeys = new Set(
    workspaceTreatmentRows.map((treatment) => `${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`),
  );
  // Q4: a carried-forward dose the clinician re-dosed via the overlay is already confirmed by the edit
  // — its inline confirm collapses, so it must not keep inflating the "N to confirm" count either.
  const doseEditedKeys = new Set(
    workspaceTreatmentRows
      .filter((treatment) => treatment.overlayEditedFields?.includes("quantity"))
      .map((treatment) => `${(treatment.area || "").trim()}|${(treatment.product || "").trim()}`),
  );
  const openDoseConfirmations = treatmentReview.filter(
    (item) =>
      item.category === "carried_forward" &&
      item.key &&
      !confirmedCarriedForward.has(item.key) &&
      renderedTreatmentKeys.has(item.key) &&
      !doseEditedKeys.has(item.key),
  );
  // A blocker only when there is an AI-*created* patient still awaiting verification — NOT any stored
  // `ai_patient_action` (a plain match, or an already-verified create, is no blocker). Gated on the same
  // predicate the resolver renders on, so the count and the reachable resolver stay in lock-step.
  const patientVerifyNeeded = Boolean(onCompleteAiCreatedPatient) && aiCreatedPatientNeedsVerification(aiPatientAction, activeSession);
  // Patient CONFLICTS (a capture dictated a different/partial-match patient than the assigned one) are
  // a session-level blocker too — surfaced in the verify region + counted, not buried in the Sources
  // drawer (FB8). Resolution is in place via the shared PatientConflictResolver. Local dismiss only.
  const [dismissedConflicts, setDismissedConflicts] = React.useState<Set<string>>(new Set());
  React.useEffect(() => setDismissedConflicts(new Set()), [activeSession?.id]);
  const assignmentCandidates = sessionAssignmentCandidates(activeSession);
  const activeAssignmentAction = activePatientAssignmentActionForSession(activeSession);
  const patientConflicts =
    !isHistorical
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
    // Topmost blocker first: the always-visible conflict band, then the strip's AI-created-patient
    // verify region (revealed by expanding the strip), then the first inline carried-forward dose row.
    const target =
      document.querySelector(".session-conflict-band") ||
      verifyRegionRef.current ||
      document.querySelector(".treatment-item.needs-confirm");
    target?.scrollIntoView({ behavior: "smooth", block: target?.classList?.contains("treatment-item") ? "center" : "start" });
  };
  // The Sources drawer opens by default while the report has no content yet (early capture, before
  // synthesis), so a fresh session never looks empty; once the report has body the drawer collapses.
  const reportHasContent = Boolean(
    activeSession?.reportModel?.sections?.some((section) => section.blocks?.length) ||
      workspaceStructuredReportCopy(activeSession).length ||
      workspaceTreatments(activeSession).length,
  );
  // --- Session-layout-diet: patient-strip derived state ---
  const patientAssigned = Boolean(activeSession?.patientId || activeSession?.patientName);
  // The collapsed strip's assignment line — "✓ assigned" / "Matched by AI" / soft-amber "Unassigned".
  const assignmentStateLabel = patientAssigned
    ? activeSession?.assignmentSource
      ? assignmentSourceLabel(activeSession.assignmentSource, t)
      : t("strip.assignedCheck")
    : t("strip.unassigned");
  const visitOrdinalLabel = sessionOrdinal ? t("strip.nthVisit", { ordinal: ordinalWord(sessionOrdinal, t) }) : null;
  // Whether the assigned patient has prior history worth auto-surfacing on (re)assignment.
  const stripHasHistory = Boolean(
    sessionContext && (sessionContext.lastVisit?.hasPriorVisit || sessionContext.totalPriorVisits > 0 || sessionContext.safetyFlags?.length),
  );
  // Changes on every (re)assignment so the strip's state machine can re-surface the history.
  const assignmentSignal = `${activeSession?.patientId ?? ""}:${activeSession?.assignmentSource ?? ""}`;
  // High-risk clinics keep the full safety panel pinned above the report (never a collapsed chip).
  const safetyPinned = highRiskClinic && keptSafetyFlags.length > 0;
  const [sourcesOpen, setSourcesOpen] = React.useState(false);
  const sourcesShown = sourcesOpen || !reportHasContent;
  const sourcesDrawerRef = React.useRef<HTMLElement>(null);
  // Basic secondary "View as document" panel (AES-1403): the tidy chronological notebook (AES-302) for
  // review / print / share. Unlike Pro's Sources drawer it NEVER auto-expands — in Basic the feed always
  // leads and the document is opt-in (§3.2). Opened by the lightweight header affordance (decision 1);
  // the curated Share lives inside the expanded document (it flows into AES-303).
  const [documentOpen, setDocumentOpen] = React.useState(false);
  const documentPanelRef = React.useRef<HTMLElement>(null);
  // The Basic "View as document" affordance shows once there is something to render as a document.
  const documentAvailable = !isPro && captureCount > 0;
  const toggleDocument = () => {
    setDocumentOpen((open) => {
      const next = !open;
      if (next) window.requestAnimationFrame(() => documentPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      return next;
    });
  };
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
                {/* Empty visit: collapse the meta to one honest fragment (UI-review #6) — a fresh visit
                    reads "Created just now", not "0 captures". The count returns once captures land. */}
                {captureCount === 0 ? t("model.session.createdJustNow") : captureCountLabel}
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
              {/* Empty active visit: collapse "Created now · 0 captures · Updated recently" (three
                  fragments, two redundant + self-contradictory) to one honest line (UI-review #6). The
                  count + updated fragments return once they carry real, diverging information. */}
              {!isHistorical && captureCount === 0 ? (
                <p data-testid="session-meta">{t("model.session.createdJustNow")}</p>
              ) : (
                <p data-testid="session-meta">{sessionCreatedLabel} <span aria-hidden="true">&bull;</span> {captureCountLabel} <span aria-hidden="true">&bull;</span> {sessionUpdatedLabel}</p>
              )}
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
      {/* AI-usage notice — a thin, calm bar ABOVE the patient strip (rare; only near/at budget). */}
      {!isHistorical && usageNotice ? usageNotice : null}
      {!isHistorical && activeSession ? (
        <>
          {/* The pinned, collapsible patient strip: identity + context + verify chips + safety chip in
              one line above the report; the diet turns nine zones into strip → report. */}
          <PatientStrip
            patientName={patientName}
            assigned={patientAssigned}
            assignmentStateLabel={assignmentStateLabel}
            visitOrdinalLabel={visitOrdinalLabel}
            onAssignOrChange={onCloseAssignment}
            onViewHistory={activeSession.patientId && onViewPatientHistory ? () => onViewPatientHistory(activeSession.patientId as string) : undefined}
            verifyCount={verifyCount}
            onReview={scrollToVerify}
            safetyChipCount={safetyPinned ? 0 : keptSafetyFlags.length}
            hasCaptures={captureCount > 0}
            reportHasContent={reportHasContent}
            hasHistory={stripHasHistory}
            assignmentSignal={assignmentSignal}
            isHistorical={false}
            contextCard={
              activeSession.patientId && sessionContext ? (
                <SessionContextCard
                  context={sessionContext}
                  isPro={isPro}
                  lineupCard={lineupCard}
                  onOpenVisit={onOpenVisit}
                  onUseAsNote={onUseAsNote}
                  onResolveFile={onResolveFile}
                  collapsed={false}
                />
              ) : null
            }
            safetyPanel={
              !safetyPinned ? (
                <SessionSafetyPanel
                  flags={keptSafetyFlags}
                  sessionId={activeSession.id}
                  canEdit={!readOnly}
                  onReject={onRejectSafetyFlag}
                />
              ) : null
            }
            aiCreatedPanel={
              patientVerifyNeeded ? (
                <AiCreatedPatientPanel action={aiPatientAction as Record<string, unknown>} session={activeSession} onComplete={onCompleteAiCreatedPatient as NonNullable<typeof onCompleteAiCreatedPatient>} />
              ) : null
            }
            verifyRef={verifyRegionRef}
          />
          {/* High-risk clinic: the full safety panel stays pinned above the report (never a chip). */}
          {safetyPinned ? (
            <SessionSafetyPanel flags={keptSafetyFlags} sessionId={activeSession.id} canEdit={!readOnly} onReject={onRejectSafetyFlag} />
          ) : null}
          {nextLinedUpPatient && !activeSession.patientId && !activeSession.patientName ? (
            <NextLinedUpBar
              patientName={nextLinedUpPatient.patientName}
              hasCaptures={Boolean(activeSession.items.length)}
              onAssignActiveToNext={onAssignActiveToNext}
              onStartNextVisit={onStartNextVisit}
            />
          ) : null}
          {/* Active patient conflicts stay in a thin, always-visible band above the report — visible and
              resolvable in place, never buried in the strip (owner round-2 decision). */}
          {patientConflicts.length ? (
            <section className="session-conflict-band" aria-label={t("capture.patientNeedsConfirmation")}>
              {patientConflicts.map((conflict) => (
                <PatientConflictResolver
                  key={conflict.captureId}
                  suggestion={conflict.suggestion as Exclude<typeof conflict.suggestion, null>}
                  basisCaptureId={conflict.captureId}
                  onApply={onAssignPatient ? (draft) => onAssignPatient(activeSession.id, draft) : undefined}
                  onApplyNameCorrection={(spokenName) => onApplyNameCorrection(activeSession.id, spokenName, conflict.captureId)}
                  onUnassign={() => onUnassignPatient(activeSession.id, conflict.captureId)}
                  onChooseAnother={onOpenResolver}
                  onDismiss={() => setDismissedConflicts((current) => new Set(current).add(conflict.captureId))}
                />
              ))}
            </section>
          ) : null}
        </>
      ) : null}
      {/* Fresh visit (no local session yet, zero captures): the same patient strip so identity + Assign
          are reachable from visit creation (AES-1801) — assignment stays optional and capture-first is untouched.
          Tapping Assign lazily creates the local session and opens the assignment sheet; once the session
          exists the full strip above takes over. All AI/context/safety panels are absent (nothing to show). */}
      {!isHistorical && !activeSession ? (
        <PatientStrip
          patientName={patientName}
          assigned={false}
          assignmentStateLabel={assignmentStateLabel}
          visitOrdinalLabel={null}
          onAssignOrChange={onCloseAssignment}
          verifyCount={0}
          onReview={scrollToVerify}
          safetyChipCount={0}
          hasCaptures={false}
          reportHasContent={false}
          hasHistory={false}
          assignmentSignal={assignmentSignal}
          isHistorical={false}
        />
      ) : null}
      {/* Historical review keeps the flat patient card (no strip diet — it's read-only visit review). */}
      {isHistorical ? (
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
              <button className="patient-context-action" onClick={() => onViewPatientHistory(activeSession.patientId as string)} type="button">
                <ClockHistoryIcon />
                {t("capture.history")}
              </button>
            ) : null}
            {onCloseAssignment ? (
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
      ) : null}
      <Card className={`workspace-report-card ${isPro ? "" : "basic-feed-primary"} ${isUpdatingReport ? "processing" : ""}`}>
        <div className="report-heading">
          <div className="report-title-lockup">
            {/* The clipboard/document icon reads as "the report"; it anchors Pro's report title. Basic's
                primary is the raw captures FEED (no report artifact), so it drops the icon — the document
                the clipboard stands for lives behind the "View as document" affordance instead. */}
            {isPro ? (
              <span className="report-title-icon" aria-hidden="true">
                <ClipboardIcon />
              </span>
            ) : null}
            {/* Pro primary = the synthesized report; Basic primary = the captures feed itself (AES-1402). */}
            <h2>{isPro ? t("capture.clinicalReport") : t("capture.capturesHeading")}</h2>
            {/* AI-provenance mark: the Pro report is AI-synthesized; the spark twinkles while the
                synthesis is organizing (the "editing" phase), so the icon itself signals AI is at work.
                Absent in zero-AI Basic (AES-1404 — omitted, not disabled). */}
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
            {/* Basic's lightweight "View as document" header affordance (AES-1403, decision 1): opens the
                secondary document panel — the tidy chronological notebook that flows into the curated
                Share. This is where the "report" concept lives in Basic: a review/outbound artifact, not
                the daily surface. */}
            {documentAvailable ? (
              <button
                className="report-doc-button"
                type="button"
                onClick={toggleDocument}
                aria-expanded={documentOpen}
                title={t("capture.viewAsDocumentHint")}
              >
                <ClipboardIcon />
                <span className="report-doc-button-label">{t("capture.viewAsDocument")}</span>
              </button>
            ) : null}
            {/* E17 report version-history (AES-17xx) — the sole mount surface; all history UI is self-contained. */}
            {isPro && activeSession && activeSession.items.length ? (
              <ReportHistoryButton session={activeSession} canRestore={!isHistorical && !readOnly} />
            ) : null}
          </div>
        </div>
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
          {/* Tier-appropriate primary working surface (AES-1401/1402): Pro = the synthesized report;
              Basic = the captures FEED itself (edit / play / delete directly reachable, no drawer to open
              for daily work). Basic's tidy chronological document is the secondary "View as document"
              panel below — not the daily surface. */}
          {isPro ? (
            <LiveReportView
              isPro={isPro}
              session={activeSession}
              onResolveFile={onResolveFile}
              onConfirmCarriedForward={onConfirmCarriedForward}
              onFixAtSource={onFixAtSource}
              onOpenSource={openSourceCapture}
              onEditTreatmentField={activeSession ? (treatmentKey, field, value) => onEditTreatmentField(activeSession.id, treatmentKey, field, value) : undefined}
              onRevertTreatmentField={activeSession ? (treatmentKey, field) => onRevertTreatmentField(activeSession.id, treatmentKey, field) : undefined}
              canEditTreatments={isPro && !readOnly}
              currentUserId={currentUserId}
              reportLanguage={reportLanguage}
              appLanguage={appLanguage}
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
        {isPro && !isHistorical && !readOnly && (includedAftercare.length || aftercareConflicts.length) ? (
          <section className="report-aftercare-included" aria-label={t("capture.aftercareForThisVisit")}>
            <span className="report-aftercare-included-label">{t("capture.aftercareForThisVisitFromProtocol")}</span>
            {includedAftercare.map((template) => (
              <div className="aftercare-included-card" key={template.id}>
                <div className="aftercare-included-body">
                  <strong dir="auto">{template.name}</strong>
                  <p dir="auto">{template.body}</p>
                </div>
                {!isHistorical && activeSession ? (
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
                {/* A conflict/superseded note is opt-out too: dismissing it records the template id in
                    `dismissed_aftercare` (persists across re-synthesis) so the note stays gone. */}
                {!isHistorical && activeSession ? (
                  <button
                    className="aftercare-conflict-dismiss"
                    type="button"
                    aria-label={t("capture.removeTemplate", { name: conflict.template.name })}
                    title={t("capture.dismissConflictNote")}
                    onClick={() => onDismissAftercare(activeSession.id, conflict.template.id, true)}
                  >
                    ✕
                  </button>
                ) : null}
              </div>
            ))}
          </section>
        ) : null}
        {/* Report thumbs rating (eval golden-set harvester; eval-epic §1b) — a quiet end-cap AFTER the
            aftercare section so it reads "rate-after-reading" and never splits the clinical content;
            on mobile it's the last thing before the collapsible raw Sources. Pro report only. */}
        {isPro && activeSession && reportHasContent ? (
          // The rating prompt is app chrome, so it follows the APP UI language (isPersianLocale),
          // not the report's CONTENT language — a Persian report under an English app shows English.
          <ReportFeedbackBar isPersian={isPersianLocale()} onRate={(rating) => onRateReport(activeSession.id, rating)} />
        ) : null}
        {isPro && captureCount > 0 ? (
          // The raw captures, demoted to a collapsible "Sources" drawer beneath the report. Editing,
          // deleting, re-assigning and tapping into a capture all still live here (and via the report's
          // own source links). Auto-expanded while the report has no content yet.
          <section className="sources-drawer" ref={sourcesDrawerRef}>
            <div className="sources-drawer-header">
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
                to expand Sources and find it. Owner-only; same operation as the per-capture Delete.
                Lives INSIDE the header row (sibling of the summary — a button can't nest a button)
                as a quiet ghost action, not a floating pill on its own row. */}
            {!isHistorical && !readOnly && activeSession && lastCapture ? (
              <button
                className="sources-drawer-undo"
                type="button"
                onClick={() => onDeleteCapture(activeSession.id, lastCapture.id)}
                title={t("capture.undoLastHint")}
                aria-label={t("capture.undoLast")}
              >
                <span className="sources-drawer-undo-label">{t("capture.undoLast")}</span>
              </button>
            ) : null}
            </div>
            {sourcesShown ? <div className="sources-drawer-body">{captureFeed}</div> : null}
          </section>
        ) : null}
        {/* Basic's secondary collapsible view (AES-1403): the tidy chronological notebook (AES-302),
            opened opt-in from the "View as document" header affordance above (the feed always leads). It
            is the document's real home in Basic — a review / print / outbound artifact — and it flows
            into the curated clinic→patient Share (AES-303). The consolidated "Do more with Pro" teaser
            stays at the foot of the feed, so the screen keeps exactly one Try-Pro (E8). */}
        {documentAvailable && documentOpen ? (
          <section className="document-panel" ref={documentPanelRef} aria-label={t("capture.visitRecord")}>
            <div className="document-panel-header">
              <span className="document-panel-title">{t("capture.visitRecord")}</span>
              <div className="document-panel-actions">
                {/* Share the curated document with the patient (AES-303/401) — assigned visit only. */}
                {!isHistorical && !readOnly && activeSession?.patientId && activeSession.items.length && onShareVisit ? (
                  <button className="report-share-button" type="button" onClick={onShareVisit} aria-label={t("capture.shareWithPatient")} title={t("capture.shareWithPatient")}>
                    <ShareIcon />
                    <span className="report-share-button-label">{t("capture.share")}</span>
                  </button>
                ) : null}
                <button className="document-panel-close" type="button" onClick={() => setDocumentOpen(false)} aria-label={t("capture.closeDocument")} title={t("capture.closeDocument")}>
                  <span aria-hidden="true">✕</span>
                </button>
              </div>
            </div>
            <div className="document-panel-body">
              {/* The chronological notebook. Its own Try-Pro is suppressed — the single consolidated
                  teaser already sits at the foot of the primary feed (one Try-Pro per screen, E8). */}
              <BasicLiveReport session={activeSession} onResolveFile={onResolveFile} suppressTeaser />
            </div>
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
