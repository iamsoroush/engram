import React from "react";
import type { AiUsageState, ApiFetch, AuthSession, CaptureDraft, SyncHealth } from "../../domain/appTypes";
import type { Screen } from "../../domain/types";
import { Badge, Button, Card, Skeleton } from "../../shared/ui/primitives";
import { Shell } from "../shell/Shell";
import { AddPhotoSheet, AudioDialog, TextCaptureSheet } from "../capture/components/CaptureDialogs";
import { standardizeCaptureDraft } from "../capture/audio";
import { RegisterPatientForm } from "../aesthetics/RegisterPatientForm";
import { checkDuplicatePatient, createPatient } from "../../services/api/client";
import { TherapyCaptureScreen } from "./components/TherapyCaptureScreen";
import { AiUsageCard } from "../aiUsage/AiUsageCard";
import { AiUsageNotice } from "../aiUsage/AiUsageNotice";
import {
  getTherapyClient,
  getTherapySession,
  listTherapyClients,
  listTherapySessionCaptures,
  setTherapyFormat,
  setTherapyReflections,
  setTherapyRelease,
  setTherapyRisk,
  uploadTherapyCapture,
  type TherapyCaptureNote,
  type TherapyClient,
  type TherapyClientDetail,
  type TherapyFormat,
  type TherapySession,
} from "./therapyApi";

type View = "clients" | "client" | "session" | "settings" | "profile";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "C"
  );
}

function relativeVisit(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days <= 0) return "Last session today";
  if (days === 1) return "Last session yesterday";
  if (days < 7) return `Last session ${days} days ago`;
  return `Last session ${date.toLocaleDateString()}`;
}

/**
 * Self-contained therapy vertical app, rendered by App.tsx when tenant.vertical === "therapy".
 * Reuses the aesthetics Shell (topbar, nav, the Note/Audio/Photo capture footer) and the shared
 * capture dialogs + patient form, and mirrors the clinical-memory / patient-detail / capture-screen
 * markup, so therapy shares the aesthetics design system rather than a parallel one.
 */
