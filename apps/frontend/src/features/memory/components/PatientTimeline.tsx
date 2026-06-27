// Patient timeline detail + cards for the Clinical Memory screens.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { PatientMemoryDetailResponse } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredPatientInformation } from "../../../domain/types";
import type { PatientEditDraft } from "../../../services/api/client";
import { Badge, Button, Card } from "../../../shared/ui/primitives";
import { attributionName } from "../../../shared/lib/multiseat";
import { PatientPhotoGallery, type GalleryVisit } from "../../aesthetics/PatientPhotoGallery";
import { QaChannelButton } from "../../qa/QaChannelButton";
import type { QaThreadSummary } from "../../qa/qaClient";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { ClinicalMemoryReturnContext, PatientRowModel, TimelineSessionModel, sessionVisitTitle, sanitizeSessionLabel, visitCountLabel, patientSessionsForDetail, buildTimelineGroups, timelineSessionTimeLabel, timelineUpdatedLabel, timelineSessionStatus, timelineSessionAction, firstSeenLabel, naturalSessionSummary } from "./memoryModel";
import { BackIcon, CalendarIcon, EditPatientIcon, ShareSmallIcon, ChevronIcon, InfoIcon } from "./MemoryIcons";
import { Avatar, PatientHistoryBlock, EmptyClinicalState, TimelineCaptureChips } from "./MemoryCards";
import { PatientIdentityEditor } from "./MemorySheets";
import { appT } from "../../../shared/i18n";

