import type { CaptureStatus, SessionStatus } from "./types";

export type SessionUxState = "capturing" | "processing" | "needs_review" | "unassigned" | "verified" | "failed";

export const sessionUxStateCopy: Record<SessionUxState, string> = {
  capturing: "Capturing",
  processing: "Processing",
  needs_review: "Needs review",
  unassigned: "Unassigned",
  verified: "Verified",
  failed: "Failed",
};

export const sessionUxStateTone: Record<SessionUxState, "neutral" | "blue" | "green" | "amber" | "red"> = {
  capturing: "blue",
  processing: "blue",
  needs_review: "amber",
  unassigned: "neutral",
  verified: "green",
  failed: "red",
};

export function sessionUxState(status: SessionStatus): SessionUxState {
  if (status === "failed") return "failed";
  if (status === "processing") return "processing";
  if (status === "verified" || status === "matched") return "verified";
  if (status === "unassigned") return "unassigned";
  if (status === "needs_review" || status === "organized" || status === "reviewing") return "needs_review";
  return "capturing";
}

export const statusCopy: Record<CaptureStatus, string> = {
  saved: "Saved on device",
  syncing: "Syncing",
  uploaded: "Uploaded",
  processing: "Processing",
  processed: "Processed",
  needsReview: "Needs review",
  failed: "Failed",
};

export const statusTone: Record<CaptureStatus, "neutral" | "blue" | "green" | "amber" | "red"> = {
  saved: "neutral",
  syncing: "blue",
  uploaded: "blue",
  processing: "amber",
  processed: "green",
  needsReview: "amber",
  failed: "red",
};

export const sessionStatusCopy: Record<SessionStatus, string> = {
  draft: sessionUxStateCopy.capturing,
  unassigned: sessionUxStateCopy.unassigned,
  needs_review: sessionUxStateCopy.needs_review,
  processing: sessionUxStateCopy.processing,
  organized: sessionUxStateCopy.needs_review,
  reviewing: sessionUxStateCopy.needs_review,
  verified: sessionUxStateCopy.verified,
  reopened: sessionUxStateCopy.capturing,
  failed: sessionUxStateCopy.failed,
  current: sessionUxStateCopy.capturing,
  matched: sessionUxStateCopy.verified,
};

export const sessionStatusTone: Record<SessionStatus, "neutral" | "blue" | "green" | "amber" | "red"> = {
  draft: sessionUxStateTone.capturing,
  unassigned: sessionUxStateTone.unassigned,
  needs_review: sessionUxStateTone.needs_review,
  processing: sessionUxStateTone.processing,
  organized: sessionUxStateTone.needs_review,
  reviewing: sessionUxStateTone.needs_review,
  verified: sessionUxStateTone.verified,
  reopened: sessionUxStateTone.capturing,
  failed: sessionUxStateTone.failed,
  current: sessionUxStateTone.capturing,
  matched: sessionUxStateTone.verified,
};
