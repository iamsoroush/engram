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
import { AiCreatedPatientPanel } from "./CaptureBadges";
import { reportUpdatingLabel, workspaceReportState, textDirection, sessionSummaryStatusChip, sessionSummaryTitle, lightSessionTitle, captureNotSynced, sessionPatientName, aiPatientActionForSession, sessionSummaryCreatedLabel, sessionSummaryUpdatedLabel, workspaceTreatments, suggestedAftercareTemplateIds } from "../captureModel";
import { PatientIcon, BackIcon, ClipboardIcon, EditIcon, AddPatientIcon, SyncIcon, ClockHistoryIcon } from "./CaptureIcons";

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
  backLabel = "Clinical Memory",
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
  onFetchPatient,
  tier,
  sessionContext,
  lineupCard,
  onOpenVisit,
  onViewPatientHistory,
  onUseAsNote,
  aftercareTemplates,
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
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  tier?: string | null;
  /** Deterministic session context (last-visit digest + cross-visit photo strip), surfaced at
   * capture in both tiers once the patient is determined. */
  sessionContext?: SessionContext | null;
  /** Pro: the active patient's Job-4 curated brief, rendered in place of the raw digest. */
  lineupCard?: LineupCard | null;
  onOpenVisit?: (sessionId: string) => void;
  /** Jump to the assigned patient's full timeline, with a one-tap "back to this visit". */
  onViewPatientHistory?: (patientId: string) => void;
  onUseAsNote?: (text: string) => void;
  /** Clinic aftercare templates — one-tap deterministic follow-up instructions (both tiers). */
  aftercareTemplates?: AftercareTemplate[];
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
  const isPro = tier !== "basic";
  // Pro smart aftercare: promote the clinic's templates that match the procedures performed this
  // visit (deterministic match against the extracted treatments). Basic shows the flat list.
  const aftercareSuggestedIds =
    isPro && aftercareTemplates?.length ? suggestedAftercareTemplateIds(aftercareTemplates, workspaceTreatments(activeSession)) : new Set<string>();
  const suggestedAftercare = (aftercareTemplates || []).filter((template) => aftercareSuggestedIds.has(template.id));
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [reportView, setReportView] = React.useState<"draft" | "structured">("draft");
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const isHistorical = mode === "historical";
  // Basic active visits get a lightweight header — no "Complete" badge, no raw "Session <time>"
  // name. Title = the patient's Nth session when assigned, else the session date+time. Sync state
  // only shows when offline/unreachable (calm when everything is fine).
  const lightHeader = !isPro && !isHistorical;
  const lightTitle = lightSessionTitle(activeSession, sessionOrdinal);
  const sessionPending = !isHistorical && Boolean(activeSession?.items.some((item) => captureNotSynced(item.status)));
  const processingState = activeSession?.processingStatus?.state;
  // The live report regenerates automatically as captures land (Epic E); "updating" is a calm
  // inline state, never a gate. Pro = synthesized; Basic = chronological.
  const isUpdatingReport = isPro && (processingState === "processing" || activeSession?.report?.status === "generating");
  const reportState = workspaceReportState(activeSession);
  const selectedReportView = reportView;
  const sessionTitle = sessionSummaryTitle(activeSession, isHistorical);
  // Pro keeps its status chip + meta, but the title gets the same meaningful naming as Basic — a
  // real AI report title when there is one, otherwise "{patient}'s Nth session" / the date+time
  // (instead of a raw "Session <timestamp>" label).
  const proTitle =
    !isHistorical && (sessionTitle === "Current session" || /^session\s/i.test(sessionTitle))
      ? lightSessionTitle(activeSession, sessionOrdinal)
      : sessionTitle;
  const patientName = sessionPatientName(activeSession);
  const aiPatientAction = aiPatientActionForSession(activeSession);
  const captureCount = activeSession?.items.length || 0;
  const captureCountLabel = `${captureCount} capture${captureCount === 1 ? "" : "s"}`;
  const sessionStatusChip = sessionSummaryStatusChip(activeSession);
  const sessionCreatedLabel = sessionSummaryCreatedLabel(activeSession);
  const sessionUpdatedLabel = sessionSummaryUpdatedLabel(activeSession);

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

  return (
    <section className="capture-current session-workspace" aria-label={isHistorical ? "Historical session review" : "Active session workspace"}>
      {onBack ? (
        <button className="context-back-button" onClick={onBack} type="button">
          <BackIcon />
          {backLabel}
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
                  <span className="session-sync-pending"><SyncIcon /> Trying to sync the session</span>
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
              <p>{sessionCreatedLabel} <span aria-hidden="true">&bull;</span> {captureCountLabel} <span aria-hidden="true">&bull;</span> {sessionUpdatedLabel}</p>
            </>
          )}
        </div>
        <div className="workspace-header-actions">
          {isHistorical && onResumeCapture ? (
            <Button disabled={!activeSession} onClick={onResumeCapture} size="sm" type="button" variant="secondary">
              Add capture
            </Button>
          ) : null}
          {!isHistorical && onStartNewSession ? (
            <Button className="current-new-session" onClick={onStartNewSession} size="sm" type="button" variant="secondary">
              <span aria-hidden="true">+</span>
              New session
            </Button>
          ) : null}
        </div>
      </div>
      {readOnly && activeSession ? (
        <div className="session-readonly-banner" role="note">
          <span aria-hidden="true">🔒</span>
          <span>
            {activeSession.createdBy?.displayName
              ? `Started by ${activeSession.createdBy.displayName} — read-only for you. You can still add captures.`
              : "Owned by another clinician — read-only for you. You can still add captures."}
          </span>
        </div>
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
                ? assignmentSourceLabel(activeSession.assignmentSource)
                : "Assigned manually"
              : "Capture-first — assign when ready"}
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
              History
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
                  Change
                </>
              ) : (
                <>
                  <AddPatientIcon />
                  Assign
                </>
              )}
            </button>
          ) : null}
        </div>
      </Card>
      {!isHistorical && nextLinedUpPatient && activeSession && !activeSession.patientId && !activeSession.patientName ? (
        <div className="next-lined-up" role="note">
          <span className="next-lined-up-copy">
            Next in your list: <strong dir={textDirection(nextLinedUpPatient.patientName)}>{nextLinedUpPatient.patientName}</strong>
          </span>
          <span className="next-lined-up-actions">
            {activeSession.items.length && onAssignActiveToNext ? (
              <Button size="sm" type="button" onClick={onAssignActiveToNext}>
                Assign this visit
              </Button>
            ) : null}
            {onStartNextVisit ? (
              <Button size="sm" variant="secondary" type="button" onClick={onStartNextVisit}>
                Start their visit
              </Button>
            ) : null}
          </span>
        </div>
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
      {/* Content-driven: aftercare only surfaces when a performed procedure matches a clinic template.
          Nothing captured / no procedure detected → no aftercare bar (no static template list). */}
      {!isHistorical && !readOnly && onUseAsNote && suggestedAftercare.length ? (
        <section className="aftercare-bar" aria-label="Follow-up & aftercare">
          <span className="aftercare-bar-label">Follow-up & aftercare · suggested for this visit</span>
          <div className="aftercare-bar-chips">
            {suggestedAftercare.map((template) => (
              <button
                key={template.id}
                className="aftercare-chip suggested"
                type="button"
                title={template.body}
                onClick={() => onUseAsNote(template.body)}
              >
                ✦ <span dir="auto">{template.name}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {activeSession && aiPatientAction && onCompleteAiCreatedPatient ? (
        <AiCreatedPatientPanel
          action={aiPatientAction}
          session={activeSession}
          onComplete={onCompleteAiCreatedPatient}
        />
      ) : null}
      <Card className={`workspace-report-card ${isUpdatingReport ? "processing" : ""}`}>
        <div className="report-heading">
          <div className="report-title-lockup">
            <span className="report-title-icon" aria-hidden="true">
              <ClipboardIcon />
            </span>
            <h2>Clinical report</h2>
          </div>
          <div className="report-heading-actions">
            {isUpdatingReport ? (
              <span className="report-updating" aria-live="polite">
                <span className="report-updating-spinner" aria-hidden="true" />
                {reportUpdatingLabel(activeSession)}
              </span>
            ) : null}
          </div>
        </div>
        <div className="report-toolbar">
          <div className="report-toolbar-actions">
            <div className="report-view-switch" aria-label="Report view">
              <button className={selectedReportView === "draft" ? "active" : ""} onClick={() => setReportView("draft")} type="button">
                Captures
              </button>
              <button
                className={selectedReportView === "structured" ? "active" : ""}
                onClick={() => setReportView("structured")}
                type="button"
              >
                Live report
              </button>
            </div>
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
          {selectedReportView === "structured" ? (
            <LiveReportView
              isPro={isPro}
              session={activeSession}
              onResolveFile={onResolveFile}
              onConfirmCarriedForward={onConfirmCarriedForward}
            />
          ) : (
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
          )}
        </div>
        <div className="workspace-report-footer">
          <div className="workspace-report-footer-copy">
            {isUpdatingReport ? (
              <span>{reportUpdatingLabel(activeSession)}</span>
            ) : isPro && activeSession?.complete ? (
              <span className="report-complete-note">✓ Complete · captures processed, patient assigned, report up to date</span>
            ) : null}
          </div>
        </div>
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
