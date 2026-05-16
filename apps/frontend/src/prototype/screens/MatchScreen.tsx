import React from "react";
import { AppHeader, CaptureItemCard, ConfirmActionBar, EmptyState, PatientCandidateCard } from "../shared";
import { Alert, Badge, Card, Input } from "../ui";
import type { CaptureSession, PatientCandidate } from "../types";

export function MatchScreen({
  session,
  onConfirm,
  onKeepUnassigned,
  onBack,
}: {
  session: CaptureSession;
  onConfirm: (patientId: string) => void;
  onKeepUnassigned: () => void;
  onBack: () => void;
}) {
  const [query, setQuery] = React.useState("");
  const [selectedPatientId, setSelectedPatientId] = React.useState("");
  const [confirming, setConfirming] = React.useState(false);
  const candidates: PatientCandidate[] = [];
  const selected = candidates.find((patient) => patient.id === selectedPatientId);

  const confirm = () => {
    if (!selectedPatientId) return;
    setConfirming(true);
    window.setTimeout(() => onConfirm(selectedPatientId), 500);
  };

  return (
    <main className="page">
      <AppHeader onToday={onBack} subtitle="Explicit, reversible matching." title="Match session to patient" />
      <section className="grid match-grid">
        <Card>
          <p className="eyebrow">Captured session</p>
          <h1>{session.label}</h1>
          <p>Review context before assignment. The system does not silently auto-assign.</p>
          <div className="stack">
            {session.items.map((item) => (
              <CaptureItemCard compact item={item} key={item.id} />
            ))}
          </div>
          <Alert tone="amber">Safety cue: Matching is a conscious action. Keep unassigned if unsure.</Alert>
        </Card>
        <Card>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Patient match</p>
              <h2>Search or choose likely patient</h2>
            </div>
            <Badge tone="blue">{candidates.length} candidates</Badge>
          </div>
          <Input onChange={(event) => setQuery(event.target.value)} placeholder="Search patient name, phone, or clinic ID" value={query} />
          {!query ? <p className="muted">Suggested candidates appear below. Search can narrow the list.</p> : null}
          <div className="stack">
            {candidates.length ? (
              candidates.map((candidate) => (
                <PatientCandidateCard
                  candidate={candidate}
                  key={candidate.id}
                  onClick={() => setSelectedPatientId(candidate.id)}
                  selected={selectedPatientId === candidate.id}
                />
              ))
            ) : (
              <EmptyState body="Keep the session unassigned and search again later." title="No candidate found" />
            )}
          </div>
          {selected?.duplicateWarning ? <Alert tone="amber">Possible duplicate: similar name. Confirm only after checking context.</Alert> : null}
          <ConfirmActionBar
            disabled={!selectedPatientId || confirming}
            onPrimary={confirm}
            onSecondary={onKeepUnassigned}
            primaryLabel={confirming ? "Confirming..." : `Confirm match${selected ? ` to ${selected.name}` : ""}`}
            secondaryLabel="Keep unassigned"
          />
        </Card>
      </section>
    </main>
  );
}
