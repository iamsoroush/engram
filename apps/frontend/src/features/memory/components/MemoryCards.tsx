// Shared presentational cards/pills for the Clinical Memory screens.
// Extracted verbatim from MemoryScreens.tsx (no behavior change).
import React from "react";
import type { LineupCard as LineupCardModel, LineupCardHero, PatientMemoryHistory } from "../../../domain/appTypes";
import type { CaptureSession } from "../../../domain/types";
import { Badge, Button, Card } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";
import { LastVisitStrip } from "../../aesthetics/LastVisitStrip";
import { ClinicalTone, NeedsInputCardItem, PatientBadge, TimelineSessionModel, memoryTextDirection, latestSessionTime, captureCounts, sessionTimeLabel, formatSessionTime, avatarInitials } from "./memoryModel";
import { NeedsInputDecisionIcon, SparkleIcon, ChevronIcon, captureTypeIcon } from "./MemoryIcons";

export function AssistantStatusPill({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="assistant-status-pill" role="status">
      {icon}
      <span>{children}</span>
    </div>
  );
}

export function ClinicalSection({
  badge,
  badgeTone = "blue",
  children,
  title,
}: {
  badge?: string;
  badgeTone?: "blue" | "green" | "amber";
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="clinical-section">
      <div className="clinical-section-heading">
        <h2>{title}</h2>
        {badge ? <Badge tone={badgeTone}>{badge}</Badge> : null}
      </div>
      {children}
    </section>
  );
}

