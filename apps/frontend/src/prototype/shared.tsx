import type { CaptureItem, CaptureSession, PatientCandidate, SessionStatus } from "./types";
import { Badge, Button, Card } from "./ui";

export function AppHeader({
  title,
  subtitle,
  onToday,
}: {
  title: string;
  subtitle?: string;
  onToday: () => void;
}) {
  return (
    <header className="app-header">
      <button className="brand" onClick={onToday} type="button">
        <strong>CaptureFirst</strong>
        <span>{title}</span>
      </button>
      {subtitle ? <p>{subtitle}</p> : null}
      <span className="doctor">Dr. user</span>
    </header>
  );
}

export function CapturePrimaryButton({
  children = "Start capture",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children?: React.ReactNode }) {
  return (
    <Button className="capture-primary" size="lg" {...props}>
      {children}
    </Button>
  );
}

export function StatusBadge({ status }: { status: SessionStatus | "recording" | "paused" | "saved" }) {
  const copy = {
    draft: "Draft",
    current: "Current session",
    needs_review: "Needs review",
    processing: "Processing",
    organized: "Organized",
    reviewing: "In review",
    verified: "Verified",
    reopened: "Reopened",
    failed: "Failed/Retry",
    unassigned: "Unassigned",
    matched: "Matched",
    recording: "Recording",
    paused: "Paused",
    saved: "Saved",
  }[status];
  const tone =
    status === "matched" || status === "saved" || status === "verified"
      ? "green"
      : status === "failed"
        ? "red"
        : status === "needs_review" || status === "reviewing" || status === "reopened"
          ? "amber"
          : status === "organized" || status === "processing"
            ? "blue"
            : "neutral";
  return <Badge tone={tone}>{copy}</Badge>;
}

export function SessionCard({
  session,
  selected,
  onClick,
  action,
}: {
  session: CaptureSession;
  selected?: boolean;
  onClick?: () => void;
  action?: React.ReactNode;
}) {
  return (
    <Card className={`session-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div>
        <h3>{session.label}</h3>
        <p>{session.summary}</p>
        <small>
          {session.dateLabel} · {session.duration}
        </small>
      </div>
      <div className="session-card-side">
        <StatusBadge status={session.status} />
        {action}
      </div>
    </Card>
  );
}

export function CaptureItemCard({ item, compact = false }: { item: CaptureItem; compact?: boolean }) {
  return (
    <Card className={`capture-item ${compact ? "compact" : ""}`}>
      <div>
        <h3>{item.title}</h3>
        <p>{item.detail}</p>
      </div>
      <span>{item.sourceName}</span>
      {item.status === "uploading" ? <Badge tone="amber">Upload pending</Badge> : null}
      {item.status === "missing" ? <Badge tone="red">Source missing</Badge> : null}
    </Card>
  );
}

export function PatientCandidateCard({
  candidate,
  selected,
  onClick,
}: {
  candidate: PatientCandidate;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <Card className={`patient-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div>
        <h3>{candidate.name}</h3>
        <p>
          {candidate.gender}, {candidate.age} · {candidate.lastVisit}
        </p>
      </div>
      <Badge tone={candidate.confidence === "High" ? "blue" : candidate.confidence === "Possible" ? "amber" : "neutral"}>
        {candidate.hint}
      </Badge>
    </Card>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </Card>
  );
}

export function ConfirmActionBar({
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
  disabled,
}: {
  primaryLabel: string;
  secondaryLabel: string;
  onPrimary: () => void;
  onSecondary: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="confirm-bar">
      <Button disabled={disabled} onClick={onPrimary}>
        {primaryLabel}
      </Button>
      <Button onClick={onSecondary} variant="secondary">
        {secondaryLabel}
      </Button>
    </div>
  );
}