export function PatientTimelineDetail({
  activeSession,
  detail,
  loading,
  loadError,
  patient,
  isPro,
  sessions,
  onAssignPatient,
  onBack,
  onBackToVisit,
  onContinueSession,
  onOpenSession,
  onReviewSummary,
  onUpdatePatient,
  onFetchPatient,
  onLoadSessionCaptures,
  onResolveFile,
  onShare,
  currentUserId,
  onOpenQaChannel,
  onToast,
}: {
  activeSession: CaptureSession | null;
  detail?: PatientMemoryDetailResponse;
  loading: boolean;
  loadError: boolean;
  patient: PatientRowModel;
  isPro: boolean;
  sessions: CaptureSession[];
  onAssignPatient: (sessionId: string) => void;
  onBack: () => void;
  /** When set (arrived from an in-progress visit), the single back button returns to that visit. */
  onBackToVisit?: () => void;
  onContinueSession: (sessionId: string) => void;
  onOpenSession: (sessionId: string, context?: ClinicalMemoryReturnContext) => void;
  onReviewSummary: (sessionId: string) => void;
  onUpdatePatient?: (patientId: string, draft: PatientEditDraft) => Promise<void>;
  onFetchPatient?: (patientId: string) => Promise<StructuredPatientInformation | null>;
  onLoadSessionCaptures?: (sessionId: string) => Promise<CaptureItem[]>;
  onResolveFile?: (endpoint: string) => Promise<string>;
  onShare?: (visits: GalleryVisit[]) => void;
  currentUserId?: string;
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
}) {
  const [editingPatient, setEditingPatient] = React.useState(false);
  const localSessions = patientSessionsForDetail(patient, sessions, activeSession);
  const timelineGroups = buildTimelineGroups(detail, localSessions);
  const sessionCount = detail?.patient.sessionCount || patient.sessionCount || localSessions.length;
  const firstSeen = firstSeenLabel(detail?.sessions, localSessions);
  // AES-202 — recent visits, most-recent first, fed to the visit-grouped photo gallery (Basic).
  const galleryVisits: GalleryVisit[] = timelineGroups
    .flatMap((group) => group.sessions)
    .map((session) => ({
      sessionId: session.sessionId,
      title: sanitizeSessionLabel(session.title) || (session.localSession ? sessionVisitTitle(session.localSession) : "Visit"),
      dateLabel: timelineSessionTimeLabel(session, session.localSession),
    }))
    .filter((visit) => visit.sessionId);

  return (
    <div className="patient-detail" aria-label={`${patient.name} patient memory`}>
      {onBackToVisit ? (
        <button className="context-back-button context-back-button--to-visit" onClick={onBackToVisit} type="button">
          <BackIcon />
          Back to this visit
        </button>
      ) : (
        <button className="context-back-button" onClick={onBack} type="button">
          <BackIcon />
          Patients
        </button>
      )}

      <section className="patient-detail-header">
        <Avatar label={patient.name} tone={patient.needsInput ? "amber" : "green"} />
        <div className="patient-detail-heading">
          <h1>{patient.name}</h1>
          <div className="patient-detail-meta" aria-label="Patient metadata">
            <span>{visitCountLabel(sessionCount)}</span>
            {firstSeen ? <span>First seen {firstSeen}</span> : null}
          </div>
        </div>
      </section>

      {/* Cross-visit clinical safety flags — confirmed (non-rejected) across this patient's visits,
          surfaced prominently at the top of their file. Flag body is report-language content. */}
      {detail?.safetyFlags?.length ? (
        <div className="patient-detail-safety" role="note" aria-label={appT("context.safety.aria")}>
          <span className="patient-detail-safety-label">{appT("context.safety.label")}</span>
          <ul className="patient-detail-safety-list">
            {detail.safetyFlags.map((flag) => (
              <li key={flag.key} className={`patient-detail-safety-flag safety-${flag.kind}`} dir="auto">
                <span className="patient-detail-safety-kind">{appT(`safety.kind.${flag.kind}`)}</span>
                <span className="patient-detail-safety-text">{flag.text}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {(onUpdatePatient || onShare) && !editingPatient ? (
        <div className="patient-detail-actions">
          {onUpdatePatient ? (
            <button className="patient-detail-action" onClick={() => setEditingPatient(true)} type="button">
              <EditPatientIcon /> Edit details
            </button>
          ) : null}
          {onShare ? (
            <button className="patient-detail-action" onClick={() => onShare(galleryVisits)} type="button">
              <ShareSmallIcon /> Share with patient
            </button>
          ) : null}
          {isPro && onOpenQaChannel ? (
            <QaChannelButton patientName={patient.name} onOpen={() => onOpenQaChannel(patient.id)} onToast={onToast} />
          ) : null}
        </div>
      ) : null}

      <PatientIdentityEditor
        patient={patient}
        open={editingPatient}
        onClose={() => setEditingPatient(false)}
        onUpdatePatient={onUpdatePatient}
        onFetchPatient={onFetchPatient}
      />

      <PatientHistoryBlock
        history={detail?.history}
        isPro={isPro}
        loading={loading}
        fallbackSnapshot={detail?.patient.summary || patient.summary}
      />

      {!isPro ? (
        <TryProTeaser
          className="patient-file-teaser"
          title={'Try Pro — AI history & "what did we use last time?"'}
          subtitle="Basic lists the facts. Pro synthesizes the story and recalls products / units / lot."
        />
      ) : null}

      {onLoadSessionCaptures && onResolveFile && galleryVisits.length ? (
        <PatientPhotoGallery
          visits={galleryVisits}
          onLoadSessionCaptures={onLoadSessionCaptures}
          onResolveFile={onResolveFile}
          onOpenVisit={(sessionId) => onOpenSession(sessionId, { tab: "patients", patientId: patient.id })}
        />
      ) : null}

      {loadError ? <p className="clinical-offline-note"><InfoIcon /> Showing memory saved on this device.</p> : null}
      {loading && !timelineGroups.length ? <PatientTimelineLoading /> : null}

      <div className="patient-timeline" aria-label="Visit timeline">
        {timelineGroups.length ? (
          timelineGroups.map((group) => (
            <section className="patient-timeline-group" key={group.label}>
              <div className="patient-timeline-marker" aria-hidden="true" />
              <h2>{group.label}</h2>
              <div className="patient-timeline-cards">
                {group.sessions.map((session) => (
                  <PatientTimelineCard
                    key={session.sessionId}
                    localSession={session.localSession}
                    session={session}
                    currentUserId={currentUserId}
                    onAssignPatient={onAssignPatient}
                    onContinueSession={onContinueSession}
                    onOpenSession={(sessionId) => onOpenSession(sessionId, { tab: "patients", patientId: patient.id })}
                    onReviewSummary={onReviewSummary}
                  />
                ))}
              </div>
            </section>
          ))
        ) : loading ? null : (
          <EmptyClinicalState title="No visits yet." copy="Patient visits will appear here after capture." />
        )}
      </div>
    </div>
  );
}

export function PatientTimelineCard({
  localSession,
  session,
  currentUserId,
  onAssignPatient,
  onContinueSession,
  onOpenSession,
  onReviewSummary,
}: {
  localSession?: CaptureSession;
  session: TimelineSessionModel;
  currentUserId?: string;
  onAssignPatient: (sessionId: string) => void;
  onContinueSession: (sessionId: string) => void;
  onOpenSession: (sessionId: string) => void;
  onReviewSummary: (sessionId: string) => void;
}) {
  const status = timelineSessionStatus(session, localSession);
  const action = timelineSessionAction(session, localSession);
  const tone = status.startsWith("Needs input") ? "amber" : status === "Complete" ? "blue" : "green";
  const title = session.title || (localSession ? sessionVisitTitle(localSession) : "Visit");
  const summary = session.generatedSummary || session.summary || (localSession ? naturalSessionSummary(localSession) : "") || "This visit is saved in patient memory.";
  const updatedLabel = timelineUpdatedLabel(session, localSession);

  const runAction = () => {
    if (action.kind === "continue") onContinueSession(session.sessionId);
    else if (action.kind === "assign") onAssignPatient(session.sessionId);
    else if (action.kind === "review") onReviewSummary(session.sessionId);
    else onOpenSession(session.sessionId);
  };

  return (
    <Card className={["patient-timeline-card", `patient-timeline-card-${tone}`].join(" ")}>
      <div className="patient-timeline-card-icon" aria-hidden="true">
        <CalendarIcon />
      </div>
      <div className="patient-timeline-card-copy">
        <div className="visit-card-title-row">
          <h3>{title}</h3>
          <Badge tone={tone}>{status}</Badge>
        </div>
        <div className="visit-metadata" aria-label="Visit times">
          <div>
            <span>Session:</span>
            <strong>{timelineSessionTimeLabel(session, localSession)}</strong>
          </div>
          {updatedLabel ? (
            <div className={updatedLabel.startsWith("Updated today") ? "visit-metadata-success" : undefined}>
              {updatedLabel.startsWith("Updated today") ? null : <span>Updated:</span>}
              <strong>{updatedLabel}</strong>
            </div>
          ) : null}
          {session.createdBy ? (
            <div className="visit-metadata-attribution">
              <span>By:</span>
              <strong>{attributionName(session.createdBy, currentUserId)}</strong>
            </div>
          ) : null}
        </div>
        <p>{summary}</p>
        <TimelineCaptureChips session={session} localSession={localSession} tone={tone} />
      </div>
      <div className="patient-timeline-actions">
        <Button onClick={runAction} size="sm" type="button" variant={tone === "amber" ? "secondary" : action.kind === "open" ? "secondary" : "default"}>
          {action.label}
          <ChevronIcon />
        </Button>
      </div>
    </Card>
  );
}

export function PatientTimelineLoading() {
  return (
    <Card className="clinical-row clinical-row-loading">
      <span className="clinical-avatar clinical-avatar-blue" />
      <div className="clinical-row-copy">
        <span />
        <p />
      </div>
      <span />
    </Card>
  );
}