export function ClinicalMemoryCard({
  actionLabel,
  children,
  className,
  tone = "blue",
  onSelect,
  onAction,
}: {
  actionLabel?: string;
  children: React.ReactNode;
  className?: string;
  tone?: ClinicalTone;
  onSelect?: () => void;
  onAction?: () => void;
}) {
  return (
    <Card
      className={["clinical-row", onSelect ? "clinical-row-selectable" : "", `clinical-row-${tone}`, className].filter(Boolean).join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      {children}
      {actionLabel && onAction ? (
        <Button
          onClick={(event) => {
            event.stopPropagation();
            onAction();
          }}
          size="sm"
          type="button"
          variant={tone === "amber" ? "secondary" : "default"}
        >
          {actionLabel}
          <ChevronIcon />
        </Button>
      ) : (
        <span className="patient-row-chevron" aria-hidden="true">
          <ChevronIcon />
        </span>
      )}
    </Card>
  );
}

export function VisitCard({
  primaryActionLabel,
  session,
  statusLabel,
  summary,
  title,
  tone,
  onSelect,
  onPrimaryAction,
}: {
  primaryActionLabel?: string;
  session: CaptureSession;
  statusLabel: string;
  summary: string;
  title: string;
  tone: ClinicalTone;
  onSelect?: () => void;
  onPrimaryAction?: () => void;
}) {
  return (
    <Card
      className={["clinical-row", "visit-card", onSelect ? "clinical-row-selectable" : "", `clinical-row-${tone}`].join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      <Avatar label={session.patientName || title} tone={tone} />
      <div className="clinical-row-copy">
        <div className="visit-card-title-row">
          <h3>{title}</h3>
          <Badge tone={tone}>{statusLabel}</Badge>
        </div>
        <VisitMetadata session={session} tone={tone} />
        <p>{summary}</p>
        <CaptureChips session={session} tone={tone} />
      </div>
      <div className="visit-card-actions">
        {primaryActionLabel && onPrimaryAction ? (
          <Button
            onClick={(event) => {
              event.stopPropagation();
              onPrimaryAction();
            }}
            size="sm"
            type="button"
            variant={tone === "amber" ? "secondary" : "default"}
          >
            {primaryActionLabel}
            <ChevronIcon />
          </Button>
        ) : (
          <span className="patient-row-chevron" aria-hidden="true">
            <ChevronIcon />
          </span>
        )}
      </div>
    </Card>
  );
}

export function NeedsInputDecisionCard({
  item,
  onSelect,
  onPrimaryAction,
}: {
  item: NeedsInputCardItem;
  onSelect?: () => void;
  onPrimaryAction: () => void;
}) {
  const t = useT();
  return (
    <Card
      className={["needs-input-card", onSelect ? "clinical-row-selectable" : "", `needs-input-card-${item.tone}`].join(" ")}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      <Avatar label={item.title} tone={item.tone === "purple" ? "blue" : item.tone} />
      <div className="needs-input-card-icon" aria-hidden="true">
        <NeedsInputDecisionIcon icon={item.icon} />
      </div>
      <div className="needs-input-card-copy">
        <div className="needs-input-title-row">
          <h3>{item.title}</h3>
        </div>
        <div className="visit-metadata" aria-label={t("memcard.decisionContext")}>
          {item.contextLabel ? (
            // For patient-bound decisions contextLabel is a patient name (shown under a "Patient" label);
            // for the storage warning it is a standalone phrase with no value to pair it with.
            item.kind === "review-storage" ? (
              <div>
                <span>{item.contextLabel}</span>
              </div>
            ) : (
              <div>
                <span>{t("memcard.patientLabel")}</span>
                <strong data-content>{item.contextLabel}</strong>
              </div>
            )
          ) : null}
          {item.sessionLabel ? (
            <div>
              <span>{t("memcard.sessionLabel")}</span>
              <strong data-content>{item.sessionLabel}</strong>
            </div>
          ) : null}
          {item.needsInputSinceLabel ? (
            <div className="visit-metadata-attention">
              <span>{t("memcard.needsInputSinceLabel")}</span>
              <strong data-content>{item.needsInputSinceLabel}</strong>
            </div>
          ) : null}
        </div>
        <p data-content>{item.explanation}</p>
        {item.session && item.kind !== "choose-patient" ? <CaptureChips session={item.session} tone={item.tone === "purple" ? "blue" : item.tone} /> : null}
      </div>
      {item.possiblePatients?.length ? <PossiblePatientOptions patients={item.possiblePatients} /> : null}
      <div className="needs-input-card-actions">
        <Button
          onClick={(event) => {
            event.stopPropagation();
            onPrimaryAction();
          }}
          size="sm"
          type="button"
        >
          {item.actionLabel}
        </Button>
      </div>
    </Card>
  );
}

export function PossiblePatientOptions({ patients }: { patients: string[] }) {
  const t = useT();
  return (
    <div className="possible-patients" aria-label={t("memcard.possiblePatients")}>
      {patients.slice(0, 3).map((patient) => (
        <div className="possible-patient" key={patient}>
          <span data-content>{avatarInitials(patient).slice(0, 1)}</span>
          <strong data-content>{patient}</strong>
        </div>
      ))}
    </div>
  );
}

export function VisitMetadata({ session, tone }: { session: CaptureSession; tone: ClinicalTone }) {
  const t = useT();
  const patientName = session.patientName || session.patientId;
  const inputTime = formatSessionTime(latestSessionTime(session), t);
  const showNeedsInputSince = tone === "amber" && !patientName;
  const showUpdatedTodayStatus = tone === "blue";
  return (
    <div className="visit-metadata" aria-label={t("memcard.visitDetails")}>
      {patientName ? (
        <div>
          <span>{t("memcard.patientLabel")}</span>
          <strong data-content>{patientName}</strong>
        </div>
      ) : null}
      <div>
        <span>{t("memcard.sessionLabel")}</span>
        <strong data-content>{sessionTimeLabel(session, t)}</strong>
      </div>
      {showNeedsInputSince ? (
        <div className="visit-metadata-attention">
          <span>{t("memcard.needsInputSinceLabel")}</span>
          <strong data-content>{inputTime}</strong>
        </div>
      ) : showUpdatedTodayStatus ? (
        <div className="visit-metadata-success">
          <span>{t("memcard.updatedLabel")}</span>
          <strong data-content>{formatSessionTime(latestSessionTime(session), t)}</strong>
        </div>
      ) : (
        <div>
          <span>{t("memcard.updatedLabel")}</span>
          <strong data-content>{formatSessionTime(latestSessionTime(session), t)}</strong>
        </div>
      )}
    </div>
  );
}

// The edit-patient form (controlled open). The "Edit details" trigger lives in the patient-detail
// action row so it sits beside "Share with patient" with matched styling.
export function PatientRow({
  actionLabel,
  badges,
  latestVisitLabel,
  patientName,
  summary,
  summaryStatus,
  isPro = false,
  tone = "green",
  onAction,
  onSelect,
}: {
  actionLabel?: string;
  badges: PatientBadge[];
  latestVisitLabel: string | null;
  patientName: string;
  summary: string;
  summaryStatus?: string;
  isPro?: boolean;
  tone?: ClinicalTone;
  onAction: () => void;
  onSelect: () => void;
}) {
  const t = useT();
  return (
    <ClinicalMemoryCard actionLabel={actionLabel} className="clinical-patient-row" tone={tone} onAction={onAction} onSelect={onSelect}>
      <Avatar label={patientName} tone={tone} />
      <div className="clinical-row-copy">
        <h3 data-content>{patientName}</h3>
        {latestVisitLabel ? <span className="patient-latest-visit" data-content>{latestVisitLabel}</span> : null}
        <MemorySummary text={summary} status={summaryStatus} isPro={isPro} />
        <div className="patient-memory-badges" aria-label={t("memcard.patientMemoryStatus")}>
          {badges.map((badge) => (
            // Style on the badge's stable `kind`, not its localized text (the old string-match broke under fa).
            <span className={`patient-memory-badge ${badge.kind === "needs-input" ? "needs-input" : badge.kind === "complete" ? "verified" : ""}`} key={badge.label}>
              {badge.label}
            </span>
          ))}
        </div>
      </div>
    </ClinicalMemoryCard>
  );
}

// Pick the base direction per text so a mostly-English line keeps an LTR base (an embedded RTL
// name stays a coherent isolated run) while predominantly-Persian/Arabic content reads RTL.
export function MemorySpark({ working }: { working?: boolean }) {
  return (
    <span className={`ai-spark${working ? " working" : ""}`} aria-hidden="true">
      <SparkleIcon />
    </span>
  );
}

export function MemoryUpdatingPill({ label }: { label?: string }) {
  const t = useT();
  return (
    <span className="memory-updating-pill">
      <span className="memory-updating-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {label ?? t("memcard.organizingMemory")}…
    </span>
  );
}

// The patient summary line on a card. Keeps the current text legible while a refresh is in flight
// (a shimmer sweep + "Organizing memory" cue), then fades the new text in when it settles. The
// `key={text}` remounts on a content swap so the fade-in plays.
export function MemorySummary({ text, status, isPro }: { text: string; status?: string; isPro: boolean }) {
  const updating = status === "updating";
  return (
    <div className={`patient-memory-summary${updating ? " updating" : ""}`}>
      <p className="patient-memory-summary-text" dir={memoryTextDirection(text)} key={text}>
        {isPro ? <MemorySpark working={updating} /> : null}
        <span className="memory-text" data-content>{text}</span>
        <span className="memory-sweep" aria-hidden="true" />
      </p>
      {updating ? <MemoryUpdatingPill /> : null}
    </div>
  );
}

// The richer "patient history" brief atop the timeline. Pro renders titled prose sections; Basic
// renders a structural recent-visits recap. Same updating→ready treatment as the card summary.
export function PatientHistoryBlock({
  history,
  isPro,
  loading,
  fallbackSnapshot,
}: {
  history?: PatientMemoryHistory | null;
  isPro: boolean;
  loading: boolean;
  fallbackSnapshot?: string | null;
}) {
  const t = useT();
  const updating = history?.status === "updating";
  const heading = (
    <div className="patient-history-head">
      {isPro ? <MemorySpark working={updating} /> : null}
      <h2>{t("memcard.patientHistory")}</h2>
      {updating ? <MemoryUpdatingPill /> : null}
    </div>
  );

  if (!history) {
    if (loading) {
      return (
        <section className="patient-history-card">
          <div className="patient-history-head">
            {isPro ? <MemorySpark working /> : null}
            <h2>{t("memcard.patientHistory")}</h2>
          </div>
          <div className="patient-history-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </section>
      );
    }
    if (!fallbackSnapshot) return null;
    return (
      <section className="patient-history-card">
        {heading}
        <p className="patient-history-snapshot" dir={memoryTextDirection(fallbackSnapshot)} data-content>{fallbackSnapshot}</p>
      </section>
    );
  }

  return (
    <section className={`patient-history-card${updating ? " updating" : ""}`}>
      {heading}
      <div className="patient-history-body" key={`${history.snapshot}|${history.sections.length}|${history.visits.length}`}>
        <p className="patient-history-snapshot" dir={memoryTextDirection(history.snapshot)} data-content>{history.snapshot}</p>
        {history.mode === "pro"
          ? history.sections.map((section) => (
              <div className="patient-history-section" key={section.label}>
                <h3 data-content>{section.label}</h3>
                <p dir={memoryTextDirection(section.body)} data-content>{section.body}</p>
              </div>
            ))
          : (
              <div className="patient-history-section">
                <h3>{t("memcard.recentVisits")}</h3>
                <ul className="patient-history-visits">
                  {history.visits.map((visit, index) => (
                    <li key={index}>
                      <span className="patient-history-visit-dot" aria-hidden="true" />
                      <span dir={memoryTextDirection(visit)} data-content>{visit}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
        <span className="memory-sweep" aria-hidden="true" />
      </div>
    </section>
  );
}

// The hero photo on the line-up card: a deterministic single glance (most recent clear after-photo
// of the primary area). Resolves the capture's content endpoint to a blob URL, same as the
// before/after thumbs.
function LineupHero({ hero, onResolveFile }: { hero: LineupCardHero; onResolveFile?: (endpoint: string) => Promise<string> }) {
  const t = useT();
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    let cancelled = false;
    const endpoint = hero.contentEndpoint || hero.fileEndpoint;
    if (!endpoint || !onResolveFile) return;
    void onResolveFile(endpoint)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [hero.contentEndpoint, hero.fileEndpoint, onResolveFile]);
  return (
    <span className="lineup-card-hero">
      {url ? <img alt={hero.caption || t("memcard.mostRecentPhoto")} src={url} /> : <span className="lineup-card-hero-skeleton" aria-hidden="true" />}
    </span>
  );
}

// The compact, glanceable line-up card (Pro only) at the top of the worklist recap. ≤2 short
// paragraphs (story so far / right now), a deterministic hero photo, a "since last visit" delta,
// and surfaced flags. Same ✨ spark + updating→ready treatment as the other memory artifacts.
export function LineupCard({
  card,
  isPro,
  onResolveFile,
}: {
  card?: LineupCardModel | null;
  isPro: boolean;
  onResolveFile?: (endpoint: string) => Promise<string>;
}) {
  const t = useT();
  if (!isPro || !card) return null;
  const flags = card.flags || [];
  const hasContent = Boolean(card.storySoFar || card.rightNow || card.sinceLastVisit || flags.length || card.hero);
  if (!hasContent) return null;
  const updating = card.status === "updating";
  return (
    <section className={`lineup-card${updating ? " updating" : ""}`} aria-label={t("memcard.lineupRecap")}>
      <div className="lineup-card-head">
        <MemorySpark working={updating} />
        <h3>{t("memcard.atAGlance")}</h3>
        {updating ? <MemoryUpdatingPill /> : null}
      </div>
      <div className="lineup-card-body">
        {card.hero ? <LineupHero hero={card.hero} onResolveFile={onResolveFile} /> : null}
        <div className="lineup-card-copy" key={`${card.storySoFar}|${card.rightNow}`}>
          {card.storySoFar ? (
            <p className="lineup-card-story" dir={memoryTextDirection(card.storySoFar)} data-content>{card.storySoFar}</p>
          ) : null}
          {card.rightNow ? (
            <p className="lineup-card-now" dir={memoryTextDirection(card.rightNow)} data-content>{card.rightNow}</p>
          ) : null}
          {card.sinceLastVisit ? (
            <p className="lineup-card-delta" dir={memoryTextDirection(card.sinceLastVisit)} data-content>{card.sinceLastVisit}</p>
          ) : null}
          {flags.length ? (
            <ul className="lineup-card-flags" aria-label={t("memcard.flagsToRemember")}>
              {flags.map((flag, index) => (
                <li key={`${flag.kind}-${index}`} className={`lineup-flag lineup-flag-${flag.kind}`} dir={memoryTextDirection(flag.label)} data-content>
                  {flag.label}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <span className="memory-sweep" aria-hidden="true" />
    </section>
  );
}

// AES-903 — the "next patient" recap popup. A light glance before starting: tier-aware patient
// history (Pro AI sections / Basic structural recap, via PatientHistoryBlock) + the prior visit's
// before/after (LastVisitStrip), with Start visit + a link to the full timeline. Avoids the
// open-patient-page → back → capture round-trip.
export function PatientListLoading() {
  return (
    <>
      <Card className="clinical-row clinical-patient-row clinical-row-loading">
        <span className="clinical-avatar clinical-avatar-blue" />
        <div className="clinical-row-copy">
          <span />
          <p />
          <div className="patient-memory-badges">
            <small />
            <small />
          </div>
        </div>
        <span />
      </Card>
      <Card className="clinical-row clinical-patient-row clinical-row-loading">
        <span className="clinical-avatar clinical-avatar-green" />
        <div className="clinical-row-copy">
          <span />
          <p />
          <div className="patient-memory-badges">
            <small />
          </div>
        </div>
        <span />
      </Card>
    </>
  );
}

export function CaptureChips({ session, tone }: { session: CaptureSession; tone: ClinicalTone }) {
  const t = useT();
  const counts = captureCounts(session, t);
  if (!counts.length) return null;
  return (
    <div className="capture-chips" aria-label={t("memcard.captureTypes")}>
      {counts.map((item) => (
        <span className={`capture-chip capture-chip-${tone}`} key={item.label}>
          {captureTypeIcon(item.type)}
          <span data-content>{item.count}</span> {t(`memcard.captureChip.${item.type}`)}
        </span>
      ))}
    </div>
  );
}

export function TimelineCaptureChips({
  localSession,
  session,
  tone,
}: {
  localSession?: CaptureSession;
  session: TimelineSessionModel;
  tone: ClinicalTone;
}) {
  const t = useT();
  if (localSession) return <CaptureChips session={localSession} tone={tone} />;
  if (!session.captureCount) return null;
  return (
    <div className="capture-chips" aria-label={t("memcard.captureTypes")}>
      <span className={`capture-chip capture-chip-${tone}`}>
        {captureTypeIcon("note")}
        <span data-content>{session.captureCount}</span> {t("memcard.captureCountUnit", { n: session.captureCount })}
      </span>
    </div>
  );
}

export function EmptyClinicalState({ copy, title }: { copy: string; title: string }) {
  return (
    <Card className="clinical-empty">
      <strong>{title}</strong>
      <p>{copy}</p>
    </Card>
  );
}

export function Avatar({ label, tone }: { label: string; tone: ClinicalTone }) {
  return <span className={`clinical-avatar clinical-avatar-${tone}`}>{avatarInitials(label)}</span>;
}
