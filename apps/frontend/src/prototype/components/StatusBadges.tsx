import type { CaptureStatus, CaptureItem, SessionStatus } from "../types";
import { Badge } from "../ui";
import { sessionUxState, sessionUxStateCopy, sessionUxStateTone, statusCopy, statusTone } from "../status";

export function StatusBadge({ status }: { status?: CaptureItem["status"] }) {
  const normalized: CaptureStatus =
    status === "syncing" ||
    status === "uploaded" ||
    status === "processing" ||
    status === "processed" ||
    status === "needsReview" ||
    status === "failed"
      ? status
      : "saved";
  return <Badge tone={statusTone[normalized]}>{statusCopy[normalized]}</Badge>;
}

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const state = sessionUxState(status);
  return <Badge tone={sessionUxStateTone[state]}>{sessionUxStateCopy[state]}</Badge>;
}
