import React from "react";
import type { PatientAssignmentDraft, PatientSummary } from "../appTypes";
import type { CaptureItem, CaptureSession, SessionProcessingStatus } from "../types";
import { isLocalSessionId } from "../captureModel";
import { assignmentSourceLabel, metadataDisplay, metadataRecord } from "../metadata";
import { sessionUxState } from "../status";
import { Badge, Button, Card, Input } from "../ui";
import { SourcePreviewDialog, CaptureRawPreview } from "./SourcePreview";
import { SessionStatusBadge, StatusBadge } from "./StatusBadges";

export function CaptureScreen({
  activeSession,
  onSaveSession,
  onResolveFile,
  onUpdateTitle,
  mode = "active",
  onBack,
  onResumeCapture,
  assignmentOpen,
  onAssignPatient,
  onCloseAssignment,
  onSearchPatients,
  onVerifySession,
  onStartNewSession,
}: {
  activeSession: CaptureSession | null;
  onSaveSession: (sessionId: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
  mode?: "active" | "historical";
  onBack?: () => void;
  onResumeCapture?: () => void;
  assignmentOpen?: boolean;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onCloseAssignment?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onVerifySession?: (sessionId: string) => Promise<void>;
  onStartNewSession?: () => void;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [titleDraft, setTitleDraft] = React.useState(activeSession?.label || "");
  const [editingTitle, setEditingTitle] = React.useState(false);
  const [savingTitle, setSavingTitle] = React.useState(false);
  const [verifying, setVerifying] = React.useState(false);
  const [reportView, setReportView] = React.useState<"draft" | "structured">("draft");
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const titleFormRef = React.useRef<HTMLFormElement | null>(null);
  const titleChanged = Boolean(activeSession && titleDraft.trim() && titleDraft.trim() !== activeSession.label);
  const isHistorical = mode === "historical";
  const processingState = activeSession?.processingStatus?.state;
  const canSaveSession = activeSession
    ? !isHistorical && !isLocalSessionId(activeSession.id) && processingState !== "processing"
    : false;
  const reportState = workspaceReportState(activeSession);
  const structuredReportCopy = workspaceStructuredReportCopy(activeSession);
  const selectedReportView = reportView;
  const findings = workspaceFindings(activeSession);
  const summaryText =
    activeSession?.summaries?.clinical || activeSession?.summaries?.short || activeSession?.summary;
  const reportMilestones = workspaceReportMilestones(activeSession, reportState);
  const reportUpdatedLabel = workspaceReportUpdatedLabel(activeSession?.report?.updatedAt || activeSession?.processingStatus?.updatedAt);

  React.useEffect(() => {
    setTitleDraft(activeSession?.label || "");
    setEditingTitle(false);
    setReportView("draft");
  }, [activeSession?.id, activeSession?.label]);

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
      <Card className="workspace-session-header">
        <form
          className="current-title-form"
          ref={titleFormRef}
          onBlur={(event) => {
            const nextFocus = event.relatedTarget;
            if (nextFocus instanceof Node && titleFormRef.current?.contains(nextFocus)) return;
            if (!savingTitle) setTitleDraft(activeSession?.label || "");
            setEditingTitle(false);
          }}
          onSubmit={(event) => {
            event.preventDefault();
            if (!activeSession || !titleChanged || savingTitle) return;
            setSavingTitle(true);
            void onUpdateTitle(activeSession.id, titleDraft.trim()).finally(() => {
              setSavingTitle(false);
              setEditingTitle(false);
            });
          }}
        >
          <div className="workspace-header-main">
            <div className="workspace-title-block">
              <p className="eyebrow">{isHistorical ? "Historical session" : "Active session"}</p>
              <Input
                aria-label="Session title"
                onChange={(event) => {
                  setEditingTitle(true);
                  setTitleDraft(event.target.value);
                }}
                disabled={!activeSession}
                onFocus={() => setEditingTitle(true)}
                value={titleDraft || "Untitled session"}
              />
            </div>
            <div className="workspace-header-actions">
              {onBack ? (
                <Button onClick={onBack} size="sm" type="button" variant="secondary">
                  Back
                </Button>
              ) : null}
              {isHistorical && onResumeCapture ? (
                <Button disabled={!activeSession} onClick={onResumeCapture} size="sm" type="button" variant="secondary">
                  Add capture
                </Button>
              ) : null}
              {!isHistorical && onStartNewSession ? (
                <Button className="current-new-session" onClick={onStartNewSession} size="sm" type="button" variant="secondary">
                  + New session
                </Button>
              ) : null}
            </div>
          </div>
          <div className="workspace-context-row">
            {activeSession ? <SessionStatusBadge status={activeSession.status} /> : <Badge tone="neutral">Capturing</Badge>}
          </div>
          {editingTitle ? (
            <div className="current-title-actions">
              <Button disabled={savingTitle || !titleChanged} size="sm" type="submit" variant="secondary">
                {savingTitle ? "Saving" : "Save title"}
              </Button>
            </div>
          ) : null}
        </form>
      </Card>
      <Card className="workspace-report-card">
        <div className="report-heading">
          <div>
            <p className="eyebrow">Clinical Report</p>
          </div>
          <div className="workspace-report-progress" aria-label="Report progress">
            {reportMilestones.map((milestone) => (
              <span className={milestone.state} key={milestone.label}>
                {milestone.label}
              </span>
            ))}
          </div>
          <div className="report-heading-actions">
            {onVerifySession ? (
              <button
                aria-checked={activeSession?.status === "verified"}
                className="report-verify-check"
                disabled={!activeSession || isLocalSessionId(activeSession.id) || verifying}
                onClick={() => {
                  if (!activeSession || activeSession.status === "verified") return;
                  setVerifying(true);
                  void onVerifySession(activeSession.id).finally(() => setVerifying(false));
                }}
                role="checkbox"
                type="button"
              >
                <span aria-hidden="true" />
                {activeSession?.status === "verified" ? "Verified" : verifying ? "Verifying" : "Verify report"}
              </button>
            ) : null}
            {!isHistorical ? (
              <Button
                className="report-generate-button"
                disabled={!canSaveSession || !activeSession}
                onClick={() => {
                  if (activeSession) onSaveSession(activeSession.id);
                }}
                size="sm"
                type="button"
              >
                {activeSession && isLocalSessionId(activeSession.id)
                  ? "Syncing first"
                  : processingState === "processing"
                    ? "Generating"
                    : "Generate"}
              </Button>
            ) : null}
          </div>
        </div>
        <div className="report-toolbar">
          <div className="report-toolbar-actions">
            {onAssignPatient ? (
              <button
                className={`report-patient-action ${activeSession?.patientName ? "assigned" : ""}`}
                disabled={!activeSession || isLocalSessionId(activeSession.id)}
                onClick={onCloseAssignment}
                type="button"
              >
                <span>{activeSession?.patientName || "Assign patient"}</span>
                {activeSession?.patientName && activeSession.assignmentSource ? (
                  <small>{assignmentSourceLabel(activeSession.assignmentSource)}</small>
                ) : (
                  <small>{activeSession?.patientName ? "Patient context" : "Add patient context"}</small>
                )}
              </button>
            ) : null}
            <div className="report-view-switch" aria-label="Report view">
              <button className={selectedReportView === "draft" ? "active" : ""} onClick={() => setReportView("draft")} type="button">
                Live draft
              </button>
              <button className={selectedReportView === "structured" ? "active" : ""} onClick={() => setReportView("structured")} type="button">
                Structured report
              </button>
            </div>
          </div>
        </div>
        {assignmentOpen && activeSession && onAssignPatient ? (
          <PatientAssignmentSheet
            session={activeSession}
            onAssign={(draft) => onAssignPatient(activeSession.id, draft)}
            onCancel={onCloseAssignment}
            onSearchPatients={onSearchPatients}
          />
        ) : null}
        <div className={`workspace-report-body ${reportState.kind}`}>
          {selectedReportView === "structured" ? (
            <StructuredReportView
              paragraphs={structuredReportCopy}
              session={activeSession}
              onOpenCapture={setSelectedCapture}
              onResolveFile={onResolveFile}
            />
          ) : (
            <LiveDraftReport session={activeSession} onOpenCapture={setSelectedCapture} onResolveFile={onResolveFile} />
          )}
        </div>
        <div className="workspace-report-footer">
          <span>{reportUpdatedLabel}</span>
          {activeSession?.processingStatus?.state === "processing" ? <span>Structured report is updating from the live draft</span> : null}
        </div>
        {/* TODO(ai-integration): Replace mocked report states with progressive session report artifacts from the AI pipeline. */}
      </Card>
      <details className="workspace-disclosure" open>
        <summary>
          <span>Summary</span>
          <Badge tone={summaryText ? "blue" : "neutral"}>{activeSession?.summaries?.status || (summaryText ? "Partial" : "Mocked")}</Badge>
        </summary>
        <p>{summaryText || "Session summary will appear as captures are processed. This placeholder keeps the report layout stable."}</p>
        {/* TODO(ai-integration): Bind this section to the AI-generated session summary when available. */}
      </details>
      <details className="workspace-disclosure">
        <summary>
          <span>Extracted Findings</span>
          <Badge tone={findings.length ? "blue" : "neutral"}>{findings.length || "Mocked"}</Badge>
        </summary>
        <div className="workspace-finding-grid">
          {findings.map((finding) => (
            <div key={finding.label}>
              <span>{finding.label}</span>
              <strong>{finding.value}</strong>
            </div>
          ))}
          {findings.length === 0 ? (
            <>
              <div>
                <span>Procedure</span>
                <strong>Pending extraction</strong>
              </div>
              <div>
                <span>Body area</span>
                <strong>Pending extraction</strong>
              </div>
            </>
          ) : null}
        </div>
        {/* TODO(ai-integration): Map structured extracted findings into stable clinical rows instead of this generic metadata preview. */}
      </details>
      <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
    </section>
  );
}

function PatientAssignmentSheet({
  session,
  onAssign,
  onCancel,
  onSearchPatients,
}: {
  session: CaptureSession;
  onAssign: (draft: PatientAssignmentDraft) => Promise<void>;
  onCancel?: () => void;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
}) {
  const [query, setQuery] = React.useState(session.patientName || "");
  const [newPatientNationalId, setNewPatientNationalId] = React.useState("");
  const [matches, setMatches] = React.useState<PatientSummary[]>([]);
  const [searching, setSearching] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const trimmedQuery = query.trim();
  const canCreate = Boolean(trimmedQuery) && !saving;

  React.useEffect(() => {
    if (!onSearchPatients || !trimmedQuery) {
      setMatches([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(() => {
      void onSearchPatients(trimmedQuery)
        .then((patients) => {
          if (!cancelled) setMatches(patients.slice(0, 5));
        })
        .catch(() => {
          if (!cancelled) setMatches([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [onSearchPatients, trimmedQuery]);

  const assignDraft = (draft: PatientAssignmentDraft) => {
    setSaving(true);
    void onAssign(draft).finally(() => setSaving(false));
  };

  return (
    <div className="assignment-scrim" role="presentation">
      <section aria-label="Assign patient" className="assignment-sheet">
        <div className="assignment-sheet-header">
          <div>
            <p className="eyebrow">Patient context</p>
            <h2>{session.patientName || "Find or create patient"}</h2>
          </div>
          {onCancel ? (
            <Button aria-label="Close patient assignment" onClick={onCancel} size="sm" type="button" variant="ghost">
              x
            </Button>
          ) : null}
        </div>
        <Input
          className="assignment-search-input"
          aria-label="Search patients"
          autoFocus
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by patient name or national ID"
          value={query}
        />
        <div className="assignment-results" aria-live="polite">
          {!trimmedQuery ? (
            <div className="assignment-search-placeholder">
              <strong>Type to search</strong>
              <span>Use a name or national ID. Existing patients appear here as you type.</span>
            </div>
          ) : null}
          {searching ? <p className="assignment-searching">Looking for matches...</p> : null}
          {!searching && matches.length
            ? matches.map((patient) => (
                <button
                  disabled={saving}
                  key={patient.id}
                  onClick={() => assignDraft({ displayName: patient.displayName, nationalId: patient.nationalId || undefined })}
                  type="button"
                >
                  <span>{patient.displayName}</span>
                  <small>{patient.nationalId || "Existing patient"}</small>
                </button>
              ))
            : null}
          {!searching && trimmedQuery && !matches.length ? <p>No existing patient found yet.</p> : null}
        </div>
        {trimmedQuery ? (
          <div className="assignment-create-panel">
            <Input
              aria-label="New patient national ID"
              onChange={(event) => setNewPatientNationalId(event.target.value)}
              placeholder="National ID, optional"
              value={newPatientNationalId}
            />
            <Button
              disabled={!canCreate}
              onClick={() => assignDraft({ displayName: trimmedQuery, nationalId: newPatientNationalId.trim() || undefined })}
              size="sm"
              type="button"
              variant="secondary"
            >
              {saving ? "Updating..." : `Create "${trimmedQuery}"`}
            </Button>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function LiveDraftReport({
  session,
  onOpenCapture,
  onResolveFile,
}: {
  session: CaptureSession | null;
  onOpenCapture: (item: CaptureItem) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  if (!session?.items.length) {
    return (
      <div className="live-draft-empty">
        <h3>Start the draft with a capture</h3>
        <p>Audio, photos, and notes will appear here immediately as the session develops.</p>
      </div>
    );
  }

  return (
    <div className="live-draft">
      <div className="live-draft-context">
        <h3>Live clinical draft</h3>
        <p>{session.patientName ? `Patient context: ${session.patientName}.` : "Patient context can be assigned later."}</p>
      </div>
      {session.items.map((item, index) => (
        <article
          className={`live-draft-capture ${item.type}`}
          key={item.id}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("audio, button, input, textarea")) return;
            onOpenCapture(item);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            onOpenCapture(item);
          }}
          role="button"
          tabIndex={0}
        >
          <div className="live-draft-capture-header">
            <span>{captureDraftLabel(item, index + 1)}</span>
            <StatusBadge status={item.status} />
          </div>
          {item.type === "photo" || item.type === "audio" || item.type === "voice" ? (
            <div className={`live-draft-media ${item.type}`}>
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </div>
          ) : null}
          <p>{draftCaptureText(item)}</p>
        </article>
      ))}
      {session.processingStatus?.state === "processing" ? (
        <div className="live-draft-processing">Structured report generation is running in the background. The live draft remains reviewable.</div>
      ) : null}
    </div>
  );
}

function StructuredReportView({
  paragraphs,
  session,
  onOpenCapture,
  onResolveFile,
}: {
  paragraphs: string[];
  session: CaptureSession | null;
  onOpenCapture: (item: CaptureItem) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const photos = session?.items.filter((item) => item.type === "photo") || [];
  const bodyParagraphs = removePhotoTextFromStructuredParagraphs(paragraphs, photos);
  return (
    <div className="structured-report-view">
      <section className="structured-report-context">
        <h3>Session context</h3>
        <div>
          <span>Patient</span>
          <strong>{session?.patientName || "Unassigned patient"}</strong>
        </div>
        <div>
          <span>Source captures</span>
          <strong>{session?.items.length || 0}</strong>
        </div>
      </section>
      <section className="structured-report-body">
        <h3>Body</h3>
        {photos.length ? (
          <section className="structured-report-photos" aria-label="Report photos">
            {photos.map((item) => (
              <button className="structured-report-photo" key={item.id} onClick={() => onOpenCapture(item)} type="button">
                <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
              </button>
            ))}
          </section>
        ) : null}
        {bodyParagraphs.length ? (
          bodyParagraphs.map((paragraph, index) => (
            <section className="workspace-report-section" key={`${index}-${paragraph.slice(0, 24)}`}>
              {formatReportParagraph(paragraph)}
            </section>
          ))
        ) : (
          <>
            <h3>Structured report not generated yet</h3>
            <p>The live draft is available now. Generate a structured report when the session has enough source material.</p>
          </>
        )}
      </section>
    </div>
  );
}

function removePhotoTextFromStructuredParagraphs(paragraphs: string[], photos: CaptureItem[]) {
  const photoTexts = photos.map((photo) => draftCaptureText(photo).trim()).filter(Boolean);
  if (!photoTexts.length) return paragraphs;
  return paragraphs
    .map((paragraph) =>
      paragraph
        .split("\n")
        .filter((line) => !photoTexts.some((photoText) => line.includes(photoText)))
        .join("\n")
        .trim(),
    )
    .filter(Boolean);
}

function workspaceReportState(
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
  if (session.report?.status === "verified" || session.status === "verified") {
    return { badge: "Verified", detail: "Reviewed and accepted for this session.", kind: "verified", label: "Verified report", tone: "green" };
  }
  if (session.report?.status === "processed") {
    return {
      badge: session.report.isStale ? "Updating" : "Structured",
      detail: session.report.isStale ? "New material has been added; the report is being updated." : "Structured draft is ready for review.",
      kind: "structured",
      label: "Structured report",
      tone: "green",
    };
  }
  if (session.report?.status === "generating" || session.processingStatus?.state === "processing") {
    return { badge: "Updating", detail: stageLabel, kind: "partial", label: "Report updating", tone: "blue" };
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

function workspaceStructuredReportCopy(session: CaptureSession | null) {
  const reportBody = session?.report?.body || session?.generatedReport;
  if (reportBody) return reportBody.split(/\n{2,}/).map((line) => line.trim()).filter(Boolean);
  return [];
}

function captureDraftLabel(item: CaptureItem, sequence: number) {
  if (item.type === "audio" || item.type === "voice") return `Audio ${sequence}`;
  if (item.type === "photo") return `Photo ${sequence}`;
  return `Note ${sequence}`;
}

function draftCaptureText(item: CaptureItem) {
  const generated = generatedTextForReport(item);
  if (generated) return generated;
  if (item.type === "audio" || item.type === "voice") return "Audio capture added, processing...";
  if (item.type === "photo") return "Photo added, analyzing...";
  return item.detail || "Text note added to the draft.";
}

function generatedTextForReport(item: CaptureItem) {
  const generated = metadataRecord(
    item.type === "audio" || item.type === "voice"
      ? metadataRecord(item.metadata).transcript
      : item.type === "photo"
        ? metadataRecord(item.metadata).caption || metadataRecord(item.metadata).ocr
        : metadataRecord(item.metadata).decorated_text || metadataRecord(item.metadata).normalized_note,
  );
  const text = typeof generated.text === "string" ? generated.text.trim() : "";
  if (text) return text;
  if (item.type === "note") return item.detail;
  if (item.status === "processed" || item.status === "ready") {
    if (item.type === "audio" || item.type === "voice") {
      return `Mock transcript: clinical audio captured at ${item.time}. Source audio remains attached for review.`;
    }
    if (item.type === "photo") {
      return `Mock photo analysis: clinical photo captured at ${item.time}. Review the image above with this generated caption.`;
    }
  }
  return "";
}

function nonTechnicalStageLabel(status?: SessionProcessingStatus) {
  if (!status || status.state !== "processing") return "Report is staying current with the latest captures.";
  if (status.stage === "transcripts") return "Reading the source captures.";
  if (status.stage === "report") return "Drafting the clinical report.";
  if (status.stage === "findings") return "Organizing key details.";
  if (status.stage === "summary") return "Condensing the session.";
  return status.label || "Updating the report.";
}

function workspaceReportMilestones(session: CaptureSession | null, state: ReturnType<typeof workspaceReportState>) {
  const order = ["partial", "structured", "verified"] as const;
  const currentIndex = order.indexOf(state.kind);
  return ["Draft", "Structured", "Verified"].map((label, index) => ({
    label,
    state: index < currentIndex ? "done" : index === currentIndex || (label === "Verified" && session?.status === "verified") ? "current" : "next",
  }));
}

function workspaceReportUpdatedLabel(value?: string | null) {
  if (!value) return "Live draft updates as captures arrive";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently updated";
  return `Updated ${new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date)}`;
}

function formatReportParagraph(paragraph: string) {
  if (paragraph.startsWith("# ")) return <h3>{paragraph.replace(/^#\s+/, "")}</h3>;
  if (paragraph.startsWith("## ")) return <h4>{paragraph.replace(/^##\s+/, "")}</h4>;
  if (paragraph.startsWith("- ")) {
    return (
      <ul>
        {paragraph.split(/\n-\s+/).map((item) => (
          <li key={item}>{item.replace(/^-\s+/, "")}</li>
        ))}
      </ul>
    );
  }
  if (paragraph.includes("\n- ")) {
    const [intro, ...items] = paragraph.split(/\n-\s+/);
    return (
      <>
        {intro.trim() ? <p>{intro.trim()}</p> : null}
        <ul>
          {items.filter(Boolean).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </>
    );
  }
  return <p>{paragraph}</p>;
}

function workspaceFindings(session: CaptureSession | null) {
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
