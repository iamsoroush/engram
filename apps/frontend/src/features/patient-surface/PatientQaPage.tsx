import React from "react";
import "./patientSurface.css";
import "./patientQa.css";
import { askQuestion, fetchQaThread, type QaExchange, type QaLoadResult, type QaThreadPayload } from "./qaApi";
import { formatDate } from "../../shared/lib/datetime";

/**
 * Public post-session Q&A page (AES-402/403).
 *
 * Rendered for `/qa/{token}` — a SEPARATE area from the clinic app, no login, no clinic state. The
 * patient sees only their own questions + the clinic's verified replies and can ask a new one; the
 * AI draft + routing + every other patient are never sent here, so they cannot appear. A revoked or
 * unknown link resolves to one indistinguishable "no longer available" state (no existence leak).
 */
export function PatientQaPage({ token }: { token: string }) {
  const [result, setResult] = React.useState<QaLoadResult | null>(null);
  const [attempt, setAttempt] = React.useState(0);

  const reload = React.useCallback(() => setAttempt((value) => value + 1), []);

  React.useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    fetchQaThread(token, controller.signal).then((next) => {
      if (!controller.signal.aborted) setResult(next);
    });
    return () => controller.abort();
  }, [token, attempt]);

  React.useEffect(() => {
    if (result?.kind === "ok") {
      const clinic = result.payload.clinic?.name;
      document.title = clinic ? `${clinic} — questions` : "Your questions";
    } else {
      document.title = "Engram";
    }
  }, [result]);

  if (result === null) {
    return (
      <div className="patient-surface">
        <div className="ps-shell">
          <div className="ps-status">
            <div className="ps-spinner" role="status" aria-label="Loading" />
            <p>Loading your questions…</p>
          </div>
        </div>
      </div>
    );
  }

  if (result.kind === "unavailable") {
    return (
      <StatusScreen
        title="This link is no longer available"
        body="It may have been turned off by the clinic. If you still need to reach your care team, please contact your clinic."
      />
    );
  }

  if (result.kind === "error") {
    return (
      <StatusScreen
        title="Couldn’t load your questions"
        body="Please check your connection and try again."
        action={
          <button type="button" className="ps-retry" onClick={reload}>
            Try again
          </button>
        }
      />
    );
  }

  return <QaView token={token} payload={result.payload} onPosted={reload} />;
}

/** Localized chrome for the public Q&A page, matching the clinic's content language (Q-10). */
function qaStrings(language: string | null, greetingName: string) {
  const fa = (language || "").toLowerCase().startsWith("fa");
  return fa
    ? {
        fa: true,
        subtitle: "پرسش و پاسخ",
        yourConversation: "گفتگوی شما",
        empty: "هنوز پرسشی ندارید. از تیم مراقبت خود در پایین بپرسید.",
        askHeading: "از تیم مراقبت خود بپرسید",
        intro: "بین ویزیت‌ها سوالی دارید؟ اینجا بفرستید و کلینیک پاسخ می‌دهد. پاسخ‌ها پیش از نمایش، توسط پزشک شما بازبینی می‌شوند.",
        placeholder: "مثلاً: ورم پیشانی‌ام طبیعی است؟",
        yourQuestion: "پرسش شما",
        sending: "در حال ارسال…",
        send: "ارسال پرسش",
        sent: "ارسال شد — کلینیک اینجا پاسخ می‌دهد.",
        sendError: "ارسال پرسش ممکن نشد. لطفاً دوباره تلاش کنید.",
        footer: greetingName
          ? `لینک خصوصی برای ${greetingName} · فقط پیام‌های خودتان اینجا دیده می‌شود.`
          : "لینک خصوصی · فقط پیام‌های خودتان اینجا دیده می‌شود.",
        youAsked: "شما پرسیدید",
        verified: "تأییدشده توسط کلینیک",
        awaiting: "در انتظار پاسخ کلینیک…",
        closed: "این پرسش توسط کلینیک بسته شد.",
      }
    : {
        fa: false,
        subtitle: "Questions & answers",
        yourConversation: "Your conversation",
        empty: "No questions yet. Ask your care team below.",
        askHeading: "Ask your care team",
        intro:
          "Have a question between visits? Send it here and your clinic will reply. Replies are reviewed by your clinician before you see them.",
        placeholder: "e.g. Is the swelling on my forehead normal?",
        yourQuestion: "Your question",
        sending: "Sending…",
        send: "Send question",
        sent: "Sent — your clinic will reply here.",
        sendError: "Couldn’t send your question. Please try again.",
        footer: `Private link${greetingName ? ` for ${greetingName}` : ""} · only your own messages appear here.`,
        youAsked: "You asked",
        verified: "verified by your clinic",
        awaiting: "Waiting for your clinic to reply…",
        closed: "This question was closed by your clinic.",
      };
}

