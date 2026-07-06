import React from "react";
import { Badge, Button, Card, Textarea } from "../../../shared/ui/primitives";
import type { TherapyCaptureNote, TherapyFormat, TherapySession } from "../therapyApi";

const FORMAT_LABELS: Record<TherapyFormat, string> = { dap: "DAP", soap: "SOAP", birp: "BIRP" };

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

/**
 * Therapy session workspace — mirrors the aesthetics capture screen layout (back button →
 * active-session header → client context card → the report card with a Captures | Summary
 * segmented control). Capture itself happens through the shared Shell footer (Note / Audio /
 * Photo), exactly as in aesthetics; this screen renders the feed + the two-plane synthesis.
 */
export function TherapyCaptureScreen({
  clientName,
  session,
  captures,
  synthesizing,
  onSetFormat,
  onRelease,
  onFlagRisk,
  onClearRisk,
  onSaveReflections,
  onBack,
}: {
  clientName: string;
  session: TherapySession | null;
  captures: TherapyCaptureNote[];
  synthesizing: boolean;
  onSetFormat: (format: TherapyFormat) => void;
  onRelease: (released: boolean) => void;
  onFlagRisk: (input: { level: string; note: string }) => void;
  onClearRisk: () => void;
  onSaveReflections: (text: string) => void;
  onBack: () => void;
}) {
  const [view, setView] = React.useState<"captures" | "summary">("captures");
  const [plane, setPlane] = React.useState<"shareable" | "private">("shareable");
  const [riskOpen, setRiskOpen] = React.useState(false);
  const [riskLevel, setRiskLevel] = React.useState("moderate");
  const [riskNote, setRiskNote] = React.useState("");

  const therapy = session?.therapy || null;
  const reflectionsServer = therapy?.planes.private.reflections || "";
  const [reflections, setReflections] = React.useState(reflectionsServer);
  React.useEffect(() => {
    setReflections(reflectionsServer);
  }, [reflectionsServer, session?.id]);

  const risk = therapy?.risk;
  const release = therapy?.release;
  const statusChip = session?.complete
    ? { tone: "checked", label: "Complete" }
    : synthesizing
      ? { tone: "amber", label: "Synthesizing…" }
      : { tone: "neutral", label: "Draft" };

  return (
    <section className="capture-current session-workspace" aria-label="Therapy session workspace">
      <button className="context-back-button" onClick={onBack} type="button">
        <span aria-hidden="true">‹</span> {clientName}
      </button>

      <div className="active-session-summary light">
        <div className="session-summary-copy">
          <div className="session-summary-heading">
            <span className="session-live-dot" aria-hidden="true" />
            <h1>Session</h1>
            <span className={`status-chip ${statusChip.tone}`}><span aria-hidden="true" />{statusChip.label}</span>
          </div>
          <p>Capturing for {clientName} · private by default</p>
        </div>
      </div>

      <Card className="patient-context-card assigned">
        <span className="patient-context-avatar" aria-hidden="true">🛋️</span>
        <div className="patient-context-copy">
          <strong>{clientName}</strong>
          <p>Confidential 1:1 — this client is in your caseload only</p>
        </div>
      </Card>

      <p className="therapy-privacy-banner">🔒 Everything you capture is private by default. Nothing reaches the client until you explicitly release it.</p>

      {/* Risk — assisted suggestion vs. clinician-confirmed (top of the workspace, unmissable). */}
      {risk?.active ? (
        <div className="therapy-risk-banner active">
          <div>
            <strong>Safety flag active{risk.level ? ` · ${risk.level}` : ""}</strong>
            {risk.note ? <p>{risk.note}</p> : null}
            <span className="muted">Confirmed by {risk.confirmedBy || "clinician"}{risk.confirmedAt ? ` · ${formatDate(risk.confirmedAt)}` : ""}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={onClearRisk} type="button">Clear</Button>
        </div>
      ) : risk?.suggested ? (
        <div className="therapy-risk-banner suggested">
          <div>
            <strong>⚠ Possible risk detected</strong>
            {risk.cue ? <p>“{risk.cue}”</p> : null}
            <span className="muted">Assisted detection — review and confirm if appropriate.</span>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setRiskOpen(true)} type="button">Flag risk</Button>
        </div>
      ) : null}

      <Card className="workspace-report-card">
        <div className="report-heading">
          <div className="report-title-lockup">
            <span className="report-title-icon" aria-hidden="true">✨</span>
            <h2>Session summary</h2>
            <span className="report-tier-badge pro">Therapy</span>
          </div>
        </div>
        <div className="report-toolbar">
          <div className="report-toolbar-actions">
            <div className="report-view-switch" aria-label="Session view">
              <button className={view === "captures" ? "active" : ""} onClick={() => setView("captures")} type="button">Captures</button>
              <button className={view === "summary" ? "active" : ""} onClick={() => setView("summary")} type="button">Summary</button>
            </div>
          </div>
        </div>

        <div className="workspace-report-body">
          {view === "captures" ? (
            <div className="stack">
              {/* Session so far — live running synthesis (B2a). */}
              <div className="therapy-sofar">
                <div className="therapy-sofar-head">
                  <span className="ai-spark" aria-hidden="true">✨</span>
                  <strong>Session so far</strong>
                  {synthesizing ? <span className="memory-updating-pill">updating…</span> : null}
                </div>
                <p className="therapy-sofar-line">{therapy?.sessionSoFar.line || "No captures yet — use the buttons below to add a note."}</p>
                {therapy?.sessionSoFar.narrative ? <p className="muted">{therapy.sessionSoFar.narrative}</p> : null}
                {therapy && therapy.sessionSoFar.threadCoverage.length > 0 ? (
                  <div className="therapy-chip-row">
                    {therapy.sessionSoFar.threadCoverage.map((thread) => (
                      <span key={thread.label} className={`therapy-thread-chip ${thread.covered ? "covered" : ""}`}>
                        {thread.covered ? "✓" : "◦"} {thread.label}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>

              {captures.length === 0 ? (
                <p className="therapy-empty">No captures yet. Add a <strong>Note</strong> (or Audio / Photo) from the bar below — shorthand is fine, it gets cleaned into clinical prose.</p>
              ) : (
                captures.map((capture) => (
                  <article key={capture.id} className="therapy-capture">
                    <div className="therapy-capture-head">
                      {capture.type === "audio" ? <Badge tone="blue">audio recap · private</Badge> : capture.type === "photo" ? <Badge tone="neutral">photo</Badge> : <Badge tone="neutral">✨ decorated note</Badge>}
                      {capture.capturedAt ? <span className="muted">{formatDate(capture.capturedAt)}</span> : null}
                    </div>
                    <p>{capture.text || <span className="muted">Processing…</span>}</p>
                    {capture.raw && capture.raw !== capture.text ? <p className="therapy-capture-raw">you typed: {capture.raw}</p> : null}
                  </article>
                ))
              )}
            </div>
          ) : (
            <div className="stack">
              <div className="report-view-switch therapy-plane-switch" aria-label="Plane">
                <button className={plane === "shareable" ? "active" : ""} onClick={() => setPlane("shareable")} type="button">Shareable</button>
                <button className={plane === "private" ? "active" : ""} onClick={() => setPlane("private")} type="button">Private</button>
              </div>

              {plane === "shareable" ? (
                <div className="stack">
                  <div className="therapy-format-row">
                    <div className="therapy-format-group" aria-label="Note format">
                      {(therapy?.availableFormats || ["dap", "soap", "birp"]).map((f) => (
                        <button key={f} className={`therapy-format-btn ${therapy?.format === f ? "active" : ""}`} onClick={() => onSetFormat(f)} type="button">
                          {FORMAT_LABELS[f]}
                        </button>
                      ))}
                    </div>
                    {release?.released ? (
                      <span className="therapy-released">
                        <Badge tone="green">Released {formatDate(release.releasedAt)}</Badge>
                        <Button variant="ghost" size="sm" onClick={() => onRelease(false)} type="button">Withdraw</Button>
                      </span>
                    ) : (
                      <Button size="sm" onClick={() => onRelease(true)} disabled={!therapy} type="button">Release to client</Button>
                    )}
                  </div>
                  {therapy && therapy.planes.shareable.sections.some((s) => s.body) ? (
                    therapy.planes.shareable.sections.map((section) => (
                      <div key={section.id} className="therapy-section">
                        <h3>{section.title}</h3>
                        <p>{section.body || "—"}</p>
                      </div>
                    ))
                  ) : (
                    <p className="therapy-empty">Add a note to build the shareable progress note.</p>
                  )}
                  <p className="muted">Released summaries draw only from this shareable plane — never the private layer.</p>
                </div>
              ) : (
                <div className="stack">
                  <div className="therapy-section">
                    <h3>Reflections <span className="muted">(therapist-only)</span></h3>
                    <Textarea rows={4} placeholder="Hypotheses, process notes — never shared with the client or exported." value={reflections} onChange={(event) => setReflections(event.target.value)} />
                    <div className="therapy-format-row">
                      <span className="muted">🔒 Private plane</span>
                      <Button variant="secondary" size="sm" onClick={() => onSaveReflections(reflections)} type="button">Save reflections</Button>
                    </div>
                  </div>
                  <div className="therapy-section">
                    <h3>Audio recap transcript <span className="muted">(most-private)</span></h3>
                    {therapy && therapy.planes.private.audioTranscripts.length > 0 ? (
                      therapy.planes.private.audioTranscripts.map((entry) => <p key={entry.captureId} className="muted">{entry.text}</p>)
                    ) : (
                      <p className="muted">No audio recap for this session.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {riskOpen ? (
        <div className="resolver-backdrop" role="presentation" onClick={() => setRiskOpen(false)}>
          <Card className="resolver-sheet therapy-risk-sheet" role="dialog" aria-modal="true" aria-label="Confirm risk flag" onClick={(e) => e.stopPropagation()}>
            <div className="resolver-heading">
              <div>
                <p className="eyebrow">Safety</p>
                <h2>Confirm risk flag</h2>
                <p>Risk is clinician-confirmed and dated — never set automatically.</p>
              </div>
            </div>
            <label className="field-label">
              Level
              <select className="select" value={riskLevel} onChange={(event) => setRiskLevel(event.target.value)}>
                <option value="low">Low</option>
                <option value="moderate">Moderate</option>
                <option value="high">High</option>
              </select>
            </label>
            <Textarea rows={2} placeholder="Safety note / plan" value={riskNote} onChange={(event) => setRiskNote(event.target.value)} />
            <div className="therapy-format-row">
              <Button variant="ghost" onClick={() => setRiskOpen(false)} type="button">Cancel</Button>
              <Button variant="danger" onClick={() => { onFlagRisk({ level: riskLevel, note: riskNote }); setRiskOpen(false); }} type="button">Confirm flag</Button>
            </div>
          </Card>
        </div>
      ) : null}
    </section>
  );
}
