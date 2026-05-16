import { CapturePrimaryButton, EmptyState, SessionCard, AppHeader } from "../shared";
import { Alert, Button, Card, DropdownMenu } from "../ui";
import type { CaptureSession } from "../types";

export function TodayScreen({
  sessions,
  onStartCapture,
  onOpenInbox,
  onOpenSession,
}: {
  sessions: CaptureSession[];
  onStartCapture: (mode?: "photo" | "note") => void;
  onOpenInbox: () => void;
  onOpenSession: (session: CaptureSession) => void;
}) {
  const unassigned = sessions.filter((session) => session.status === "unassigned");
  const recent = sessions.slice(0, 4);
  const manyUnassigned = unassigned.length >= 4;

  return (
    <main className="page">
      <AppHeader onToday={() => undefined} subtitle="No patient required to begin." title="Today" />
      <section className="grid two-col">
        <Card className="hero-card">
          <div>
            <p className="eyebrow">Start without patient selection</p>
            <h1>Begin capture now. Match to a patient later.</h1>
            <p>No patient search is required before starting. This is intentional.</p>
          </div>
          <div className="action-row">
            <CapturePrimaryButton onClick={() => onStartCapture()} />
            <Button onClick={() => onStartCapture("photo")} variant="secondary">
              Add photo only
            </Button>
            <Button onClick={() => onStartCapture("note")} variant="secondary">
              Write quick note
            </Button>
          </div>
        </Card>
        <Card className="counter-card">
          <p className="eyebrow">Needs matching</p>
          <strong>{unassigned.length}</strong>
          <span>unassigned sessions</span>
          <Button onClick={onOpenInbox} variant={manyUnassigned ? "default" : "secondary"}>
            Review queue
          </Button>
          {manyUnassigned ? <Alert tone="amber">Several captures are waiting. Review when there is a natural pause.</Alert> : null}
        </Card>
      </section>

      <section className="grid two-col lower-grid">
        <Card>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Recent captures</p>
              <h2>Latest sessions from today</h2>
            </div>
            <DropdownMenu label="State">
              <button type="button">Normal</button>
              <button type="button">Empty and saving states are supported by mock data.</button>
            </DropdownMenu>
          </div>
          {recent.length ? (
            <div className="stack">
              {recent.map((session) => (
                <SessionCard key={session.id} onClick={() => onOpenSession(session)} session={session} />
              ))}
            </div>
          ) : (
            <EmptyState body="Start a capture to create the first unassigned session." title="No recent captures" />
          )}
        </Card>
        <Card className="intent-card">
          <p className="eyebrow">Design intent</p>
          <h2>What the doctor should feel</h2>
          <ul>
            <li>Capture is the default action, not patient lookup.</li>
            <li>Unassigned sessions are visible but not scary.</li>
            <li>The home screen avoids HIS-like scheduling and billing.</li>
            <li>Matching is a later review task, not a capture blocker.</li>
          </ul>
        </Card>
      </section>
    </main>
  );
}
