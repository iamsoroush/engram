import type { AiUsageState } from "../../domain/appTypes";
import { Alert } from "../../shared/ui/primitives";
import { useT } from "../../shared/i18n";

/**
 * A calm, NON-BLOCKING inline notice near the capture flow. It never renders as a modal and never
 * disables a capture control (design-principles §1 capture-first, §7 warn-don't-block): it only informs
 * when AI processing is running low, and reassures — captures are still saved — once the monthly limit
 * is reached. Renders nothing for Basic (no AI), while there is plenty left, or on a failed load.
 */
export function AiUsageNotice({ state }: { state: AiUsageState | null }) {
  const t = useT();
  if (!state || !state.hasAi) return null;

  // Over/paused takes precedence over "approaching" — reassure that captures still save.
  if (state.paused || state.status === "over") {
    return (
      <Alert tone="amber" className="ai-usage-notice" role="status">
        {t("aiUsage.noticeReached")}
      </Alert>
    );
  }
  if (state.status === "approaching") {
    return (
      <Alert tone="amber" className="ai-usage-notice" role="status">
        {t("aiUsage.noticeApproaching")}
      </Alert>
    );
  }
  return null;
}
