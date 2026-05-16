import React from "react";
import { AppHeader, CaptureItemCard, ConfirmActionBar, StatusBadge } from "../shared";
import { Alert, Badge, Button, Card, Dialog, ScrollArea, Textarea } from "../ui";
import type { CaptureItem } from "../types";

export function ActiveCaptureScreen({
  items,
  onAddItem,
  onBack,
  onSave,
}: {
  items: CaptureItem[];
  onAddItem: (item: CaptureItem) => void;
  onBack: () => void;
  onSave: () => void;
}) {
  const [recording, setRecording] = React.useState(false);
  const [paused, setPaused] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [discardOpen, setDiscardOpen] = React.useState(false);

  const addItem = (type: CaptureItem["type"]) => {
    const labels = {
      audio: ["Voice segment", "Captured while doctor was speaking.", "voice_new.m4a"],
      voice: ["Voice segment", "Captured while doctor was speaking.", "voice_new.m4a"],
      photo: ["Photo", "New photo added to this visit capture.", "photo_new.jpg"],
      note: ["Typed note", "Quick note entered during the visit.", "typed_note.txt"],
    } as const;
    const [title, detail, sourceName] = labels[type];
    onAddItem({
      id: `item-${Date.now()}`,
      type,
      title,
      detail,
      time: "now",
      sourceName,
      status: type === "photo" ? "uploading" : "ready",
    });
    setRecording(type === "voice");
    setError("");
  };

  const save = () => {
    setSaving(true);
    window.setTimeout(onSave, 500);
  };

  return (
    <main className="page">
      <AppHeader onToday={onBack} subtitle="Capture first. Match later." title="Active capture" />
      <section className="capture-header card">
        <div>
          <p className="eyebrow">Unassigned session</p>
          <h1>00:06:42</h1>
          <StatusBadge status={recording ? "recording" : paused ? "paused" : "unassigned"} />
        </div>
        <Button disabled={saving} onClick={save}>
          {saving ? "Saving..." : "Save session"}
        </Button>
      </section>
      {error ? <Alert tone="red">{error}</Alert> : null}
      <section className="grid capture-grid">
        <Card>
          <p className="eyebrow">Capture controls</p>
          <h2>Low interruption inputs</h2>
          <div className="control-stack">
            <Button onClick={() => addItem("voice")} variant={recording ? "default" : "secondary"}>
              {recording ? "Recording voice" : "Record voice"}
            </Button>
            <Button onClick={() => addItem("photo")} variant="secondary">
              Take photo
            </Button>
            <Button onClick={() => addItem("note")} variant="secondary">
              Quick note
            </Button>
          </div>
          <Textarea placeholder="Optional quick note" rows={4} />
          <ConfirmActionBar
            onPrimary={() => setPaused((value) => !value)}
            onSecondary={() => setDiscardOpen(true)}
            primaryLabel={paused ? "Resume" : "Pause"}
            secondaryLabel="Discard"
          />
          <Button onClick={() => setError("Device permission interrupted. Current captured items remain in this session.")} variant="ghost">
            Show device error
          </Button>
        </Card>
        <Card>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Session feed</p>
              <h2>Captured items appear immediately</h2>
            </div>
            <Badge tone="blue">{items.length} items</Badge>
          </div>
          <ScrollArea className="feed">
            {items.map((item) => (
              <CaptureItemCard item={item} key={item.id} />
            ))}
          </ScrollArea>
          <Alert tone="blue">No patient search appears here. Capture stays separate from matching.</Alert>
        </Card>
      </section>
      <Dialog
        footer={
          <>
            <Button onClick={onBack} variant="danger">
              Discard session
            </Button>
            <Button onClick={() => setDiscardOpen(false)} variant="secondary">
              Keep capturing
            </Button>
          </>
        }
        onClose={() => setDiscardOpen(false)}
        open={discardOpen}
        title="Discard captured material?"
      >
        <p>Captured source material may be lost. Saving keeps it safely unassigned.</p>
      </Dialog>
    </main>
  );
}
