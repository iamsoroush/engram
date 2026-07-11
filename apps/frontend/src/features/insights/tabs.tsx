import React from "react";
import type { ApiFetch } from "../../domain/appTypes";
import { useAppLang, useT, type Translator } from "../../shared/i18n";
import { Badge, Card, Skeleton } from "../../shared/ui/primitives";
import { Tabs } from "../../shared/ui/primitives";
import { PermissionDeniedState, RetryableErrorState } from "../../shared/ui/StateViews";
import {
  fetchOverview,
  fetchPatientInsights,
  fetchTeamInsights,
  fetchTreatmentInsights,
  type OverviewResponse,
  type PatientsResponse,
  type RangeParams,
  type TeamResponse,
  type TreatmentsResponse,
} from "./insightsApi";
import { BarList, ChartPlaceholder, ColumnChart, Donut, Heatmap, SERIES_COLORS, StatCard, useNum } from "./charts";

// --- Shared async loader ----------------------------------------------------------------------------
// `error` carries the HTTP status (or -1 for a non-HTTP failure) so callers can split 403 (permission,
// not retryable) from transient failures. `retry` re-runs the fetch for the retryable case.
type AsyncState<T> = { data: T | null; loading: boolean; error: number | null; retry: () => void };

function useAsync<T>(fn: () => Promise<T>, deps: React.DependencyList): AsyncState<T> {
  const [state, setState] = React.useState<{ data: T | null; loading: boolean; error: number | null }>({
    data: null,
    loading: true,
    error: null,
  });
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    let active = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => active && setState({ data, loading: false, error: null }))
      .catch((err) => active && setState({ data: null, loading: false, error: (err as { status?: number }).status ?? -1 }));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  const retry = React.useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, retry };
}

function SectionSkeleton() {
  return (
    <div className="stack">
      <Skeleton className="ins-skel-line" />
      <Skeleton className="ins-skel-block" />
    </div>
  );
}

/** A 403 here is a role mismatch (the route guard normally prevents reaching Insights at all, but a
 *  race or a server-side role change can still 403): show the shared permission state, no retry. Every
 *  other failure is retryable, so it gets the calm error + a Retry button (docs/ux/states.md). */
function LoadError({ status, onRetry }: { status: number | null; onRetry: () => void }) {
  if (status === 403) return <PermissionDeniedState className="ins-state" />;
  return <RetryableErrorState className="ins-state" onRetry={onRetry} />;
}

/** Localized weekday short labels, Monday-first (matches the backend's Python weekday()). */
function useWeekdayLabels(): string[] {
  const { lang } = useAppLang();
  return React.useMemo(() => {
    const fmt = new Intl.DateTimeFormat(lang === "fa" ? "fa-IR" : "en-US", { weekday: "short" });
    // 2024-01-01 is a Monday; index 0..6 → Mon..Sun.
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(Date.UTC(2024, 0, 1 + i))));
  }, [lang]);
}

/** Short bucket labels for a time series, shown on a few evenly-spaced columns to avoid clutter. */
function useColumnLabeler(count: number): (dateISO: string, index: number) => string | undefined {
  const { lang } = useAppLang();
  return React.useCallback(
    (dateISO, index) => {
      const showEvery = Math.max(1, Math.ceil(count / 5));
      if (index % showEvery !== 0 && index !== count - 1) return undefined;
      const fmt = new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian" : "en-US", { month: "short", day: "numeric" });
      const [y, m, d] = dateISO.split("-").map(Number);
      return fmt.format(new Date(Date.UTC(y, m - 1, d)));
    },
    [count, lang],
  );
}

