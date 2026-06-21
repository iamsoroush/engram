import React from "react";
import "./patientSurface.css";
import { fetchShare, shareMediaUrl, type ShareLoadResult, type ShareMedia, type SharePayload } from "./shareApi";
import { formatDate as formatLocaleDate } from "../../shared/lib/datetime";

/**
 * Public, read-only patient page (AES-401/403).
 *
 * Rendered for `/share/{token}` — a SEPARATE area from the clinic app, with no login and no clinic
 * state. It renders ONLY the curated snapshot the clinic chose (before/after + sections + aftercare);
 * raw clinic internals are never sent by the backend, so they cannot appear here. A revoked, expired,
 * or unknown link resolves to one indistinguishable "no longer available" state (no existence leak).
 */
export function PatientSharePage({ token }: { token: string }) {
  const [result, setResult] = React.useState<ShareLoadResult | null>(null);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    fetchShare(token, controller.signal).then((next) => {
      if (!controller.signal.aborted) setResult(next);
    });
    return () => controller.abort();
  }, [token, attempt]);

  React.useEffect(() => {
    if (result?.kind === "ok") {
      const clinic = result.payload.clinic?.name;
      document.title = clinic ? `${clinic} — your visit` : "Your visit";
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
            <p>Loading your visit…</p>
          </div>
        </div>
      </div>
    );
  }

  if (result.kind === "unavailable") {
    return (
      <StatusScreen
        icon={<LockIcon />}
        title="This link is no longer available"
        body="It may have been turned off by the clinic or reached its expiry date. If you still need your care summary, please contact your clinic for a new link."
      />
    );
  }

  if (result.kind === "error") {
    return (
      <StatusScreen
        icon={<CloudIcon />}
        title="Couldn’t load your visit"
        body="Please check your connection and try again."
        action={
          <button type="button" className="ps-retry" onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </button>
        }
      />
    );
  }

  return <ShareView token={token} payload={result.payload} />;
}

function ShareView({ token, payload }: { token: string; payload: SharePayload }) {
  const greetingName = firstName(payload.patientName);
  const metaBits = [payload.title, formatDate(payload.visitDate)].filter(Boolean) as string[];
  const aftercareLines = payload.aftercare ? splitLines(payload.aftercare.body) : [];
  // Localize the page chrome to the clinic's language so labels match the (curated) content.
  const fa = (payload.language || "").toLowerCase().startsWith("fa");
  const t = fa
    ? {
        careSummary: "خلاصهٔ مراقبت شما",
        beforeAfter: "قبل و بعد شما",
        whatWeDid: "آنچه انجام شد",
        aftercare: "دستورالعمل‌های مراقبت",
        privateLink: greetingName ? `لینک خصوصی برای ${greetingName} · این همهٔ چیزی است که با شما به اشتراک گذاشته شده.` : "لینک خصوصی · این همهٔ چیزی است که با شما به اشتراک گذاشته شده.",
        availableUntil: (date: string) => `در دسترس تا ${date}.`,
      }
    : {
        careSummary: "Your care summary",
        beforeAfter: "Your before / after",
        whatWeDid: "What we did",
        aftercare: "Aftercare instructions",
        privateLink: `Private link${greetingName ? ` for ${greetingName}` : ""} · this is everything shared with you.`,
        availableUntil: (date: string) => `Available until ${date}.`,
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
              <div className="ps-clinic-sub" dir="auto">{t.careSummary}</div>
            </div>
          </div>
          {greetingName ? (
            <div className="ps-hi" dir="auto">
              {greetingName} 👋
            </div>
          ) : null}
          {metaBits.length ? (
            <div className="ps-meta" dir="auto">
              {metaBits.join(" · ")}
            </div>
          ) : null}
        </header>

        <main className="ps-body">
          {payload.media.length ? (
            <section className="ps-sec" aria-label="Your photos">
              <h2 dir="auto">{t.beforeAfter}</h2>
              <div className={`ps-media${payload.media.length === 1 ? " one" : ""}`}>
                {payload.media.map((item) => (
                  <ShareFigure key={item.captureId} token={token} item={item} />
                ))}
              </div>
            </section>
          ) : null}

          {payload.sections.map((section, index) => (
            <section className="ps-sec" key={`${section.label}-${index}`}>
              {section.label ? <h2 dir="auto">{section.label}</h2> : null}
              <p dir="auto">{section.body}</p>
            </section>
          ))}

          {payload.treatments?.length ? (
            <section className="ps-sec" aria-label="What we did">
              <h2 dir="auto">{t.whatWeDid}</h2>
              <ul className="ps-care">
                {payload.treatments.map((line, index) => (
                  <li dir="auto" key={`${index}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {payload.aftercare && aftercareLines.length ? (
            <section className="ps-sec" aria-label="Aftercare">
              <h2 dir="auto">{payload.aftercare.name || t.aftercare}</h2>
              <ul className="ps-care">
                {aftercareLines.map((line, index) => (
                  <li key={index} dir="auto">
                    <span className="ck">
                      <CheckIcon className="ps-ic sm" />
                    </span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </main>

        <footer className="ps-foot">
          <LockIcon className="ps-ic sm" />
          <span dir="auto">
            {t.privateLink}
            {payload.expiresAt ? <span className="ps-expiry">{t.availableUntil(formatDate(payload.expiresAt))}</span> : null}
          </span>
        </footer>
      </div>
    </div>
  );
}

/** A single curated photo with caption; degrades gracefully if the image can't load. */
function ShareFigure({ token, item }: { token: string; item: ShareMedia }) {
  const [failed, setFailed] = React.useState(false);
  return (
    <figure className="ps-figure">
      <div className={`ps-img-wrap${failed ? " failed" : ""}`}>
        {failed ? (
          <span>Photo unavailable</span>
        ) : (
          <img
            src={shareMediaUrl(token, item.captureId)}
            alt={item.caption || "Visit photo"}
            loading="lazy"
            onError={() => setFailed(true)}
          />
        )}
      </div>
      {item.caption ? (
        <figcaption className="ps-cap" dir="auto">
          {item.caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

function StatusScreen({
  icon,
  title,
  body,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="patient-surface">
      <div className="ps-shell">
        <div className="ps-status">
          <div className="ps-status-icon">{icon}</div>
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
  const letters = parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "");
  return letters.join("") || "·";
}

function formatDate(iso: string | null): string {
  return formatLocaleDate(iso, { day: "numeric", month: "short", year: "numeric" });
}

/** Split aftercare body into checklist lines, tolerating bullets and blank lines. */
function splitLines(body: string): string[] {
  return body
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*[-•*]\s*/, "").trim())
    .filter(Boolean);
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

function CloudIcon({ className = "ps-ic lg" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.3A3.5 3.5 0 0 1 18 18z" />
      <path d="M12 12v5M9.5 14.5 12 17l2.5-2.5" />
    </svg>
  );
}
