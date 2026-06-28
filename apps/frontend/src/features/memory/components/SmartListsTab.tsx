// Clinical Memory → Lists (Pro; AES-501 smart lists + AES-502 lot/product recall).
// One coherent surface: a small rail of named, deterministic lenses (with live counts) + a lot/product
// lookup that doubles as the safety-grade recall cohort. Sibling to the Today/Patients/Needs-input
// tabs. Design: docs/ux/redesign-smart-lists-recall.md. All chrome via t(); clinical content (lot
// strings, treatment phrases) is verbatim.
import React from "react";
import type { LotLedger, LotRecallResult, SmartListCounts, SmartListKey, SmartListResponse } from "../../../domain/appTypes";
import type { QaThreadSummary } from "../../qa/qaClient";
import { useT } from "../../../shared/i18n";
import { formatDate } from "../../../shared/lib/datetime";
import { Input } from "../../../shared/ui/primitives";
import { QaChannelButton } from "../../qa/QaChannelButton";
import { EmptyClinicalState, PatientListLoading } from "./MemoryCards";
import { CalendarIcon, ChevronIcon, SearchIcon, SparkleIcon } from "./MemoryIcons";

const SMART_LIST_KEYS: SmartListKey[] = ["seen-this-week", "due-to-return", "missing-after-photo"];

type View = { kind: "home" } | { kind: "list"; key: SmartListKey } | { kind: "recall" };

