// Capture badge/attribution cluster for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import type { PatientAssignmentDraft } from "../../../domain/appTypes";
import type { CaptureItem, CaptureSession } from "../../../domain/types";
import { metadataDisplay, metadataRecord } from "../metadata";
import { Card } from "../../../shared/ui/primitives";
import { PatientForm } from "../../patient/PatientForm";
import { suggestionNameFromInformation, suggestionNationalId, captureNotSynced, AssignmentCandidate } from "../captureModel";
import { SyncIcon } from "./CaptureIcons";

export type PatientConflictSuggestion = { name: string; patientId?: string; nationalId?: string; spokenName?: string };

/**
 * The in-place patient-conflict resolver — a partial/fuzzy match or a dictated different/new patient,
 * with Keep match / Create new / Choose another / Edit. Self-contained (owns its applying/editing
 * state) so it renders identically on a capture card (in the Sources drawer) AND at the session level
 * in the verify region (FB8 — a patient conflict is a session blocker, not buried in the feed).
 */
export function PatientConflictResolver({
  suggestion,
  basisCaptureId,
  onApply,
  onChooseAnother,
  onDismiss,
}: {
  suggestion: PatientConflictSuggestion;
  basisCaptureId: string;
  onApply?: (draft: PatientAssignmentDraft) => Promise<void>;
  onChooseAnother?: () => void;
  onDismiss?: () => void;
}) {
  const [applying, setApplying] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [editName, setEditName] = React.useState("");
  const [editNationalId, setEditNationalId] = React.useState("");
  const showMatchedVsSpoken = Boolean(suggestion.patientId && suggestion.spokenName && suggestion.spokenName !== suggestion.name);
  const applyDraft = (draft: PatientAssignmentDraft) => {
    if (!onApply || applying) return;
    setApplying(true);
    void onApply(draft).finally(() => setApplying(false));
  };
  const keepMatch = () => {
    if (!suggestion.patientId) return;
    applyDraft({ patientId: suggestion.patientId, displayName: suggestion.name, basisCaptureId });
  };
  const createNew = (name: string, nationalId?: string) => {
    const display = name.trim();
    if (!display) return;
    applyDraft({ displayName: display, nationalId: nationalId?.trim() || undefined, basisCaptureId });
  };
  const openEditor = () => {
    setEditName(suggestion.spokenName || suggestion.name || "");
    setEditNationalId(suggestion.nationalId || "");
    setEditing(true);
  };
  return (
    <div className="effect-chip is-suggested partial-match">
      <div className="partial-match-head">
        <span className="effect-chip-label">
          {suggestion.patientId ? (
            <>Suggested: reassign to <strong>{suggestion.name}</strong></>
          ) : (
            <>New patient: <strong>{suggestion.name}</strong></>
          )}
        </span>
        {onDismiss ? (
          <button aria-label="Dismiss suggestion" className="partial-match-close" onClick={onDismiss} type="button">×</button>
        ) : null}
      </div>
      {showMatchedVsSpoken ? (
        <span className="partial-match-identity">
          Matched <strong>{suggestion.name}</strong> · you said <strong>{suggestion.spokenName}</strong>
        </span>
      ) : null}
      {editing ? (
        <div className="partial-match-edit">
          <span className="partial-match-edit-title">New patient details</span>
          <input aria-label="Patient name" onChange={(event) => setEditName(event.target.value)} placeholder="Patient name" value={editName} />
          <input aria-label="National ID (optional)" onChange={(event) => setEditNationalId(event.target.value)} placeholder="National ID (optional)" value={editNationalId} />
          <div className="partial-match-edit-actions">
            <button className="effect-chip-action" disabled={applying || !editName.trim()} onClick={() => createNew(editName, editNationalId)} type="button">
              {applying ? "Creating…" : "Create patient"}
            </button>
            <button className="effect-chip-ghost" onClick={() => setEditing(false)} type="button">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="partial-match-actions">
          {suggestion.patientId && onApply ? (
            <button className="effect-chip-action" disabled={applying} onClick={keepMatch} type="button">
              {applying ? "Applying…" : "Keep match"}
            </button>
          ) : null}
          {onApply ? (
            <button className="effect-chip-secondary" disabled={applying} onClick={openEditor} type="button">
              {suggestion.patientId ? "Create new instead" : "Create patient"}
            </button>
          ) : null}
          {onChooseAnother ? (
            <button className="effect-chip-secondary" onClick={onChooseAnother} type="button">Choose another</button>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** The pending patient-conflict a capture carries (suggested reassignment / new patient), or null if
 * it's the active source or has no conflict. Shared by the per-capture badge + the session panel. */
export function captureConflictSuggestion(
  item: CaptureItem,
  alternateCandidate: AssignmentCandidate | null | undefined,
  activePatientAction: Record<string, unknown> | null,
): PatientConflictSuggestion | null {
  if (captureAssignmentInfo(item, activePatientAction) !== null) return null;
  const candidate = metadataRecord(metadataRecord(item.metadata).patient_match_candidate);
  const status = metadataDisplay(candidate.status || candidate.decision);
  const isSuggestion = status === "suggested_reassignment";
  const matchedName = isSuggestion ? metadataDisplay(candidate.matchedName || candidate.displayName) || suggestionNameFromInformation(candidate) : "";
  const spokenName = isSuggestion ? metadataDisplay(candidate.spokenName) : "";
  if (isSuggestion && (matchedName || spokenName)) {
    return {
      name: matchedName || spokenName,
      patientId: metadataDisplay(candidate.patientId) || undefined,
      nationalId: suggestionNationalId(candidate),
      spokenName: spokenName || undefined,
    };
  }
  if (alternateCandidate) return { name: alternateCandidate.displayName, patientId: alternateCandidate.patientId };
  return null;
}

export function CapturePatientBadges({
  activePatientAction,
  alternateCandidate,
  item,
  onApplyReassignment,
  onChooseAnother,
  outOfContext,
  onMarkRelevant,
  needsReviewReason = "",
}: {
  activePatientAction: Record<string, unknown> | null;
  alternateCandidate?: AssignmentCandidate | null;
  item: CaptureItem;
  onApplyReassignment?: (draft: PatientAssignmentDraft) => Promise<void>;
  onChooseAnother?: () => void;
  outOfContext?: boolean;
  onMarkRelevant?: () => void;
  /** §7: a low-confidence / flagged photo caption — renders a "Needs review" chip with this reason. */
  needsReviewReason?: string;
}) {
  const [dismissed, setDismissed] = React.useState(false);

  // A pending patient conflict (partial/fuzzy match or a dictated different/new patient) on a
  // NON-source capture — resolved in place via the shared PatientConflictResolver (also rendered at
  // the session level in the verify region, FB8).
  const suggestion = captureConflictSuggestion(item, alternateCandidate, activePatientAction);
  const showSuggestion = Boolean(suggestion) && !dismissed;
  const showNeedsReview = Boolean(needsReviewReason) && !outOfContext;
  if (!showSuggestion && !outOfContext && !showNeedsReview) return null;

  return (
    <div className="capture-effect-chips" aria-label="Capture effects">
      {showSuggestion && suggestion ? (
        <div className="partial-match-row">
          <PatientConflictResolver
            suggestion={suggestion}
            basisCaptureId={item.id}
            onApply={onApplyReassignment}
            onChooseAnother={onChooseAnother}
            onDismiss={() => setDismissed(true)}
          />
        </div>
      ) : null}
      {outOfContext ? (
        <span className="effect-chip is-context">
          <span className="effect-chip-label">⌀ Out of context · not in report</span>
          {onMarkRelevant ? (
            <button className="effect-chip-dismiss" onClick={onMarkRelevant} type="button">
              Mark relevant
            </button>
          ) : null}
        </span>
      ) : null}
      {showNeedsReview ? (
        <span className="effect-chip is-review">
          <span className="effect-chip-label">⚠ Needs review · {needsReviewReason}</span>
        </span>
      ) : null}
    </div>
  );
}

/** Report-contribution status (Pro): an in-progress badge ONLY while the capture is being folded
 * into the live report. Once it's in (`added`), the capture carries no badge — a capture with no
 * status chip is one that's uploaded, processed, and already in the report. */
export function CaptureReportBadge({ isPro, item, outOfContext }: { isPro?: boolean; item: CaptureItem; outOfContext?: boolean }) {
  const status = metadataDisplay(metadataRecord(metadataRecord(item.metadata).report_contribution).status);
  if (!isPro || outOfContext || !["updating", "pending"].includes(status)) return null;
  return (
    <span className="capture-title-badge effect-chip is-report adding">
      <span className="effect-chip-dot" aria-hidden="true" />
      Adding to report…
    </span>
  );
}

export type CaptureAssignmentInfo = { kind: "assigned" | "created"; name: string; closeMatch: boolean; spokenName: string };

/** Whether this capture is the active assignment source, and the patient it (re)assigned. */
export function captureAssignmentInfo(item: CaptureItem, activePatientAction: Record<string, unknown> | null): CaptureAssignmentInfo | null {
  const action = metadataRecord(activePatientAction);
  const actionMetadata = metadataRecord(action.actionMetadata);
  const actionCaptureId = metadataDisplay(action.captureId || action.basisCaptureId || actionMetadata.basisCaptureId);
  if (!actionCaptureId || actionCaptureId !== item.id) return null;
  if (action.assigned === false || !(action.patientId || actionMetadata.patientId)) return null;
  const created =
    action.created === true || actionMetadata.created === true || action.action === "created_and_assigned" || actionMetadata.action === "created_and_assigned";
  const matchedName = metadataDisplay(action.matchedName || actionMetadata.matchedName);
  const spokenName = metadataDisplay(action.spokenName || actionMetadata.spokenName);
  const closeMatch = (action.closeMatch === true || actionMetadata.closeMatch === true) && matchedName !== "" && spokenName !== "" && matchedName !== spokenName;
  return { kind: created ? "created" : "assigned", name: metadataDisplay(action.displayName || actionMetadata.displayName), closeMatch, spokenName };
}

/** Assignment-source badge, shown beside the capture title (the patient this capture (re)assigned). */
export function CaptureAssignmentBadge({ info }: { info: CaptureAssignmentInfo | null }) {
  if (!info) return null;
  return (
    <span className={`capture-title-badge effect-chip ${info.kind === "created" ? "is-created" : "is-assign"}`}>
      {info.kind === "created" ? "New patient + assigned" : "Patient assigned"}
      {info.name ? ` → ${info.name}` : ""}
      {info.closeMatch ? <span className="effect-chip-note"> · close match · you said {info.spokenName}</span> : null}
    </span>
  );
}

export function AiCreatedPatientPanel({
  action,
  session,
  onComplete,
}: {
  action: Record<string, unknown>;
  session: CaptureSession;
  onComplete: (
    sessionId: string,
    patientId: string,
    draft: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string },
    action: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const patientInfo = metadataRecord(action.patientInformation);
  const patientId = metadataDisplay(action.patientId || session.patientId);
  const [saving, setSaving] = React.useState(false);
  const status = metadataDisplay(action.status);
  const needsVerification = action.needsVerification !== false && status !== "verified";
  if (!patientId || action.action !== "created_and_assigned" || !needsVerification) return null;
  // Seed the unified create/edit form from the AI-extracted identity.
  const initial = {
    displayName: metadataDisplay(action.displayName || session.patientName || patientInfo.raw_mentioned_name),
    nationalId: metadataDisplay(patientInfo.national_id),
    phone: metadataDisplay(patientInfo.phone),
    dateOfBirth: metadataDisplay(patientInfo.date_of_birth),
    sex: metadataDisplay(patientInfo.sex),
    notes: "",
  };
  return (
    <Card className="ai-patient-review-card">
      <div className="ai-patient-review-copy">
        <strong>AI created this patient from audio</strong>
        <p>Complete the details now and verify the patient record while staying in this visit.</p>
      </div>
      <PatientForm
        busy={saving}
        initial={initial}
        onSubmit={(values) => {
          setSaving(true);
          void onComplete(
            session.id,
            patientId,
            { displayName: values.displayName, nationalId: values.nationalId, phone: values.phone, dateOfBirth: values.dateOfBirth, sex: values.sex, notes: values.notes },
            action,
          ).finally(() => setSaving(false));
        }}
        submitLabel="Save & verify patient"
      />
    </Card>
  );
}

export function CaptureInlineStatus({ status, isPro = true, offline = false }: { status?: CaptureItem["status"]; isPro?: boolean; offline?: boolean }) {
  // When connected and healthy, a capture shows no status — it just syncs. The only sync indicator
  // appears when we're offline / the backend is unreachable and this capture isn't synced yet.
  const notSynced = captureNotSynced(status);
  if (offline && notSynced) {
    return (
      <span className="capture-inline-status syncing-offline">
        <SyncIcon />
        Trying to sync
      </span>
    );
  }
  // Pro AI states (online only) keep their markers.
  if (isPro && (status === "uploaded" || status === "processing")) {
    return (
      <span className="capture-inline-status active processing">
        <span aria-hidden="true" />
        Processing
      </span>
    );
  }
  if (isPro && (status === "failed" || status === "needsReview")) return <span className="capture-inline-status issue">Needs attention</span>;
  return null;
}

export function CaptureWorkingPlaceholder({ label }: { label: string }) {
  return (
    <div className="capture-working-placeholder" aria-live="polite">
      <span className="capture-working-copy">
        <span>{label}</span>
        <span className="capture-working-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </span>
      <span className="capture-working-track" aria-hidden="true" />
    </div>
  );
}

export function pendingGeneratedAttribution(item: CaptureItem) {
  // During the upload phase the animated placeholder label (audioPendingTranscriptLabel:
  // "Waiting to upload" / "Uploading audio") already conveys the state, so we show NO duplicate
  // attribution badge next to the heading. Once the gateway is transcribing, the ✨ mark applies.
  if (item.status === "saved" || item.status === "syncing" || item.status === "uploading") return "";
  return "Generated by AI";
}

export function audioPendingTranscriptLabel(item: CaptureItem) {
  if (item.status === "saved") return "Waiting to upload";
  if (item.status === "syncing" || item.status === "uploading") return "Uploading audio";
  return "Transcribing audio";
}

// The ✨ AI provenance mark, shared with the patient-memory surfaces (`.ai-spark`). It animates
// (twinkle + glow) while `working`, so the icon itself signals "AI is processing".
export function AiSpark({ working }: { working?: boolean }) {
  return (
    <span className={`ai-spark${working ? " working" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="m12 3 1.4 4.2L17.5 9l-4.1 1.8L12 15l-1.4-4.2L6.5 9l4.1-1.8L12 3ZM5.5 13l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM18 14l.9 2.6 2.6.9-2.6.9L18 21l-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
      </svg>
    </span>
  );
}

// AI-generated text shows the ✨ icon instead of a "Generated by AI" badge; staff edits / upload
// states keep their text label. `working` animates the icon (processing).
export function CaptureAttribution({ value, working }: { value: string; working?: boolean }) {
  if (!value) return null;
  if (value === "Generated by AI") {
    return (
      <span className="capture-ai-tag" role="img" aria-label="Generated by AI" title="Generated by AI">
        <AiSpark working={working} />
      </span>
    );
  }
  return <span>{value}</span>;
}

export function CaptureGeneratedHeading({ attribution, label }: { attribution: string; label: string }) {
  return (
    <div className="capture-generated-heading">
      <h4>{label}</h4>
      <CaptureAttribution value={attribution} working />
    </div>
  );
}

/** A generated text block (transcript/caption) with an inline Edit affordance (A4). Saved edits
 * carry edited-vs-AI attribution and feed the live report via the same handlers as the source sheet. */
/** Render a model-authored display string that is plain text plus **bold** spans. Only `**bold**` is
 * supported (safe: we build text + <strong> nodes, never inject HTML); anything else renders literally. */
function renderMarkdownBold(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    const match = /^\*\*([^*]+)\*\*$/.exec(part);
    return match ? <strong key={index}>{match[1]}</strong> : <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

export function CaptureGeneratedText({
  label,
  text,
  attribution,
  dir,
  onSave,
  addLabel = "Add",
  display,
}: {
  label: string;
  text: string;
  attribution: string;
  dir?: "rtl" | "ltr";
  onSave?: (text: string) => Promise<void>;
  addLabel?: string;
  /** Model-authored Markdown variant (clean `text` plus **bold**) shown read-only; editing uses `text`. */
  display?: string;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(text);
  const [saving, setSaving] = React.useState(false);
  // No text yet (e.g. an un-captioned Basic photo) → offer a manual "Add" instead of a placeholder.
  const hasText = !!text.trim();
  const start = () => {
    setDraft(text);
    setEditing(true);
  };
  const save = () => {
    if (!onSave || saving || !draft.trim()) return;
    setSaving(true);
    void onSave(draft.trim())
      .then(() => setEditing(false))
      .finally(() => setSaving(false));
  };
  return (
    <>
      <div className="capture-generated-heading">
        <h4>{label}</h4>
        <div className="capture-generated-heading-meta">
          {hasText ? <CaptureAttribution value={attribution} /> : null}
        </div>
      </div>
      {editing ? (
        <div className="capture-generated-editor">
          <textarea aria-label={`Edit ${label.toLowerCase()}`} dir={dir} onChange={(event) => setDraft(event.target.value)} rows={Math.min(8, Math.max(3, Math.ceil(draft.length / 56)))} value={draft} />
          <div className="capture-generated-editor-actions">
            <button className="capture-generated-cancel" onClick={() => setEditing(false)} type="button">
              Cancel
            </button>
            <button className="capture-generated-save" disabled={saving || !draft.trim()} onClick={save} type="button">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : hasText ? (
        // Tap the text itself to edit it inline — no separate Edit button.
        onSave ? (
          <button className="live-draft-preview live-draft-preview-edit" dir={dir} onClick={start} type="button" title="Tap to edit">
            {display && display !== text ? renderMarkdownBold(display) : text}
          </button>
        ) : (
          <p className="live-draft-preview" dir={dir}>{display && display !== text ? renderMarkdownBold(display) : text}</p>
        )
      ) : onSave ? (
        <button className="capture-generated-add" onClick={start} type="button">{addLabel}</button>
      ) : null}
    </>
  );
}

export function captureTextAttribution(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  const value = item.type === "photo" ? metadata.caption : metadata.transcript;
  const record = metadataRecord(value);
  const source = metadataDisplay(record.source);
  const editorName = metadataDisplay(record.edited_by_name || record.editedByName || record.edited_by_email || record.editedByEmail);
  if (source === "staff_edit" || editorName) return `Edited by ${editorName || "staff"}`;
  return "Generated by AI";
}

export function CaptureTimelineIcon({ type }: { type: CaptureItem["type"] }) {
  if (type === "photo") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M8.5 7.5 10 5h4l1.5 2.5H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2h3.5Z" />
        <path d="M12 16.8a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2Z" />
      </svg>
    );
  }
  if (type === "note") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M6 3.5h9l3 3V20.5H6v-17Z" />
        <path d="M15 3.5v4h4" />
        <path d="M8.5 11h7" />
        <path d="M8.5 15h5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 14.5a3 3 0 0 0 3-3v-5a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0" />
      <path d="M12 17v3.5" />
      <path d="M9 20.5h6" />
    </svg>
  );
}
