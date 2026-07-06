import React from "react";
import { useAppLang, useT } from "../../shared/i18n";

/**
 * Lightweight, dependency-free chart primitives for the Insights panel. Deliberately mostly
 * HTML/CSS (bars, columns, heatmap grid) so they mirror correctly in RTL for free — the app sets
 * `dir` on the document, and flex/grid honor it. Only the sparkline and donut are SVG (a decorative
 * glyph and a direction-agnostic ring). All numbers are localized (Persian digits + grouping under
 * fa) via `useNum`. These are presentational: no data fetching, no business logic.
 */

/** A locale-aware number formatter bound to the authed app language (Persian digits + grouping under fa). */
export function useNum(): (value: number, opts?: Intl.NumberFormatOptions) => string {
  const { lang } = useAppLang();
  return React.useCallback(
    (value, opts) => new Intl.NumberFormat(lang === "fa" ? "fa-IR" : "en-US", opts).format(value),
    [lang],
  );
}

// A calm, on-brand categorical palette (design tokens) for multi-series charts.
export const SERIES_COLORS = ["#075eff", "#6b3df0", "#0a9d6e", "#995c00", "#1d4ed8", "#b42318"];

/**
 * Shared empty-state block for charts. Keeps the card's visual weight (fixed min-height matching the
 * chart it replaces + dashed frame) so an all-empty panel reads as intentional, not broken.
 */
export function ChartPlaceholder({ label, variant = "chart" }: { label: string; variant?: "chart" | "heatmap" | "list" }) {
  const t = useT();
  return (
    <div className={`ins-placeholder ins-placeholder--${variant}`} role="status">
      <svg className="ins-placeholder-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 15l3-4 3 3 4-6" />
      </svg>
      <span className="ins-placeholder-label">{label}</span>
      <span className="ins-placeholder-hint">{t("insights.emptyHint")}</span>
    </div>
  );
}

// --- StatCard + Sparkline ---------------------------------------------------------------------------
export type Delta = { current: number; previous: number; pct: number | null };

export function StatCard({
  label,
  value,
  delta,
  spark,
  compare,
}: {
  label: string;
  value: number;
  delta?: Delta;
  spark?: number[];
  compare?: boolean;
}) {
  const num = useNum();
  return (
    <div className="ins-stat">
      <div className="ins-stat-label">{label}</div>
      <div className="ins-stat-value">{num(value)}</div>
      <div className="ins-stat-foot">
        {compare && delta ? <DeltaChip delta={delta} /> : <span />}
        {spark && spark.length > 1 ? <Sparkline points={spark} /> : null}
      </div>
    </div>
  );
}

/** Neutral, informational delta chip (never red-alarm — fewer visits is not inherently "bad"). */
export function DeltaChip({ delta }: { delta: Delta }) {
  const num = useNum();
  if (delta.pct == null) return <span className="ins-delta ins-delta-flat">—</span>;
  // Sign-indexed (no comparison operators) so the numbers read as data, not code.
  const dir = (["down", "flat", "up"] as const)[Math.sign(delta.pct) + 1];
  const arrow = ({ up: "▲", down: "▼", flat: "▬" } as const)[dir];
  return (
    <span className={`ins-delta ins-delta-${dir}`}>
      <span aria-hidden="true">{arrow}</span> {num(Math.abs(delta.pct), { maximumFractionDigits: 1 })}%
    </span>
  );
}

