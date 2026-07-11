// Close-the-day sweep (AES-1004): the severity-ordered, session-grouped, resolve-in-place lens the
// Needs-input tab evolved into. It is a router + a list — every action opens the SAME focused
// resolver the item uses at its source (the inline assign/choose resolver, the visit in Active
// Session for a dose/verify/safety flag, or the Q&A inbox thread); it reimplements nothing.
import React from "react";
import type { AttentionItem, AttentionResponse, AttentionScope } from "../../../domain/appTypes";
import "../attention.css";
import { useT } from "../../../shared/i18n";
import { EmptyClinicalState } from "./MemoryCards";
import {
  TIER_TONE,
  attentionActionKey,
  attentionItemRoute,
  attentionTitleKey,
  groupAttentionItems,
  groupConfirmVisits,
  type AttentionRowUnit,
  type AttentionSectionKey,
  type FetchAttention,
} from "./attentionModel";

// Per-day dismissal for the opt-in end-of-day reminder (AES-1006) — a pure, non-blocking nudge.
const NUDGE_DISMISS_KEY = "engram.attention.nudgeDismissed";

function nudgeDismissedToday(dayKey: string): boolean {
  try {
    return window.localStorage.getItem(NUDGE_DISMISS_KEY) === dayKey;
  } catch {
    return false;
  }
}

function dismissNudgeToday(dayKey: string): void {
  try {
    window.localStorage.setItem(NUDGE_DISMISS_KEY, dayKey);
  } catch {
    /* private mode — the reminder simply reappears next open, never blocks */
  }
}

// The reminder is an *end-of-day* nudge — it only appears in the late-afternoon window, so it reads
// as "before you leave, clear what's open" rather than nagging mid-morning. Pure heuristic, no gate.
const END_OF_DAY_HOUR = 16;

function isEndOfDay(): boolean {
  return new Date().getHours() >= END_OF_DAY_HOUR;
}

