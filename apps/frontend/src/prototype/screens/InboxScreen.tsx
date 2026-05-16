import React from "react";
import { AppHeader, CaptureItemCard, EmptyState, SessionCard } from "../shared";
import { Badge, Button, Card, Input, Skeleton, Tabs } from "../ui";
import type { CaptureSession } from "../types";

type QueueFilter = "all" | "today" | "photos" | "voice";

export function InboxScreen({
  sessions,
  selectedSessionId,
  onSelectSession,
  onMatch,
  onBack,
}: {
  sessions: CaptureSession[];
  selectedSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onMatch: () => void;
  onBack: () => void;
}) {
  const [filter, setFilter] = React.useState<QueueFilter>("all");
  const [query, setQuery] = React.useState("");
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const unassigned = sessions.filter((session) => session.status === "unassigned");
  const filtered = unassigned.filter((session) => {
    const queryMatch = `${session.label} ${session.summary}`.toLowerCase().includes(query.toLowerCase());
    const filterMatch =
      filter === "all" ||
      (filter === "today" && session.dateLabel === "Today") ||
      (filter === "photos" && session.items.some((item) => item.type === "photo")) ||
      (filter === "voice" && session.items.some((item) => item.type === "voice"));
    return queryMatch && filterMatch;
  });
  const selected = unassigned.find((session) => session.id === selectedSessionId) ?? filtered[0];

  React.useEffect(() => {
    if (selected && selected.id !== selectedSessionId) onSelectSession(selected.id);
  }, [selected, selectedSessionId, onSelectSession]);

  const select = (sessionId: string) => {
    onSelectSession(sessionId);
    setLoadingPreview(true);
    window.setTimeout(() => setLoadingPreview(false), 350);
  };

  return (
    <main className="page">
      <AppHeader onToday={onBack} subtitle="Review and match when there is time." title="Unassigned sessions" />
      <section className="grid inbox-grid">
        <Card>
          <p className="eyebrow">Queue controls</p>
          <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search sessions" value={query} />
          <Tabs
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "today", label: "Today" },
              { value: "photos", label: "With photos" },
              { value: "voice", label: "Voice only" },
            ]}
            value={filter}
          />
        </Card>
        <Card>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Unassigned sessions</p>
              <h2>Select one to preview</h2>
            </div>
            <Badge tone="blue">{filtered.length}</Badge>
          </div>
          <div className="stack">
            {filtered.length ? (
              filtered.map((session) => (
                <SessionCard
                  action={
                    <Button onClick={onMatch} size="sm">
                      Match
                    </Button>
                  }
                  key={session.id}
                  onClick={() => select(session.id)}
                  selected={selected?.id === session.id}
                  session={session}
                />
              ))
            ) : (
              <EmptyState body="Try another filter or start a new capture from Today." title="No sessions in this view" />
            )}
          </div>
        </Card>
        <Card>
          <p className="eyebrow">Preview</p>
          {loadingPreview ? (
            <div className="stack">
              <Skeleton className="h-16" />
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          ) : selected ? (
            <>
              <h2>{selected.label}</h2>
              <p>{selected.summary}</p>
              <div className="stack">
                {selected.items.slice(0, 3).map((item) => (
                  <CaptureItemCard compact item={item} key={item.id} />
                ))}
              </div>
              <Button onClick={onMatch}>Find patient to match</Button>
            </>
          ) : (
            <EmptyState body="There are no unassigned sessions waiting right now." title="Queue is clear" />
          )}
        </Card>
      </section>
    </main>
  );
}
