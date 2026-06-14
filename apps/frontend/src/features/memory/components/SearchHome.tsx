// Clinical Memory search home screen.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { SyncHealth } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Badge, Input } from "../../../shared/ui/primitives";
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
    <section className="memory-home" aria-label="Search">
      <div>
        <p className="eyebrow">Search</p>
        <h1>Find clinical memory</h1>
        <p>Search loaded patients, sessions, and captures from this device session.</p>
      </div>
      {!syncHealth.online ? <p className="clinical-offline-note"><InfoIcon /> You're offline. Patient search may be limited.</p> : null}
      <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search patients, sessions, captures" value={query} />
      <div className="memory-section">
        <div className="section-heading">
          <div>
            <h2>Results</h2>
            <p>Matches include local session and capture text already loaded in the app.</p>
          </div>
          <Badge tone={results.length ? "blue" : "neutral"}>{results.length}</Badge>
        </div>
        <div className="stack">
          {results.map((session) => (
            <button className="search-result-card" key={session.id} onClick={() => onOpenSession(session.id)} type="button">
              <div>
                <strong>{session.label}</strong>
                <p>{session.summary}</p>
                <span>{session.patientName || session.reviewReason || "Unassigned session"}</span>
              </div>
              <SessionStatusBadge status={session.status} />
            </button>
          ))}
          {query && results.length === 0 ? <p>No matching loaded memory.</p> : null}
          {!query ? <p>Enter a term to search the currently loaded clinical memory.</p> : null}
        </div>
      </div>
    </section>
  );
}
