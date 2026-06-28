import React from "react";
import { useAppLang } from "../../../shared/i18n";

/**
 * A lightweight thumbs rating on the synthesized report (eval golden-set harvester; eval-epic §1b).
 * One tap records a +1/-1 signal via `onRate`, then collapses to a calm thank-you — never a blocker,
 * never a form. Bilingual + RTL-aware: labels follow the report language (Persian → RTL).
 */
export function ReportFeedbackBar({
  onRate,
  isPersian,
}: {
  onRate: (rating: number) => void | Promise<void>;
  // Kept for callers that still pass it; chrome now follows the app language via the i18n seam.
  isPersian?: boolean;
}) {
  const { t, dir } = useAppLang();
  const [rated, setRated] = React.useState<number | null>(null);

  const rate = (value: number) => {
    if (rated !== null) return;
    setRated(value);
    void onRate(value);
  };

  return (
    <div className="report-feedback-bar" dir={dir}>
      {rated === null ? (
        <>
          <span className="report-feedback-prompt">{t("feedback.prompt")}</span>
          <span className="report-feedback-actions">
            {/* Icon-only thumbs — the label lives in aria-label/title (tooltip), not on the button. */}
            <button
              type="button"
              className="report-feedback-btn"
              onClick={() => rate(1)}
              aria-label={t("feedback.helpful")}
              title={t("feedback.helpful")}
            >
              👍
            </button>
            <button
              type="button"
              className="report-feedback-btn"
              onClick={() => rate(-1)}
              aria-label={t("feedback.needsWork")}
              title={t("feedback.needsWork")}
            >
              👎
            </button>
          </span>
        </>
      ) : (
        <span className="report-feedback-thanks" aria-live="polite">
          {rated === 1 ? "✓ " : ""}
          {t("feedback.thanks")}
        </span>
      )}
    </div>
  );
}
