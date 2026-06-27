import React from "react";
import { useT } from "../../../shared/i18n";

/**
 * Sticky, session-level "needs your confirmation" driver (Pro, unified layout). It counts ONLY
 * blockers — unconfirmed carried-forward doses + AI-created-patient identity — so it stays calm;
 * soft warnings (missing lot, low confidence) live inline in the report and are never counted here.
 * "Review" jumps to the consolidated verify region (dose confirmations + the verify-patient panel).
 * Renders nothing when there is nothing to confirm, so a clean visit shows no nag.
 */
export function SessionVerifyBar({ count, onReview }: { count: number; onReview: () => void }) {
  const t = useT();
  if (count <= 0) return null;
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
