import { AppHeader, CapturePrimaryButton } from "../shared";
import { Alert, Badge, Button, Card } from "../ui";
import type { CaptureSession } from "../types";

export function SavedScreen({
  session,
  onStartAnother,
  onReview,
  onBack,
}: {
  session: CaptureSession;
  onStartAnother: () => void;
  onReview: () => void;
  onBack: () => void;
}) {
  return (
    <main className="page">
      <AppHeader onToday={onBack} subtitle="No patient match required yet." title="Session saved" />
      <section className="center-stage">
        <Card className="success-card">
          <div className="success-mark">✓</div>
          <Badge tone="green">Saved successfully</Badge>
          <h1>Capture saved safely</h1>
          <p>This session is unassigned and can be matched to the correct patient later.</p>
          <div className="stack">
            <CapturePrimaryButton onClick={onStartAnother}>Start another capture</CapturePrimaryButton>
            <Button onClick={onReview} variant="secondary">
              Review unassigned sessions
            </Button>
          </div>
          <small>Session label: {session.label}</small>
          <Alert tone="amber">If sync is pending, the capture remains visible here until retry succeeds.</Alert>
        </Card>
      </section>
    </main>
  );
}
