// Live draft report + per-capture item rows for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { PatientAssignmentDraft } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession } from "../../../domain/types";
import { metadataRecord, metadataText } from "../metadata";
import { TryProTeaser } from "../../aesthetics/TryProTeaser";
import { VoiceMemoPlayer } from "../../aesthetics/VoiceMemoPlayer";
import { CaptureRawPreview } from "./SourcePreview";
import { BasicNoteEditor } from "./BasicNoteEditor";
import { CapturePatientBadges, CaptureReportBadge, captureAssignmentInfo, CaptureAssignmentBadge, CaptureInlineStatus, CaptureWorkingPlaceholder, pendingGeneratedAttribution, audioPendingTranscriptLabel, CaptureGeneratedHeading, CaptureGeneratedText, captureTextAttribution, CaptureTimelineIcon } from "./CaptureBadges";
import { captureOutOfContext, captureDraftLabel, draftCaptureText, generatedTextForReport, textDirection, captureNeedsReview, captionDisplay, activePatientAssignmentActionForSession, AssignmentCandidate, sessionAssignmentCandidates, alternateCandidateForCapture } from "../captureModel";

export function LiveDraftReport({
  isPro,
  offline = false,
  session,
  currentUserId = null,
  onApplyRelevant,
  onAssignPatient,
  onDeleteCapture,
  onOpenCapture,
  onOpenResolver,
  onRenameCapture,
  onResolveFile,
  onUpdateCaptureCaption,
  onUpdateCaptureTranscript,
  onUpdateNote,
}: {
  isPro: boolean;
  offline?: boolean;
  session: CaptureSession | null;
  currentUserId?: string | null;
  onApplyRelevant?: (sessionId: string, captureId: string) => Promise<void>;
  onAssignPatient?: (sessionId: string, draft: PatientAssignmentDraft) => Promise<void>;
  onDeleteCapture?: (sessionId: string, captureId: string) => Promise<void>;
  onOpenCapture: (item: CaptureItem) => void;
  onOpenResolver?: () => void;
  onRenameCapture?: (sessionId: string, captureId: string, title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateCaptureCaption?: (sessionId: string, captureId: string, caption: string) => Promise<CaptureItem | null>;
  onUpdateCaptureTranscript?: (sessionId: string, captureId: string, transcript: string) => Promise<CaptureItem | null>;
  onUpdateNote?: (sessionId: string, captureId: string, text: string) => Promise<void>;
}) {
  const [openMenuId, setOpenMenuId] = React.useState("");
  const activePatientAction = activePatientAssignmentActionForSession(session);
  const candidates = sessionAssignmentCandidates(session);

  React.useEffect(() => {
    setOpenMenuId("");
  }, [session?.id]);

  // Smoothly bring a newly added capture into view (handy in a long timeline) — only when a capture
  // is appended to the *same* session, not on session switch / refresh / edit.
  const newestCaptureRef = React.useRef<HTMLElement | null>(null);
  const captureCountRef = React.useRef(0);
  const feedSessionIdRef = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    const count = session?.items.length || 0;
    const sameSession = session?.id === feedSessionIdRef.current;
    if (sameSession && count > captureCountRef.current) {
      newestCaptureRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    captureCountRef.current = count;
    feedSessionIdRef.current = session?.id;
  }, [session?.id, session?.items.length]);

  if (!session?.items.length) {
    return (
      <div className="live-draft-empty">
        <h3>Start the draft with a capture</h3>
        <p>Audio, photos, and notes will appear here immediately as the session develops.</p>
      </div>
    );
  }

  // Render in capture order (chronological): a merge/refresh must never let a newer capture jump
  // above older ones. Every item has capturedAt (local + backend); ISO strings sort lexicographically.
  const orderedItems = [...session.items].sort((a, b) => (a.capturedAt || "").localeCompare(b.capturedAt || ""));

  return (
    <div className="live-draft">
      {orderedItems.map((item, index) => (
        <LiveDraftCaptureItem
          activePatientAction={activePatientAction}
          alternateCandidate={alternateCandidateForCapture(candidates, item.id)}
          isPro={isPro}
          offline={offline}
          item={item}
          key={item.sourceUrl || item.id}
          menuOpen={openMenuId === item.id}
          onApplyReassignment={onAssignPatient ? (draft) => onAssignPatient(session.id, draft) : undefined}
          onApplyRelevant={onApplyRelevant ? () => onApplyRelevant(session.id, item.id) : undefined}
          onChooseAnother={onOpenResolver}
          onCloseMenu={() => setOpenMenuId("")}
          onDeleteCapture={onDeleteCapture ? () => onDeleteCapture(session.id, item.id) : undefined}
          onEditCaption={onUpdateCaptureCaption ? (text) => onUpdateCaptureCaption(session.id, item.id, text).then(() => undefined) : undefined}
          onEditTranscript={onUpdateCaptureTranscript ? (text) => onUpdateCaptureTranscript(session.id, item.id, text).then(() => undefined) : undefined}
          onEditNote={onUpdateNote ? (text) => onUpdateNote(session.id, item.id, text) : undefined}
          onOpenCapture={() => onOpenCapture(item)}
          onRenameCapture={onRenameCapture ? (title) => onRenameCapture(session.id, item.id, title) : undefined}
          onResolveFile={onResolveFile}
          onToggleMenu={() => setOpenMenuId((current) => (current === item.id ? "" : item.id))}
          rootRef={index === session.items.length - 1 ? newestCaptureRef : undefined}
          sequence={index + 1}
          currentUserId={currentUserId}
        />
      ))}
      {isPro && session.processingStatus?.state === "processing" ? (
        <div className="live-draft-processing">Engram is refining the live report. Your captures stay reviewable while it updates.</div>
      ) : null}
      {!isPro ? (
        // One consolidated Try Pro for the whole capture surface (the per-capture badges are gone).
        <TryProTeaser
          className="capture-feed-teaser"
          title="Do more with Pro"
          subtitle="Basic captures fast and stays AI-free. Pro adds the understanding layer to the same captures."
          features={[
            "Dictate the visit — your audio is transcribed",
            "Photos auto-captioned & paired before/after with a slider",
            "A structured treatment report (area · product · units · lot), extracted from your dictation",
          ]}
        />
      ) : null}
    </div>
  );
}

