import React from "react";
import type { AiUsageState, ApiFetch } from "../../domain/appTypes";
import { fetchAiUsage } from "../../services/api/client";

/**
 * Fair-use monthly AI usage/limit for the current clinic. Fetches on mount and re-fetches whenever
 * `refreshSignal` changes (the app bumps it after captures), so the calm usage surfaces stay current
 * without polling. Never throws to the caller — a failed load simply yields `state === null`, so the
 * usage UI stays hidden rather than intruding on capture.
 */
export function useAiUsage(apiFetch: ApiFetch, refreshSignal: unknown = 0): {
  state: AiUsageState | null;
  loading: boolean;
  refresh: () => void;
} {
  const [state, setState] = React.useState<AiUsageState | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [manualSignal, setManualSignal] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAiUsage(apiFetch)
      .then((next) => {
        if (!cancelled) setState(next);
      })
      .catch(() => {
        // Usage is informational only — a failed load must never disrupt capture, so stay silent.
        if (!cancelled) setState(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiFetch, refreshSignal, manualSignal]);

  const refresh = React.useCallback(() => setManualSignal((n) => n + 1), []);

  return { state, loading, refresh };
}
