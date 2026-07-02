import React from "react";
import type { AiUsageState, ApiFetch, AiUsageStatus } from "../../domain/appTypes";
import { Alert, Button, Card } from "../../shared/ui/primitives";
import { formatDate } from "../../shared/lib/datetime";
import { IS_DEV } from "../../shared/lib/config";
import { useT, type Translator } from "../../shared/i18n";
import { setAiUsageDev } from "../../services/api/client";

// Maps the calm status to the ring tone. `ok` reads as neutral/green (all-clear); `approaching` and
// `over` both read amber — restrained, never alarming (design-principles §7: warn, don't block).
const STATUS_TONE: Record<AiUsageStatus, "green" | "amber"> = {
  ok: "green",
  approaching: "amber",
  over: "amber",
};

/** A calm usage ring: a conic dial filled to `percent`, tinted by status, with the percent inside. */
function UsageRing({ percent, tone, label }: { percent: number; tone: "green" | "amber"; label: string }) {
  // Clamp the visual fill to 100% even when spend runs over (percentUsed can exceed 100).
  const filled = Math.max(0, Math.min(100, percent));
  return (
    <div
      className={`ai-usage-ring ai-usage-ring-${tone}`}
      style={{ ["--ai-usage-fill" as string]: `${filled}%` }}
      role="img"
      aria-label={label}
    >
      <span className="ai-usage-ring-value" aria-hidden="true">
        {label}
      </span>
    </div>
  );
}

function DevUsageControl({ apiFetch, onChanged }: { apiFetch: ApiFetch; onChanged: () => void }) {
  const t = useT();
  const [busy, setBusy] = React.useState(false);
  const jump = (percent: number) => {
    setBusy(true);
    void setAiUsageDev(apiFetch, percent)
      .catch(() => undefined)
      .finally(() => {
        setBusy(false);
        onChanged();
      });
  };
  return (
    <div className="ai-usage-dev">
      <span className="ai-usage-dev-label">{t("aiUsage.devTitle")}</span>
      <div className="ai-usage-dev-buttons">
        {[0, 50, 85, 110].map((percent) => (
          <Button key={percent} disabled={busy} onClick={() => jump(percent)} size="sm" type="button" variant="ghost">
            {t("aiUsage.devJump", { percent })}
          </Button>
        ))}
      </div>
    </div>
  );
}

function statusLine(t: Translator, status: AiUsageStatus): string {
  if (status === "over") return t("aiUsage.statusOver");
  if (status === "approaching") return t("aiUsage.statusApproaching");
  return t("aiUsage.statusOk");
}

/**
 * The calm "AI usage" card for Settings. Renders NOTHING when the clinic has no AI (Basic / zero-AI) —
 * there are no limits to show. Presentational: it takes the already-fetched state + an `apiFetch` used
 * only by the dev control. Tone stays neutral/green at ok and restrained amber at approaching/over.
 */
export function AiUsageCard({
  state,
  apiFetch,
  onRefresh,
}: {
  state: AiUsageState | null;
  apiFetch: ApiFetch;
  onRefresh: () => void;
}) {
  const t = useT();
  if (!state || !state.hasAi) return null;

  const tone = STATUS_TONE[state.status];
  const resetLabel = formatDate(state.resetAt, { year: "numeric", month: "long", day: "numeric" });
  const percentLabel = t("aiUsage.percentValue", { percent: state.percentUsed });

  return (
    <Card className="settings-group ai-usage-card">
      <div className="settings-group-head">
        <h2>{t("aiUsage.title")}</h2>
        <p>{t("aiUsage.subtitle")}</p>
      </div>

      <div className="ai-usage-body">
        <UsageRing percent={state.percentUsed} tone={tone} label={percentLabel} />
        <div className="ai-usage-copy">
          <p className={`ai-usage-status ai-usage-status-${tone}`}>{statusLine(t, state.status)}</p>
          <p className="ai-usage-percent-line">{t("aiUsage.percentUsed", { percent: state.percentUsed })}</p>
          <p className="ai-usage-reset">{t("aiUsage.resetsOn", { date: resetLabel })}</p>
        </div>
      </div>

      {state.paused ? (
        <Alert tone="amber" className="ai-usage-paused-note">
          {t("aiUsage.pausedNote")}
        </Alert>
      ) : null}

      {IS_DEV ? <DevUsageControl apiFetch={apiFetch} onChanged={onRefresh} /> : null}
    </Card>
  );
}
