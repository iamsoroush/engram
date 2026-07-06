import React from "react";
import type {
  LotLedger,
  LotRecallResult,
  PatientMemoryRow,
  SmartPatientMatch,
  SyncHealth,
} from "../../domain/appTypes";
import type { CaptureSession } from "../../domain/types";
import type { MemoryApi } from "../memory/useMemoryApi";
import { QaChannelButton } from "../qa/QaChannelButton";
import { useT, type Translator } from "../../shared/i18n";
import { lotSuggestions, localSessionMatches, todaysVisits, type FinderLotSuggestion } from "./finderModel";
import "./finder.css";

// AES-1201/1202/1203/1204/1205 — the unified finder overlay. One patients-first, app-wide retrieval
// surface that REPLACES the old top-nav `/#search` local-substring screen: online it hits the real,
// Persian-orthography-aware patient search (AES-204) plus the Pro lot recall (safety-grade, exact
// match); offline it falls back to the preserved local substring over loaded sessions. It composes
// existing endpoints (patients/search + patient-memory + lot-ledger/lot-recall) — no new backend
// surface — and floats over whatever screen is beneath (the capture bar stays the trust anchor).

const SEARCH_DEBOUNCE_MS = 280; // matches the Patients-tab smart search
const RECENT_LIMIT = 6;

/** Singular/plural label selector: `${base}.one` for n === 1, else `${base}.other` (fa keeps singular). */
function plural(t: Translator, base: string, n: number): string {
  return t(n === 1 ? `${base}.one` : `${base}.other`, { n });
}

export type FinderOverlayProps = {
  /** Close the overlay (also invoked by hardware Back via the caller's back-level registration). */
  onClose: () => void;
  /** The Clinical-Memory API surface (patient search, recent memory, Pro lot ledger/recall, Q&A). */
  memoryApi: MemoryApi;
  /** Sessions already loaded in the client — the offline fallback + the instant "Today's visits" grain. */
  sessions: CaptureSession[];
  /** Online flag drives backend-vs-local behavior + the "limited" offline note. */
  syncHealth: SyncHealth;
  /** Open a patient's timeline (Clinical Memory → patient file). */
  onOpenPatient: (patientId: string, name?: string) => void;
  /** Open a visit/session in historical review. */
  onOpenSession: (sessionId: string) => void;
  /** Hand off to the Patients screen to add a record (routes through the shared duplicate-guarded form). */
  onCreatePatient?: () => void;
  onToast?: (message: string) => void;
};

/**
 * The finder overlay. Mounted only while open (the caller owns the open state + back-level), so mount
 * effects double as open effects.
 */
