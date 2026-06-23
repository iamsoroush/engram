import React from "react";

/**
 * Sticky, session-level "needs your confirmation" driver (Pro, unified layout). It counts ONLY
 * blockers — unconfirmed carried-forward doses + AI-created-patient identity — so it stays calm;
 * soft warnings (missing lot, low confidence) live inline in the report and are never counted here.
 * "Review" jumps to the consolidated verify region (dose confirmations + the verify-patient panel).
 * Renders nothing when there is nothing to confirm, so a clean visit shows no nag.
 */
export function SessionVerifyBar({ count, onReview }: { count: number; onReview: () => void }) {
  if (count <= 0) return null;
  return (
    <div className="session-verify-bar" role="status">
      <span className="session-verify-bar-icon" aria-hidden="true">
        ⚠
      </span>
      <span className="session-verify-bar-copy">
        {count} thing{count === 1 ? "" : "s"} to confirm before this visit is trusted
      </span>
      <button className="session-verify-bar-action" type="button" onClick={onReview}>
        Review →
      </button>
    </div>
  );
}
