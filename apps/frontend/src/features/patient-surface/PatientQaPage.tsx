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
      document.title = "Memara";
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

function QaView({ token, payload, onPosted }: { token: string; payload: QaThreadPayload; onPosted: () => void }) {
  const greetingName = firstName(payload.patientName);
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
      setPostError("Couldn’t send your question. Please try again.");
      return;
    }
    setDraft("");
    setJustSent(true);
    onPosted();
  };

  return (
    <div className="patient-surface">
      <div className="ps-shell">
        <header className="ps-head">
          <div className="ps-clinic">
            <div className="ps-logo">{initials(payload.clinic?.name)}</div>
            <div>
              <div className="ps-clinic-name" dir="auto">
                {payload.clinic?.name || "Your clinic"}
              </div>
              <div className="ps-clinic-sub">Questions &amp; answers</div>
            </div>
          </div>
          {greetingName ? (
            <div className="ps-hi" dir="auto">
              {greetingName} 👋
            </div>
          ) : null}
        </header>

        <main className="ps-body">
          <section className="ps-sec" aria-label="Your conversation">
            <h2>Your conversation</h2>
            {payload.exchanges.length ? (
              <div className="psqa-thread">
                {payload.exchanges.map((exchange) => (
                  <ExchangeView key={exchange.id} exchange={exchange} />
                ))}
              </div>
            ) : (
              <p className="psqa-empty">No questions yet. Ask your care team below.</p>
            )}
          </section>

          {/* Composer pinned at the bottom — newest at the end, like a chat thread. */}
          <section className="ps-sec psqa-ask" aria-label="Ask a question">
            <h2>Ask your care team</h2>
            <p className="psqa-intro">
              Have a question between visits? Send it here and your clinic will reply. Replies are reviewed by your
              clinician before you see them.
            </p>
            <div className="psqa-composer">
              <textarea
                dir="auto"
                value={draft}
                placeholder="e.g. Is the swelling on my forehead normal?"
                onChange={(event) => {
                  setDraft(event.target.value);
                  setJustSent(false);
                }}
                aria-label="Your question"
              />
              <button type="button" className="psqa-send" onClick={submit} disabled={!draft.trim() || posting}>
                {posting ? "Sending…" : "Send question"}
              </button>
              {justSent ? <div className="psqa-sent">Sent — your clinic will reply here.</div> : null}
              {postError ? (
                <div className="psqa-sent" style={{ color: "#b42318", background: "#fef3f2", borderColor: "#fecdc9" }}>
                  {postError}
                </div>
              ) : null}
            </div>
          </section>
        </main>

        <footer className="ps-foot">
          <LockIcon className="ps-ic sm" />
          <span>Private link{greetingName ? ` for ${greetingName}` : ""} · only your own messages appear here.</span>
        </footer>
      </div>
    </div>
  );
}

function ExchangeView({ exchange }: { exchange: QaExchange }) {
  return (
    <div className="psqa-exchange">
      <div className="psqa-bubble psqa-q">
        <div className="psqa-role">You asked</div>
        <div dir="auto">{exchange.question}</div>
        {exchange.askedAt ? <div className="psqa-time">{formatDateTime(exchange.askedAt)}</div> : null}
      </div>
      {exchange.reply ? (
        <div className="psqa-bubble psqa-a">
          <div className="psqa-role">
            <span dir="auto">{exchange.reply.byline}</span>
            {exchange.reply.verified ? (
              <span className="psqa-verified">
                <CheckIcon className="ps-ic sm" /> verified by your clinic
              </span>
            ) : null}
          </div>
          <div dir="auto">{exchange.reply.text}</div>
          {exchange.reply.repliedAt ? <div className="psqa-time">{formatDateTime(exchange.reply.repliedAt)}</div> : null}
        </div>
      ) : exchange.status === "awaiting" ? (
        <div className="psqa-await">Waiting for your clinic to reply…</div>
      ) : (
        <div className="psqa-await">This question was closed by your clinic.</div>
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
