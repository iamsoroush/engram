import React from "react";
import "./qaInbox.css";
import type { ApiFetch } from "../../domain/appTypes";
import { Alert, Badge, Button, Card, Skeleton, Textarea } from "../../shared/ui/primitives";
import {
  dismissQaQuestion,
  fetchQaInbox,
  fetchQaSettings,
  fetchQaThreadDetail,
  fetchTreatingDoctors,
  routeQaThread,
  sendQaReply,
  setQaRoutingMode,
  type QaInboxItem,
  type QaSettings,
  type QaThreadMessage,
  type QaTreatingDoctor,
} from "./qaClient";

/**
 * Doctor Q&A inbox (AES-402).
 *
 * Pending patient questions with an AI-suggested reply the doctor can Send / edit / Dismiss —
 * nothing sends without the doctor approving it. Routing defaults to the patient's treating doctor
 * and is manually re-routable from that patient's treating-doctor list (foundation §7). Pro-gated
 * (the parent only mounts this for Pro tenants; the API also enforces the capability).
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
      .then((next) => {
        if (!cancelled) setSettings(next);
      })
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
      const next = await setQaRoutingMode(apiFetch, mode);
      setSettings(next);
      onToast?.(mode === "manual" ? "New questions now wait for manual routing." : "New questions now auto-route to the treating doctor.");
    } catch {
      onToast?.("Couldn’t update routing.");
    }
  };

  const handleSend = async (item: QaInboxItem, reply: string) => {
    const text = reply.trim();
    if (!text) {
      onToast?.("Add a reply before sending.");
      return;
    }
    if (!window.confirm(`Send this reply to ${item.patientName}? They will see it on their private link.`)) return;
    try {
      await sendQaReply(apiFetch, item.messageId, text);
      onToast?.("Reply sent and captured into the patient’s memory.");
      reload();
    } catch {
      onToast?.("Couldn’t send the reply.");
    }
  };

  const handleDismiss = async (item: QaInboxItem) => {
    if (!window.confirm(`Dismiss ${item.patientName}’s question without replying?`)) return;
    try {
      await dismissQaQuestion(apiFetch, item.messageId);
      onToast?.("Question dismissed.");
      reload();
    } catch {
      onToast?.("Couldn’t dismiss the question.");
    }
  };

  const handleReroute = async (item: QaInboxItem, doctorUserId: string) => {
    try {
      await routeQaThread(apiFetch, item.threadId, doctorUserId);
      onToast?.("Question re-routed.");
      reload();
    } catch {
      onToast?.("Couldn’t re-route this question.");
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
        <p className="qa-empty">All caught up — no pending questions{scope === "mine" ? " routed to you" : ""}.</p>
      ) : (
        items.map((item) => (
          <QaInboxCard
            key={item.messageId}
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

function QaInboxCard({
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
  const [reply, setReply] = React.useState(item.suggestedReply || "");
  const [doctors, setDoctors] = React.useState<QaTreatingDoctor[] | null>(null);
  const [history, setHistory] = React.useState<QaThreadMessage[] | null>(null);

  // Keep the editable reply in sync when the draft finishes after the card first rendered.
  React.useEffect(() => {
    setReply((current) => (current.trim() ? current : item.suggestedReply || ""));
  }, [item.suggestedReply]);

  const loadDoctors = () => {
    if (doctors !== null) return;
    fetchTreatingDoctors(apiFetch, item.patientId)
      .then(setDoctors)
      .catch(() => setDoctors([]));
  };

  const loadHistory = () => {
    if (history !== null) return;
    fetchQaThreadDetail(apiFetch, item.threadId)
      // Everything in the thread except the question being answered right now (shown above).
      .then((detail) => setHistory(detail.messages.filter((message) => message.id !== item.messageId)))
      .catch(() => setHistory([]));
  };

  const draftReady = item.draftStatus === "ready";
  const draftPending = item.draftStatus === "pending" || item.draftStatus === "none";

  return (
    <Card className="qa-card">
      <div className="qa-card-top">
        <span className="qa-patient" dir="auto">
          {item.patientName} asks
        </span>
        <span className="qa-asked">
          {item.assignedDoctor ? (
            <Badge tone="blue">
              {item.routingSource === "manual" ? "re-routed" : "treating"} · {item.assignedDoctor.name}
            </Badge>
          ) : (
            <Badge tone="amber">unrouted</Badge>
          )}{" "}
          {formatDateTime(item.askedAt)}
        </span>
      </div>

      <div className="qa-question" dir="auto">
        {item.question}
      </div>

      <details className="qa-history" onToggle={(event) => (event.currentTarget as HTMLDetailsElement).open && loadHistory()}>
        <summary>Conversation so far</summary>
        <div className="qa-history-list">
          {history === null ? (
            <span className="qa-current">Loading…</span>
          ) : history.length === 0 ? (
            <span className="qa-current">This is the first message in the thread.</span>
          ) : (
            history.map((message) => (
              <div key={message.id} className={`qa-history-msg ${message.role === "doctor" ? "doctor" : "patient"}`}>
                <div className="qa-history-role">
                  {message.role === "doctor" ? "Clinic" : item.patientName}
                  {message.status === "dismissed" ? " · dismissed" : ""}
                  <span className="qa-history-time"> · {formatDateTime(message.createdAt)}</span>
                </div>
                <div className="qa-history-body" dir="auto">
                  {message.body}
                </div>
              </div>
            ))
          )}
        </div>
      </details>

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

      <Textarea
        className="qa-reply-input"
        dir="auto"
        value={reply}
        placeholder={draftPending ? "Drafting… you can type a reply now too." : "Type your reply…"}
        onChange={(event) => setReply(event.target.value)}
        aria-label={`Reply to ${item.patientName}`}
      />

      <div className="qa-card-actions">
        <Button variant="default" onClick={() => onSend(item, reply)} disabled={!reply.trim()}>
          Send
        </Button>
        <Button variant="ghost" onClick={() => onDismiss(item)}>
          Dismiss
        </Button>
        <span className="qa-spacer" />
        <details className="qa-reroute" onToggle={(event) => (event.currentTarget as HTMLDetailsElement).open && loadDoctors()}>
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
                  <button
                    key={doctor.userId}
                    type="button"
                    disabled={isCurrent}
                    onClick={() => onReroute(item, doctor.userId)}
                  >
                    {doctor.name} · {doctor.sessionCount} visit{doctor.sessionCount === 1 ? "" : "s"}
                    {isCurrent ? " (current)" : ""}
                  </button>
                );
              })
            )}
          </div>
        </details>
      </div>
    </Card>
  );
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}