export function Sparkline({ points, width = 64, height = 20 }: { points: number[]; width?: number; height?: number }) {
  const { dir } = useAppLang();
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = max - min || 1;
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const coords = points.map((p, i) => {
    const x = dir === "rtl" ? width - i * step : i * step; // time flows start→end even in RTL
    const y = height - ((p - min) / span) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg className="ins-spark" viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <polyline points={coords.join(" ")} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// --- BarList (ranked horizontal bars) ---------------------------------------------------------------
export function BarList({
  items,
  emptyLabel,
  valueSuffix,
}: {
  items: Array<{ label: string; value: number; sublabel?: string; content?: boolean }>;
  emptyLabel: string;
  valueSuffix?: string;
}) {
  const num = useNum();
  if (!items.length) return <ChartPlaceholder label={emptyLabel} variant="list" />;
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="ins-barlist">
      {items.map((item, i) => (
        <li className="ins-bar-row" key={`${item.label}-${i}`}>
          <span className="ins-bar-label" {...(item.content ? { "data-content": "true" } : {})}>{item.label}</span>
          <span className="ins-bar-track">
            <span className="ins-bar-fill" style={{ inlineSize: `${Math.max((item.value / max) * 100, 2)}%`, background: SERIES_COLORS[0] }} />
          </span>
          <span className="ins-bar-value">
            {num(item.value)}
            {valueSuffix ? ` ${valueSuffix}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

// --- ColumnChart (time series; single or stacked) ---------------------------------------------------
export type Column = { key: string; label?: string; segments: Array<{ seriesKey: string; value: number; color: string }> };

export function ColumnChart({ columns, height = 128, emptyLabel }: { columns: Column[]; height?: number; emptyLabel?: string }) {
  const totals = columns.map((c) => c.segments.reduce((s, seg) => s + seg.value, 0));
  const max = Math.max(...totals, 1);
  const nonEmpty = totals.some((t) => t > 0);
  if (!nonEmpty && emptyLabel) return <ChartPlaceholder label={emptyLabel} variant="chart" />;
  return (
    <div className="ins-columns" style={{ blockSize: height }}>
      {columns.map((col, i) => (
        <div className="ins-col" key={col.key} title={col.label || col.key}>
          <div className="ins-col-stack">
            {col.segments.map((seg) => (
              <span
                key={seg.seriesKey}
                className="ins-col-seg"
                style={{ blockSize: `${(seg.value / max) * 100}%`, background: seg.color }}
              />
            ))}
          </div>
          {col.label ? <span className="ins-col-label">{col.label}</span> : null}
        </div>
      ))}
    </div>
  );
}

// --- Donut ------------------------------------------------------------------------------------------
export function Donut({
  segments,
  centerValue,
  centerLabel,
}: {
  segments: Array<{ label: string; value: number; color: string }>;
  centerValue?: string;
  centerLabel?: string;
}) {
  const num = useNum();
  const total = segments.reduce((s, seg) => s + seg.value, 0);
  const radius = 42;
  const circ = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="ins-donut-wrap">
      <svg className="ins-donut" viewBox="0 0 100 100" width={112} height={112}>
        <circle cx={50} cy={50} r={radius} fill="none" stroke="var(--color-border)" strokeWidth={12} />
        {total > 0 &&
          segments.map((seg) => {
            const len = (seg.value / total) * circ;
            const dash = <circle
              key={seg.label}
              cx={50}
              cy={50}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={12}
              strokeDasharray={`${len} ${circ - len}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 50 50)"
            />;
            offset += len;
            return dash;
          })}
        {centerValue ? (
          <text x={50} y={49} textAnchor="middle" className="ins-donut-center-value">{centerValue}</text>
        ) : null}
        {centerLabel ? (
          <text x={50} y={62} textAnchor="middle" className="ins-donut-center-label">{centerLabel}</text>
        ) : null}
      </svg>
      <ul className="ins-legend">
        {segments.map((seg) => (
          <li key={seg.label}>
            <span className="ins-legend-swatch" style={{ background: seg.color }} aria-hidden="true" />
            {seg.label} <strong>{num(seg.value)}</strong>
            {total > 0 ? <span className="muted"> · {num(Math.round((seg.value / total) * 100))}%</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Heatmap (day-of-week × hour) -------------------------------------------------------------------
export function Heatmap({
  grid,
  rowLabels,
  colLabels,
  emptyLabel,
}: {
  grid: number[][];
  rowLabels: string[];
  colLabels: string[];
  emptyLabel: string;
}) {
  const max = Math.max(...grid.flat(), 0);
  if (max === 0) return <ChartPlaceholder label={emptyLabel} variant="heatmap" />;
  return (
    <div className="ins-heatmap" style={{ gridTemplateColumns: `auto repeat(${colLabels.length}, 1fr)` }}>
      <span />
      {colLabels.map((c, i) => (
        <span className="ins-heat-col-label" key={`c${i}`}>{c}</span>
      ))}
      {grid.map((row, r) => (
        <React.Fragment key={`r${r}`}>
          <span className="ins-heat-row-label">{rowLabels[r]}</span>
          {row.map((v, c) => (
            <span
              className="ins-heat-cell"
              key={`r${r}c${c}`}
              title={`${rowLabels[r]} · ${colLabels[c]}: ${v}`}
              style={{ background: v === 0 ? "var(--color-surface-soft)" : `color-mix(in srgb, ${SERIES_COLORS[0]} ${Math.round((v / max) * 100)}%, var(--color-surface))` }}
            />
          ))}
        </React.Fragment>
      ))}
    </div>
  );
}
