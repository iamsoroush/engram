// Capture destination panel for the Clinical Memory flow.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import type { CaptureDraft } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Button } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
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
  const t = useT();
  const options = [selectedSession, activeSession, ...sessions]
    .filter((session): session is CaptureSession => Boolean(session))
    .filter((session, index, all) => all.findIndex((candidate) => candidate.id === session.id) === index)
    .slice(0, 3);
  return (
    <section className="capture-destination-panel" aria-label={t("capturedest.ariaLabel")}>
      <div>
        <p className="eyebrow">{t("capturedest.eyebrow")}</p>
        <h2>{captureKindLabel(kind, t)}</h2>
        <p>{t("capturedest.chooseWhere")}</p>
      </div>
      <div className="capture-destination-actions">
        {options.map((session) => (
          <Button key={session.id} onClick={() => onUseSession(session.id)} size="sm" type="button" variant="secondary" data-content>
            {session.label}
          </Button>
        ))}
        <Button onClick={onNewSession} size="sm" type="button">
          {t("capturedest.newSession")}
        </Button>
        <Button onClick={onCancel} size="sm" type="button" variant="secondary">
          {t("capturedest.cancel")}
        </Button>
      </div>
    </section>
  );
}
