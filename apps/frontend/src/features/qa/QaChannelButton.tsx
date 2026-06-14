import React from "react";
import { Button, Dialog } from "../../shared/ui/primitives";
import type { QaThreadSummary } from "./qaClient";

/**
 * Staff control to open (or reuse) a patient's post-session Q&A channel and copy the tokenized link
 * to send them (AES-402). The clinic opening the channel is the explicit, patient-surface "share"
 * gesture; the link is the patient's capability (no login). Pro-gated by the caller.
 */
export function QaChannelButton({
  patientName,
  onOpen,
  onToast,
}: {
  patientName: string;
  onOpen: () => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [thread, setThread] = React.useState<QaThreadSummary | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const link = thread ? `${window.location.origin}${thread.publicPath}` : "";

  const handleClick = async () => {
    setBusy(true);
    try {
      const summary = await onOpen();
      setThread(summary);
      setCopied(false);
      setOpen(true);
    } catch {
      onToast?.("Couldn’t open the Q&A channel.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      onToast?.("Q&A link copied.");
    } catch {
      // Clipboard can be blocked (e.g. insecure context) — the field is selectable as a fallback.
      onToast?.("Copy failed — select the link and copy manually.");
    }
  };

  return (
    <>
      <button className="patient-detail-action" onClick={handleClick} type="button" disabled={busy}>
        <QaChannelIcon /> {busy ? "Opening…" : "Open Q&A channel"}
      </button>
      <Dialog
        open={open}
        title="Patient Q&A channel"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button variant="default" onClick={copy}>
              {copied ? "Copied ✓" : "Copy link"}
            </Button>
          </>
        }
      >
        <p style={{ marginTop: 0, color: "var(--color-muted, #5b6472)", fontSize: 14, lineHeight: 1.5 }}>
          Send this private link to {patientName}. They can ask questions between visits with no login; you’ll
          review and approve every reply in the Q&A inbox. {thread?.assignedDoctor ? `Routed to ${thread.assignedDoctor.name}.` : "Awaiting routing."}
        </p>
        <input
          readOnly
          value={link}
          aria-label="Patient Q&A link"
          onFocus={(event) => event.currentTarget.select()}
          style={{
            width: "100%",
            boxSizing: "border-box",
            border: "1px solid var(--color-border, #d8dde6)",
            borderRadius: 10,
            padding: "10px 12px",
            font: "inherit",
            fontSize: 13,
            color: "#1f2733",
            background: "#f7f9fc",
          }}
        />
      </Dialog>
    </>
  );
}

function QaChannelIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" focusable="false" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5.5 5.5h13a1.5 1.5 0 0 1 1.5 1.5v7.5a1.5 1.5 0 0 1-1.5 1.5H10l-3.5 3v-3H5.5A1.5 1.5 0 0 1 4 15.5V7a1.5 1.5 0 0 1 1.5-1.5Z" />
      <path d="M8.5 10.25h7M8.5 12.75h4" />
    </svg>
  );
}
