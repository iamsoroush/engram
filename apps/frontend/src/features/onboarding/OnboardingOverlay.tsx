import React from "react";
import { dirFor, type Lang, translate } from "../../shared/i18n";
import { Button, Card } from "../../shared/ui/primitives";

type StepDef = { id: string; kind: "modal" } | { id: string; kind: "spotlight"; target: string; live?: boolean };

const CAPTURE_BAR = '[data-onboarding="capture-bar"]';

/**
 * Tour steps, tier-accurate. Basic is zero-AI (capture + deterministic organize), so its third step
 * describes saving/organizing — never AI report drafting — and its fourth step is a Pro upsell. Pro
 * describes AI report synthesis + its patient-memory / Q&A tools.
 */
function buildSteps(tier: string): StepDef[] {
  const isPro = tier !== "basic";
  return [
    { id: "welcome", kind: "modal" },
    { id: "capture", kind: "spotlight", target: CAPTURE_BAR, live: true },
    { id: isPro ? "organizePro" : "organizeBasic", kind: "modal" },
    { id: isPro ? "proTools" : "proCallout", kind: "modal" },
    { id: "done", kind: "modal" },
  ];
}

/** Track a target element's viewport rect while the spotlight step is active (cheap polling + events). */
function useTargetRect(selector: string | null): DOMRect | null {
  const [rect, setRect] = React.useState<DOMRect | null>(null);
  // Layout effect so the first painted frame is already the spotlight (no flash of the modal fallback).
  React.useLayoutEffect(() => {
    if (!selector) {
      setRect(null);
      return;
    }
    const measure = () => {
      const el = document.querySelector(selector);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    measure();
    const interval = window.setInterval(measure, 250);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [selector]);
  return rect;
}

type Translator = (key: string, vars?: Record<string, string | number>) => string;

/**
 * First-run guided "capture your first visit" for a freshly signed-up founder. A short, animated,
 * skippable tour: welcome → a **spotlight** on the live capture bar that waits for a real first
 * capture → "it organizes itself" → (Pro) a tools step → a finish step that can jump to inviting the
 * team. Rendered in the founder's app language (fa/en + RTL). Hides itself while a capture sheet is
 * open so the founder can actually capture during the live step.
 */
export function OnboardingOverlay({
  lang,
  displayName,
  tier,
  captureCount,
  captureDialogOpen,
  canInviteTeam,
  onInviteTeam,
  onSeePlan,
  onFinish,
}: {
  lang: Lang;
  displayName: string;
  tier: string;
  captureCount: number;
  captureDialogOpen: boolean;
  canInviteTeam: boolean;
  onInviteTeam: () => void;
  onSeePlan: () => void;
  onFinish: () => void;
}) {
  const steps = React.useMemo(() => buildSteps(tier), [tier]);
  const [index, setIndex] = React.useState(0);
  const step = steps[index];
  const t = React.useCallback<Translator>((key, vars) => translate(lang, key, vars), [lang]);
  const dir = dirFor(lang);

  const isLiveStep = step.kind === "spotlight" && Boolean(step.live);
  const next = React.useCallback(() => setIndex((i) => Math.min(i + 1, steps.length - 1)), [steps.length]);

  // Live first-capture: remember the count when the live step opens; advance once it increases.
  const baselineRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (!isLiveStep) {
      baselineRef.current = null;
      return;
    }
    if (baselineRef.current === null) {
      baselineRef.current = captureCount;
    } else if (captureCount > baselineRef.current) {
      baselineRef.current = null;
      next();
    }
  }, [isLiveStep, captureCount, next]);

  // While a capture sheet is open, get out of the way so the founder can capture during the live step.
  const targetSelector = step.kind === "spotlight" && !captureDialogOpen ? step.target : null;
  const rect = useTargetRect(targetSelector);
  if (captureDialogOpen) return null;

  const progress = t("onboarding.progress", { n: index + 1, total: steps.length });
  const isLast = index === steps.length - 1;
  const title = step.id === "welcome" ? t("onboarding.welcome.title", { name: displayName }) : t(`onboarding.${step.id}.title`);
  const body = t(`onboarding.${step.id}.body`);

  const dots = (
    <div aria-hidden className="onboarding-dots">
      {steps.map((s, i) => (
        <span className={`onboarding-dot ${i === index ? "active" : ""}`} key={s.id} />
      ))}
    </div>
  );

  // Spotlight step: dim around the live capture bar, pulse a ring on it, and float a coachmark above.
  if (step.kind === "spotlight" && rect) {
    const pad = 8;
    const top = Math.max(0, rect.top - pad);
    const left = Math.max(0, rect.left - pad);
    const width = rect.width + pad * 2;
    const height = rect.height + pad * 2;
    return (
      <div className="onboarding-spotlight" dir={dir} role="dialog" aria-modal="true">
        <div className="onboarding-dim" style={{ left: 0, top: 0, width: "100%", height: top }} />
        <div className="onboarding-dim" style={{ left: 0, top: top + height, width: "100%", height: `calc(100vh - ${top + height}px)` }} />
        <div className="onboarding-dim" style={{ left: 0, top, width: left, height }} />
        <div className="onboarding-dim" style={{ left: left + width, top, width: `calc(100vw - ${left + width}px)`, height }} />
        <div className="onboarding-ring" style={{ left, top, width, height }} />
        <div className="onboarding-bubble" style={{ left: 12, right: 12, bottom: `calc(100vh - ${top}px + 12px)` }}>
          <span className="onboarding-step-index">{progress}</span>
          <h2>{title}</h2>
          <p>{body}</p>
          <div className="onboarding-actions">
            <button className="auth-link" onClick={onFinish} type="button">
              {t("onboarding.skip")}
            </button>
            <Button onClick={next} type="button" variant="secondary">
              {t(isLiveStep ? "onboarding.later" : "onboarding.next")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Modal step (and the fallback if a spotlight target can't be measured yet).
  return (
    <div className="onboarding-overlay" dir={dir} role="dialog" aria-modal="true">
      <Card className="onboarding-card">
        <span className="onboarding-step-index">{progress}</span>
        <h2>{title}</h2>
        <p>{body}</p>
        {step.id === "proCallout" ? (
          <Button onClick={onSeePlan} type="button" variant="secondary">
            {t("onboarding.seePlan")}
          </Button>
        ) : null}
        {dots}
        <div className="onboarding-actions">
          {isLast ? (
            <>
              {canInviteTeam ? (
                <button className="auth-link" onClick={onInviteTeam} type="button">
                  {t("onboarding.inviteTeam")}
                </button>
              ) : (
                <span />
              )}
              <Button onClick={onFinish} type="button">
                {t("onboarding.finish")}
              </Button>
            </>
          ) : (
            <>
              <button className="auth-link" onClick={onFinish} type="button">
                {t("onboarding.skip")}
              </button>
              <Button onClick={next} type="button">
                {t("onboarding.next")}
              </Button>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