export function AttentionSweep({
  fetchAttention,
  defaultScope,
  refreshSignal,
  clientItems = [],
  nudgeEnabled = false,
  onItemPrimary,
  onItemSelect,
}: {
  fetchAttention: FetchAttention;
  defaultScope: AttentionScope;
  refreshSignal: number;
  /** Client-only items the backend roll-up can't see (e.g. the device storage warning); merged into
   *  the sweep so they stay actionable alongside the server signals. */
  clientItems?: AttentionItem[];
  /** AES-1006 — opt-in end-of-day reminder; a pure dismissible prompt, never a gate. */
  nudgeEnabled?: boolean;
  onItemPrimary: (item: AttentionItem) => void;
  onItemSelect: (item: AttentionItem) => void;
}) {
  const t = useT();
  const [scope, setScope] = React.useState<AttentionScope>(defaultScope);
  const [feed, setFeed] = React.useState<AttentionResponse | null>(null);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState(false);
  // Items resolved during this sweep — for the "N of M cleared" progress (never completion pressure).
  const [actedIds, setActedIds] = React.useState<Set<string>>(() => new Set());
  const dayKey = new Date().toDateString();
  const [nudgeDismissed, setNudgeDismissed] = React.useState(() => nudgeDismissedToday(dayKey));

  React.useEffect(() => {
    let cancelled = false;
    setActedIds(new Set());
    void fetchAttention(scope)
      .then((result) => {
        if (cancelled) return;
        setFeed(result);
        setLoaded(true);
        setError(false);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchAttention, scope, refreshSignal]);

  const items = React.useMemo(() => [...clientItems, ...(feed?.items ?? [])], [clientItems, feed]);
  const { todaySections, earlierItems } = React.useMemo(() => groupAttentionItems(items), [items]);
  const total = items.length;
  const cleared = items.filter((item) => actedIds.has(item.id)).length;

  const markActed = (ids: string[]) =>
    setActedIds((current) => {
      const next = new Set(current);
      ids.forEach((id) => next.add(id));
      return next;
    });

  const handlePrimary = (item: AttentionItem) => {
    markActed([item.id]);
    onItemPrimary(item);
  };

  const renderRow = (item: AttentionItem) => (
    <AttentionRow
      key={item.id}
      item={item}
      acted={actedIds.has(item.id)}
      onPrimary={() => handlePrimary(item)}
      onSelect={attentionItemRoute(item) ? () => onItemSelect(item) : undefined}
    />
  );

  // A visit with ≥2 open confirmations collapses to one grouped row; its single action opens the
  // visit (onItemSelect) so the same per-source confirmations are walked in place (AES-1008).
  const renderUnit = (unit: AttentionRowUnit) => {
    if (unit.type === "single") return renderRow(unit.item);
    const openVisit = () => {
      markActed(unit.items.map((item) => item.id));
      onItemSelect(unit.items[0]);
    };
    return (
      <AttentionGroupRow
        key={unit.key}
        patientName={unit.patientName}
        count={unit.items.length}
        acted={unit.items.every((item) => actedIds.has(item.id))}
        onOpen={openVisit}
      />
    );
  };

  if (error && !loaded) {
    return (
      <div className="clinical-tab-panel" role="tabpanel">
        <EmptyClinicalState title={t("attention.offline.title")} copy={t("attention.offline.copy")} />
      </div>
    );
  }

  return (
    <div className="clinical-tab-panel attention-sweep" role="tabpanel">
      <div className="attention-sweep-head">
        <div className="attention-sweep-heading">
          <h2>{t("attention.sweep.title")}</h2>
          {total ? (
            <p className="attention-progress" aria-live="polite">
              {t("attention.progress", { cleared, total })}
            </p>
          ) : null}
        </div>
        <div className="attention-scope" role="group" aria-label={t("attention.scope.aria")}>
          {(["mine", "clinic"] as AttentionScope[]).map((value) => (
            <button
              key={value}
              type="button"
              className={scope === value ? "active" : ""}
              aria-pressed={scope === value}
              onClick={() => setScope(value)}
            >
              {t(`attention.scope.${value}`)}
            </button>
          ))}
        </div>
      </div>

      {nudgeEnabled && !nudgeDismissed && isEndOfDay() && feed && feed.counts.total > 0 ? (
        <div className="attention-nudge" role="status">
          <span>{t("attention.nudge", { n: feed.counts.total })}</span>
          <button
            type="button"
            className="attention-nudge-dismiss"
            onClick={() => {
              dismissNudgeToday(dayKey);
              setNudgeDismissed(true);
            }}
          >
            {t("attention.nudge.dismiss")}
          </button>
        </div>
      ) : null}

      {!loaded ? (
        <p className="clinical-helper">{t("attention.loading")}</p>
      ) : total === 0 ? (
        <EmptyClinicalState title={t("attention.empty.title")} copy={t("attention.empty.copy")} />
      ) : (
        <>
          {todaySections.map((section) => (
            <AttentionSection
              key={section.key}
              sectionKey={section.key}
              count={section.items.length}
              tone={TIER_TONE[section.tier]}
            >
              {groupConfirmVisits(section.items).map(renderUnit)}
            </AttentionSection>
          ))}
          {earlierItems.length ? (
            <AttentionSection sectionKey="earlier" count={earlierItems.length} tone="muted">
              {groupConfirmVisits(earlierItems).map(renderUnit)}
            </AttentionSection>
          ) : null}
        </>
      )}
    </div>
  );
}

function AttentionSection({
  sectionKey,
  count,
  tone,
  children,
}: {
  sectionKey: AttentionSectionKey | "earlier";
  count: number;
  tone: string;
  children: React.ReactNode;
}) {
  const t = useT();
  return (
    <section className={`attention-section attention-tone-${tone}`}>
      <h3 className="attention-section-head">
        <span>{t(`attention.section.${sectionKey}`)}</span>
        <span className="attention-section-count" aria-hidden="true">
          {count}
        </span>
      </h3>
      <div className="attention-list">{children}</div>
    </section>
  );
}

function AttentionRow({
  item,
  acted,
  onPrimary,
  onSelect,
}: {
  item: AttentionItem;
  acted: boolean;
  onPrimary: () => void;
  onSelect?: () => void;
}) {
  const t = useT();
  const tone = TIER_TONE[item.tier];
  const title = t(attentionTitleKey(item.kind));
  const actionLabel = t(attentionActionKey(item.kind));
  return (
    <div className={`attention-card attention-tone-${tone}${acted ? " attention-card-acted" : ""}`}>
      <button type="button" className="attention-card-body" onClick={onSelect} disabled={!onSelect}>
        <span className="attention-card-title">
          {title}
          {item.patientName ? (
            <>
              {" · "}
              {/* Patient name is clinical CONTENT — bidi-isolate so a Persian name renders cleanly. */}
              <bdi>{item.patientName}</bdi>
            </>
          ) : null}
        </span>
        {item.reason ? (
          // Reason is verbatim report-language content — pick per-line direction.
          <span className="attention-card-reason" dir="auto">
            {item.reason}
          </span>
        ) : null}
      </button>
      <button type="button" className="attention-card-action" onClick={onPrimary}>
        {acted ? t("attention.action.done") : actionLabel}
      </button>
    </div>
  );
}

// One row for a visit with several open confirmations: «<patient> — N to confirm». Both the body and
// the action open the visit, where the per-source confirmations are resolved in place (AES-1008).
function AttentionGroupRow({
  patientName,
  count,
  acted,
  onOpen,
}: {
  patientName: string | null;
  count: number;
  acted: boolean;
  onOpen: () => void;
}) {
  const t = useT();
  return (
    <div className={`attention-card attention-tone-amber attention-card-group${acted ? " attention-card-acted" : ""}`}>
      <button type="button" className="attention-card-body" onClick={onOpen}>
        <span className="attention-card-title">
          {/* Patient name is clinical CONTENT — bidi-isolate so a Persian name renders cleanly. */}
          {patientName ? <bdi>{patientName}</bdi> : <span>{t("attention.group.fallbackVisit")}</span>}
          {" — "}
          {t("attention.group.confirmCount", { n: count })}
        </span>
      </button>
      <button type="button" className="attention-card-action" onClick={onOpen}>
        {acted ? t("attention.action.done") : t("attention.group.action")}
      </button>
    </div>
  );
}
