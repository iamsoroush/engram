// Close-the-day / unified attention model (AES-1001..1004).
//
// Pure grouping + presentation logic for the severity-tiered sweep and the top-bar indicator. Chrome
// labels are keyed here and resolved through `t()` in the components; clinical CONTENT (an item's
// `reason`/`patientName`) is passed through verbatim in the report language.

import type { AttentionCounts, AttentionItem, AttentionResponse, AttentionScope, AttentionTier } from "../../../domain/appTypes";

/** Fetch the unified attention roll-up for a scope (named here so the .tsx props stay guard-clean). */
export type FetchAttention = (scope: AttentionScope) => Promise<AttentionResponse>;

export type AttentionSectionKey = "confirm" | "safety" | "messages" | "suggested";
export type AttentionTone = "amber" | "red" | "violet" | "blue";

// Tier → sweep section. The sweep renders sections in `SECTION_ORDER` (Confirm first as the true
// to-do, then Safety-to-review, Messages, Suggested — per the reviewed layout).
export const TIER_SECTION: Record<AttentionTier, AttentionSectionKey> = {
  S2: "confirm",
  S1: "safety",
  qa: "messages",
  S3: "suggested",
};

export const SECTION_ORDER: AttentionSectionKey[] = ["confirm", "safety", "messages", "suggested"];

// Colour rail per tier — the shared severity language (also used by the indicator + in-place chips).
export const TIER_TONE: Record<AttentionTier, AttentionTone> = {
  S1: "red",
  S2: "amber",
  qa: "violet",
  S3: "blue",
};

// Severity rank for ordering the flat "Earlier, still open" carry-over group.
const SECTION_RANK: Record<AttentionSectionKey, number> = { confirm: 0, safety: 1, messages: 2, suggested: 3 };

export type AttentionSection = { key: AttentionSectionKey; tier: AttentionTier; items: AttentionItem[] };

export type AttentionGrouping = {
  /** Today's items, bucketed into non-empty severity sections, in display order. */
  todaySections: AttentionSection[];
  /** Prior-day undecided items — one flat, severity-then-recency ordered "Earlier" group. */
  earlierItems: AttentionItem[];
};

function bySortTimeDesc(a: AttentionItem, b: AttentionItem): number {
  return (b.sortTime || "").localeCompare(a.sortTime || "");
}

/** Split the feed into today's severity sections and the "Earlier, still open" carry-over group. */
export function groupAttentionItems(items: AttentionItem[]): AttentionGrouping {
  const today = items.filter((item) => item.dayGroup !== "earlier");
  const earlier = items.filter((item) => item.dayGroup === "earlier");

  const todaySections: AttentionSection[] = [];
  for (const key of SECTION_ORDER) {
    const sectionItems = today
      .filter((item) => TIER_SECTION[item.tier] === key)
      .sort(bySortTimeDesc);
    if (sectionItems.length) {
      todaySections.push({ key, tier: sectionItems[0].tier, items: sectionItems });
    }
  }

  const earlierItems = [...earlier].sort((a, b) => {
    const rank = SECTION_RANK[TIER_SECTION[a.tier]] - SECTION_RANK[TIER_SECTION[b.tier]];
    return rank !== 0 ? rank : bySortTimeDesc(a, b);
  });

  return { todaySections, earlierItems };
}

/** The primary "needs you" number for the indicator: confirm + messages (safety is opt-out, never a
 * to-do; suggested is a quiet optional count shown separately). */
export function attentionBadgeCount(counts: AttentionCounts): number {
  return counts.confirm + counts.messages;
}

/** Whether the indicator should render at all — any open item, including a shown-not-counted safety
 * flag (its red presence must never be hidden). */
export function hasAttention(counts: AttentionCounts): boolean {
  return counts.total > 0 || counts.safety > 0;
}

// Indicator colour from the backend's highest-open-tier (safety keeps top salience).
export const HIGHEST_TIER_TONE: Record<NonNullable<AttentionResponseHighest>, AttentionTone> = {
  safety: "red",
  confirm: "amber",
  messages: "violet",
  suggested: "blue",
};
type AttentionResponseHighest = "safety" | "confirm" | "messages" | "suggested" | null;

// i18n key for an item's chrome title (the localized noun; the reason body stays report-language).
export function attentionTitleKey(kind: string): string {
  return `attention.kind.${kind}`;
}

// i18n key for an item's primary action (Confirm / Assign patient / Open reply …).
export function attentionActionKey(kind: string): string {
  return `attention.action.${kind}`;
}

export type AttentionRoute = { type: "session"; sessionId: string } | { type: "qa"; threadId: string } | null;

/** Where an item's primary action / row-select routes: its source visit in Active Session (where the
 * inline resolver lives) or the Q&A inbox thread (the sweep never reimplements the reply flow). */
export function attentionItemRoute(item: AttentionItem): AttentionRoute {
  if (item.kind === "qa-pending" && item.threadId) return { type: "qa", threadId: item.threadId };
  if (item.sessionId) return { type: "session", sessionId: item.sessionId };
  return null;
}