export function FinderOverlay({
  onClose,
  memoryApi,
  sessions,
  syncHealth,
  onOpenPatient,
  onOpenSession,
  onCreatePatient,
  onToast,
}: FinderOverlayProps) {
  const t = useT();
  const online = syncHealth.online;
  // Pro lot recall is present exactly when the capability-gated binders are (the Lists-tab pattern).
  const canRecallLots = Boolean(memoryApi.fetchLotLedger && memoryApi.fetchLotRecall);

  const [query, setQuery] = React.useState("");
  const [patients, setPatients] = React.useState<SmartPatientMatch[] | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [recent, setRecent] = React.useState<PatientMemoryRow[]>([]);
  const [ledger, setLedger] = React.useState<LotLedger | null>(null);
  const [recall, setRecall] = React.useState<LotRecallResult | null>(null);
  const [recallLoading, setRecallLoading] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Land the caret in the search box the moment the finder opens (it's a find-first surface).
  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Escape closes the finder (desktop nicety; hardware Back covers mobile via the caller's back level).
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Pre-query grain data, loaded once per open (online only): recent patients + the Pro lot ledger that
  // powers live recall suggestions. Failures are silent — the empty state degrades gracefully.
  React.useEffect(() => {
    if (!online) return;
    let cancelled = false;
    void memoryApi
      .listPatientMemory({ filter: "recent", limit: RECENT_LIMIT })
      .then((response) => {
        if (!cancelled) setRecent(response.items);
      })
      .catch(() => undefined);
    if (memoryApi.fetchLotLedger) {
      void memoryApi
        .fetchLotLedger()
        .then((loaded) => {
          if (!cancelled) setLedger(loaded);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [online, memoryApi]);

  // Debounced backend patient search (AES-204). Offline or blank query → no backend call.
  React.useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || !online) {
      setPatients(null);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const handle = window.setTimeout(() => {
      void memoryApi
        .smartSearchPatients(trimmed)
        .then((response) => {
          if (!cancelled) setPatients(response.items);
        })
        .catch(() => {
          if (!cancelled) setPatients([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [query, online, memoryApi]);

  // A new query invalidates any open recall cohort (the lot action re-appears from suggestions).
  React.useEffect(() => {
    setRecall(null);
  }, [query]);

  const lotHits = React.useMemo<FinderLotSuggestion[]>(
    () => (canRecallLots && online ? lotSuggestions(ledger, query) : []),
    [canRecallLots, online, ledger, query],
  );

  const runRecall = React.useCallback(
    (lookup: { lot?: string; product?: string }) => {
      if (!memoryApi.fetchLotRecall) return;
      setRecallLoading(true);
      setRecall(null);
      void memoryApi
        .fetchLotRecall(lookup)
        .then(setRecall)
        .catch(() => onToast?.(t("recall.error")))
        .finally(() => setRecallLoading(false));
    },
    [memoryApi, onToast, t],
  );

  const trimmed = query.trim();
  const hasQuery = trimmed.length > 0;
  const localMatches = React.useMemo(
    () => (!online && hasQuery ? localSessionMatches(sessions, query) : []),
    [online, hasQuery, sessions, query],
  );
  const today = React.useMemo(() => (hasQuery ? [] : todaysVisits(sessions, Date.now())), [hasQuery, sessions]);

  const openPatient = (patientId: string, name?: string) => {
    onOpenPatient(patientId, name);
    onClose();
  };
  const openSession = (sessionId: string) => {
    onOpenSession(sessionId);
    onClose();
  };

  return (
    <div className="finder-overlay overlay sheet-overlay" role="presentation">
      <div className="finder-panel sheet" role="dialog" aria-modal="true" aria-label={t("finder.title")}>
        <div className="dialog-header">
          <div className="sheet-title">
            <span className="sheet-title-icon" aria-hidden="true"><FinderIcon /></span>
            <h2>{t("finder.title")}</h2>
          </div>
          <button className="sheet-close" onClick={onClose} type="button" aria-label={t("finder.close")}>
            <CloseIcon />
          </button>
        </div>

        <label className="clinical-search finder-search">
          <SearchIcon />
          <input
            ref={inputRef}
            className="input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("finder.placeholder")}
            aria-label={t("finder.searchAria")}
            enterKeyHint="search"
          />
        </label>

        {!online ? (
          <p className="clinical-offline-note finder-offline">{t("search.offlineNote")}</p>
        ) : null}

        <div className="finder-results sheet-stack" data-testid="finder-results">
          {/* Pre-query: instant Today's visits (local) + recent patients (backend). */}
          {!hasQuery ? (
            <>
              {today.length ? (
                <FinderGroup label={t("finder.group.visits")}>
                  {today.map((session) => (
                    <SessionRow key={session.id} session={session} onOpen={() => openSession(session.id)} t={t} />
                  ))}
                </FinderGroup>
              ) : null}
              {recent.length ? (
                <FinderGroup label={t("finder.group.recent")}>
                  {recent.map((row) => (
                    <button
                      key={row.patientId}
                      className="search-result-card finder-row"
                      type="button"
                      onClick={() => openPatient(row.patientId, row.displayName)}
                    >
                      <div>
                        <strong data-content>{row.displayName}</strong>
                        {row.metadataSentence ? <p data-content>{row.metadataSentence}</p> : null}
                      </div>
                    </button>
                  ))}
                </FinderGroup>
              ) : null}
              <p className="finder-hint">{t("finder.hint")}</p>
            </>
          ) : null}

          {/* Lot/product recall (Pro): the action appears ABOVE patient results; selecting runs the
              exact-match recall and renders the cohort inline. */}
          {hasQuery && lotHits.length ? (
            <FinderGroup label={t("finder.group.recallLot")}>
              {lotHits.map((hit) => (
                <button
                  key={`${hit.kind}:${hit.value}`}
                  className="search-result-card finder-lot-action"
                  type="button"
                  onClick={() => runRecall(hit.kind === "lot" ? { lot: hit.value } : { product: hit.value })}
                >
                  <div>
                    <strong data-content>
                      {hit.kind === "lot" ? t("finder.lotAction", { lot: hit.value }) : t("finder.productAction", { product: hit.value })}
                    </strong>
                    {hit.sub ? <p data-content>{hit.sub}</p> : null}
                  </div>
                  <span className="finder-count">{plural(t, "recall.chip", hit.patientCount)}</span>
                </button>
              ))}
            </FinderGroup>
          ) : null}
          {recallLoading ? <p className="finder-hint">{t("finder.searching")}</p> : null}
          {recall ? (
            <FinderRecall
              result={recall}
              onOpenPatient={openPatient}
              onOpenSession={openSession}
              onOpenQaChannel={memoryApi.openQaChannel}
              onToast={onToast}
              onRecallSimilar={(lot) => runRecall({ lot })}
            />
          ) : null}

          {/* Patient search results (online) — the primary grain. */}
          {hasQuery && online ? (
            <FinderPatientResults
              searching={searching}
              patients={patients}
              query={trimmed}
              suppressNoResults={lotHits.length > 0}
              onOpenPatient={openPatient}
              onCreatePatient={
                onCreatePatient
                  ? () => {
                      onCreatePatient();
                      onClose();
                    }
                  : undefined
              }
            />
          ) : null}

          {/* Offline fallback: local substring over loaded sessions (the preserved old behavior). */}
          {hasQuery && !online ? (
            localMatches.length ? (
              <FinderGroup label={t("finder.group.visits")}>
                {localMatches.map((session) => (
                  <SessionRow key={session.id} session={session} onOpen={() => openSession(session.id)} t={t} />
                ))}
              </FinderGroup>
            ) : (
              <p className="finder-empty">{t("finder.noResultsOffline")}</p>
            )
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** The online patient-search grain: spinner while the debounced search is in flight, the ranked
 *  results, or a no-results state with the duplicate-guarded "add a patient" hand-off. Extracted so the
 *  overlay body stays a flat list of grains (no nested ternary). */
function FinderPatientResults({
  searching,
  patients,
  query,
  suppressNoResults,
  onOpenPatient,
  onCreatePatient,
}: {
  searching: boolean;
  patients: SmartPatientMatch[] | null;
  query: string;
  suppressNoResults: boolean;
  onOpenPatient: (patientId: string, name?: string) => void;
  onCreatePatient?: () => void;
}) {
  const t = useT();
  if (searching && patients === null) {
    return <p className="finder-hint">{t("finder.searching")}</p>;
  }
  if (patients && patients.length) {
    return (
      <FinderGroup label={t("finder.group.patients")}>
        {patients.map((match) => (
          <button
            key={match.id}
            className="search-result-card finder-row"
            type="button"
            onClick={() => onOpenPatient(match.id, match.displayName)}
          >
            <div>
              <strong data-content>{match.displayName}</strong>
              {match.reason ? <p>{match.reason}</p> : null}
              {match.phone ? <span data-content>{match.phone}</span> : null}
            </div>
          </button>
        ))}
      </FinderGroup>
    );
  }
  if (patients && patients.length === 0 && !suppressNoResults) {
    return (
      <div className="finder-empty" data-testid="finder-no-results">
        <p>{t("finder.noResults", { q: query })}</p>
        {onCreatePatient ? (
          <button className="finder-create" type="button" onClick={onCreatePatient}>
            {t("finder.createPatient")}
          </button>
        ) : null}
      </div>
    );
  }
  return null;
}

function FinderGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="finder-group" aria-label={label}>
      <p className="finder-group-head smart-search-note">{label}</p>
      <div className="finder-list clinical-list">{children}</div>
    </section>
  );
}

function SessionRow({ session, onOpen, t }: { session: CaptureSession; onOpen: () => void; t: Translator }) {
  return (
    <button className="search-result-card finder-row" type="button" onClick={onOpen}>
      <div>
        <strong data-content>{session.label}</strong>
        {session.summary ? <p data-content>{session.summary}</p> : null}
        <span data-content>{session.patientName || session.reviewReason || t("search.unassignedSession")}</span>
      </div>
    </button>
  );
}

/**
 * Compact recall cohort rendered inside the finder — the safety-grade contract, unchanged: exact-match
 * `affected` patients each cite their verbatim treatment line(s); near-miss lots sit in their own
 * "Similar lots (not included)" group (never folded in); the Pro outreach handoff (Open channel) is
 * reachable per patient. Deliberately lighter than the Lists-tab RecallCohort so it fits the overlay.
 */
function FinderRecall({
  result,
  onOpenPatient,
  onOpenSession,
  onOpenQaChannel,
  onToast,
  onRecallSimilar,
}: {
  result: LotRecallResult;
  onOpenPatient: (patientId: string, name?: string) => void;
  onOpenSession: (sessionId: string) => void;
  onOpenQaChannel?: MemoryApi["openQaChannel"];
  onToast?: (message: string) => void;
  onRecallSimilar: (lot: string) => void;
}) {
  const t = useT();
  const isLot = result.kind === "lot";
  const title = isLot ? t("recall.lotTitle", { lot: result.value }) : t("recall.productTitle", { product: result.value });
  const summary = t("recall.summary", {
    patients: plural(t, "recall.patients", result.patientCount),
    visits: plural(t, "recall.visits", result.visitCount),
  });

  return (
    <section className="finder-recall" aria-label={title} data-testid="finder-recall">
      <p className="finder-group-head smart-search-note">
        <span data-content>{title}</span> · {summary}
      </p>
      {result.affected.length === 0 ? <p className="finder-empty">{t("recall.empty.copy")}</p> : null}
      <div className="finder-list clinical-list">
        {result.affected.map((patient) => (
          <div className="finder-recall-patient" key={patient.patientId}>
            <button
              className="search-result-card finder-row"
              type="button"
              onClick={() => onOpenPatient(patient.patientId, patient.displayName)}
            >
              <div>
                <strong data-content>{patient.displayName}</strong>
                {patient.identifyingContext?.phone ? <span data-content>{patient.identifyingContext.phone}</span> : null}
              </div>
            </button>
            {/* Source citations: verbatim treatment line(s) per affected visit — tap to open the visit. */}
            <ul className="finder-cites">
              {patient.visits.map((visit) => {
                const line = visit.treatments
                  .map((treatment) => treatment.phrase)
                  .filter(Boolean)
                  .join(" · ");
                return line ? (
                  <li key={visit.sessionId}>
                    <button className="finder-cite" type="button" data-content onClick={() => onOpenSession(visit.sessionId)}>
                      {line}
                    </button>
                  </li>
                ) : null;
              })}
            </ul>
            {onOpenQaChannel ? (
              <QaChannelButton patientName={patient.displayName} onOpen={() => onOpenQaChannel(patient.patientId)} onToast={onToast} />
            ) : null}
          </div>
        ))}
      </div>
      {result.similar.length ? (
        <div className="finder-similar">
          <span className="lot-suggestions-label">{t("recall.similarLabel")}</span>
          <p className="finder-hint">{t("recall.similarNote")}</p>
          <div className="lot-suggestions">
            {result.similar.map((similar) => (
              <button
                key={similar.lot}
                className="lot-chip lot-chip-lot"
                type="button"
                onClick={() => onRecallSimilar(similar.lot)}
              >
                <span className="lot-chip-value" data-content>{similar.lot}</span>
                <span className="lot-chip-count">{plural(t, "recall.chip", similar.patientCount)}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FinderIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M16.8 16.8 20 20" />
      <path d="M18 11.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" focusable="false" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16.8 16.8 20 20" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}