export function TherapyApp({ auth, apiFetch, onLogout, aiUsage, onRefreshAiUsage }: { auth: AuthSession; apiFetch: ApiFetch; onLogout: () => void; aiUsage?: AiUsageState | null; onRefreshAiUsage?: () => void }) {
  const [view, setView] = React.useState<View>("clients");
  const [clients, setClients] = React.useState<TherapyClient[] | null>(null);
  const [clientDetail, setClientDetail] = React.useState<TherapyClientDetail | null>(null);
  const [clientName, setClientName] = React.useState("");
  const [selectedClientId, setSelectedClientId] = React.useState<string | null>(null);
  const [session, setSession] = React.useState<TherapySession | null>(null);
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(null);
  const [captures, setCaptures] = React.useState<TherapyCaptureNote[]>([]);
  const [synthesizing, setSynthesizing] = React.useState(false);
  const [error, setError] = React.useState("");
  const [captureKind, setCaptureKind] = React.useState<CaptureDraft["kind"] | null>(null);
  // True while a session is open or being composed — so the "Active Session" nav shows the
  // workspace (or a clear empty state) rather than silently doing nothing.
  const [composing, setComposing] = React.useState(false);
  const [newClientOpen, setNewClientOpen] = React.useState(false);
  const [creatingClient, setCreatingClient] = React.useState(false);
  const [online, setOnline] = React.useState(typeof navigator === "undefined" ? true : navigator.onLine);

  React.useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  const syncHealth: SyncHealth = { online, backendReachable: online, pendingCaptures: 0, pendingOperations: 0, syncing: false };

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
    setComposing(false);
    setView("client");
    await loadClientDetail(client.patientId);
  }, [loadClientDetail]);

  const refreshSession = React.useCallback(async (sessionId: string) => {
    const [nextSession, nextCaptures] = await Promise.all([
      getTherapySession(apiFetch, sessionId),
      listTherapySessionCaptures(apiFetch, sessionId).catch(() => [] as TherapyCaptureNote[]),
    ]);
    setSession(nextSession);
    setCaptures(nextCaptures);
    return nextSession;
  }, [apiFetch]);

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
    setComposing(true);
    setView("session");
  }, []);

  const openSession = React.useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setSession(null);
    setCaptures([]);
    setComposing(true);
    setView("session");
    await refreshSession(sessionId);
  }, [refreshSession]);

  // Capture-first: the Shell footer (Note / Audio / Photo) opens a dialog; the saved draft uploads
  // into the active session (or starts one for the selected client). Audio is standardized to WAV.
  const handleCaptureSave = React.useCallback(async (draft: CaptureDraft) => {
    setCaptureKind(null);
    setError("");
    try {
      const prepared = await standardizeCaptureDraft(draft);
      const { sessionId } = await uploadTherapyCapture(apiFetch, {
        draft: prepared,
        sessionId: activeSessionId || undefined,
        patientId: !activeSessionId && selectedClientId ? selectedClientId : undefined,
      });
      if (sessionId) {
        setActiveSessionId(sessionId);
        setView("session");
        await pollUntilSettled(sessionId);
      }
    } catch {
      setError(draft.kind === "audio" ? "Audio conversion or upload failed." : "Could not save the capture.");
    }
  }, [apiFetch, activeSessionId, selectedClientId, pollUntilSettled]);

  const therapyAction = React.useCallback(async (run: (sessionId: string) => Promise<TherapySession>) => {
    if (!activeSessionId) return;
    try {
      setSession(await run(activeSessionId));
      setCaptures(await listTherapySessionCaptures(apiFetch, activeSessionId).catch(() => captures));
    } catch {
      setError("Could not update the session.");
    }
  }, [activeSessionId, apiFetch, captures]);

  const createClient = React.useCallback(async (values: { displayName: string; nationalId?: string; phone?: string; dateOfBirth?: string; sex?: string; notes?: string }) => {
    setCreatingClient(true);
    try {
      await createPatient(apiFetch, values);
      setNewClientOpen(false);
      await loadClients();
    } catch {
      setError("Could not create the client.");
    } finally {
      setCreatingClient(false);
    }
  }, [apiFetch, loadClients]);

  const screen: Screen = view === "session" ? "active-session" : view === "settings" ? "settings" : view === "profile" ? "profile" : "patients";

  const onNavigate = React.useCallback((target: Screen) => {
    if (target === "active-session") {
      setView("session"); // shows the workspace, or a clear empty state when nothing is in progress
    } else if (target === "settings" || target === "profile") {
      setView(target);
    } else {
      setComposing(false);
      setView("clients"); // patients + search both land on the caseload
    }
  }, []);

  const captureContextLabel = view === "session" && clientName ? `${clientName} · Session` : "New session";

  return (
    <Shell
      auth={auth}
      screen={screen}
      syncHealth={syncHealth}
      onNavigate={onNavigate}
      onCapture={(kind) => setCaptureKind(kind)}
      onLogout={onLogout}
      captureContextLabel={captureContextLabel}
    >
      <div className="therapy-page">
        {error ? <div className="alert alert-red">{error}</div> : null}

        {/* Fair-use notice: calm, non-blocking; capture is never gated. Not on settings/profile —
            the settings usage card already conveys it there. */}
        {view !== "settings" && view !== "profile" ? <AiUsageNotice state={aiUsage ?? null} /> : null}

        {view === "clients" ? (
          <section className="clinical-memory" aria-label="Clients">
            <div className="clinical-memory-hero">
              <div>
                <p className="eyebrow">My caseload</p>
                <h1>Clients</h1>
                <p>You see only your own clients — therapy caseloads are private between clinicians.</p>
              </div>
              <Button onClick={() => setNewClientOpen(true)} type="button"><span aria-hidden="true">+</span> New client</Button>
            </div>
            {clients === null ? (
              <div className="clinical-list"><Card className="clinical-row clinical-row-loading"><Skeleton className="h-12" /></Card><Card className="clinical-row clinical-row-loading"><Skeleton className="h-12" /></Card></div>
            ) : clients.length === 0 ? (
              <Card className="clinical-row"><div className="clinical-row-copy"><p className="muted">No clients in your caseload yet. Add your first client.</p></div></Card>
            ) : (
              <div className="clinical-list">
                {clients.map((client) => (
                  <Card
                    key={client.patientId}
                    className="clinical-row clinical-row-selectable clinical-row-green clinical-patient-row"
                    role="button"
                    tabIndex={0}
                    onClick={() => void openClient(client)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); void openClient(client); } }}
                  >
                    <span className="clinical-avatar clinical-avatar-green">{initials(client.displayName)}</span>
                    <div className="clinical-row-copy">
                      <h3>{client.displayName}</h3>
                      {relativeVisit(client.latestVisitAt) ? <span className="patient-latest-visit">{relativeVisit(client.latestVisitAt)}</span> : null}
                      <div className="patient-memory-summary">
                        <p className="patient-memory-summary-text">
                          <span className="ai-spark" aria-hidden="true">✨</span>
                          <span className="memory-text">{client.summary || "No sessions yet."}</span>
                        </p>
                      </div>
                      <div className="patient-memory-badges">
                        <span className="patient-memory-badge">{client.sessionCount} session{client.sessionCount === 1 ? "" : "s"}</span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </section>
        ) : null}

        {view === "client" ? (
          <div className="patient-detail">
            <button className="context-back-button" onClick={() => setView("clients")} type="button"><span aria-hidden="true">‹</span> Clients</button>
            <section className="patient-detail-header">
              <span className="clinical-avatar clinical-avatar-green">{initials(clientName)}</span>
              <div className="patient-detail-heading">
                <h1>{clientName}</h1>
                <div className="patient-detail-meta">
                  <span>{(clientDetail?.client.sessionCount ?? 0)} session{(clientDetail?.client.sessionCount ?? 0) === 1 ? "" : "s"}</span>
                </div>
              </div>
            </section>
            <div className="patient-detail-actions">
              <button className="patient-detail-action" onClick={startSession} type="button"><span aria-hidden="true">+</span> New session</button>
            </div>

            <section className="patient-history-card">
              <div className="patient-history-head">
                <span className="ai-spark" aria-hidden="true">✨</span>
                <h2>Client history</h2>
              </div>
              {clientDetail === null ? (
                <div className="patient-history-skeleton" aria-hidden="true"><span /><span /><span /></div>
              ) : clientDetail.history && (clientDetail.history.snapshot || clientDetail.history.sections.length) ? (
                <div className="patient-history-body">
                  {clientDetail.history.snapshot ? <p className="patient-history-snapshot">{clientDetail.history.snapshot}</p> : null}
                  {clientDetail.history.sections.map((section) => (
                    <div className="patient-history-section" key={section.label}>
                      <h3>{section.label}</h3>
                      <p>{section.body}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="patient-history-snapshot">{clientDetail.client.summary || "No sessions captured yet. Start the first session to build this client's memory."}</p>
              )}
            </section>

            {clientDetail && clientDetail.sessions.length > 0 ? (
              <div className="patient-timeline" aria-label="Session timeline">
                <section className="patient-timeline-group">
                  <h2>Sessions</h2>
                  <div className="patient-timeline-cards">
                    {clientDetail.sessions.map((s) => (
                      <Card
                        key={s.sessionId}
                        className={`patient-timeline-card patient-timeline-card-${s.complete ? "blue" : "amber"}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => void openSession(s.sessionId)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); void openSession(s.sessionId); } }}
                      >
                        <span className="patient-timeline-card-icon" aria-hidden="true">🗓️</span>
                        <div className="patient-timeline-card-copy">
                          <div className="visit-card-title-row">
                            <h3>{s.title || "Session"}</h3>
                            <Badge tone={s.complete ? "green" : "amber"}>{s.complete ? "Complete" : s.status}</Badge>
                          </div>
                          <p>{s.summary}</p>
                        </div>
                      </Card>
                    ))}
                  </div>
                </section>
              </div>
            ) : clientDetail ? (
              <Card className="clinical-row"><div className="clinical-row-copy"><p className="muted">No sessions yet. Start the first session.</p></div></Card>
            ) : null}
          </div>
        ) : null}

        {view === "session" && !composing && !activeSessionId ? (
          <Card className="stack therapy-empty-session">
            <p className="eyebrow">Active session</p>
            <h1>No session in progress</h1>
            <p className="muted">Open a client and start a session, or capture below to begin — capture-first, assign when ready.</p>
            <Button variant="secondary" onClick={() => { setComposing(false); setView("clients"); }} type="button">Go to clients</Button>
          </Card>
        ) : null}

        {view === "session" && (composing || activeSessionId) ? (
          <TherapyCaptureScreen
            clientName={clientName || "Unassigned"}
            session={session}
            captures={captures}
            synthesizing={synthesizing}
            onSetFormat={(format: TherapyFormat) => void therapyAction((id) => setTherapyFormat(apiFetch, id, format))}
            onRelease={(released) => void therapyAction((id) => setTherapyRelease(apiFetch, id, released))}
            onFlagRisk={(input) => void therapyAction((id) => setTherapyRisk(apiFetch, id, { active: true, ...input }))}
            onClearRisk={() => void therapyAction((id) => setTherapyRisk(apiFetch, id, { active: false }))}
            onSaveReflections={(text) => void therapyAction((id) => setTherapyReflections(apiFetch, id, text))}
            onBack={() => { if (selectedClientId) { setView("client"); void loadClientDetail(selectedClientId); } else { setView("clients"); } }}
          />
        ) : null}

        {view === "settings" || view === "profile" ? (
          <>
            <Card className="stack">
              <h1>{view === "settings" ? "Settings" : "Profile"}</h1>
              <p className="muted">{auth.user.displayName || auth.user.email} · {auth.tenant.name} (therapy)</p>
              <Button variant="secondary" onClick={() => setView("clients")} type="button">Back to clients</Button>
            </Card>
            {view === "settings" ? (
              <AiUsageCard state={aiUsage ?? null} apiFetch={apiFetch} onRefresh={() => onRefreshAiUsage?.()} />
            ) : null}
          </>
        ) : null}
      </div>

      <TextCaptureSheet open={captureKind === "note"} onClose={() => setCaptureKind(null)} onSave={(draft) => handleCaptureSave(draft)} />
      <AudioDialog open={captureKind === "audio"} onClose={() => setCaptureKind(null)} onSave={(draft) => handleCaptureSave(draft)} />
      <AddPhotoSheet open={captureKind === "photo"} onClose={() => setCaptureKind(null)} onSave={(draft) => handleCaptureSave(draft)} />

      {newClientOpen ? (
        <div className="resolver-backdrop" role="presentation" onClick={() => setNewClientOpen(false)}>
          <Card className="resolver-sheet" role="dialog" aria-modal="true" aria-label="New client" onClick={(e) => e.stopPropagation()}>
            <div className="resolver-heading">
              <div>
                <p className="eyebrow">Intake</p>
                <h2>New client</h2>
                <p>Create a client in your caseload. You can capture before consent — reception/consent catches up.</p>
              </div>
            </div>
            <RegisterPatientForm
              busy={creatingClient}
              onDuplicateCheck={(body) => checkDuplicatePatient(apiFetch, body)}
              onSubmit={(values) => void createClient(values)}
              onCancel={() => setNewClientOpen(false)}
            />
          </Card>
        </div>
      ) : null}
    </Shell>
  );
}
