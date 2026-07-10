import { useT } from "../i18n";
import { Button } from "./primitives";

/**
 * Shared, calm state views for two failure classes that must NOT look alike (see docs/ux/states.md):
 *
 * - `PermissionDeniedState` — a 403 role mismatch. Retrying can never help, so there is no Retry
 *   affordance; it explains the access boundary instead. Any owner/admin-gated surface maps its 403
 *   here rather than to a generic "try again".
 * - `RetryableErrorState` — a transient/retryable failure (network, 5xx). Reserves the "try again"
 *   copy + a Retry button, the only place retry belongs.
 */

function LockGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function PermissionDeniedState({ className }: { className?: string }) {
  const t = useT();
  return (
    <div className={["state-view", "state-view--permission", className].filter(Boolean).join(" ")} role="status">
      <span className="state-view-icon" aria-hidden="true">
        <LockGlyph />
      </span>
      <p className="state-view-title">{t("state.permissionDenied.title")}</p>
      <p className="state-view-body">{t("state.permissionDenied.body")}</p>
    </div>
  );
}

export function RetryableErrorState({
  message,
  onRetry,
  className,
}: {
  message?: string;
  onRetry: () => void;
  className?: string;
}) {
  const t = useT();
  return (
    <div className={["state-view", "state-view--error", className].filter(Boolean).join(" ")} role="alert">
      <p className="state-view-body">{message ?? t("state.loadError")}</p>
      <Button onClick={onRetry} size="sm" type="button" variant="secondary">
        {t("state.retry")}
      </Button>
    </div>
  );
}
