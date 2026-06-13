import React from "react";
import type { AuthSession, ClinicMember, PatientSummary, WorklistEntry } from "../../../domain/appTypes";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { attributionName } from "../../../shared/lib/multiseat";

// AES-903 — the soft "Today / up next" worklist. Reception lines a patient up for a clinician; the
// clinician sees them here and taps through to the patient (history + before/after) to start a
// session. A convenience lane, never a gate — capture-first still starts a fresh session from the
// footer regardless of anything here. A soft list, NOT a scheduler.

type WorklistScope = "mine" | "clinic";

export function WorklistSection({
  auth,
  onListWorklist,
  onLineUpPatient,
  onMarkWorklistSeen,
  onCancelWorklistEntry,
  onListClinicMembers,
  onSearchPatients,
  onOpenPatient,
  refreshSignal = 0,
}: {
  auth: AuthSession | null;
  onListWorklist: (options?: { scope?: WorklistScope; status?: "waiting"; clinicianId?: string }) => Promise<{ items: WorklistEntry[] }>;
  onLineUpPatient: (input: { patientId: string; clinicianUserId: string; note?: string }) => Promise<WorklistEntry>;
  onMarkWorklistSeen: (entryId: string, sessionId?: string) => Promise<WorklistEntry>;
  onCancelWorklistEntry: (entryId: string) => Promise<WorklistEntry>;
  onListClinicMembers: () => Promise<ClinicMember[]>;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onOpenPatient: (patientId: string) => void;
  refreshSignal?: number;
}) {
  const [scope, setScope] = React.useState<WorklistScope>("mine");
  const [entries, setEntries] = React.useState<WorklistEntry[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [version, setVersion] = React.useState(0);
  const [adding, setAdding] = React.useState(false);
  const [members, setMembers] = React.useState<ClinicMember[]>([]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void onListWorklist({ scope, status: "waiting" })
      .then((result) => {
        if (!cancelled) setEntries(result.items);
      })
      .catch(() => {
        if (!cancelled) setEntries([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onListWorklist, scope, version, refreshSignal]);

  const reload = () => setVersion((v) => v + 1);

  const markSeen = (entry: WorklistEntry) => {
    void onMarkWorklistSeen(entry.id).then(reload).catch(() => undefined);
  };
  const cancel = (entry: WorklistEntry) => {
    void onCancelWorklistEntry(entry.id).then(reload).catch(() => undefined);
  };

  return (
    <Card className="worklist-section">
      <div className="worklist-head">
        <div className="worklist-head-copy">
          <h3>Up next</h3>
          <p className="worklist-subtle">
            {scope === "mine" ? "Patients reception lined up for you." : "Everyone lined up across the clinic."} Tap a patient to open
            their file — you can always start a fresh capture from the footer instead.
          </p>
        </div>
        <div className="mine-clinic-toggle" role="group" aria-label="Worklist scope">
          {(["mine", "clinic"] as WorklistScope[]).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={scope === value}
              className={scope === value ? "active" : ""}
              onClick={() => setScope(value)}
            >
              {value === "mine" ? "Mine" : "Clinic"}
            </button>
          ))}
        </div>
      </div>

      {loading && entries.length === 0 ? (
        <p className="worklist-empty">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="worklist-empty">No one waiting{scope === "mine" ? " for you" : ""} right now.</p>
      ) : (
        <ul className="worklist-list">
          {entries.map((entry) => (
            <li key={entry.id} className="worklist-item">
              <button type="button" className="worklist-item-main" onClick={() => onOpenPatient(entry.patientId)}>
                <span className="worklist-item-name">{entry.patientName || "Unnamed patient"}</span>
                <span className="worklist-item-meta">
                  {scope === "clinic" && entry.clinician ? `for ${attributionName(entry.clinician, auth?.user.id)} · ` : ""}
                  lined up {entry.linedUpBy ? `by ${attributionName(entry.linedUpBy, auth?.user.id)}` : ""}
                  {entry.note ? ` · ${entry.note}` : ""}
                </span>
              </button>
              <span className="worklist-item-actions">
                <Button size="sm" variant="secondary" type="button" onClick={() => onOpenPatient(entry.patientId)}>
                  Open
                </Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => markSeen(entry)}>
                  Done
                </Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => cancel(entry)} aria-label="Remove from worklist">
                  ✕
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {onSearchPatients ? (
        adding ? (
          <LineUpForm
            auth={auth}
            members={members}
            onLoadMembers={() => onListClinicMembers().then(setMembers)}
            onSearchPatients={onSearchPatients}
            onSubmit={(input) => onLineUpPatient(input).then(() => {
              setAdding(false);
              reload();
            })}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button size="sm" variant="secondary" type="button" className="worklist-add" onClick={() => setAdding(true)}>
            + Line up a patient
          </Button>
        )
      ) : null}
    </Card>
  );
}

function LineUpForm({
  auth,
  members,
  onLoadMembers,
  onSearchPatients,
  onSubmit,
  onCancel,
}: {
  auth: AuthSession | null;
  members: ClinicMember[];
  onLoadMembers: () => Promise<void>;
  onSearchPatients: (query: string) => Promise<PatientSummary[]>;
  onSubmit: (input: { patientId: string; clinicianUserId: string; note?: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<PatientSummary[]>([]);
  const [patient, setPatient] = React.useState<PatientSummary | null>(null);
  const [clinicianId, setClinicianId] = React.useState("");
  const [note, setNote] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    void onLoadMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clinicians = members.filter((m) => m.isClinician);
  React.useEffect(() => {
    if (clinicianId || clinicians.length === 0) return;
    // Default to the current user if they're a clinician, else the first clinician.
    const self = auth ? clinicians.find((c) => c.userId === auth.user.id) : undefined;
    setClinicianId((self || clinicians[0]).userId);
  }, [clinicians, clinicianId, auth]);

  React.useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void onSearchPatients(query.trim())
        .then((found) => {
          if (!cancelled) setResults(found.slice(0, 6));
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, onSearchPatients]);

  const submit = () => {
    if (!patient || !clinicianId) return;
    setSaving(true);
    void onSubmit({ patientId: patient.id, clinicianUserId: clinicianId, note: note.trim() || undefined }).finally(() =>
      setSaving(false),
    );
  };

  return (
    <div className="worklist-lineup">
      {patient ? (
        <div className="worklist-lineup-chosen">
          <span>{patient.displayName}</span>
          <Button size="sm" variant="ghost" type="button" onClick={() => setPatient(null)}>
            Change
          </Button>
        </div>
      ) : (
        <>
          <Input
            aria-label="Find a patient"
            placeholder="Find a patient…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {results.length > 0 ? (
            <ul className="worklist-lineup-results">
              {results.map((result) => (
                <li key={result.id}>
                  <button type="button" onClick={() => setPatient(result)}>
                    {result.displayName}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
      <label className="worklist-lineup-field">
        <span>For</span>
        <select aria-label="Clinician" value={clinicianId} onChange={(event) => setClinicianId(event.target.value)}>
          {clinicians.map((member) => (
            <option key={member.userId} value={member.userId}>
              {member.displayName}
              {auth && member.userId === auth.user.id ? " (you)" : ""}
            </option>
          ))}
        </select>
      </label>
      <Input
        aria-label="Note (optional)"
        placeholder="Note (optional)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="worklist-lineup-actions">
        <Button size="sm" type="button" disabled={!patient || !clinicianId || saving} onClick={submit}>
          {saving ? "Adding…" : "Line up"}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