export function SmartListsTab({
  onFetchCounts,
  onFetchList,
  onFetchLedger,
  onFetchRecall,
  onOpenPatient,
  onOpenSession,
  onOpenQaChannel,
  onToast,
  refreshSignal = 0,
}: {
  onFetchCounts: () => Promise<SmartListCounts>;
  onFetchList: (key: SmartListKey) => Promise<SmartListResponse>;
  onFetchLedger: () => Promise<LotLedger>;
  onFetchRecall: (query: { lot?: string; product?: string }) => Promise<LotRecallResult>;
  onOpenPatient: (patientId: string, name?: string) => void;
  onOpenSession: (sessionId: string) => void;
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
  refreshSignal?: number;
}) {
  const t = useT();
  const [view, setView] = React.useState<View>({ kind: "home" });
  const [counts, setCounts] = React.useState<SmartListCounts | null>(null);
  const [ledger, setLedger] = React.useState<LotLedger | null>(null);

  // Rail counts + the lot ledger load on open and refresh after captures land.
  React.useEffect(() => {
    let cancelled = false;
    void onFetchCounts().then((value) => !cancelled && setCounts(value)).catch(() => undefined);
    void onFetchLedger().then((value) => !cancelled && setLedger(value)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [onFetchCounts, onFetchLedger, refreshSignal]);

  if (view.kind === "list") {
    return <SmartListView listKey={view.key} dueToReturnWeeks={counts?.dueToReturnWeeks ?? 12} onFetchList={onFetchList} onBack={() => setView({ kind: "home" })} onOpenPatient={onOpenPatient} onOpenSession={onOpenSession} />;
  }

  return (
    <div className="clinical-tab-panel smart-lists" role="tabpanel">
      <SmartListRail counts={counts} onOpen={(key) => setView({ kind: "list", key })} />
      <LotLookup ledger={ledger} onFetchRecall={onFetchRecall} onOpenPatient={onOpenPatient} onOpenSession={onOpenSession} onOpenQaChannel={onOpenQaChannel} onToast={onToast} />
    </div>
  );
}

function SmartListIcon({ listKey }: { listKey: SmartListKey }) {
  if (listKey === "seen-this-week") return <CalendarIcon />;
  if (listKey === "missing-after-photo") return <CameraIcon />;
  return <ClockIcon />;
}

function SmartListRail({ counts, onOpen }: { counts: SmartListCounts | null; onOpen: (key: SmartListKey) => void }) {
  const t = useT();
  return (
    <section className="smart-list-rail" aria-label={t("smartlists.railAria")}>
      <h2 className="smart-list-heading">{t("smartlists.heading")}</h2>
      <div className="smart-list-cards">
        {SMART_LIST_KEYS.map((key) => {
          const count = counts?.counts[key];
          const weeks = counts?.dueToReturnWeeks ?? 12;
          return (
            <button className="smart-list-card" key={key} type="button" onClick={() => onOpen(key)}>
              <span className="smart-list-card-top">
                <span className="smart-list-card-icon" aria-hidden="true"><SmartListIcon listKey={key} /></span>
                <span className="smart-list-count">{count == null ? "—" : count}</span>
              </span>
              <span className="smart-list-card-title">{t(`smartlists.${key}.title`)}</span>
              <span className="smart-list-card-defn">{key === "due-to-return" ? t("smartlists.due-to-return.defn", { weeks }) : t(`smartlists.${key}.defn`)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// --- One smart list's rows -------------------------------------------------------------------------
function SmartListView({
  listKey,
  dueToReturnWeeks,
  onFetchList,
  onBack,
  onOpenPatient,
  onOpenSession,
}: {
  listKey: SmartListKey;
  dueToReturnWeeks: number;
  onFetchList: (key: SmartListKey) => Promise<SmartListResponse>;
  onBack: () => void;
  onOpenPatient: (patientId: string, name?: string) => void;
  onOpenSession: (sessionId: string) => void;
}) {
  const t = useT();
  const [data, setData] = React.useState<SmartListResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    void onFetchList(listKey)
      .then((value) => !cancelled && setData(value))
      .catch(() => !cancelled && setError(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [listKey, onFetchList]);

  const rows = data?.rows ?? [];
  return (
    <div className="clinical-tab-panel smart-lists" role="tabpanel">
      <button className="smart-list-back" type="button" onClick={onBack}>
        <span className="smart-list-back-chevron" aria-hidden="true"><ChevronIcon /></span> {t("smartlists.backToLists")}
      </button>
      <header className="smart-list-detail-head">
        <h2>{t(`smartlists.${listKey}.title`)}</h2>
        <p>{listKey === "due-to-return" ? t("smartlists.due-to-return.defn", { weeks: dueToReturnWeeks }) : t(`smartlists.${listKey}.defn`)}</p>
      </header>
      {loading ? (
        <PatientListLoading />
      ) : error ? (
        <EmptyClinicalState title={t("smartlists.error.title")} copy={t("smartlists.error.copy")} />
      ) : rows.length ? (
        <div className="clinical-list">
          {rows.map((row) => (
            <SmartListRowCard
              key={`${row.patientId}:${row.sessionId ?? ""}`}
              listKey={listKey}
              row={row}
              dueToReturnWeeks={dueToReturnWeeks}
              onOpen={() => (row.sessionId ? onOpenSession(row.sessionId) : onOpenPatient(row.patientId, row.displayName))}
            />
          ))}
        </div>
      ) : (
        <EmptyClinicalState title={t(`smartlists.${listKey}.empty.title`)} copy={t(`smartlists.${listKey}.empty.copy`)} />
      )}
    </div>
  );
}

function weeksSince(iso?: string | null): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((Date.now() - then) / (7 * 24 * 60 * 60 * 1000)));
}

function smartListRowLabel(listKey: SmartListKey, row: SmartListResponse["rows"][number], t: ReturnType<typeof useT>): string {
  if (listKey === "seen-this-week") return t("smartlists.row.visited", { date: formatDate(row.visitAt) || "—" });
  if (listKey === "due-to-return") return t("smartlists.row.lastSeen", { weeks: weeksSince(row.visitAt) ?? "—" });
  return t("smartlists.row.missingAfter");
}

function SmartListRowCard({
  listKey,
  row,
  onOpen,
}: {
  listKey: SmartListKey;
  row: SmartListResponse["rows"][number];
  dueToReturnWeeks: number;
  onOpen: () => void;
}) {
  const t = useT();
  const label = smartListRowLabel(listKey, row, t);
  const phone = row.identifyingContext?.phone;
  return (
    <button className="smart-list-row" type="button" onClick={onOpen}>
      <span className="smart-list-row-copy">
        <span className="smart-list-row-name" data-content>{row.displayName}</span>
        <span className="smart-list-row-label">{label}</span>
        {row.detail ? <span className="smart-list-row-detail" data-content>{row.detail}</span> : null}
        {phone ? <span className="smart-list-row-phone" data-content>{phone}</span> : null}
      </span>
      <span className="smart-list-row-go" aria-hidden="true"><ChevronIcon /></span>
    </button>
  );
}

// --- Lot / product lookup + recall -----------------------------------------------------------------
type Suggestion = { kind: "lot" | "product"; value: string; sub?: string | null; patientCount: number };

function LotLookup({
  ledger,
  onFetchRecall,
  onOpenPatient,
  onOpenSession,
  onOpenQaChannel,
  onToast,
}: {
  ledger: LotLedger | null;
  onFetchRecall: (query: { lot?: string; product?: string }) => Promise<LotRecallResult>;
  onOpenPatient: (patientId: string, name?: string) => void;
  onOpenSession: (sessionId: string) => void;
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
}) {
  const t = useT();
  const [query, setQuery] = React.useState("");
  const [result, setResult] = React.useState<LotRecallResult | null>(null);
  const [loading, setLoading] = React.useState(false);

  const runRecall = React.useCallback(
    (q: { lot?: string; product?: string }) => {
      setLoading(true);
      setResult(null);
      void onFetchRecall(q)
        .then(setResult)
        .catch(() => onToast?.(t("recall.error")))
        .finally(() => setLoading(false));
    },
    [onFetchRecall, onToast, t],
  );

  const needle = query.trim().toLowerCase();
  const suggestions: Suggestion[] = React.useMemo(() => {
    if (!ledger) return [];
    const lots: Suggestion[] = ledger.lots
      .filter((entry) => !needle || entry.lot.toLowerCase().includes(needle) || (entry.brand || "").toLowerCase().includes(needle) || (entry.product || "").toLowerCase().includes(needle))
      .map((entry) => ({ kind: "lot", value: entry.lot, sub: entry.brand || entry.product || null, patientCount: entry.patientCount }));
    const products: Suggestion[] = ledger.products
      .filter((entry) => !needle || entry.name.toLowerCase().includes(needle))
      .map((entry) => ({ kind: "product", value: entry.name, sub: null, patientCount: entry.patientCount }));
    return [...lots, ...products].slice(0, needle ? 8 : 5);
  }, [ledger, needle]);

  return (
    <section className="lot-lookup" aria-label={t("recall.heading")}>
      <h2 className="smart-list-heading">{t("recall.heading")}</h2>
      <p className="lot-lookup-intro">{t("recall.intro")}</p>
      <form
        className="lot-lookup-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) runRecall({ lot: query.trim() });
        }}
      >
        <label className="clinical-search lot-lookup-search">
          <SearchIcon />
          <Input aria-label={t("recall.searchAria")} placeholder={t("recall.searchPlaceholder")} value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      </form>
      {suggestions.length ? (
        <div className="lot-suggestions">
          <span className="lot-suggestions-label">{needle ? t("recall.matches") : t("recall.recentInData")}</span>
          {suggestions.map((s) => (
            <button
              className={`lot-chip lot-chip-${s.kind}`}
              key={`${s.kind}:${s.value}`}
              type="button"
              onClick={() => runRecall(s.kind === "lot" ? { lot: s.value } : { product: s.value })}
            >
              <span className="lot-chip-value" data-content>{s.value}</span>
              {s.sub ? <span className="lot-chip-sub" data-content>{s.sub}</span> : null}
              <span className="lot-chip-count">{t("recall.chipCount", { n: s.patientCount })}</span>
            </button>
          ))}
        </div>
      ) : ledger ? (
        <p className="lot-lookup-empty">{needle ? t("recall.noMatches") : t("recall.noData")}</p>
      ) : null}
      {loading ? <PatientListLoading /> : null}
      {result ? <RecallCohort result={result} onOpenPatient={onOpenPatient} onOpenSession={onOpenSession} onOpenQaChannel={onOpenQaChannel} onToast={onToast} onRecallSimilar={(lot) => { setQuery(lot); runRecall({ lot }); }} /> : null}
    </section>
  );
}

function RecallCohort({
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
  onOpenQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  onToast?: (message: string) => void;
  onRecallSimilar: (lot: string) => void;
}) {
  const t = useT();
  const isLot = result.kind === "lot";
  const title = isLot ? t("recall.lotTitle", { lot: result.value }) : t("recall.productTitle", { product: result.value });

  const copyList = async () => {
    const lines = result.affected.map((p) => {
      const phone = p.identifyingContext?.phone ? ` · ${p.identifyingContext.phone}` : "";
      return `${p.displayName}${phone}`;
    });
    const header = isLot ? `${t("recall.lotTitle", { lot: result.value })} — ${t("recall.summary", { patients: result.patientCount, visits: result.visitCount })}` : title;
    try {
      await navigator.clipboard.writeText([header, ...lines].join("\n"));
      onToast?.(t("recall.copied"));
    } catch {
      onToast?.(t("recall.copyFailed"));
    }
  };

  return (
    <div className={`recall-cohort${isLot ? " recall-cohort-lot" : ""}`}>
      <header className="recall-cohort-head">
        <h3 data-content={isLot ? undefined : true}>
          {isLot ? <span className="recall-warn" aria-hidden="true"><WarnIcon /></span> : null}
          {title}
        </h3>
        <p className="recall-cohort-summary">{t("recall.summary", { patients: result.patientCount, visits: result.visitCount })}</p>
      </header>
      {result.patientCount === 0 ? (
        <EmptyClinicalState title={t("recall.empty.title")} copy={t("recall.empty.copy")} />
      ) : (
        <>
          <div className="recall-cohort-actions">
            <button className="recall-copy-button" type="button" onClick={copyList}>{t("recall.copyList")}</button>
          </div>
          <div className="recall-cohort-list">
            {result.affected.map((patient) => (
              <article className="recall-patient" key={patient.patientId}>
                <div className="recall-patient-head">
                  <button className="recall-patient-name" type="button" onClick={() => onOpenPatient(patient.patientId, patient.displayName)}>
                    <span data-content>{patient.displayName}</span>
                    {patient.identifyingContext?.phone ? <span className="recall-patient-phone" data-content>{patient.identifyingContext.phone}</span> : null}
                  </button>
                  {onOpenQaChannel ? (
                    <QaChannelButton patientName={patient.displayName} onOpen={() => onOpenQaChannel(patient.patientId)} onToast={onToast} />
                  ) : null}
                </div>
                <ul className="recall-visit-list">
                  {patient.visits.map((visit) => (
                    <li className="recall-visit" key={visit.sessionId}>
                      <button className="recall-visit-open" type="button" onClick={() => onOpenSession(visit.sessionId)}>
                        <span className="recall-visit-date">{formatDate(visit.visitAt) || "—"}</span>
                        <span className="recall-visit-treatments" data-content>
                          {visit.treatments.map((tr, i) => (
                            <span className="recall-treatment" key={i}>{tr.phrase || [tr.brand || tr.product, tr.area].filter(Boolean).join(", ")}</span>
                          ))}
                        </span>
                        <span className="recall-visit-go" aria-hidden="true"><ChevronIcon /></span>
                      </button>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </>
      )}
      {result.similar.length ? (
        <div className="recall-similar">
          <span className="recall-similar-label"><SparkleIcon /> {t("recall.similarLabel")}</span>
          <p className="recall-similar-note">{t("recall.similarNote")}</p>
          <div className="lot-suggestions">
            {result.similar.map((s) => (
              <button className="lot-chip lot-chip-lot lot-chip-similar" key={s.lot} type="button" onClick={() => onRecallSimilar(s.lot)}>
                <span className="lot-chip-value" data-content>{s.lot}</span>
                <span className="lot-chip-count">{t("recall.chipCount", { n: s.patientCount })}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// --- Local icons (the shared set lacks a clock/camera/warn) ----------------------------------------
function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" focusable="false" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}
function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" focusable="false" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 8.5h2.5L9 6.5h6L16.5 8.5H19a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17v-7A1.5 1.5 0 0 1 5 8.5Z" />
      <circle cx="12" cy="13" r="3" />
    </svg>
  );
}
function WarnIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" focusable="false" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 4.5 21 19H3L12 4.5Z" />
      <path d="M12 10v4M12 16.5h.01" />
    </svg>
  );
}