// ====================================================================================================
// Overview
// ====================================================================================================
export function OverviewTab({ apiFetch, params, compare }: { apiFetch: ApiFetch; params: RangeParams; compare: boolean }) {
  const t = useT();
  const { data, loading, error, retry } = useAsync<OverviewResponse>(() => fetchOverview(apiFetch, params), [apiFetch, params]);
  const [series, setSeries] = React.useState<"visits" | "captures" | "newPatients">("visits");
  const label = useColumnLabeler(data?.activitySeries.length ?? 0);
  const weekdays = useWeekdayLabels();
  const num = useNum();

  if (loading) return <SectionSkeleton />;
  if (error || !data) return <LoadError status={error} onRetry={retry} />;

  const s = data.activitySeries;
  const kpiSpark = (key: "visits" | "captures" | "newPatients") => s.map((row) => row[key]);
  // Collapse the 7×24 UTC heatmap into 12 two-hour buckets for a phone-readable grid.
  const heat = data.busyHeatmap.map((row) =>
    Array.from({ length: 12 }, (_, b) => row[b * 2] + row[b * 2 + 1]),
  );
  const hourLabels = Array.from({ length: 12 }, (_, b) => (b % 2 === 0 ? num(b * 2) : ""));
  const nvr = data.newVsReturning;
  const needs = data.needsAttention;

  return (
    <div className="ins-panel">
      <div className="ins-kpi-grid">
        <StatCard label={t("insights.kpi.visits")} value={data.kpis.visits.current} delta={data.kpis.visits} spark={kpiSpark("visits")} compare={compare} />
        <StatCard label={t("insights.kpi.newPatients")} value={data.kpis.newPatients.current} delta={data.kpis.newPatients} spark={kpiSpark("newPatients")} compare={compare} />
        <StatCard label={t("insights.kpi.activePatients")} value={data.kpis.activePatients.current} delta={data.kpis.activePatients} compare={compare} />
        <StatCard label={t("insights.kpi.captures")} value={data.kpis.captures.current} delta={data.kpis.captures} spark={kpiSpark("captures")} compare={compare} />
      </div>

      <Card className="ins-card ins-card--wide">
        <div className="ins-card-head">
          <h2>{t("insights.activity.title")}</h2>
          <Tabs
            value={series}
            onChange={(v) => setSeries(v)}
            options={[
              { value: "visits", label: t("insights.kpi.visits") },
              { value: "captures", label: t("insights.kpi.captures") },
              { value: "newPatients", label: t("insights.kpi.newPatients") },
            ]}
          />
        </div>
        <ColumnChart
          emptyLabel={t("insights.empty")}
          columns={s.map((row, i) => ({
            key: row.date,
            label: label(row.date, i),
            segments: [{ seriesKey: series, value: row[series], color: SERIES_COLORS[0] }],
          }))}
        />
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.newReturning.title")}</h2></div>
        {nvr.new + nvr.returning === 0 ? (
          <ChartPlaceholder label={t("insights.empty")} variant="chart" />
        ) : (
          <div className="ins-split">
            <Donut
              centerValue={nvr.repeatRate == null ? "—" : `${num(Math.round(nvr.repeatRate * 100))}%`}
              centerLabel={t("insights.newReturning.repeat")}
              segments={[
                { label: t("insights.newReturning.new"), value: nvr.new, color: SERIES_COLORS[2] },
                { label: t("insights.newReturning.returning"), value: nvr.returning, color: SERIES_COLORS[0] },
              ]}
            />
          </div>
        )}
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head">
          <h2>{t("insights.busy.title")}</h2>
          <span className="muted ins-hint">{t("insights.busy.utc")}</span>
        </div>
        <div className="ins-heatmap-scroll">
          <Heatmap grid={heat} rowLabels={weekdays} colLabels={hourLabels} emptyLabel={t("insights.empty")} />
        </div>
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.needs.title")}</h2></div>
        <div className="ins-needs">
          <NeedTile label={t("insights.needs.unassigned")} value={needs.unassignedCaptures} />
          <NeedTile label={t("insights.needs.review")} value={needs.awaitingReview} />
          <NeedTile label={t("insights.needs.failed")} value={needs.failed} tone={needs.failed > 0 ? "warn" : undefined} />
        </div>
      </Card>
    </div>
  );
}

function NeedTile({ label, value, tone }: { label: string; value: number; tone?: "warn" }) {
  const num = useNum();
  return (
    <div className={`ins-need-tile${value > 0 ? " active" : ""}${tone === "warn" && value > 0 ? " warn" : ""}`}>
      <span className="ins-need-value">{num(value)}</span>
      <span className="ins-need-label">{label}</span>
    </div>
  );
}

