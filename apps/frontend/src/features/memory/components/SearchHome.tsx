// Clinical Memory search home screen.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { SyncHealth } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Badge, Input } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
import { SessionStatusBadge } from "../../capture/components/StatusBadges";
import { InfoIcon } from "./MemoryIcons";

export function SearchHome({
  sessions,
  syncHealth,
  onOpenSession,
}: {
  sessions: CaptureSession[];
  syncHealth: SyncHealth;
  onOpenSession: (sessionId: string) => void;
}) {
  const t = useT();
  const [query, setQuery] = React.useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const results = normalizedQuery
    ? sessions.filter((session) =>
        [
          session.label,
          session.summary,
          session.patientName,
          session.reviewReason,
          ...session.items.flatMap((item) => [item.title, item.detail, item.sourceName, item.patientName]),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery),
      )
    : [];

  return (
    <section className="memory-home" aria-label={t("search.sectionAria")}>
      <div>
        <p className="eyebrow">{t("search.eyebrow")}</p>
        <h1>{t("search.title")}</h1>
        <p>{t("search.subtitle")}</p>
      </div>
      {!syncHealth.online ? <p className="clinical-offline-note"><InfoIcon /> {t("search.offlineNote")}</p> : null}
      <Input onChange={(event) => setQuery(event.target.value)} placeholder={t("search.placeholder")} value={query} />
      <div className="memory-section">
        <div className="section-heading">
          <div>
            <h2>{t("search.resultsHeading")}</h2>
            <p>{t("search.resultsHint")}</p>
          </div>
          <Badge tone={results.length ? "blue" : "neutral"}>{results.length}</Badge>
        </div>
        <div className="stack">
          {results.map((session) => (
            <button className="search-result-card" key={session.id} onClick={() => onOpenSession(session.id)} type="button">
              <div>
                <strong data-content>{session.label}</strong>
                <p data-content>{session.summary}</p>
                <span data-content>{session.patientName || session.reviewReason || t("search.unassignedSession")}</span>
              </div>
              <SessionStatusBadge status={session.status} />
            </button>
          ))}
          {query && results.length === 0 ? <p>{t("search.noResults")}</p> : null}
          {!query ? <p>{t("search.emptyPrompt")}</p> : null}
        </div>
      </div>
    </section>
  );
}
