import React from "react";
import type { AuthSession, ClinicMember, LastVisitInfo, PatientSummary, WorklistEntry } from "../../../domain/appTypes";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { attributionName, currentUserRoles } from "../../../shared/lib/multiseat";
import { LastVisitStrip } from "../../aesthetics/LastVisitStrip";

// AES-903 — the soft "Today / up next" worklist. Role-aware (foundation §7):
//  • Reception (assistant/admin) is the *creator*: they line a patient up FOR a doctor.
//  • The doctor is the *consumer*: a read-only queue of who's lined up for them, with a one-tap
//    inline recap (last visit + before/after) and Start visit — no page round-trip.
// A convenience lane, never a gate — capture-first still starts a fresh session from the footer.
// Both tiers (deterministic; the recap reuses the Basic AES-106 last-visit retrieval).

type WorklistScope = "mine" | "clinic";

export function WorklistSection({
  auth,
  onListWorklist,
  onLineUpPatient,
  onMarkWorklistSeen,
  onCancelWorklistEntry,
  onListClinicMembers,
  onSearchPatients,
  onStartVisit,
  onOpenPatient,
  onLoadLastVisit,
  onResolveFile,
  refreshSignal = 0,
}: {
  auth: AuthSession | null;
  onListWorklist: (options?: { scope?: WorklistScope; status?: "waiting"; clinicianId?: string }) => Promise<{ items: WorklistEntry[] }>;
  onLineUpPatient: (input: { patientId: string; clinicianUserId: string; note?: string }) => Promise<WorklistEntry>;
  onMarkWorklistSeen: (entryId: string, sessionId?: string) => Promise<WorklistEntry>;
  onCancelWorklistEntry: (entryId: string) => Promise<WorklistEntry>;
  onListClinicMembers: () => Promise<ClinicMember[]>;
  onSearchPatients?: (query: string) => Promise<PatientSummary[]>;
  onStartVisit?: (patientId: string, worklistEntryId?: string) => Promise<void>;
  onOpenPatient: (patientId: string, patientName?: string) => void;
  onLoadLastVisit?: (patientId: string) => Promise<LastVisitInfo>;
  onResolveFile?: (endpoint: string) => Promise<string>;
  refreshSignal?: number;
}) {
  const roles = currentUserRoles(auth);
  const viewerIsDoctor = roles.includes("doctor");
  // Assistant is the reception/intake seat here; admin manages the clinic. Both create line-ups.
  const viewerIsReception = roles.includes("assistant") || roles.includes("admin");

  const [scope, setScope] = React.useState<WorklistScope>(viewerIsDoctor ? "mine" : "clinic");
  const [entries, setEntries] = React.useState<WorklistEntry[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [version, setVersion] = React.useState(0);
  const [adding, setAdding] = React.useState(false);
  const [members, setMembers] = React.useState<ClinicMember[]>([]);
  // Inline recap: which entry is expanded + a per-patient last-visit cache (undefined = loading).
  const [expandedId, setExpandedId] = React.useState("");
  const [recaps, setRecaps] = React.useState<Record<string, LastVisitInfo | null>>({});

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

  const toggleRecap = (entry: WorklistEntry) => {
    const next = expandedId === entry.id ? "" : entry.id;
    setExpandedId(next);
    if (next && onLoadLastVisit && !(entry.patientId in recaps)) {
      void onLoadLastVisit(entry.patientId)
        .then((info) => setRecaps((current) => ({ ...current, [entry.patientId]: info })))
        .catch(() => setRecaps((current) => ({ ...current, [entry.patientId]: null })));
    }
  };

  const markSeen = (entry: WorklistEntry) => {
    void onMarkWorklistSeen(entry.id).then(reload).catch(() => undefined);
  };
  const cancel = (entry: WorklistEntry) => {
    void onCancelWorklistEntry(entry.id).then(reload).catch(() => undefined);
  };
  const startVisit = (entry: WorklistEntry) => {
    if (!onStartVisit) return;
    void onStartVisit(entry.patientId, entry.id).catch(() => undefined);
  };

  const subtitle =
    scope === "mine"
      ? "Patients reception lined up for you. Tap one to peek at last visit, then start. The footer always starts a fresh capture too."
      : "Everyone lined up across the clinic. Line a patient up for a doctor, or open their file.";
  const emptyCopy =
    scope === "mine"
      ? "No one is waiting for you. Reception lines patients up here."
      : "No one is lined up right now.";

  return (
    <Card className="worklist-section">
      <div className="worklist-head">
        <div className="worklist-head-copy">
          <h3>Up next</h3>
          <p className="worklist-subtle">{subtitle}</p>
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
        <p className="worklist-empty">{emptyCopy}</p>
      ) : (
        <ul className="worklist-list">
          {entries.map((entry) => {
            const mine = Boolean(auth && entry.clinicianUserId === auth.user.id);
            const expanded = expandedId === entry.id;
            const recap = entry.patientId in recaps ? recaps[entry.patientId] : undefined;
            return (
              <li key={entry.id} className={`worklist-item${expanded ? " expanded" : ""}`}>
                <button
                  type="button"
                  className="worklist-item-header"
                  aria-expanded={expanded}
                  onClick={() => toggleRecap(entry)}
                >
                  <span className="worklist-item-headcopy">
                    <span className="worklist-item-name">{entry.patientName || "Unnamed patient"}</span>
                    <span className="worklist-item-meta">
                      {!mine && entry.clinician ? `for ${attributionName(entry.clinician, auth?.user.id)} · ` : ""}
                      lined up {entry.linedUpBy ? `by ${attributionName(entry.linedUpBy, auth?.user.id)}` : ""}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </span>
                  </span>
                  <span className={`worklist-item-chev${expanded ? " open" : ""}`} aria-hidden="true">
                    ⌄
                  </span>
                </button>

                {expanded ? (
                  <div className="worklist-recap">
                    {recap === undefined ? (
                      <p className="worklist-recap-note">Loading last visit…</p>
                    ) : recap?.hasPriorVisit && recap.visit && onResolveFile ? (
                      <LastVisitStrip lastVisit={recap} onResolveFile={onResolveFile} />
                    ) : (
                      <p className="worklist-recap-note">First visit — no history yet.</p>
                    )}
                    <button type="button" className="worklist-recap-fulllink" onClick={() => onOpenPatient(entry.patientId, entry.patientName || undefined)}>
                      See full patient file →
                    </button>
                  </div>
                ) : null}

                <div className="worklist-item-actions">
                  {mine && onStartVisit ? (
                    <Button size="sm" type="button" onClick={() => startVisit(entry)}>
                      Start visit
                    </Button>
                  ) : null}
                  <Button size="sm" variant="secondary" type="button" onClick={() => onOpenPatient(entry.patientId, entry.patientName || undefined)}>
                    Open
                  </Button>
                  {mine ? (
                    <Button size="sm" variant="ghost" type="button" onClick={() => markSeen(entry)}>
                      Done
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" type="button" onClick={() => cancel(entry)} aria-label="Remove from worklist">
                      Remove
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Reception creates line-ups (for a doctor); doctors only consume their queue. */}
      {viewerIsReception && onSearchPatients ? (
        adding ? (
          <LineUpForm
            members={members}
            onLoadMembers={() => onListClinicMembers().then(setMembers)}
            onSearchPatients={onSearchPatients}
            onSubmit={(input) =>
              onLineUpPatient(input).then(() => {
                setAdding(false);
                reload();
              })
            }
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button size="sm" variant="secondary" type="button" className="worklist-add" onClick={() => setAdding(true)}>
            + Line up a patient for a doctor
          </Button>
        )
      ) : null}
    </Card>
  );
}

function LineUpForm({
  members,
  onLoadMembers,
  onSearchPatients,
  onSubmit,
  onCancel,
}: {
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

  // You line a patient up *for a doctor* — only doctors are valid targets (never reception itself).
  const doctors = members.filter((m) => m.role === "doctor");
  React.useEffect(() => {
    if (clinicianId || doctors.length === 0) return;
    setClinicianId(doctors[0].userId);
  }, [doctors, clinicianId]);

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
        <span>For Dr.</span>
        <select aria-label="Doctor" value={clinicianId} onChange={(event) => setClinicianId(event.target.value)}>
          {doctors.length === 0 ? <option value="">No doctors in this clinic</option> : null}
          {doctors.map((member) => (
            <option key={member.userId} value={member.userId}>
              {member.displayName}
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
