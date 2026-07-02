import React from "react";
import type { ApiFetch, AuthSession } from "../../domain/appTypes";
import { useT } from "../../shared/i18n";
import { Button } from "../../shared/ui/primitives";
import { SelectMenu } from "../../shared/ui/SelectMenu";
import { Tabs } from "../../shared/ui/primitives";
import type { RangeKey, RangeParams } from "./insightsApi";
import { OverviewTab, PatientsTab, TeamTab, TreatmentsTab } from "./tabs";
import "./insights.css";

type InsightsTab = "overview" | "team" | "patients" | "treatments";
const RANGE_KEYS: RangeKey[] = ["this-week", "this-month", "last-3-months", "this-year"];
const RANGE_STORAGE_KEY = "engram-insights-range";

/**
 * Owner/admin Insights: clinic + individuals analytics over the data the platform already captures.
 * Deterministic, no revenue/scheduling metrics (that data does not exist). Chrome routes through the
 * i18n seam (`useT`); clinical CONTENT (treatment/product/area names, member names) is rendered
 * verbatim (`data-content`). The Treatments tab is Pro; Basic sees the upsell. Backend gates the
 * endpoints owner/admin + Pro. See `docs/ux/screens/insights.md`.
 */
export function InsightsScreen({ auth, apiFetch, onBack }: { auth: AuthSession; apiFetch: ApiFetch; onBack: () => void }) {
  const t = useT();
  const isPro = auth.tenant.tier !== "basic";
  const [tab, setTab] = React.useState<InsightsTab>("overview");
  const [range, setRange] = React.useState<RangeKey>(() => {
    try {
      const stored = window.localStorage.getItem(RANGE_STORAGE_KEY) as RangeKey | null;
      if (stored && RANGE_KEYS.includes(stored)) return stored;
    } catch {
      /* ignore */
    }
    return "this-month";
  });
  const [compare, setCompare] = React.useState(true);

  const setRangePersisted = (next: RangeKey) => {
    setRange(next);
    try {
      window.localStorage.setItem(RANGE_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  };

  // A stable params object so tabs don't refetch on every render.
  const params = React.useMemo<RangeParams>(() => ({ range }), [range]);

  const tabOptions: Array<{ value: InsightsTab; label: string }> = [
    { value: "overview", label: t("insights.tab.overview") },
    { value: "team", label: t("insights.tab.team") },
    { value: "patients", label: t("insights.tab.patients") },
    { value: "treatments", label: t("insights.tab.treatments") },
  ];
  const rangeOptions = RANGE_KEYS.map((value) => ({ value, label: t(`insights.range.${value}`) }));

  return (
    <div className="account-screen" data-screen="insights">
      <div className="account-header">
        <Button className="account-back" onClick={onBack} size="sm" type="button" variant="secondary">
          <span aria-hidden="true">←</span> {t("insights.back")}
        </Button>
        <h1>{t("insights.title")}</h1>
      </div>

      <div className="ins-controls">
        <SelectMenu ariaLabel={t("insights.rangeAria")} onChange={(v) => setRangePersisted(v as RangeKey)} options={rangeOptions} value={range} />
        <button
          className={`ins-compare${compare ? " on" : ""}`}
          type="button"
          aria-pressed={compare}
          onClick={() => setCompare((c) => !c)}
        >
          {t("insights.compare")}
        </button>
      </div>

      <div className="ins-tabs">
        <Tabs value={tab} onChange={(v) => setTab(v)} options={tabOptions} />
      </div>

      {tab === "overview" ? <OverviewTab apiFetch={apiFetch} params={params} compare={compare} /> : null}
      {tab === "team" ? <TeamTab apiFetch={apiFetch} params={params} /> : null}
      {tab === "patients" ? <PatientsTab apiFetch={apiFetch} params={params} /> : null}
      {tab === "treatments" ? <TreatmentsTab apiFetch={apiFetch} params={params} isPro={isPro} /> : null}
    </div>
  );
}
