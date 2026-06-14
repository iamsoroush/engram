// Capture destination panel for the Clinical Memory flow.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import type { CaptureDraft } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Button } from "../../../shared/ui/primitives";
import { captureKindLabel } from "./memoryModel";

export function CaptureDestinationPanel({
  kind,
  sessions,
  activeSession,
  selectedSession,
  onCancel,
  onNewSession,
  onUseSession,
}: {
  kind: CaptureDraft["kind"];
  sessions: CaptureSession[];
  activeSession: CaptureSession | null;
  selectedSession?: CaptureSession | null;
  onCancel: () => void;
  onNewSession: () => void;
  onUseSession: (sessionId: string) => void;
}) {
  const options = [selectedSession, activeSession, ...sessions]
    .filter((session): session is CaptureSession => Boolean(session))
    .filter((session, index, all) => all.findIndex((candidate) => candidate.id === session.id) === index)
    .slice(0, 3);
  return (
    <section className="capture-destination-panel" aria-label="Capture destination">
      <div>
        <p className="eyebrow">Capture destination</p>
        <h2>{captureKindLabel(kind)}</h2>
        <p>Choose where this capture should be saved.</p>
      </div>
      <div className="capture-destination-actions">
        {options.map((session) => (
          <Button key={session.id} onClick={() => onUseSession(session.id)} size="sm" type="button" variant="secondary">
            {session.label}
          </Button>
        ))}
        <Button onClick={onNewSession} size="sm" type="button">
          New session
        </Button>
        <Button onClick={onCancel} size="sm" type="button" variant="secondary">
          Cancel
        </Button>
      </div>
    </section>
  );
}
