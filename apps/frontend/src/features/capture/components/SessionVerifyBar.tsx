import React from "react";
import { useT } from "../../../shared/i18n";

/**
 * Sticky, session-level "needs your confirmation" driver (Pro, unified layout). It counts ONLY
 * blockers — unconfirmed carried-forward doses + AI-created-patient identity — so it stays calm;
 * soft warnings (missing lot, low confidence) live inline in the report and are never counted here.
 * "Review" jumps to the consolidated verify region (dose confirmations + the verify-patient panel).
 *
 * While the report is still being synthesized (`pending`) and there are no blockers yet, it shows a
 * quiet "Checks pending · organizing" state instead of nothing — so an empty bar reads as "all good"
 * ONLY once analysis has actually run, never while checks are still in flight. It renders nothing at
 * all when the report is settled AND nothing needs confirming (a clean, checked visit shows no nag).
 */
export function SessionVerifyBar({ count, onReview, pending = false }: { count: number; onReview: () => void; pending?: boolean }) {
  const t = useT();
  if (count <= 0) {
    if (!pending) return null;
    return (
      <div className="session-verify-bar session-verify-bar-pending" role="status" aria-live="polite">
        <span className="session-verify-bar-dot" aria-hidden="true" />
        <span className="session-verify-bar-copy">{t("verify.checksPending")}</span>
      </div>
    );
  }
  return (
    <div className="session-verify-bar" role="status">
      <span className="session-verify-bar-icon" aria-hidden="true">
        ⚠
      </span>
      <span className="session-verify-bar-copy">{t("verify.toConfirm", { count })}</span>
      <button className="session-verify-bar-action" type="button" onClick={onReview}>
        {t("verify.review")}
        <span className="verify-arrow" aria-hidden="true">
          →
        </span>
      </button>
    </div>
  );
}
