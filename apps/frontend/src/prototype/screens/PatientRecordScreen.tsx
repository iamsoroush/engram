import React from "react";
import { AppHeader, CaptureItemCard, StatusBadge } from "../shared";
import { Alert, Badge, Button, Card, Dialog, Separator, Sheet } from "../ui";
import type { CaptureItem, CaptureSession } from "../types";

export function PatientRecordScreen({
  session,
  onUndoMatch,
  onBack,
}: {
  session: CaptureSession;
  onUndoMatch: () => void;
  onBack: () => void;
}) {
  const [source, setSource] = React.useState<CaptureItem | null>(null);
  const [undoOpen, setUndoOpen] = React.useState(false);
  const patientName = session.patientName || session.patientId || "Assigned patient";
  const itemsWithMissing = session.items;

  return (
    <main className="page">
      <AppHeader onToday={onBack} subtitle="Matched capture with sources preserved." title="Patient visit session" />
      <section className="grid record-grid">
        <Card className="patient-summary">
          <p className="eyebrow">Patient</p>
          <h1>{patientName}</h1>
          <p>{session.patientId ? `Patient ID ${session.patientId}` : "Patient details unavailable"}</p>
          <StatusBadge status="matched" />
          <Separator />
          <p>Today {session.time}</p>
          <p>{session.label}</p>
          <small>Matched by doctor</small>
          <Button onClick={() => setUndoOpen(true)} variant="ghost">
            Undo match
          </Button>
        </Card>
        <Card>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Captured material</p>
              <h2>Organized for review, not HIS replacement</h2>
            </div>
            <Badge tone="green">Visit session</Badge>
          </div>
          <div className="stack">
            <Card className="note-block">
              <h3>Voice notes</h3>
              <p>Patient reported symptoms started last Friday. Mild improvement after topical cream.</p>
            </Card>
            <Card className="note-block">
              <h3>Photos</h3>
              <p>{session.items.filter((item) => item.type === "photo").length} image captures linked to this session.</p>
            </Card>
            <Card className="note-block">
              <h3>Doctor note</h3>
              <p>Quick note entered during visit.</p>
            </Card>
          </div>
          <Alert tone="blue">Clinical decision support or diagnosis is outside this prototype. This view focuses on capture organization.</Alert>
        </Card>
        <Card>
          <p className="eyebrow">Sources</p>
          <h2>Original inputs remain accessible</h2>
          <div className="stack">
            {itemsWithMissing.map((item) => (
              <Button key={item.id} onClick={() => setSource(item)} variant="secondary">
                {item.sourceName}
              </Button>
            ))}
          </div>
          <Alert tone="amber">Audit and clinical decision support are excluded. This view is capture organization only.</Alert>
        </Card>
      </section>
      <Sheet onClose={() => setSource(null)} open={Boolean(source)} title="Original source">
        {source ? (
          <div className="stack">
            <CaptureItemCard item={source} />
            {source.status === "missing" ? (
              <Alert tone="red">Source preview is unavailable. The session still keeps the source reference.</Alert>
            ) : (
              <Card className="source-preview">
                <p>{source.detail}</p>
              </Card>
            )}
          </div>
        ) : null}
      </Sheet>
      <Dialog
        footer={
          <>
            <Button onClick={onUndoMatch} variant="danger">
              Undo match
            </Button>
            <Button onClick={() => setUndoOpen(false)} variant="secondary">
              Keep matched
            </Button>
          </>
        }
        onClose={() => setUndoOpen(false)}
        open={undoOpen}
        title="Return session to unassigned queue?"
      >
        <p>This reverses the patient match. Captured material remains saved.</p>
      </Dialog>
    </main>
  );
}
