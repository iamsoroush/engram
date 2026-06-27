import React from "react";

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
  isPersian?: boolean;
}) {
  const [rated, setRated] = React.useState<number | null>(null);
  const t = isPersian
    ? { prompt: "این گزارش مفید بود؟", up: "مفید بود", down: "نیاز به اصلاح", thanks: "ممنون از بازخورد شما" }
    : { prompt: "Was this report helpful?", up: "Helpful", down: "Needs work", thanks: "Thanks — noted" };

  const rate = (value: number) => {
    if (rated !== null) return;
    setRated(value);
    void onRate(value);
  };

  return (
    <div className="report-feedback-bar" dir={isPersian ? "rtl" : "ltr"}>
      {rated === null ? (
        <>
          <span className="report-feedback-prompt">{t.prompt}</span>
          <span className="report-feedback-actions">
            {/* Icon-only thumbs — the label lives in aria-label/title (tooltip), not on the button. */}
            <button type="button" className="report-feedback-btn" onClick={() => rate(1)} aria-label={t.up} title={t.up}>
              👍
            </button>
            <button type="button" className="report-feedback-btn" onClick={() => rate(-1)} aria-label={t.down} title={t.down}>
              👎
            </button>
          </span>
        </>
      ) : (
        <span className="report-feedback-thanks" aria-live="polite">
          {rated === 1 ? "✓ " : ""}
          {t.thanks}
        </span>
      )}
    </div>
  );
}
