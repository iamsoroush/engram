import type { CaptureStatus, SessionStatus } from "./types";

export const statusCopy: Record<CaptureStatus, string> = {
  saved: "Saved on device",
  syncing: "Syncing",
  uploaded: "Uploaded",
  processing: "Processing",
  processed: "Processed",
  needsReview: "Needs review",
  failed: "Failed/Retry",
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
  draft: "Draft",
  unassigned: "Unassigned",
  needs_review: "Needs review",
  processing: "Processing",
  organized: "Organized",
  reviewing: "In review",
  verified: "Verified",
  reopened: "Reopened",
  failed: "Failed/Retry",
  current: "Current session",
  matched: "Matched",
};

export const sessionStatusTone: Record<SessionStatus, "neutral" | "blue" | "green" | "amber" | "red"> = {
  draft: "neutral",
  unassigned: "neutral",
  needs_review: "amber",
  processing: "blue",
  organized: "blue",
  reviewing: "amber",
  verified: "green",
  reopened: "amber",
  failed: "red",
  current: "blue",
  matched: "green",
};
