import type { CaptureDraft } from "../../../domain/appTypes";

export function CaptureActions({
  compact,
  contextLabel,
  onAction,
  tier,
}: {
  compact?: boolean;
  contextLabel?: string;
  onAction: (kind: CaptureDraft["kind"]) => void;
  /** Footer order encodes the tier: Basic leads with Note (audio = voice memo); Pro leads with Audio (dictate). */
  tier?: string | null;
}) {
  const isBasic = tier === "basic";
  // Basic (aesthetics): Note is primary, audio is a labelled voice memo. Pro: Audio-first dictation.
  const actions: Array<{
    kind: CaptureDraft["kind"];
    label: string;
    sub?: string;
    tone: "primary" | "secondary";
    icon: "audio" | "photo" | "note";
  }> = isBasic
    ? [
        { kind: "note", label: "Note", sub: "memo", tone: "primary", icon: "note" },
        { kind: "photo", label: "Photo", tone: "secondary", icon: "photo" },
        { kind: "audio", label: "Audio", sub: "memo", tone: "secondary", icon: "audio" },
      ]
    : [
        { kind: "audio", label: "Record", sub: "dictate", tone: "primary", icon: "audio" },
        { kind: "photo", label: "Photo", tone: "secondary", icon: "photo" },
        { kind: "note", label: "Note", tone: "secondary", icon: "note" },
      ];

  const actionButtons = actions.map((action) => (
    <button
      className={`capture-action-button ${action.tone}`}
      key={action.kind}
      onClick={() => onAction(action.kind)}
      type="button"
    >
      <span className="capture-action-icon" aria-hidden="true">
        <CaptureActionIcon name={action.icon} />
      </span>
      <span className="capture-action-copy">
        <strong>{action.label}</strong>
        {action.sub ? <small>{action.sub}</small> : null}
      </span>
    </button>
  ));

  if (compact) {
    return (
      <div className="capture-pills">
        {contextLabel ? <div className="capture-pills-context">{contextLabel}</div> : null}
        <div className="capture-pills-actions">{actionButtons}</div>
      </div>
    );
  }

  return (
    <div className="capture-actions">
      {actionButtons}
    </div>
  );
}

function CaptureActionIcon({ name }: { name: "audio" | "photo" | "note" }) {
  if (name === "audio") {
    return (
      <svg viewBox="0 0 48 48" focusable="false" aria-hidden="true">
        <path d="M24 5.5a8 8 0 0 0-8 8v12a8 8 0 0 0 16 0v-12a8 8 0 0 0-8-8Z" />
        <path d="M10.5 23.5v2a13.5 13.5 0 0 0 27 0v-2" />
        <path d="M24 39v5" />
        <path d="M17 44h14" />
      </svg>
    );
  }
  if (name === "photo") {
    return (
      <svg viewBox="0 0 48 48" focusable="false" aria-hidden="true">
        <path d="M14.5 15.5h4.3l2.8-4h4.8l2.8 4h4.3a5 5 0 0 1 5 5v12a5 5 0 0 1-5 5h-19a5 5 0 0 1-5-5v-12a5 5 0 0 1 5-5Z" />
        <path d="M24 31.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" focusable="false" aria-hidden="true">
      <path d="M10.5 11.5h27v22h-17l-10 8v-30Z" />
      <path d="M17.5 19.5h13" />
      <path d="M17.5 26.5h10" />
    </svg>
  );
}
