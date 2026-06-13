import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { Badge, Button, Card, Skeleton } from "../../shared/ui/primitives";
import { TherapyCaptureScreen } from "./components/TherapyCaptureScreen";
import {
  getTherapyClient,
  getTherapySession,
  listTherapyClients,
  listTherapySessionCaptures,
  setTherapyFormat,
  setTherapyReflections,
  setTherapyRelease,
  setTherapyRisk,
  uploadTherapyNote,
  type TherapyCaptureNote,
  type TherapyClient,
  type TherapyClientDetail,
  type TherapyFormat,
  type TherapySession,
} from "./therapyApi";

type View = "clients" | "client" | "session";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Self-contained therapy vertical shell. Rendered by App.tsx when the tenant's vertical is
 * "therapy" (the aesthetics CaptureScreen is never touched). Holds its own view/data state and
 * talks to the backend through the shared auth-aware `apiFetch`.
 */
export function TherapyApp({ auth, apiFetch, onLogout }: { auth: AuthSession; apiFetch: ApiFetch; onLogout: () => void }) {
  const [view, setView] = React.useState<View>("clients");
  const [clients, setClients] = React.useState<TherapyClient[] | null>(null);
  const [clientDetail, setClientDetail] = React.useState<TherapyClientDetail | null>(null);
  const [clientName, setClientName] = React.useState("");
  const [selectedClientId, setSelectedClientId] = React.useState<string | null>(null);
  const [session, setSession] = React.useState<TherapySession | null>(null);
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(null);
  const [captures, setCaptures] = React.useState<TherapyCaptureNote[]>([]);
  const [saving, setSaving] = React.useState(false);
  const [synthesizing, setSynthesizing] = React.useState(false);
  const [error, setError] = React.useState("");

  const clinician = auth.user.displayName || auth.user.email;

  const loadClients = React.useCallback(async () => {
    setClients(null);
    try {
      setClients(await listTherapyClients(apiFetch));
    } catch {
      setClients([]);
      setError("Could not load your caseload.");
    }
  }, [apiFetch]);

  React.useEffect(() => {
    void loadClients();
  }, [loadClients]);

  const loadClientDetail = React.useCallback(async (patientId: string) => {
    try {
      setClientDetail(await getTherapyClient(apiFetch, patientId));
    } catch {
      setError("Could not open client.");
    }
  }, [apiFetch]);

  const openClient = React.useCallback(async (client: TherapyClient) => {
    setSelectedClientId(client.patientId);
    setClientName(client.displayName);
    setClientDetail(null);
    setView("client");
    await loadClientDetail(client.patientId);
  }, [loadClientDetail]);

  const backToClient = React.useCallback(() => {
    if (!selectedClientId) {
      setView("clients");
      return;
    }
    setView("client");
    void loadClientDetail(selectedClientId); // surface a newly-created session in the list
  }, [selectedClientId, loadClientDetail]);

  const refreshSession = React.useCallback(async (sessionId: string) => {
    const [nextSession, nextCaptures] = await Promise.all([
      getTherapySession(apiFetch, sessionId),
      listTherapySessionCaptures(apiFetch, sessionId).catch(() => [] as TherapyCaptureNote[]),
    ]);
    setSession(nextSession);
    setCaptures(nextCaptures);
    return nextSession;
  }, [apiFetch]);

  // Poll until the capture chain settles and the synthesis is current (mirrors the aesthetics
  // memory-refresh ladder — capture processing is async).
  const pollUntilSettled = React.useCallback(async (sessionId: string) => {
    setSynthesizing(true);
    try {
      for (let attempt = 0; attempt < 18; attempt += 1) {
        const next = await refreshSession(sessionId);
        if (next.status !== "processing" && next.therapy) return;
        await sleep(1200);
      }
    } finally {
      setSynthesizing(false);
    }
  }, [refreshSession]);

  const startSession = React.useCallback(() => {
    setActiveSessionId(null);
    setSession(null);
    setCaptures([]);
    setView("session");
  }, []);

  const openSession = React.useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setSession(null);
    setCaptures([]);
    setView("session");
    await refreshSession(sessionId);
  }, [refreshSession]);

  const addNote = React.useCallback(async (text: string) => {
    setSaving(true);
    setError("");
    try {
      const { sessionId } = await uploadTherapyNote(apiFetch, {
        text,
        sessionId: activeSessionId || undefined,
        patientId: !activeSessionId && selectedClientId ? selectedClientId : undefined,
      });
      if (sessionId) setActiveSessionId(sessionId);
      if (sessionId) await pollUntilSettled(sessionId);
    } catch {
      setError("Could not save the note. Try again.");
    } finally {
      setSaving(false);
    }
  }, [apiFetch, activeSessionId, selectedClientId, pollUntilSettled]);

  const therapyAction = React.useCallback(async (run: (sessionId: string) => Promise<TherapySession>) => {
    if (!activeSessionId) return;
    try {
      const next = await run(activeSessionId);
      setSession(next);
      setCaptures(await listTherapySessionCaptures(apiFetch, activeSessionId).catch(() => captures));
    } catch {
      setError("Could not update the session.");
    }
  }, [activeSessionId, apiFetch, captures]);

  const renderClients = () => (
    <div className="stack">
      <div className="section-heading">
        <div>
          <p className="eyebrow">My caseload</p>
          <h1>Clients</h1>
          <p className="muted">You see only your own clients — therapy caseloads are private between clinicians.</p>
        </div>
      </div>
      {clients === null ? (
        <Card className="stack"><Skeleton className="h-12" /><Skeleton className="h-12" /></Card>
      ) : clients.length === 0 ? (
        <Card><p className="muted">No clients in your caseload yet.</p></Card>
      ) : (
        clients.map((client) => (
          <Card key={client.patientId} className="therapy-client-row" onClick={() => void openClient(client)} role="button" tabIndex={0}>
            <div>
              <strong>{client.displayName}</strong>
              <p className="muted">{client.summary || "No sessions yet."}</p>
            </div>
            <Badge tone="neutral">{client.sessionCount} session{client.sessionCount === 1 ? "" : "s"}</Badge>
          </Card>
        ))
      )}
    </div>
  );

  const renderClient = () => (
    <div className="stack">
      <div className="section-heading">
        <div>
          <button className="link-button" onClick={() => setView("clients")} type="button">‹ Clients</button>
          <h1>{clientName}</h1>
          {clientDetail?.history?.snapshot ? <p className="muted">{clientDetail.history.snapshot}</p> : null}
        </div>
        <Button onClick={startSession} type="button">New session</Button>
      </div>
      {clientDetail === null ? (
        <Card className="stack"><Skeleton className="h-12" /></Card>
      ) : clientDetail.sessions.length === 0 ? (
        <Card><p className="muted">No sessions yet. Start the first session.</p></Card>
      ) : (
        clientDetail.sessions.map((s) => (
          <Card key={s.sessionId} className="therapy-client-row" onClick={() => void openSession(s.sessionId)} role="button" tabIndex={0}>
            <div>
              <strong>{s.title || "Session"}</strong>
              <p className="muted">{s.summary}</p>
            </div>
            {s.complete ? <Badge tone="green">Complete</Badge> : <Badge tone="amber">{s.status}</Badge>}
          </Card>
        ))
      )}
    </div>
  );

  return (
    <div className="therapy-app">
      <header className="topbar">
        <div className="topbar-brand">
          <strong>Memara</strong>
          <Badge tone="green">Therapy</Badge>
        </div>
        <div className="topbar-actions">
          <span className="muted">{clinician}</span>
          <Button variant="ghost" onClick={onLogout} type="button">Logout</Button>
        </div>
      </header>
      <main className="therapy-main">
        {error ? <div className="alert alert-red">{error}</div> : null}
        {view === "clients" ? renderClients() : null}
        {view === "client" ? renderClient() : null}
        {view === "session" ? (
          <TherapyCaptureScreen
            clientName={clientName}
            session={session}
            captures={captures}
            saving={saving}
            synthesizing={synthesizing}
            onAddNote={addNote}
            onSetFormat={(format: TherapyFormat) => void therapyAction((id) => setTherapyFormat(apiFetch, id, format))}
            onRelease={(released) => void therapyAction((id) => setTherapyRelease(apiFetch, id, released))}
            onFlagRisk={(input) => void therapyAction((id) => setTherapyRisk(apiFetch, id, { active: true, ...input }))}
            onClearRisk={() => void therapyAction((id) => setTherapyRisk(apiFetch, id, { active: false }))}
            onSaveReflections={(text) => void therapyAction((id) => setTherapyReflections(apiFetch, id, text))}
            onBack={backToClient}
          />
        ) : null}
      </main>
    </div>
  );
}
