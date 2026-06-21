import React from "react";
import "./qaInbox.css";
import type { ApiFetch } from "../../domain/appTypes";
import { Alert, Badge, Button, Card, Skeleton, Textarea } from "../../shared/ui/primitives";
import { formatDate } from "../../shared/lib/datetime";
import {
  dismissQaQuestion,
  fetchQaInbox,
  fetchQaSettings,
  fetchTreatingDoctors,
  routeQaThread,
  sendQaReply,
  setQaRoutingMode,
  type QaInboxItem,
  type QaSettings,
  type QaThreadMessage,
  type QaTreatingDoctor,
  type QaVisitMarker,
} from "./qaClient";
import { useVoiceEdit } from "./useVoiceEdit";

/**
 * Doctor Q&A inbox — thread-centric (AES-402).
 *
 * One entry per patient conversation; threads awaiting the doctor's approval sort first (the badge
 * counts them), the rest follow by recent activity — a triaged message list, not a flat all-patients
 * chat. Each entry shows the whole conversation with visit markers interleaved, and (when a question
 * is pending) the AI-suggested reply the doctor can Send / edit / Dismiss inline. Nothing sends
 * without the doctor approving it. Pro-gated (the parent only mounts this for Pro tenants).
 */
export function DoctorQaInbox({
  apiFetch,
  onToast,
  onChanged,
}: {
  apiFetch: ApiFetch;
  onToast?: (message: string) => void;
  onChanged?: () => void;
}) {
  const [scope, setScope] = React.useState<"mine" | "all">("mine");
  const [items, setItems] = React.useState<QaInboxItem[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [settings, setSettings] = React.useState<QaSettings | null>(null);
  const [refresh, setRefresh] = React.useState(0);

  const reload = React.useCallback(() => setRefresh((value) => value + 1), []);

  React.useEffect(() => {
    let cancelled = false;
    fetchQaSettings(apiFetch)
      .then((next) => !cancelled && setSettings(next))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [apiFetch]);

  React.useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    setError("");
    fetchQaInbox(apiFetch, scope)
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        setLoaded(true);
        onChanged?.(); // keep the top-bar pending badge in sync
      })
      .catch(() => {
        if (cancelled) return;
        setError("Couldn’t load the Q&A inbox.");
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [apiFetch, scope, refresh, onChanged]);

  const handleRoutingMode = async (mode: "ai_default" | "manual") => {
    try {
      setSettings(await setQaRoutingMode(apiFetch, mode));
      onToast?.(mode === "manual" ? "New questions now wait for manual routing." : "New questions now auto-route to the treating doctor.");
    } catch {
      onToast?.("Couldn’t update routing.");
    }
  };

  const handleSend = async (item: QaInboxItem, reply: string) => {
    const messageId = item.pendingQuestion?.messageId;
    const text = reply.trim();
    if (!messageId || !text) {
      onToast?.("Add a reply before sending.");
      return;
    }
    if (!window.confirm(`Send this reply to ${item.patientName}? They will see it on their private link.`)) return;
    try {
      await sendQaReply(apiFetch, messageId, text);
      onToast?.("Reply sent and captured into the patient’s memory.");
      reload();
    } catch {
      onToast?.("Couldn’t send the reply.");
    }
  };

  const handleDismiss = async (item: QaInboxItem) => {
    const messageId = item.pendingQuestion?.messageId;
    if (!messageId) return;
    if (!window.confirm(`Dismiss ${item.patientName}’s question without replying?`)) return;
    try {
      await dismissQaQuestion(apiFetch, messageId);
      onToast?.("Question dismissed.");
      reload();
    } catch {
      onToast?.("Couldn’t dismiss the question.");
    }
  };

  const handleReroute = async (item: QaInboxItem, doctorUserId: string) => {
    try {
      await routeQaThread(apiFetch, item.threadId, doctorUserId);
      onToast?.("Conversation re-routed.");
      reload();
    } catch {
      onToast?.("Couldn’t re-route this conversation.");
    }
  };

  return (
    <div className="qa-inbox">
      <div className="qa-inbox-head">
        <h1>Q&amp;A inbox</h1>
        <div className="qa-inbox-controls">
          <div className="qa-scope" role="tablist" aria-label="Inbox scope">
            <button className={scope === "mine" ? "active" : ""} onClick={() => setScope("mine")} type="button">
              Mine
            </button>
            <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
              Clinic
            </button>
          </div>
          {settings ? (
            <label className="qa-routing">
              Routing
              <select
                value={settings.routingMode === "manual" ? "manual" : "ai_default"}
                onChange={(event) => void handleRoutingMode(event.target.value as "ai_default" | "manual")}
              >
                <option value="ai_default">Auto · treating doctor</option>
                <option value="manual">Manual</option>
              </select>
            </label>
          ) : null}
        </div>
      </div>

      {error ? <Alert tone="red">{error}</Alert> : null}

      {!loaded ? (
        <Card className="qa-card">
          <Skeleton className="h-16" />
          <Skeleton className="h-12" />
        </Card>
      ) : items.length === 0 ? (
        <p className="qa-empty">No conversations yet{scope === "mine" ? " routed to you" : ""}.</p>
      ) : (
        items.map((item) => (
          <QaThreadCard
            key={item.threadId}
            item={item}
            apiFetch={apiFetch}
            onSend={handleSend}
            onDismiss={handleDismiss}
            onReroute={handleReroute}
          />
        ))
      )}
    </div>
  );
}

type TimelineEntry =
  | { kind: "message"; at: number; message: QaThreadMessage }
  | { kind: "visit"; at: number; visit: QaVisitMarker };

/** Merge messages + visit markers into one chronological timeline (Telegram-style with visit chips). */
function buildTimeline(messages: QaThreadMessage[], visits: QaVisitMarker[]): TimelineEntry[] {
  const ms = (iso: string | null): number => {
    if (!iso) return 0;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? 0 : t;
  };
  const entries: TimelineEntry[] = [
    ...messages.map((message): TimelineEntry => ({ kind: "message", at: ms(message.createdAt), message })),
    ...visits.map((visit): TimelineEntry => ({ kind: "visit", at: ms(visit.date), visit })),
  ];
  return entries.sort((a, b) => a.at - b.at);
}

function QaThreadCard({
  item,
  apiFetch,
  onSend,
  onDismiss,
  onReroute,
}: {
  item: QaInboxItem;
  apiFetch: ApiFetch;
  onSend: (item: QaInboxItem, reply: string) => void;
  onDismiss: (item: QaInboxItem) => void;
  onReroute: (item: QaInboxItem, doctorUserId: string) => void;
}) {
  const pending = item.pendingQuestion;
  const [reply, setReply] = React.useState(pending?.suggestedReply || "");
  const [doctors, setDoctors] = React.useState<QaTreatingDoctor[] | null>(null);
  // Collapsed by default: an open conversation shows just its latest question + the suggested reply;
  // a resolved one shows a one-line preview. Clicking the header reveals the full history either way.
  const [expanded, setExpanded] = React.useState(false);
  const convoRef = React.useRef<HTMLDivElement>(null);

  // Voice edit: the doctor speaks a change; the AI revises or replaces the draft (it decides which).
  const [voiceMode, setVoiceMode] = React.useState<"revise" | "replace" | null>(null);
  const [voiceError, setVoiceError] = React.useState("");
  const replyRef = React.useRef(reply);
  replyRef.current = reply;
  const preVoiceRef = React.useRef("");
  const voice = useVoiceEdit({
    apiFetch,
    messageId: pending?.messageId,
    getDraft: () => replyRef.current,
    onApplied: (text, mode) => {
      setReply(text);
      setVoiceMode(mode);
    },
    onError: setVoiceError,
  });
  const startVoice = () => {
    preVoiceRef.current = reply;
    setVoiceError("");
    setVoiceMode(null);
    void voice.start();
  };
  const undoVoice = () => {
    setReply(preVoiceRef.current);
    setVoiceMode(null);
  };

  React.useEffect(() => {
    setReply((current) => (current.trim() ? current : item.pendingQuestion?.suggestedReply || ""));
  }, [item.pendingQuestion?.suggestedReply]);

  // When the full conversation is open, scroll it to the newest message.
  React.useEffect(() => {
    if (!expanded) return;
    const el = convoRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [expanded, item.messages.length]);

  const loadDoctors = () => {
    if (doctors !== null) return;
    fetchTreatingDoctors(apiFetch, item.patientId)
      .then(setDoctors)
      .catch(() => setDoctors([]));
  };

  const timeline = buildTimeline(item.messages, item.visits);
  const draftPending = pending?.draftStatus === "pending" || pending?.draftStatus === "none";
  const draftReady = pending?.draftStatus === "ready";
  const lastMessage = item.messages[item.messages.length - 1];

  // Re-route only makes sense when the patient has more than one treating doctor to choose between.
  const canReroute = item.treatingDoctorCount >= 2;
  // Earlier messages that are hidden when collapsed (open shows the pending question; resolved shows
  // a one-line preview), so the disclosure can name how many there are.
  const hiddenCount = item.needsApproval ? item.messages.length - 1 : item.messages.length;

  return (
    <Card className={`qa-card ${item.needsApproval ? "qa-needs" : ""}`}>
      <div className="qa-card-head">
        <span className="qa-patient" dir="auto">
          {item.patientName}
        </span>
        <span className="qa-head-right">
          {item.needsApproval ? <Badge tone="amber">needs reply</Badge> : null}
          {item.assignedDoctor ? (
            <Badge tone="blue">
              {item.routingSource === "manual" ? "re-routed" : "treating"} · {item.assignedDoctor.name}
            </Badge>
          ) : (
            <Badge tone="amber">unrouted</Badge>
          )}
        </span>
      </div>

      {expanded ? (
        <div className="qa-convo" ref={convoRef}>
          {timeline.map((entry, index) =>
            entry.kind === "visit" ? (
              <div className="qa-visit" key={`v-${entry.visit.sessionId}-${index}`}>
                <span dir="auto">🗓 Visit · {entry.visit.title}</span>
                <span className="qa-visit-date">{formatDateTime(entry.visit.date)}</span>
              </div>
            ) : (
              <div
                key={entry.message.id}
                className={`qa-msg ${entry.message.role === "doctor" ? "clinic" : "patient"} ${
                  pending && entry.message.id === pending.messageId ? "awaiting" : ""
                }`}
              >
                <div className="qa-msg-meta">
                  {entry.message.role === "doctor" ? "Clinic" : item.patientName}
                  <span className="qa-msg-time"> · {formatDateTime(entry.message.createdAt)}</span>
                  {entry.message.status === "dismissed" ? <span className="qa-msg-time"> · dismissed</span> : null}
                </div>
                <div dir="auto">{entry.message.body}</div>
              </div>
            ),
          )}
        </div>
      ) : item.needsApproval && pending ? (
        // Collapsed open conversation: just the question awaiting a reply.
        <div className="qa-msg patient awaiting qa-msg-flush">
          <div className="qa-msg-meta">
            {item.patientName}
            <span className="qa-msg-time"> · {formatDateTime(pending.askedAt)}</span>
          </div>
          <div dir="auto">{pending.question}</div>
        </div>
      ) : (
        // Collapsed resolved conversation: one-line preview of the latest message.
        <div className="qa-preview">
          <span className="qa-preview-role">{lastMessage?.role === "doctor" ? "Clinic" : item.patientName}:</span>{" "}
          <span className="qa-preview-text" dir="auto">
            {lastMessage?.body}
          </span>
          <span className="qa-msg-time"> · {formatDateTime(item.lastActivityAt)}</span>
        </div>
      )}

      {/* Explicit, labelled disclosure for the full thread (replaces the easy-to-miss chevron). */}
      {hiddenCount > 0 ? (
        <button className="qa-expand-toggle" type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          <Chevron open={expanded} />
          {expanded ? "Hide full conversation" : `View full conversation · ${item.messages.length} messages`}
        </button>
      ) : null}

      {item.needsApproval ? (
        <div className="qa-approve">
          <div className="qa-draft-label">
            Suggested reply
            {draftReady ? (
              <Badge tone="green">AI draft · verify before send</Badge>
            ) : draftPending ? (
              <span className="qa-draft-hint">drafting a suggestion…</span>
            ) : (
              <span className="qa-draft-hint">no draft — type a reply</span>
            )}
          </div>
          {voiceMode ? (
            <div className="qa-voice-note">
              ✨ {voiceMode === "replace" ? "Rewrote" : "Revised"} from your voice note ·{" "}
              <button type="button" className="qa-voice-undo" onClick={undoVoice}>
                Undo
              </button>
            </div>
          ) : null}
          <div className="qa-reply-wrap">
            <Textarea
              className={`qa-reply-input ${voice.state === "applying" ? "is-applying" : ""}`}
              dir="auto"
              value={reply}
              placeholder={draftPending ? "Drafting… you can type a reply now too." : "Type your reply…"}
              onChange={(event) => setReply(event.target.value)}
              disabled={voice.state === "applying"}
              aria-label={`Reply to ${item.patientName}`}
            />
            {voice.state === "applying" ? (
              <div className="qa-reply-overlay">
                <span className="qa-voice-spinner" aria-hidden="true" /> Applying your voice note…
              </div>
            ) : null}
          </div>
          {voiceError ? <div className="qa-voice-error">{voiceError}</div> : null}
          <div className="qa-card-actions">
            <Button variant="default" onClick={() => onSend(item, reply)} disabled={!reply.trim() || voice.state !== "idle"}>
              Send
            </Button>
            <Button variant="ghost" onClick={() => onDismiss(item)} disabled={voice.state === "applying"}>
              Dismiss
            </Button>
            <VoiceControl voice={voice} onStart={startVoice} />
            {canReroute ? (
              <>
                <span className="qa-spacer" />
                <Rerouter item={item} doctors={doctors} onOpen={loadDoctors} onReroute={onReroute} />
              </>
            ) : null}
          </div>
        </div>
      ) : expanded && canReroute ? (
        <div className="qa-card-actions">
          <span className="qa-resolved">Replied — re-route future questions if needed.</span>
          <span className="qa-spacer" />
          <Rerouter item={item} doctors={doctors} onOpen={loadDoctors} onReroute={onReroute} />
        </div>
      ) : null}
    </Card>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className="qa-chevron"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function VoiceControl({ voice, onStart }: { voice: ReturnType<typeof useVoiceEdit>; onStart: () => void }) {
  if (voice.state === "recording") {
    return (
      <span className="qa-voice-live">
        <span className="qa-voice-dot" aria-hidden="true" />
        {formatSeconds(voice.seconds)}
        <button type="button" className="qa-voice-stop" onClick={voice.stop}>
          Stop
        </button>
        <button type="button" className="qa-voice-cancel" onClick={voice.cancel}>
          Cancel
        </button>
      </span>
    );
  }
  if (voice.state === "applying") return null; // the textarea overlay shows the applying state
  return (
    <button type="button" className="qa-voice-btn" onClick={onStart} title="Edit this reply by voice">
      <MicIcon /> Voice edit
    </button>
  );
}

function formatSeconds(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function Rerouter({
  item,
  doctors,
  onOpen,
  onReroute,
}: {
  item: QaInboxItem;
  doctors: QaTreatingDoctor[] | null;
  onOpen: () => void;
  onReroute: (item: QaInboxItem, doctorUserId: string) => void;
}) {
  return (
    <details className="qa-reroute" onToggle={(event) => (event.currentTarget as HTMLDetailsElement).open && onOpen()}>
      <summary>Re-route</summary>
      <div className="qa-reroute-list">
        {doctors === null ? (
          <span className="qa-current">Loading…</span>
        ) : doctors.length === 0 ? (
          <span className="qa-current">No treating doctors on record yet.</span>
        ) : (
          doctors.map((doctor) => {
            const isCurrent = item.assignedDoctor?.userId === doctor.userId;
            return (
              <button key={doctor.userId} type="button" disabled={isCurrent} onClick={() => onReroute(item, doctor.userId)}>
                {doctor.name} · {doctor.sessionCount} visit{doctor.sessionCount === 1 ? "" : "s"}
                {isCurrent ? " (current)" : ""}
              </button>
            );
          })
        )}
      </div>
    </details>
  );
}

function formatDateTime(iso: string | null): string {
  return formatDate(iso, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}
