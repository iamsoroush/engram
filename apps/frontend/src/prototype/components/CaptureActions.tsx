import type { CaptureDraft } from "../appTypes";
import { Button } from "../ui";

export function CaptureActions({ compact, onAction }: { compact?: boolean; onAction: (kind: CaptureDraft["kind"]) => void }) {
  return (
    <div className={compact ? "capture-pills" : "capture-actions"}>
      <Button onClick={() => onAction("audio")} size={compact ? "sm" : "lg"}>
        Record audio
      </Button>
      <Button onClick={() => onAction("photo")} size={compact ? "sm" : "lg"} variant={compact ? "secondary" : "default"}>
        Take photo
      </Button>
      <Button onClick={() => onAction("note")} size={compact ? "sm" : "lg"} variant={compact ? "secondary" : "default"}>
        Write note
      </Button>
    </div>
  );
}
