import React from "react";
import type { CaptureSession } from "../../../domain/types";
import { sessionTreatmentReview, sessionConfirmedCarriedForward, textDirection } from "../captureModel";

/**
 * The session's "needs your confirmation" surface (Pro) — the synthesis's clinician-confirmation
 * items (ambiguous correction, carried-forward dose, low confidence, missing lot, free-text
 * uncertainty), with the carried-forward dose confirm action (Q3).
 *
 * Lifted out of the live report so it's actionable from EITHER the captures or the report view — the
 * doctor confirms a dose without toggling views ("act upon verifications" wherever they are).
 */
export function SessionConfirmations({
  session,
  onConfirmCarriedForward,
}: {
  session: CaptureSession | null;
  onConfirmCarriedForward?: (sessionId: string, key: string) => Promise<void>;
}) {
  const review = sessionTreatmentReview(session);
  const confirmedCarriedForward = new Set(sessionConfirmedCarriedForward(session));
  const [confirming, setConfirming] = React.useState<string | null>(null);
  if (!session || !review.length) return null;

  return (
    <section className="session-confirmations report-review" aria-label="Items that need your confirmation">
      <h3>Needs your confirmation</h3>
      <ul className="report-review-chips">
        {review.map((item, index) => {
          const isCarriedForward = item.category === "carried_forward" && Boolean(item.key);
          const isConfirmed = isCarriedForward && confirmedCarriedForward.has(item.key as string);
          return (
            <li
              className={`report-review-chip ${item.category}${isConfirmed ? " confirmed" : ""}`}
              dir={textDirection(item.reason)}
              key={`${index}-${item.reason.slice(0, 32)}`}
            >
              <span className="report-review-chip-reason">{item.reason}</span>
              {isCarriedForward && isConfirmed ? (
                <span className="report-review-chip-confirmed" aria-label="Dose confirmed">✓ confirmed</span>
              ) : isCarriedForward && onConfirmCarriedForward ? (
                <button
                  type="button"
                  className="report-review-confirm"
                  disabled={confirming === item.key}
                  onClick={async () => {
                    if (!item.key) return;
                    setConfirming(item.key);
                    try {
                      await onConfirmCarriedForward(session.id, item.key);
                    } finally {
                      setConfirming(null);
                    }
                  }}
                >
                  {confirming === item.key ? "Confirming…" : "Confirm dose"}
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
