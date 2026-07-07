import React from "react";
import type { AuthSession, ClinicMember, PatientSummary, WorklistEntry } from "../../../domain/appTypes";
import { Button, Card, Input } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
import { attributionName, currentUserRoles } from "../../../shared/lib/multiseat";

// AES-903 — the soft "Today / up next" worklist. Role-aware (foundation §7):
//  • Reception (assistant/admin) is the *creator*: they line a patient up FOR a doctor.
//  • The doctor is the *consumer*: a read-only queue. Tapping a card opens a recap popup (history +
//    before/after) with Start visit + the full timeline — no page round-trip.
// A convenience lane, never a gate — capture-first still starts a fresh session from the footer.
// Both tiers (deterministic).

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
  onPeekPatient,
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
  // Open the recap popup for a queued patient (history + before/after + Start visit + full timeline).
  onPeekPatient: (patientId: string, patientName: string | undefined, worklistEntryId: string, canStartVisit: boolean) => void;
  refreshSignal?: number;
}) {
  const t = useT();
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
  const [showInfo, setShowInfo] = React.useState(false);

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
  const startVisit = (entry: WorklistEntry) => {
    if (!onStartVisit) return;
    void onStartVisit(entry.patientId, entry.id).catch(() => undefined);
  };

  const subtitle = scope === "mine" ? t("needsinput.subtitleMine") : t("needsinput.subtitleClinic");
  const emptyCopy = t("needsinput.empty");

  // A pure consumer (doctor, not reception) with an empty queue gets *no box at all* — the worklist
  // only appears once reception has lined someone up. Reception always sees it (they add to it).
  if (!viewerIsReception && entries.length === 0) return null;

  return (
    <Card className="worklist-section">
      <div className="worklist-head">
        <div className="worklist-head-copy">
          <div className="worklist-title-row">
            <h3>{t("needsinput.title")}</h3>
            <button
              type="button"
              className="worklist-info-btn"
              aria-label={t("needsinput.aboutAria")}
              aria-expanded={showInfo}
              onClick={() => setShowInfo((v) => !v)}
            >
              ⓘ
            </button>
          </div>
          {showInfo ? <p className="worklist-subtle">{subtitle}</p> : null}
        </div>
        <div className="mine-clinic-toggle" role="group" aria-label={t("needsinput.scopeAria")}>
          {(["mine", "clinic"] as WorklistScope[]).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={scope === value}
              className={scope === value ? "active" : ""}
              onClick={() => setScope(value)}
            >
              {value === "mine" ? t("needsinput.scopeMine") : t("needsinput.scopeClinic")}
            </button>
          ))}
        </div>
      </div>

      {loading && entries.length === 0 ? (
        <p className="worklist-empty">{t("needsinput.loading")}</p>
      ) : entries.length === 0 ? (
        <p className="worklist-empty">{emptyCopy}</p>
      ) : (
        <ul className="worklist-list">
          {entries.map((entry) => {
            const mine = Boolean(auth && entry.clinicianUserId === auth.user.id);
            return (
              <li key={entry.id} className="worklist-item">
                <button
                  type="button"
                  className="worklist-item-header"
                  onClick={() => onPeekPatient(entry.patientId, entry.patientName || undefined, entry.id, mine)}
                >
                  <span className="worklist-item-headcopy">
                    <span className="worklist-item-name" data-content>
                      {entry.patientName || t("needsinput.unnamedPatient")}
                    </span>
                    <span className="worklist-item-meta">
                      {!mine && entry.clinician
                        ? `${t("needsinput.forClinician", { name: attributionName(entry.clinician, auth?.user.id) })} · `
                        : ""}
                      {entry.linedUpBy
                        ? t("needsinput.linedUpBy", { name: attributionName(entry.linedUpBy, auth?.user.id) })
                        : t("needsinput.linedUp")}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </span>
                  </span>
                  <span className="worklist-item-peek">{t("needsinput.recap")}</span>
                </button>

                <div className="worklist-item-actions">
                  {mine && onStartVisit ? (
                    <Button size="sm" type="button" onClick={() => startVisit(entry)}>
                      {t("needsinput.startVisit")}
                    </Button>
                  ) : null}
                  {mine ? (
                    <Button size="sm" variant="ghost" type="button" onClick={() => markSeen(entry)}>
                      {t("needsinput.done")}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      type="button"
                      onClick={() => cancel(entry)}
                      aria-label={t("needsinput.removeAria")}
                    >
                      {t("needsinput.remove")}
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
            {t("needsinput.lineUpCta")}
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
  const t = useT();
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
          <span data-content>{patient.displayName}</span>
          <Button size="sm" variant="ghost" type="button" onClick={() => setPatient(null)}>
            {t("needsinput.change")}
          </Button>
        </div>
      ) : (
        <>
          <Input
            aria-label={t("needsinput.findPatient")}
            placeholder={t("needsinput.findPatientPlaceholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {results.length > 0 ? (
            <ul className="worklist-lineup-results">
              {results.map((result) => (
                <li key={result.id}>
                  <button type="button" onClick={() => setPatient(result)} data-content>
                    {result.displayName}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
      <label className="worklist-lineup-field">
        <span>{t("needsinput.forDr")}</span>
        <select className="select" aria-label={t("needsinput.doctorAria")} value={clinicianId} onChange={(event) => setClinicianId(event.target.value)}>
          {doctors.length === 0 ? <option value="">{t("needsinput.noDoctors")}</option> : null}
          {doctors.map((member) => (
            <option key={member.userId} value={member.userId} data-content>
              {member.displayName}
            </option>
          ))}
        </select>
      </label>
      <Input
        aria-label={t("needsinput.noteOptional")}
        placeholder={t("needsinput.noteOptional")}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="worklist-lineup-actions">
        <Button size="sm" type="button" disabled={!patient || !clinicianId || saving} onClick={submit}>
          {saving ? t("needsinput.adding") : t("needsinput.lineUp")}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={onCancel}>
          {t("needsinput.cancel")}
        </Button>
      </div>
    </div>
  );
}