export function LiveDraftCaptureItem({
  activePatientAction,
  alternateCandidate,
  isPro,
  offline = false,
  item,
  menuOpen,
  onApplyReassignment,
  onApplyRelevant,
  onChooseAnother,
  onCloseMenu,
  onDeleteCapture,
  onEditCaption,
  onEditTranscript,
  onEditNote,
  onOpenCapture,
  onRenameCapture,
  onResolveFile,
  onToggleMenu,
  rootRef,
  sequence,
  currentUserId = null,
}: {
  activePatientAction: Record<string, unknown> | null;
  alternateCandidate: AssignmentCandidate | null;
  isPro: boolean;
  offline?: boolean;
  item: CaptureItem;
  menuOpen: boolean;
  onApplyReassignment?: (draft: PatientAssignmentDraft) => Promise<void>;
  onApplyRelevant?: () => Promise<void>;
  onChooseAnother?: () => void;
  onCloseMenu: () => void;
  onDeleteCapture?: () => Promise<void>;
  onEditCaption?: (text: string) => Promise<void>;
  onEditTranscript?: (text: string) => Promise<void>;
  onEditNote?: (text: string) => Promise<void>;
  onOpenCapture: () => void;
  onRenameCapture?: (title: string) => Promise<void>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onToggleMenu: () => void;
  rootRef?: React.Ref<HTMLElement>;
  sequence: number;
  currentUserId?: string | null;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  const isPhoto = item.type === "photo";
  const title = captureDraftLabel(item, sequence);
  const generatedText = generatedTextForReport(item);
  // Only Pro photos are AI-captioned, so only they show the "Reading image" cue while processing.
  // Basic photos are never captioned → go straight to a manual "Add caption" (no AI badge/spinner).
  const captionStillProcessing =
    isPro && item.status !== "processed" && item.status !== "ready" && item.status !== "needsReview";
  // Note text (both tiers): the staff-edited note, else the raw typed note. Notes are a pure
  // passthrough now — no AI "decoration" — so the card shows the raw note, inline-editable.
  const noteRawText = metadataText(metadataRecord(metadataRecord(item.metadata).note).text) || item.detail || "";
  // §7: a low-confidence / flagged photo caption surfaces a "Needs review" chip with the reason.
  const captionReviewReason = captureNeedsReview(item);
  // Model-authored Markdown variant of the caption (clean text for AI jobs; **bold** for the UI).
  const captionDisplayText = captionDisplay(item);
  const textAttribution = captureTextAttribution(item);
  const [busy, setBusy] = React.useState(false);
  const [markedRelevant, setMarkedRelevant] = React.useState(false);
  const outOfContext = captureOutOfContext(item) && !markedRelevant;
  const assignmentInfo = captureAssignmentInfo(item, activePatientAction);
  // Persist "Mark relevant" (clears the AI out-of-context marker + re-folds into the report),
  // optimistically clearing the chip while the session refreshes.
  const markRelevant = () => {
    setMarkedRelevant(true);
    if (onApplyRelevant) void onApplyRelevant();
  };

  const rename = () => {
    if (!onRenameCapture || busy) return;
    const nextTitle = window.prompt("Rename capture", title);
    if (!nextTitle?.trim() || nextTitle.trim() === title) return;
    setBusy(true);
    void onRenameCapture(nextTitle.trim()).finally(() => {
      setBusy(false);
      onCloseMenu();
    });
  };

  const remove = () => {
    if (!onDeleteCapture || busy) return;
    if (!window.confirm(`Delete ${title}? The live report will update.`)) return;
    setBusy(true);
    void onDeleteCapture().finally(() => {
      setBusy(false);
      onCloseMenu();
    });
  };

  return (
    <article
      ref={rootRef}
      className={`live-draft-capture ${item.type}${outOfContext ? " is-out-of-context" : ""}${assignmentInfo ? " is-assignment-source" : ""}`}
    >
      <div className="live-draft-marker" aria-hidden="true">
        <CaptureTimelineIcon type={item.type} />
      </div>
      <div className="live-draft-capture-content">
        <header className="live-draft-capture-header">
          <div className="live-draft-capture-meta">
            <div className="live-draft-title-row">
              <span className="live-draft-title-main">
                <h3>{title}</h3>
                <CaptureAssignmentBadge info={assignmentInfo} />
                <CaptureReportBadge isPro={isPro} item={item} outOfContext={outOfContext} />
              </span>
              <time>
                {item.time}
                {item.createdBy ? (
                  <span className="capture-attribution">
                    {" · by "}
                    {currentUserId && item.createdBy.userId === currentUserId ? "you" : item.createdBy.displayName || "another clinician"}
                  </span>
                ) : null}
              </time>
            </div>
            <CaptureInlineStatus status={item.status} isPro={isPro} offline={offline} />
            <CapturePatientBadges
              activePatientAction={activePatientAction}
              alternateCandidate={alternateCandidate}
              item={item}
              onApplyReassignment={onApplyReassignment}
              onChooseAnother={onChooseAnother}
              outOfContext={outOfContext}
              onMarkRelevant={markRelevant}
              needsReviewReason={isPro ? captionReviewReason : ""}
            />
          </div>
          <button
            aria-expanded={menuOpen}
            aria-label={`Capture settings for ${title}`}
            className="live-draft-overflow"
            onClick={(event) => {
              event.stopPropagation();
              onToggleMenu();
            }}
            type="button"
          >
            <span aria-hidden="true" />
          </button>
          {menuOpen ? (
            <div className="capture-item-menu">
              <button disabled={!onRenameCapture || busy} onClick={rename} type="button">
                Rename
              </button>
              <button className="danger" disabled={!onDeleteCapture || busy} onClick={remove} type="button">
                Delete
              </button>
            </div>
          ) : null}
        </header>
        {isAudio ? (
          // Both tiers use the compact custom player (much better than native <audio> on mobile).
          // Pro adds the AI transcript section below it; Basic keeps it a plain voice memo. (AES-101/102/802)
          <>
            <VoiceMemoPlayer item={item} onResolveFile={onResolveFile} />
            {isPro ? (
              <section className={`capture-generated-section ${generatedText ? "ready" : "pending"}`}>
                {generatedText ? (
                  <CaptureGeneratedText attribution={textAttribution} dir={textDirection(generatedText)} label="Transcript" onSave={onEditTranscript} text={generatedText} />
                ) : (
                  <>
                    <CaptureGeneratedHeading label="Transcript" attribution={pendingGeneratedAttribution(item)} />
                    <CaptureWorkingPlaceholder label={audioPendingTranscriptLabel(item)} />
                  </>
                )}
              </section>
            ) : null}
          </>
        ) : null}
        {isPhoto ? (
          isPro ? (
            <div className="live-draft-photo-row">
              <div className="live-draft-photo-thumb">
                <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
              </div>
              <div className="live-draft-photo-copy">
                <section className={`capture-generated-section ${generatedText ? "ready" : captionStillProcessing ? "pending" : "ready"}`}>
                  {generatedText ? (
                    <CaptureGeneratedText attribution={textAttribution} dir={textDirection(generatedText)} label="Caption" onSave={onEditCaption} text={generatedText} display={captionDisplayText} />
                  ) : captionStillProcessing ? (
                    <>
                      <CaptureGeneratedHeading label="Caption" attribution={textAttribution} />
                      <CaptureWorkingPlaceholder label="Reading image" />
                    </>
                  ) : (
                    <CaptureGeneratedText addLabel="Add caption" attribution="" dir="ltr" label="Caption" onSave={onEditCaption} text="" />
                  )}
                </section>
              </div>
            </div>
          ) : (
            // Basic: the photo is filed to the patient and shown whole — no tagging, no AI caption.
            // (AES-103); the upsell is the single consolidated Try Pro at the foot of the feed.
            <div className="live-draft-photo-basic">
              <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
            </div>
          )
        ) : null}
        {!isPhoto && !isAudio ? (
          // A note is just the doctor's words (no AI decoration) — tap the text to edit it inline.
          // Both tiers share the raw-note editor. (AES-101)
          <BasicNoteEditor text={noteRawText} onSave={onEditNote} />
        ) : null}
      </div>
    </article>
  );
}

/**
 * AES-101 — a Basic note: tap the text to edit it inline (no Edit button), blur to save. The note
 * is the doctor's own words — no AI "decoration", no transcript.
 */
