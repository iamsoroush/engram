// Basic (free-tier) note editor for the capture flow.
// Extracted verbatim from CaptureScreen.tsx (no behavior change).
import React from "react";
import { textDirection } from "../captureModel";

export function BasicNoteEditor({ text, onSave }: { text: string; onSave?: (text: string) => Promise<void> }) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(text);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!editing) setDraft(text);
  }, [text, editing]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (!onSave || !next || next === text.trim()) return;
    setSaving(true);
    void onSave(next).finally(() => setSaving(false));
  };

  if (editing) {
    return (
      <textarea
        autoFocus
        className="basic-note-input"
        dir={textDirection(draft)}
        disabled={saving}
        onBlur={commit}
        onChange={(event) => setDraft(event.target.value)}
        onClick={(event) => event.stopPropagation()}
        rows={Math.min(8, Math.max(2, Math.ceil((draft.length || 1) / 42)))}
        value={draft}
      />
    );
  }

  const empty = !text.trim();
  return (
    <p
      className={`basic-note-text${onSave ? " editable" : ""}${empty ? " empty" : ""}`}
      dir={textDirection(text || "")}
      onClick={
        onSave
          ? (event) => {
              event.stopPropagation();
              setEditing(true);
            }
          : undefined
      }
      onKeyDown={
        onSave
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                event.stopPropagation();
                setEditing(true);
              }
            }
          : undefined
      }
      role={onSave ? "button" : undefined}
      tabIndex={onSave ? 0 : undefined}
    >
      {text.trim() || (onSave ? "Tap to add a note" : "—")}
    </p>
  );
}
