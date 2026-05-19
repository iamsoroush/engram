import React from "react";
import type { CaptureDraft } from "../appTypes";
import type { CaptureItem, CaptureSession } from "../types";
import { isLocalSessionId } from "../captureModel";
import { CaptureGeneratedDetails } from "../metadata";
import { Button, Card, Input } from "../ui";
import { SourcePreviewDialog, CaptureRawPreview } from "./SourcePreview";
import { StatusBadge } from "./StatusBadges";

export function CaptureItemCard({
  item,
  onOpen,
  onResolveFile,
}: {
  item: CaptureItem;
  onOpen?: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const isAudio = item.type === "audio" || item.type === "voice";
  return (
    <Card className="v2-capture-item">
      <div className="capture-card-header">
        <button className="capture-title-button" onClick={onOpen} type="button">
          <span>
            <h3>{item.title}</h3>
            <small>{item.time}</small>
          </span>
        </button>
        <StatusBadge status={item.status} />
      </div>
      <div
        className="capture-card-body"
        onClick={isAudio ? undefined : onOpen}
        onKeyDown={(event) => {
          if (!onOpen || isAudio || (event.key !== "Enter" && event.key !== " ")) return;
          event.preventDefault();
          onOpen();
        }}
        role={onOpen && !isAudio ? "button" : undefined}
        tabIndex={onOpen && !isAudio ? 0 : undefined}
      >
        <CaptureRawPreview item={item} onResolveFile={onResolveFile} />
      </div>
      <CaptureGeneratedDetails item={item} />
    </Card>
  );
}

export function CaptureScreen({
  activeSession,
  onCapture,
  onSaveSession,
  onResolveFile,
  onUpdateTitle,
}: {
  activeSession: CaptureSession | null;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  onSaveSession: (sessionId: string) => void;
  onResolveFile: (endpoint: string) => Promise<string>;
  onUpdateTitle: (sessionId: string, title: string) => Promise<void>;
}) {
  const [selectedCapture, setSelectedCapture] = React.useState<CaptureItem | null>(null);
  const [titleDraft, setTitleDraft] = React.useState(activeSession?.label || "");
  const [editingTitle, setEditingTitle] = React.useState(false);
  const [savingTitle, setSavingTitle] = React.useState(false);
  const latestCaptureRef = React.useRef<HTMLDivElement | null>(null);
  const previousCaptureCountRef = React.useRef(activeSession?.items.length || 0);
  const titleFormRef = React.useRef<HTMLFormElement | null>(null);
  const titleChanged = Boolean(activeSession && titleDraft.trim() && titleDraft.trim() !== activeSession.label);
  const canSaveSession = activeSession
    ? !isLocalSessionId(activeSession.id) &&
      (activeSession.status === "draft" || activeSession.status === "failed" || activeSession.status === "reopened")
    : false;

  React.useEffect(() => {
    setTitleDraft(activeSession?.label || "");
    setEditingTitle(false);
  }, [activeSession?.id, activeSession?.label]);

  React.useEffect(() => {
    if (!activeSession) previousCaptureCountRef.current = 0;
  }, [activeSession]);

  React.useEffect(() => {
    if (!activeSession?.items.length) return;
    const previousCaptureCount = previousCaptureCountRef.current;
    previousCaptureCountRef.current = activeSession.items.length;
    window.requestAnimationFrame(() => {
      if (previousCaptureCount === 0) {
        window.scrollTo({ top: 0, behavior: "instant" });
        return;
      }
      latestCaptureRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    });
  }, [activeSession?.items.length]);

  if (!activeSession || activeSession.items.length === 0) {
    return (
      <section className="capture-empty" aria-label="Capture">
        <div className="capture-empty-panel">
          <div className="capture-empty-copy">
            <p className="eyebrow">Capture</p>
            <h1>Nothing captured yet</h1>
            <p>Start with audio, a photo, or a note. Your captures will appear here in order as the current session builds.</p>
          </div>
          <div className="capture-empty-preview" aria-hidden="true">
            <div className="empty-capture-row">
              <span />
              <div>
                <strong>First capture</strong>
                <small>Saved here</small>
              </div>
            </div>
            <div className="empty-capture-row muted">
              <span />
              <div>
                <strong>Next capture</strong>
                <small>Added below</small>
              </div>
            </div>
            <div className="empty-capture-line" />
          </div>
        </div>
        <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
      </section>
    );
  }

  return (
    <section className="capture-current" aria-label="Current session">
      <div className="current-header">
        <form
          className="current-title-form"
          ref={titleFormRef}
          onBlur={(event) => {
            const nextFocus = event.relatedTarget;
            if (nextFocus instanceof Node && titleFormRef.current?.contains(nextFocus)) return;
            if (!savingTitle) setTitleDraft(activeSession.label);
            setEditingTitle(false);
          }}
          onSubmit={(event) => {
            event.preventDefault();
            if (!titleChanged || savingTitle) return;
            setSavingTitle(true);
            void onUpdateTitle(activeSession.id, titleDraft.trim()).finally(() => {
              setSavingTitle(false);
              setEditingTitle(false);
            });
          }}
        >
          <p className="eyebrow">Current session</p>
          <div className="current-title-line">
            <Input
              aria-label="Session title"
              onChange={(event) => {
                setEditingTitle(true);
                setTitleDraft(event.target.value);
              }}
              onFocus={() => setEditingTitle(true)}
              value={titleDraft}
            />
            <Button
              className="current-save-session"
              disabled={!canSaveSession}
              onClick={() => onSaveSession(activeSession.id)}
              size="sm"
              type="button"
            >
              {isLocalSessionId(activeSession.id) ? "Syncing first" : activeSession.status === "processing" ? "Processing" : "Save session"}
            </Button>
          </div>
          <small>New captures save here by default.</small>
          {editingTitle ? (
            <div className="current-title-actions">
              <Button disabled={savingTitle || !titleChanged} size="sm" type="submit" variant="secondary">
                {savingTitle ? "Saving" : "Save title"}
              </Button>
            </div>
          ) : null}
        </form>
      </div>
      <div className="feed-focus">
        {activeSession.items.map((item, index) => (
          <div className="capture-feed-item" key={item.id} ref={index === activeSession.items.length - 1 ? latestCaptureRef : undefined}>
            <CaptureItemCard item={item} onOpen={() => setSelectedCapture(item)} onResolveFile={onResolveFile} />
          </div>
        ))}
      </div>
      <SourcePreviewDialog item={selectedCapture} onClose={() => setSelectedCapture(null)} onResolveFile={onResolveFile} />
    </section>
  );
}