// ====================================================================================================
// Team
// ====================================================================================================
export function TeamTab({ apiFetch, params }: { apiFetch: ApiFetch; params: RangeParams }) {
  const t = useT();
  const { lang } = useAppLang();
  const num = useNum();
  const { data, loading, error, retry } = useAsync<TeamResponse>(() => fetchTeamInsights(apiFetch, params), [apiFetch, params]);
  if (loading) return <SectionSkeleton />;
  if (error || !data) return <LoadError status={error} onRetry={retry} />;

  const active = data.members.filter((m) => m.visits + m.captures > 0);
  const relFmt = new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian" : "en-US", { month: "short", day: "numeric" });
  const roleLabel = (role: string) => {
    const key = `role.${role}`;
    return t(key) === key ? role : t(key);
  };

  return (
    <div className="ins-panel">
      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.team.workload")}</h2></div>
        <BarList
          emptyLabel={t("insights.empty")}
          items={active.map((m) => ({ label: m.name || t("insights.team.unnamed"), value: m.visits, content: true }))}
        />
      </Card>

      <Card className="ins-card ins-card--wide">
        <div className="ins-card-head"><h2>{t("insights.team.members")}</h2></div>
        {data.members.length === 0 ? (
          <ChartPlaceholder label={t("insights.empty")} variant="list" />
        ) : (
          <ul className="ins-member-list">
            {data.members.map((m) => (
              <li className="ins-member" key={m.userId}>
                <div className="ins-member-id">
                  <strong data-content="true">{m.name || t("insights.team.unnamed")}</strong>
                  <Badge tone="neutral">{roleLabel(m.role)}</Badge>
                </div>
                <div className="ins-member-stats">
                  <span>{t("insights.team.patientsN", { n: m.patients })}</span>
                  <span>{t("insights.team.visitsN", { n: m.visits })}</span>
                  <span>{t("insights.team.capturesN", { n: m.captures })}</span>
                </div>
                <div className="ins-member-foot muted">
                  {m.lastActiveAt
                    ? t("insights.team.lastActive", { when: relFmt.format(new Date(m.lastActiveAt)) })
                    : t("insights.team.neverActive")}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="muted ins-note">{t("insights.team.attributionNote")}</p>
    </div>
  );
}

// ====================================================================================================
// Patients
// ====================================================================================================
export function PatientsTab({ apiFetch, params }: { apiFetch: ApiFetch; params: RangeParams }) {
  const t = useT();
  const num = useNum();
  const { data, loading, error, retry } = useAsync<PatientsResponse>(() => fetchPatientInsights(apiFetch, params), [apiFetch, params]);
  const label = useColumnLabeler(data?.growth.buckets.length ?? 0);
  if (loading) return <SectionSkeleton />;
  if (error || !data) return <LoadError status={error} onRetry={retry} />;

  const ages = data.ageHistogram.filter((a) => a.band !== "unknown" || a.count > 0);
  const sexSegments = [
    { label: t("insights.sex.female"), value: data.sexSplit.female, color: SERIES_COLORS[1] },
    { label: t("insights.sex.male"), value: data.sexSplit.male, color: SERIES_COLORS[0] },
    { label: t("insights.sex.other"), value: data.sexSplit.other, color: SERIES_COLORS[2] },
    { label: t("insights.sex.unknown"), value: data.sexSplit.unknown, color: "var(--color-border-strong)" },
  ].filter((seg) => seg.value > 0);

  // Cumulative growth line: baseline (patients before the window) + running sum of new-per-bucket.
  let running = data.growth.baseline;
  const growthCols = data.growth.buckets.map((b, i) => {
    running += b.newPatients;
    return { key: b.date, label: label(b.date, i), segments: [{ seriesKey: "total", value: running, color: SERIES_COLORS[0] }] };
  });

  return (
    <div className="ins-panel">
      <Card className="ins-card ins-card--wide">
        <div className="ins-card-head"><h2>{t("insights.patients.recency")}</h2></div>
        <div className="ins-recency">
          <RecencyTile label={t("insights.patients.active")} sub={t("insights.patients.activeSub")} value={data.recency.active} />
          <RecencyTile label={t("insights.patients.lapsing")} sub={t("insights.patients.lapsingSub")} value={data.recency.lapsing} tone="lapsing" />
          <RecencyTile label={t("insights.patients.lapsed")} sub={t("insights.patients.lapsedSub")} value={data.recency.lapsed} tone="lapsed" />
        </div>
        {data.recency.neverVisited > 0 ? (
          <p className="muted ins-note">{t("insights.patients.neverVisited", { n: data.recency.neverVisited })}</p>
        ) : null}
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.patients.age")}</h2></div>
        <BarList
          emptyLabel={t("insights.empty")}
          items={ages.map((a) => ({ label: a.band === "unknown" ? t("insights.unknown") : a.band, value: a.count }))}
        />
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.patients.sex")}</h2></div>
        {sexSegments.length ? <Donut segments={sexSegments} centerValue={num(data.totalActive)} centerLabel={t("insights.patients.total")} /> : <ChartPlaceholder label={t("insights.empty")} variant="chart" />}
      </Card>

      <Card className="ins-card ins-card--wide">
        <div className="ins-card-head"><h2>{t("insights.patients.growth")}</h2></div>
        <ColumnChart columns={growthCols} emptyLabel={t("insights.empty")} />
      </Card>
    </div>
  );
}

function RecencyTile({ label, sub, value, tone }: { label: string; sub: string; value: number; tone?: "lapsing" | "lapsed" }) {
  const num = useNum();
  return (
    <div className={`ins-recency-tile${tone ? ` ${tone}` : ""}`}>
      <span className="ins-recency-value">{num(value)}</span>
      <span className="ins-recency-label">{label}</span>
      <span className="ins-recency-sub muted">{sub}</span>
    </div>
  );
}

// ====================================================================================================
// Treatments (Pro)
// ====================================================================================================
export function TreatmentsTab({ apiFetch, params, isPro }: { apiFetch: ApiFetch; params: RangeParams; isPro: boolean }) {
  const t = useT();
  const num = useNum();
  const label = useColumnLabeler(0);
  const { data, loading, error, retry } = useAsync<TreatmentsResponse | null>(
    async () => (isPro ? await fetchTreatmentInsights(apiFetch, params) : null),
    [apiFetch, params, isPro],
  );
  const mixLabel = useColumnLabeler(data?.mixSeries.length ?? 0);

  if (!isPro || error === 403) return <ProUpsell t={t} />;
  if (loading) return <SectionSkeleton />;
  if (error || !data) return <LoadError status={error} onRetry={retry} />;
  void label;

  const unitLabel = (unit: string) => {
    const key = `insights.unit.${unit}`;
    return t(key) === key ? unit : t(key);
  };

  return (
    <div className="ins-panel">
      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.tx.top")}</h2></div>
        <BarList emptyLabel={t("insights.empty")} items={data.topTreatments.map((x) => ({ label: x.name, value: x.count, content: true }))} />
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.tx.consumption")}</h2></div>
        {data.consumption.length ? (
          <div className="ins-consumption">
            {data.consumption.map((c) => (
              <div className="ins-consume-tile" key={c.unit}>
                <span className="ins-consume-total">{num(c.total, { maximumFractionDigits: 1 })}</span>
                <span className="ins-consume-unit">{unitLabel(c.unit)}</span>
                <span className="ins-consume-count muted">{t("insights.tx.acrossN", { n: c.count })}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="ins-empty">{t("insights.empty")}</p>
        )}
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.tx.products")}</h2></div>
        <BarList emptyLabel={t("insights.empty")} items={data.topProducts.map((x) => ({ label: x.name, value: x.count, content: true }))} />
      </Card>

      <Card className="ins-card ins-card--wide">
        <div className="ins-card-head"><h2>{t("insights.tx.mix")}</h2></div>
        <ColumnChart
          emptyLabel={t("insights.empty")}
          columns={data.mixSeries.map((row, i) => ({
            key: row.date,
            label: mixLabel(row.date, i),
            segments: [
              ...data.mixKeys.map((k, ki) => ({ seriesKey: k, value: (row as Record<string, number>)[k] || 0, color: SERIES_COLORS[ki % SERIES_COLORS.length] })),
              { seriesKey: "other", value: (row as Record<string, number>).other || 0, color: "var(--color-border-strong)" },
            ],
          }))}
        />
        <ul className="ins-legend ins-legend-row">
          {data.mixKeys.map((k, ki) => (
            <li key={k}><span className="ins-legend-swatch" style={{ background: SERIES_COLORS[ki % SERIES_COLORS.length] }} aria-hidden="true" /><span data-content="true">{k}</span></li>
          ))}
        </ul>
      </Card>

      <Card className="ins-card">
        <div className="ins-card-head"><h2>{t("insights.tx.byArea")}</h2></div>
        <BarList emptyLabel={t("insights.empty")} items={data.byArea.map((x) => ({ label: x.name, value: x.count, content: true }))} />
      </Card>
    </div>
  );
}

function ProUpsell({ t }: { t: Translator }) {
  return (
    <Card className="ins-card ins-upsell">
      <div className="ins-upsell-preview" aria-hidden="true">
        {[90, 62, 38].map((w) => (
          <div className="ins-bar-row" key={w}>
            <span className="ins-bar-label" />
            <span className="ins-bar-track"><span className="ins-bar-fill" style={{ inlineSize: `${w}%` }} /></span>
          </div>
        ))}
      </div>
      <div className="ins-upsell-cta">
        <Badge tone="blue">{t("insights.upsell.badge")}</Badge>
        <h3>{t("insights.upsell.title")}</h3>
        <p className="muted">{t("insights.upsell.body")}</p>
      </div>
    </Card>
  );
}
