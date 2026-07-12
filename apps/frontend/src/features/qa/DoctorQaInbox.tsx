import React from "react";
import "./qaInbox.css";
import type { ApiFetch } from "../../domain/appTypes";
import { Alert, Badge, Button, Card, Dialog, DisclosureRow, Skeleton, Tabs, Textarea } from "../../shared/ui/primitives";
import { SelectMenu } from "../../shared/ui/SelectMenu";
import { formatDate } from "../../shared/lib/datetime";
import { useT } from "../../shared/i18n";
import {
  dismissQaQuestion,
  fetchQaInbox,
  fetchQaLibraryItem,
  fetchQaSettings,
  fetchTreatingDoctors,
  routeQaThread,
  saveReplyAsTemplate,
  sendQaReply,
  setQaRoutingMode,
  type LibraryItem,
  type QaDraftProvenance,
  type QaInboxItem,
  type QaProvenanceSource,
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
  onShareQaLink,
}: {
  apiFetch: ApiFetch;
  onToast?: (message: string) => void;
  onChanged?: () => void;
  /** Opens the patient finder so the doctor can share a patient's Q&A link — the shortcut the
   *  teaching empty state offers when no thread has arrived yet. */
  onShareQaLink?: () => void;
}) {
  const t = useT();
  const [tab, setTab] = React.useState<"inbox" | "library">("inbox");
  const [scope, setScope] = React.useState<"mine" | "all">("mine");
  const [helpOpen, setHelpOpen] = React.useState(false);
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
          <h1>{tab === "library" ? t("qa.tabLibrary") : t("qa.inboxTitle")}</h1>
          <button type="button" className="qa-help-button" aria-label={t("qa.helpAria")} onClick={() => setHelpOpen(true)}>
            ?
          </button>
        </div>
        {tab === "inbox" ? (
          <div className="qa-inbox-controls">
            <Tabs
              ariaLabel={t("qa.scopeAria")}
              value={scope}
              onChange={setScope}
              options={[
                { value: "mine", label: t("qa.scopeMine") },
                { value: "all", label: t("qa.scopeClinic") },
              ]}
            />
            {settings ? (
              // Shared select-trigger style (SelectMenu), same family as the Insights range control.
              <div className="qa-routing">
                <span className="qa-routing-label">{t("qa.routingLabel")}</span>
                <SelectMenu
                  ariaLabel={t("qa.routingLabel")}
                  value={settings.routingMode === "manual" ? "manual" : "ai_default"}
                  onChange={(value) => void handleRoutingMode(value as "ai_default" | "manual")}
                  options={[
                    { value: "ai_default", label: t("qa.routingAuto") },
                    { value: "manual", label: t("qa.routingManual") },
                  ]}
                />
              </div>
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
            // Teach rather than dead-end (#8): how a thread arrives + a shortcut to share a Q&A link.
            <Card className="qa-empty-card">
              <p className="qa-empty-title">{scope === "mine" ? t("qa.emptyMine") : t("qa.emptyClinic")}</p>
              <p className="qa-empty-teach">{t("qa.emptyTeach")}</p>
              {onShareQaLink ? (
                <Button variant="secondary" onClick={onShareQaLink} type="button">
                  {t("qa.emptyShareCta")}
                </Button>
              ) : null}
            </Card>
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

      <Dialog open={helpOpen} title={t("qa.help.title")} onClose={() => setHelpOpen(false)}>
        <div className="qa-help-body">
          <p>{t("qa.help.inboxLibrary")}</p>
          <p>{t("qa.help.mineClinic")}</p>
          <p>{t("qa.help.routing")}</p>
        </div>
      </Dialog>

      {/* Inbox | Library lives in a fixed bottom bar (AES-1901): the capture bar is hidden on this
          screen, so this reads as the screen's own navigation and never competes with the per-reply
          voice-edit mic. */}
      <nav className="qa-bottom-nav" aria-label={t("qa.tabsAria")}>
        <Tabs
          ariaLabel={t("qa.tabsAria")}
          value={tab}
          onChange={setTab}
          options={[
            { value: "inbox", label: t("qa.tabInbox"), testId: "qa-tab-inbox" },
            { value: "library", label: t("qa.tabLibrary"), testId: "qa-tab-library" },
          ]}
        />
      </nav>
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
  // The draft surface grows with its content (up to a cap) — a clipped reply behind a scrollbar reads
  // as broken and hides what the doctor is about to send.
  const replyWrapRef = React.useRef<HTMLDivElement>(null);
  React.useLayoutEffect(() => {
    const el = replyWrapRef.current?.querySelector("textarea");
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight + 2, Math.round(window.innerHeight * 0.5))}px`;
  });

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

  // Escalation (AES-1901): a red-flagged pending question turns the whole row to the warning style and
  // names the flags, so a possible emergency (e.g. filler occlusion) can't read as a routine question.
  const urgentFlags = item.urgent ? item.pendingQuestion?.urgentFlags ?? item.urgentFlags ?? [] : [];
  const urgentLabel = urgentFlags.length
    ? urgentFlags.map((flag) => t(`qa.redflag.${flag}`)).join("، ")
    : t("qa.redflag.generic");

  return (
    <Card className={`qa-card ${item.needsApproval ? "qa-needs" : ""} ${item.urgent ? "qa-urgent" : ""}`}>
      <div className="qa-card-head">
        <span className="qa-avatar" aria-hidden="true" data-content>
          {(item.patientName || "?").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("")}
        </span>
        <span className="qa-head-id">
          <span className="qa-patient" dir="auto" data-content>
            {item.patientName}
          </span>
          <span className="qa-head-time" data-content>
            {formatDateTime(item.needsApproval && pending ? pending.askedAt : item.lastActivityAt)}
          </span>
        </span>
      </div>
      <div className="qa-head-badges">
          {item.urgent ? <Badge tone="red" data-testid="qa-urgent-badge">{t("qa.urgentBadge")}</Badge> : null}
          {item.needsApproval ? <Badge tone="amber">{t("qa.badgeNeedsReply")}</Badge> : null}
          {item.assignedDoctor ? (
            <Badge tone="blue">
              {item.routingSource === "manual" ? t("qa.badgeRerouted") : t("qa.badgeTreating")}{"\u00A0·\u00A0"}
              <span data-content>{item.assignedDoctor.name}</span>
            </Badge>
          ) : (
            <Badge tone="amber">{t("qa.badgeUnrouted")}</Badge>
          )}
      </div>
      {item.urgent ? (
        <div className="qa-urgent-banner" data-testid="qa-urgent-banner" role="status">
          <span aria-hidden="true">⚠</span> {t("qa.urgentBanner", { flags: urgentLabel })}
        </div>
      ) : null}

      {hiddenCount > 0 ? (
        <div className="qa-convo-toolbar">
          <DisclosureRow className="qa-expand-toggle" open={expanded} onToggle={() => setExpanded((value) => !value)}>
            {expanded ? t("qa.hideConversation") : t("qa.viewConversation", { n: item.messages.length })}
          </DisclosureRow>
        </div>
      ) : null}

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
        <div className="qa-convo qa-convo-collapsed">
          <div className="qa-msg patient" dir="auto" data-content>
            {pending.question}
          </div>
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

      {item.needsApproval ? (
        <div className="qa-approve">
          <div className="qa-draft-bubble">
          <div className="qa-draft-label">
            {t("qa.suggestedReply")}
            <DraftStatusBadge
              draftReady={draftReady}
              draftFailed={draftFailed}
              draftPending={draftPending}
              isStarterDraft={isStarterDraft}
            />
          </div>
          {/* The «بر اساس» source row (AES-1903): every grounding source the draft actually used, or the
              honest general-knowledge caution when none did. Independent of the starter marker above. */}
          {draftReady ? (
            <DraftProvenancePanel provenance={pending?.draftProvenance} apiFetch={apiFetch} onOpenLibrary={onOpenLibrary} />
          ) : null}
          {voiceMode ? (
            <div className="qa-voice-note">
              ✨ {voiceMode === "replace" ? t("qa.voiceRewrote") : t("qa.voiceRevised")} ·{" "}
              <button type="button" className="qa-voice-undo" onClick={undoVoice}>
                {t("qa.undo")}
              </button>
            </div>
          ) : null}
          <div className="qa-reply-wrap" ref={replyWrapRef}>
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
          </div>
          <div className="qa-card-actions">
            <Button className="qa-send" variant="default" onClick={() => onSend(item, reply)} disabled={!reply.trim() || voice.state !== "idle"}>
              {t("qa.send")}
            </Button>
            <VoiceControl voice={voice} onStart={startVoice} />
          </div>
          <div className="qa-card-actions qa-card-actions-quiet">
            <Button variant="secondary" size="sm" onClick={() => onDismiss(item)} disabled={voice.state === "applying"}>
              {t("qa.dismiss")}
            </Button>
            <span className="qa-spacer" />
            {canReroute ? <Rerouter item={item} doctors={doctors} onOpen={loadDoctors} onReroute={onReroute} /> : null}
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

/**
 * The «بر اساس» provenance panel (AES-1903): a compact source row under a ready draft, built
 * deterministically by the backend from what the payload carried. A grounded draft shows the strong
 * template / previous-reply attribution plus a chip per patient-record / conversation block it used;
 * an ungrounded draft shows the honest caution chip «دانش عمومی — بدون منبع کلینیکی» so the doctor
 * knows this one deserves the hardest review. Chrome is bilingual; the revealed Q/A text is CONTENT.
 */
function DraftProvenancePanel({
  provenance,
  apiFetch,
  onOpenLibrary,
}: {
  provenance?: QaDraftProvenance | null;
  apiFetch: ApiFetch;
  onOpenLibrary: () => void;
}) {
  const t = useT();
  // New structured shape wins; fall back to the legacy top-level attribution ({kind,exemplarId,label}).
  const sources: QaProvenanceSource[] = Array.isArray(provenance?.sources)
    ? provenance!.sources!
    : provenance?.kind
      ? [{ type: provenance.kind, exemplarId: provenance.exemplarId, label: provenance.label ?? null }]
      : [];
  const grounded = provenance?.grounded ?? sources.length > 0;
  if (!provenance) return null; // no backend signal at all (transient legacy draft) → no row

  return (
    <div className="qa-provenance" data-testid="qa-draft-provenance">
      <span className="qa-provenance-label">{t("qa.basedOnLabel")}</span>
      {grounded && sources.length ? (
        sources.map((source, index) => (
          <ProvenanceChip key={`${source.type}-${index}`} source={source} apiFetch={apiFetch} onOpenLibrary={onOpenLibrary} />
        ))
      ) : (
        <span className="qa-provenance-chip qa-provenance-general" data-testid="qa-provenance-general">
          {t("qa.basedOnGeneral")}
        </span>
      )}
    </div>
  );
}

function ProvenanceChip({
  source,
  apiFetch,
  onOpenLibrary,
}: {
  source: QaProvenanceSource;
  apiFetch: ApiFetch;
  onOpenLibrary: () => void;
}) {
  const t = useT();
  switch (source.type) {
    case "template":
      return (
        <button
          type="button"
          className="qa-provenance-chip qa-provenance-strong"
          data-testid="qa-provenance-template"
          onClick={onOpenLibrary}
          title={t("qa.basedOnOpenLibrary")}
        >
          {t("qa.basedOnTemplate", { name: source.label ?? "" })}
        </button>
      );
    case "sent_reply":
      return <SentReplyChip exemplarId={source.exemplarId} apiFetch={apiFetch} />;
    case "patient_aftercare":
      return <RevealChip label={t("qa.basedOnAftercare")} text={source.text} testId="qa-provenance-aftercare" />;
    case "patient_summary":
      return <RevealChip label={t("qa.basedOnSummary")} text={source.text} testId="qa-provenance-summary" />;
    case "conversation":
      return <RevealChip label={t("qa.basedOnConversation")} text={source.text} testId="qa-provenance-conversation" />;
    default:
      return null;
  }
}

/** A provenance chip that reveals its own grounding snippet inline on tap (patient-record / conversation
 * sources carry the text with them). Static when there's no snippet. */
function RevealChip({ label, text, testId }: { label: string; text?: string; testId?: string }) {
  const [open, setOpen] = React.useState(false);
  if (!text) return <span className="qa-provenance-chip" data-testid={testId}>{label}</span>;
  return (
    <span className="qa-provenance-reply">
      <button
        type="button"
        className="qa-provenance-chip qa-provenance-revealable"
        data-testid={testId}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open ? (
        <div className="qa-provenance-reveal" dir="auto" data-content>
          {text}
        </div>
      ) : null}
    </span>
  );
}

/** The "پاسخ قبلی کلینیک" chip: reveals the exemplar's OWN Q/A (never the other patient's thread). */
function SentReplyChip({ exemplarId, apiFetch }: { exemplarId?: string; apiFetch: ApiFetch }) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const [item, setItem] = React.useState<LibraryItem | null>(null);
  const [error, setError] = React.useState("");
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && item === null && exemplarId) {
      fetchQaLibraryItem(apiFetch, exemplarId)
        .then(setItem)
        .catch(() => setError(t("qa.basedOnReplyError")));
    }
  };
  // Build the reveal body with if/else (not a nested JSX ternary) so the content is unambiguous.
  let revealBody: React.ReactNode = <span>{t("qa.loading")}</span>;
  if (error) {
    revealBody = <span className="qa-provenance-error">{error}</span>;
  } else if (item) {
    revealBody = (
      <>
        {item.question ? (
          <p dir="auto">
            <strong>{t("qa.basedOnReplyQ")}</strong> <span data-content>{item.question}</span>
          </p>
        ) : null}
        <p dir="auto">
          <strong>{t("qa.basedOnReplyA")}</strong> <span data-content>{item.answer}</span>
        </p>
      </>
    );
  }
  return (
    <span className="qa-provenance-reply">
      <button
        type="button"
        className="qa-provenance-chip qa-provenance-strong"
        data-testid="qa-provenance-sentreply"
        aria-expanded={open}
        onClick={toggle}
        title={t("qa.basedOnReplyOpen")}
      >
        {t("qa.basedOnReply")}
      </button>
      {open ? <div className="qa-provenance-reveal">{revealBody}</div> : null}
    </span>
  );
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
  return formatDate(iso, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}
