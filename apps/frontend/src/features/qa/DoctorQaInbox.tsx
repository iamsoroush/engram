import React from "react";
import "./qaInbox.css";
import type { ApiFetch } from "../../domain/appTypes";
import { Alert, Badge, Button, Card, DisclosureRow, Skeleton, Textarea } from "../../shared/ui/primitives";
import { formatDate } from "../../shared/lib/datetime";
import { useT } from "../../shared/i18n";
import {
  dismissQaQuestion,
  fetchQaInbox,
  fetchQaSettings,
  fetchTreatingDoctors,
  routeQaThread,
  saveReplyAsTemplate,
  sendQaReply,
  setQaRoutingMode,
  type QaInboxItem,
  type QaSettings,
  type QaThreadMessage,
  type QaTreatingDoctor,
  type QaVisitMarker,
} from "./qaClient";
import { LibraryTab } from "./LibraryTab";
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
  const t = useT();
  const [tab, setTab] = React.useState<"inbox" | "library">("inbox");
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
        setError(t("qa.loadError"));
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [apiFetch, scope, refresh, onChanged, t]);

  // Poll while any pending question is still drafting (Q-7): the initial draft runs in the background
  // and the inbox otherwise never learns when it lands or terminally fails. One deferred reload per
  // load settles the state; it stops as soon as nothing is drafting (ready / failed → no reschedule).
  React.useEffect(() => {
    if (!loaded) return;
    const stillDrafting = items.some(
      (item) => item.pendingQuestion && ["pending", "none"].includes(item.pendingQuestion.draftStatus),
    );
    if (!stillDrafting) return;
    const handle = window.setTimeout(reload, 3000);
    return () => window.clearTimeout(handle);
  }, [items, loaded, reload]);

  const handleRoutingMode = async (mode: "ai_default" | "manual") => {
    try {
      setSettings(await setQaRoutingMode(apiFetch, mode));
      onToast?.(mode === "manual" ? t("qa.routingNowManual") : t("qa.routingNowAuto"));
    } catch {
      onToast?.(t("qa.routingUpdateError"));
    }
  };

  const handleSend = async (item: QaInboxItem, reply: string) => {
    const messageId = item.pendingQuestion?.messageId;
    const text = reply.trim();
    if (!messageId || !text) {
      onToast?.(t("qa.addReplyBeforeSend"));
      return;
    }
    if (!window.confirm(t("qa.confirmSend", { name: item.patientName }))) return;
    try {
      await sendQaReply(apiFetch, messageId, text);
      onToast?.(t("qa.replySent"));
      reload();
    } catch {
      onToast?.(t("qa.sendError"));
    }
  };

  const handleDismiss = async (item: QaInboxItem) => {
    const messageId = item.pendingQuestion?.messageId;
    if (!messageId) return;
    if (!window.confirm(t("qa.confirmDismiss", { name: item.patientName }))) return;
    try {
      await dismissQaQuestion(apiFetch, messageId);
      onToast?.(t("qa.questionDismissed"));
      reload();
    } catch {
      onToast?.(t("qa.dismissError"));
    }
  };

  const handleReroute = async (item: QaInboxItem, doctorUserId: string) => {
    try {
      await routeQaThread(apiFetch, item.threadId, doctorUserId);
      onToast?.(t("qa.conversationRerouted"));
      reload();
    } catch {
      onToast?.(t("qa.rerouteError"));
    }
  };

  return (
    <div className="qa-inbox" data-testid="qa-inbox">
      <div className="qa-inbox-head">
        <div className="qa-inbox-head-top">
          <h1>{t("qa.inboxTitle")}</h1>
          <div className="qa-tabs" role="tablist" aria-label={t("qa.tabsAria")}>
            <button
              className={tab === "inbox" ? "active" : ""}
              data-testid="qa-tab-inbox"
              onClick={() => setTab("inbox")}
              type="button"
              role="tab"
              aria-selected={tab === "inbox"}
            >
              {t("qa.tabInbox")}
            </button>
            <button
              className={tab === "library" ? "active" : ""}
              data-testid="qa-tab-library"
              onClick={() => setTab("library")}
              type="button"
              role="tab"
              aria-selected={tab === "library"}
            >
              {t("qa.tabLibrary")}
            </button>
          </div>
        </div>
        {tab === "inbox" ? (
          <div className="qa-inbox-controls">
            <div className="qa-scope" role="tablist" aria-label={t("qa.scopeAria")}>
              <button className={scope === "mine" ? "active" : ""} onClick={() => setScope("mine")} type="button">
                {t("qa.scopeMine")}
              </button>
              <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
                {t("qa.scopeClinic")}
              </button>
            </div>
            {settings ? (
              <label className="qa-routing">
                {t("qa.routingLabel")}
                <select
                  className="select"
                  value={settings.routingMode === "manual" ? "manual" : "ai_default"}
                  onChange={(event) => void handleRoutingMode(event.target.value as "ai_default" | "manual")}
                >
                  <option value="ai_default">{t("qa.routingAuto")}</option>
                  <option value="manual">{t("qa.routingManual")}</option>
                </select>
              </label>
            ) : null}
          </div>
        ) : null}
      </div>

      {tab === "library" ? (
        <LibraryTab apiFetch={apiFetch} onToast={onToast} />
      ) : (
        <>
          {error ? <Alert tone="red">{error}</Alert> : null}

          {!loaded ? (
            <Card className="qa-card">
              <Skeleton className="h-16" />
              <Skeleton className="h-12" />
            </Card>
          ) : items.length === 0 ? (
            <p className="qa-empty">{scope === "mine" ? t("qa.emptyMine") : t("qa.emptyClinic")}</p>
          ) : (
            items.map((item) => (
              <QaThreadCard
                key={item.threadId}
                item={item}
                apiFetch={apiFetch}
                onToast={onToast}
                onSend={handleSend}
                onDismiss={handleDismiss}
                onReroute={handleReroute}
                onOpenLibrary={() => setTab("library")}
              />
            ))
          )}
        </>
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
  onToast,
  onSend,
  onDismiss,
  onReroute,
  onOpenLibrary,
}: {
  item: QaInboxItem;
  apiFetch: ApiFetch;
  onToast?: (message: string) => void;
  onSend: (item: QaInboxItem, reply: string) => void;
  onDismiss: (item: QaInboxItem) => void;
  onReroute: (item: QaInboxItem, doctorUserId: string) => void;
  onOpenLibrary: () => void;
}) {
  const t = useT();
  const pending = item.pendingQuestion;

  // Promote a sent doctor reply into a reusable template (AES-410) — grows the retrieval corpus.
  const saveAsTemplate = async (messageId: string) => {
    try {
      await saveReplyAsTemplate(apiFetch, messageId);
      onToast?.(t("qa.library.savedToast"));
    } catch {
      onToast?.(t("qa.library.saveError"));
    }
  };
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
    t,
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
  // A terminally-failed draft (initial or voice edit) is a visible state, not an endless "drafting…".
  const draftFailed = pending?.draftStatus === "failed" || pending?.draftStatus === "failed_revise";
  // The gateway-less deterministic draft is a cautious STARTER, not a real AI reply — mark it so the
  // doctor reviews rather than trusting it as generated guidance (Q-10).
  const isStarterDraft = draftReady && pending?.draftSource === "mock-deterministic";
  const lastMessage = item.messages[item.messages.length - 1];

  // Re-route only makes sense when the patient has more than one treating doctor to choose between.
  const canReroute = item.treatingDoctorCount >= 2;
  // Earlier messages that are hidden when collapsed (open shows the pending question; resolved shows
  // a one-line preview), so the disclosure can name how many there are.
  const hiddenCount = item.needsApproval ? item.messages.length - 1 : item.messages.length;

  return (
    <Card className={`qa-card ${item.needsApproval ? "qa-needs" : ""}`}>
      <div className="qa-card-head">
        <span className="qa-patient" dir="auto" data-content>
          {item.patientName}
        </span>
        <span className="qa-head-right">
          {item.needsApproval ? <Badge tone="amber">{t("qa.badgeNeedsReply")}</Badge> : null}
          {item.assignedDoctor ? (
            <Badge tone="blue">
              {item.routingSource === "manual" ? t("qa.badgeRerouted") : t("qa.badgeTreating")} ·{" "}
              <span data-content>{item.assignedDoctor.name}</span>
            </Badge>
          ) : (
            <Badge tone="amber">{t("qa.badgeUnrouted")}</Badge>
          )}
        </span>
      </div>

      {expanded ? (
        <div className="qa-convo" ref={convoRef}>
          {timeline.map((entry, index) =>
            entry.kind === "visit" ? (
              <div className="qa-visit" key={`v-${entry.visit.sessionId}-${index}`}>
                <span dir="auto">
                  🗓 {t("qa.visit")} · <span data-content>{entry.visit.title}</span>
                </span>
                <span className="qa-visit-date" data-content>{formatDateTime(entry.visit.date)}</span>
              </div>
            ) : (
              <div
                key={entry.message.id}
                className={`qa-msg ${entry.message.role === "doctor" ? "clinic" : "patient"} ${
                  pending && entry.message.id === pending.messageId ? "awaiting" : ""
                }`}
              >
                <div className="qa-msg-meta">
                  {entry.message.role === "doctor" ? t("qa.clinic") : <span data-content>{item.patientName}</span>}
                  <span className="qa-msg-time" data-content> · {formatDateTime(entry.message.createdAt)}</span>
                  {entry.message.status === "dismissed" ? <span className="qa-msg-time"> · {t("qa.dismissed")}</span> : null}
                </div>
                <div dir="auto" data-content>{entry.message.body}</div>
                {entry.message.role === "doctor" && entry.message.status === "sent" ? (
                  <button
                    type="button"
                    className="qa-save-template"
                    data-testid="qa-save-template"
                    onClick={() => void saveAsTemplate(entry.message.id)}
                  >
                    {t("qa.saveAsTemplate")}
                  </button>
                ) : null}
              </div>
            ),
          )}
        </div>
      ) : item.needsApproval && pending ? (
        // Collapsed open conversation: just the question awaiting a reply.
        <div className="qa-msg patient awaiting qa-msg-flush">
          <div className="qa-msg-meta">
            <span data-content>{item.patientName}</span>
            <span className="qa-msg-time" data-content> · {formatDateTime(pending.askedAt)}</span>
          </div>
          <div dir="auto" data-content>{pending.question}</div>
        </div>
      ) : (
        // Collapsed resolved conversation: one-line preview of the latest message.
        <div className="qa-preview">
          <span className="qa-preview-role" data-content>
            {lastMessage?.role === "doctor" ? t("qa.clinic") : item.patientName}:
          </span>{" "}
          <span className="qa-preview-text" dir="auto" data-content>
            {lastMessage?.body}
          </span>
          <span className="qa-msg-time" data-content> · {formatDateTime(item.lastActivityAt)}</span>
        </div>
      )}

      {/* Explicit, labelled disclosure for the full thread (replaces the easy-to-miss chevron). */}
      {hiddenCount > 0 ? (
        <DisclosureRow className="qa-expand-toggle" open={expanded} onToggle={() => setExpanded((value) => !value)}>
          {expanded ? t("qa.hideConversation") : t("qa.viewConversation", { n: item.messages.length })}
        </DisclosureRow>
      ) : null}

      {item.needsApproval ? (
        <div className="qa-approve">
          <div className="qa-draft-label">
            {t("qa.suggestedReply")}
            <DraftStatusBadge
              draftReady={draftReady}
              draftFailed={draftFailed}
              draftPending={draftPending}
              isStarterDraft={isStarterDraft}
            />
            {draftReady && pending?.draftProvenance ? (
              <button
                type="button"
                className="qa-draft-provenance"
                data-testid="qa-draft-provenance"
                onClick={onOpenLibrary}
                title={t("qa.basedOnOpenLibrary")}
              >
                {pending.draftProvenance.kind === "template"
                  ? t("qa.basedOnTemplate", { name: pending.draftProvenance.label ?? "" })
                  : t("qa.basedOnReply")}
              </button>
            ) : null}
          </div>
          {voiceMode ? (
            <div className="qa-voice-note">
              ✨ {voiceMode === "replace" ? t("qa.voiceRewrote") : t("qa.voiceRevised")} ·{" "}
              <button type="button" className="qa-voice-undo" onClick={undoVoice}>
                {t("qa.undo")}
              </button>
            </div>
          ) : null}
          <div className="qa-reply-wrap">
            <Textarea
              className={`qa-reply-input ${voice.state === "applying" ? "is-applying" : ""}`}
              dir="auto"
              value={reply}
              placeholder={draftPending ? t("qa.replyPlaceholderDrafting") : t("qa.replyPlaceholder")}
              onChange={(event) => setReply(event.target.value)}
              disabled={voice.state === "applying"}
              aria-label={t("qa.replyToAria", { name: item.patientName })}
            />
            {voice.state === "applying" ? (
              <div className="qa-reply-overlay">
                <span className="qa-voice-spinner" aria-hidden="true" /> {t("qa.applyingVoice")}
              </div>
            ) : null}
          </div>
          {voiceError ? <div className="qa-voice-error">{voiceError}</div> : null}
          <div className="qa-card-actions">
            <Button variant="default" onClick={() => onSend(item, reply)} disabled={!reply.trim() || voice.state !== "idle"}>
              {t("qa.send")}
            </Button>
            <Button variant="ghost" onClick={() => onDismiss(item)} disabled={voice.state === "applying"}>
              {t("qa.dismiss")}
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
          <span className="qa-resolved">{t("qa.repliedReroute")}</span>
          <span className="qa-spacer" />
          <Rerouter item={item} doctors={doctors} onOpen={loadDoctors} onReroute={onReroute} />
        </div>
      ) : null}
    </Card>
  );
}

/** The draft-status marker beside "Suggested reply": ready / starter-fallback / failed / drafting. */
function DraftStatusBadge({
  draftReady,
  draftFailed,
  draftPending,
  isStarterDraft,
}: {
  draftReady: boolean;
  draftFailed: boolean;
  draftPending: boolean;
  isStarterDraft: boolean;
}) {
  const t = useT();
  if (draftReady && isStarterDraft) return <Badge tone="amber">{t("qa.starterReply")}</Badge>;
  if (draftReady) return <Badge tone="green">{t("qa.aiDraftVerify")}</Badge>;
  if (draftFailed) return <span className="qa-draft-hint">{t("qa.draftFailedHint")}</span>;
  if (draftPending) return <span className="qa-draft-hint">{t("qa.draftingHint")}</span>;
  return <span className="qa-draft-hint">{t("qa.noDraftHint")}</span>;
}

function VoiceControl({ voice, onStart }: { voice: ReturnType<typeof useVoiceEdit>; onStart: () => void }) {
  const t = useT();
  if (voice.state === "recording") {
    return (
      <span className="qa-voice-live">
        <span className="qa-voice-dot" aria-hidden="true" />
        <span data-content>{formatSeconds(voice.seconds)}</span>
        <button type="button" className="qa-voice-stop" onClick={voice.stop}>
          {t("qa.stop")}
        </button>
        <button type="button" className="qa-voice-cancel" onClick={voice.cancel}>
          {t("qa.cancel")}
        </button>
      </span>
    );
  }
  if (voice.state === "applying") return null; // the textarea overlay shows the applying state
  return (
    <button type="button" className="qa-voice-btn" onClick={onStart} title={t("qa.voiceEditTitle")}>
      <MicIcon /> {t("qa.voiceEdit")}
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
  const t = useT();
  return (
    <details className="qa-reroute" onToggle={(event) => (event.currentTarget as HTMLDetailsElement).open && onOpen()}>
      <summary>{t("qa.reroute")}</summary>
      <div className="qa-reroute-list">
        {doctors === null ? (
          <span className="qa-current">{t("qa.loading")}</span>
        ) : doctors.length === 0 ? (
          <span className="qa-current">{t("qa.noTreatingDoctors")}</span>
        ) : (
          doctors.map((doctor) => {
            const isCurrent = item.assignedDoctor?.userId === doctor.userId;
            return (
              <button key={doctor.userId} type="button" disabled={isCurrent} onClick={() => onReroute(item, doctor.userId)}>
                <span data-content>{doctor.name}</span> · {t("qa.visitCount", { n: doctor.sessionCount })}
                {isCurrent ? ` ${t("qa.current")}` : ""}
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
