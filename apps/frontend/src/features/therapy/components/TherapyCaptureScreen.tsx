import React from "react";
import { Alert, Badge, Button, Card, Tabs, Textarea } from "../../../shared/ui/primitives";
import type { TherapyCaptureNote, TherapyFormat, TherapySession } from "../therapyApi";

const FORMAT_LABELS: Record<TherapyFormat, string> = { dap: "DAP", soap: "SOAP", birp: "BIRP" };

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

export function TherapyCaptureScreen({
  clientName,
  session,
  captures,
  saving,
  synthesizing,
  onAddNote,
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
  saving: boolean;
  synthesizing: boolean;
  onAddNote: (text: string) => Promise<void>;
  onSetFormat: (format: TherapyFormat) => void;
  onRelease: (released: boolean) => void;
  onFlagRisk: (input: { level: string; note: string }) => void;
  onClearRisk: () => void;
  onSaveReflections: (text: string) => void;
  onBack: () => void;
}) {
  const [draft, setDraft] = React.useState("");
  const [plane, setPlane] = React.useState<"shareable" | "private">("shareable");
  const [reflections, setReflections] = React.useState(session?.therapy?.planes.private.reflections || "");
  const [riskOpen, setRiskOpen] = React.useState(false);
  const [riskLevel, setRiskLevel] = React.useState("moderate");
  const [riskNote, setRiskNote] = React.useState("");

  const therapy = session?.therapy || null;
  const reflectionsServer = therapy?.planes.private.reflections || "";
  React.useEffect(() => {
    setReflections(reflectionsServer);
  }, [reflectionsServer, session?.id]);

  const addNote = async () => {
    const text = draft.trim();
    if (!text || saving) return;
    setDraft("");
    await onAddNote(text);
  };

  const risk = therapy?.risk;
  const release = therapy?.release;

  return (
    <div className="therapy-screen stack">
      <div className="section-heading">
        <div>
          <button className="link-button" onClick={onBack} type="button">‹ {clientName}</button>
          <h1>Session</h1>
          <p className="muted">Capturing for {clientName} · private by default</p>
        </div>
        {session?.complete ? <Badge tone="green">Complete</Badge> : synthesizing ? <Badge tone="amber">Synthesizing…</Badge> : <Badge tone="neutral">Draft</Badge>}
      </div>

      {/* Risk — assisted detection (suggested) vs. clinician-confirmed (active). */}
      {risk?.active ? (
        <Alert tone="red">
          <strong>Safety flag active{risk.level ? ` · ${risk.level}` : ""}</strong>
          {risk.note ? <div>{risk.note}</div> : null}
          <div className="muted">Confirmed by {risk.confirmedBy || "clinician"}{risk.confirmedAt ? ` · ${formatDate(risk.confirmedAt)}` : ""}</div>
          <Button variant="ghost" onClick={onClearRisk} type="button">Clear flag</Button>
        </Alert>
      ) : risk?.suggested ? (
        <Alert tone="amber">
          <strong>⚠ Possible risk detected</strong>
          {risk.cue ? <div>“{risk.cue}”</div> : null}
          <div className="muted">Assisted detection only — review and confirm if appropriate.</div>
          <Button variant="secondary" onClick={() => setRiskOpen(true)} type="button">Flag risk</Button>
        </Alert>
      ) : null}

      {/* Session so far — a live running synthesis + thread coverage (B2a). */}
      <Card className="stack">
        <div className="section-heading">
          <h2>✨ Session so far</h2>
          {synthesizing ? <Badge tone="amber">updating…</Badge> : null}
        </div>
        <p><strong>{therapy?.sessionSoFar.line || "No captures yet."}</strong></p>
        {therapy?.sessionSoFar.narrative ? <p className="muted">{therapy.sessionSoFar.narrative}</p> : null}
        {therapy && therapy.sessionSoFar.threadCoverage.length > 0 ? (
          <div className="chip-row">
            {therapy.sessionSoFar.threadCoverage.map((thread) => (
              <Badge key={thread.label} tone={thread.covered ? "green" : "neutral"}>
                {thread.covered ? "✓" : "◦"} {thread.label}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>

      {/* Note-first capture (B2). */}
      <Card className="stack">
        <h2>Add a note</h2>
        <Textarea
          rows={3}
          placeholder="Type a quick note — shorthand is fine, it gets cleaned into clinical prose."
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <div className="row-end">
          <span className="muted">Private by default · note-first</span>
          <Button onClick={() => void addNote()} disabled={!draft.trim() || saving} type="button">
            {saving ? "Adding…" : "Add note"}
          </Button>
        </div>
        {captures.length > 0 ? (
          <div className="stack">
            {captures.map((capture) => (
              <div key={capture.id} className="therapy-note">
                <div>
                  {capture.type === "audio" ? <Badge tone="blue">audio recap (private)</Badge> : <Badge tone="neutral">✨ decorated</Badge>}
                </div>
                <p>{capture.text || <span className="muted">Processing…</span>}</p>
                {capture.raw && capture.raw !== capture.text ? <p className="muted">you typed: {capture.raw}</p> : null}
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      {/* Two-plane summary (B3) — shareable progress note + private layer. */}
      <Card className="stack">
        <div className="section-heading">
          <h2>Session summary</h2>
          <Tabs value={plane} onChange={setPlane} options={[{ value: "shareable", label: "Shareable" }, { value: "private", label: "Private" }]} />
        </div>

        {plane === "shareable" ? (
          <div className="stack">
            <div className="row-between">
              <Tabs
                value={therapy?.format || "dap"}
                onChange={(value) => onSetFormat(value as TherapyFormat)}
                options={(therapy?.availableFormats || ["dap", "soap", "birp"]).map((f) => ({ value: f, label: FORMAT_LABELS[f] }))}
              />
              {release?.released ? (
                <div className="row-end">
                  <Badge tone="green">Released {formatDate(release.releasedAt)}</Badge>
                  <Button variant="ghost" onClick={() => onRelease(false)} type="button">Withdraw</Button>
                </div>
              ) : (
                <Button onClick={() => onRelease(true)} disabled={!therapy} type="button">Release to client</Button>
              )}
            </div>
            {therapy && therapy.planes.shareable.sections.some((s) => s.body) ? (
              therapy.planes.shareable.sections.map((section) => (
                <div key={section.id} className="therapy-section">
                  <h3>{section.title}</h3>
                  <p>{section.body || <span className="muted">—</span>}</p>
                </div>
              ))
            ) : (
              <p className="muted">Add a note to build the shareable progress note.</p>
            )}
            <p className="muted">Released summaries draw only from this shareable plane — never the private layer.</p>
          </div>
        ) : (
          <div className="stack">
            <h3>Reflections (therapist-only)</h3>
            <Textarea
              rows={4}
              placeholder="Hypotheses, process notes — never shared with the client or exported."
              value={reflections}
              onChange={(event) => setReflections(event.target.value)}
            />
            <div className="row-end">
              <Button variant="secondary" onClick={() => onSaveReflections(reflections)} type="button">Save reflections</Button>
            </div>
            <h3>Audio recap transcript (most-private)</h3>
            {therapy && therapy.planes.private.audioTranscripts.length > 0 ? (
              therapy.planes.private.audioTranscripts.map((entry) => (
                <p key={entry.captureId} className="muted">{entry.text}</p>
              ))
            ) : (
              <p className="muted">No audio recap for this session.</p>
            )}
          </div>
        )}
      </Card>

      {riskOpen ? (
        <Card className="stack therapy-risk-dialog">
          <h3>Confirm risk flag</h3>
          <p className="muted">Risk is clinician-confirmed and dated — never set automatically.</p>
          <label className="field-label">
            Level
            <select value={riskLevel} onChange={(event) => setRiskLevel(event.target.value)}>
              <option value="low">Low</option>
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
            </select>
          </label>
          <Textarea rows={2} placeholder="Safety note / plan" value={riskNote} onChange={(event) => setRiskNote(event.target.value)} />
          <div className="row-end">
            <Button variant="ghost" onClick={() => setRiskOpen(false)} type="button">Cancel</Button>
            <Button variant="danger" onClick={() => { onFlagRisk({ level: riskLevel, note: riskNote }); setRiskOpen(false); }} type="button">Confirm flag</Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