function QaView({ token, payload, onPosted }: { token: string; payload: QaThreadPayload; onPosted: () => void }) {
  const greetingName = firstName(payload.patientName);
  const s = qaStrings(payload.language, greetingName);
  const [draft, setDraft] = React.useState("");
  const [posting, setPosting] = React.useState(false);
  const [justSent, setJustSent] = React.useState(false);
  const [postError, setPostError] = React.useState("");

  const submit = async () => {
    const question = draft.trim();
    if (!question || posting) return;
    setPosting(true);
    setPostError("");
    const { ok } = await askQuestion(token, question);
    setPosting(false);
    if (!ok) {
      setPostError(s.sendError);
      return;
    }
    setDraft("");
    setJustSent(true);
    onPosted();
  };

  return (
    <div className="patient-surface" dir={s.fa ? "rtl" : "ltr"}>
      <div className="ps-shell">
        <header className="ps-head">
          <div className="ps-clinic">
            <div className="ps-logo">{initials(payload.clinic?.name)}</div>
            <div>
              <div className="ps-clinic-name" dir="auto">
                {payload.clinic?.name || "Your clinic"}
              </div>
              <div className="ps-clinic-sub" dir="auto">{s.subtitle}</div>
            </div>
          </div>
          {greetingName ? (
            <div className="ps-hi" dir="auto">
              {greetingName} 👋
            </div>
          ) : null}
        </header>

        <main className="ps-body">
          <section className="ps-sec" aria-label={s.yourConversation}>
            <h2 dir="auto">{s.yourConversation}</h2>
            {payload.exchanges.length ? (
              <div className="psqa-thread">
                {payload.exchanges.map((exchange) => (
                  <ExchangeView key={exchange.id} exchange={exchange} s={s} />
                ))}
              </div>
            ) : (
              <p className="psqa-empty" dir="auto">{s.empty}</p>
            )}
          </section>

          {/* Composer pinned at the bottom — newest at the end, like a chat thread. */}
          <section className="ps-sec psqa-ask" aria-label={s.askHeading}>
            <h2 dir="auto">{s.askHeading}</h2>
            <p className="psqa-intro" dir="auto">{s.intro}</p>
            <div className="psqa-composer">
              <textarea
                dir="auto"
                value={draft}
                placeholder={s.placeholder}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setJustSent(false);
                }}
                aria-label={s.yourQuestion}
              />
              <button type="button" className="psqa-send" onClick={submit} disabled={!draft.trim() || posting}>
                {posting ? s.sending : s.send}
              </button>
              {justSent ? <div className="psqa-sent" dir="auto">{s.sent}</div> : null}
              {postError ? (
                <div className="psqa-sent" dir="auto" style={{ color: "#b42318", background: "#fef3f2", borderColor: "#fecdc9" }}>
                  {postError}
                </div>
              ) : null}
            </div>
          </section>
        </main>

        <footer className="ps-foot">
          <LockIcon className="ps-ic sm" />
          <span dir="auto">{s.footer}</span>
        </footer>
      </div>
    </div>
  );
}

function ExchangeView({ exchange, s }: { exchange: QaExchange; s: ReturnType<typeof qaStrings> }) {
  return (
    <div className="psqa-exchange">
      <div className="psqa-bubble psqa-q">
        <div className="psqa-role" dir="auto">{s.youAsked}</div>
        <div dir="auto">{exchange.question}</div>
        {exchange.askedAt ? <div className="psqa-time">{formatDateTime(exchange.askedAt)}</div> : null}
      </div>
      {exchange.reply ? (
        <div className="psqa-bubble psqa-a">
          <div className="psqa-role">
            <span dir="auto">{exchange.reply.byline}</span>
            {exchange.reply.verified ? (
              <span className="psqa-verified">
                <CheckIcon className="ps-ic sm" /> {s.verified}
              </span>
            ) : null}
          </div>
          <div dir="auto">{exchange.reply.text}</div>
          {exchange.reply.repliedAt ? <div className="psqa-time">{formatDateTime(exchange.reply.repliedAt)}</div> : null}
        </div>
      ) : exchange.status === "awaiting" ? (
        <div className="psqa-await" dir="auto">{s.awaiting}</div>
      ) : (
        <div className="psqa-await" dir="auto">{s.closed}</div>
      )}
    </div>
  );
}

function StatusScreen({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="patient-surface">
      <div className="ps-shell">
        <div className="ps-status">
          <div className="ps-status-icon">
            <LockIcon />
          </div>
          <h1>{title}</h1>
          <p>{body}</p>
          {action}
        </div>
      </div>
    </div>
  );
}

// --- helpers ---------------------------------------------------------------

function firstName(name: string | null): string {
  if (!name) return "";
  return name.trim().split(/\s+/)[0] || "";
}

function initials(name: string | null | undefined): string {
  if (!name) return "·";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "·";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "·";
}

function formatDateTime(iso: string): string {
  return formatDate(iso, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

// --- icons (inline, no asset deps) -----------------------------------------

function CheckIcon({ className = "ps-ic" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}

function LockIcon({ className = "ps-ic lg" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}
