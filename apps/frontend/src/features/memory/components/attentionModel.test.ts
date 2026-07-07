import { describe, expect, it } from "vitest";
import type { AttentionCounts, AttentionItem } from "../../../domain/appTypes";
import {
  attentionBadgeCount,
  attentionItemRoute,
  groupAttentionItems,
  hasAttention,
} from "./attentionModel";

function item(partial: Partial<AttentionItem> & Pick<AttentionItem, "id" | "kind" | "tier">): AttentionItem {
  return {
    sessionId: null,
    patientId: null,
    patientName: null,
    clinicianId: null,
    threadId: null,
    reason: null,
    key: null,
    sortTime: null,
    dayGroup: "today",
    ...partial,
  };
}

describe("groupAttentionItems", () => {
  it("orders today's sections Confirm → Safety → Messages → Suggested and drops empty ones", () => {
    const items: AttentionItem[] = [
      item({ id: "s", kind: "safety-flag", tier: "S1", sortTime: "2026-07-06T09:00:00Z" }),
      item({ id: "m", kind: "qa-pending", tier: "qa", sortTime: "2026-07-06T09:00:00Z" }),
      item({ id: "c", kind: "dose", tier: "S2", sortTime: "2026-07-06T09:00:00Z" }),
      item({ id: "g", kind: "suggested-unassign", tier: "S3", sortTime: "2026-07-06T09:00:00Z" }),
    ];
    const { todaySections, earlierItems } = groupAttentionItems(items);
    expect(todaySections.map((s) => s.key)).toEqual(["confirm", "safety", "messages", "suggested"]);
    expect(earlierItems).toHaveLength(0);
  });

  it("sorts items within a section newest-first", () => {
    const items: AttentionItem[] = [
      item({ id: "old", kind: "dose", tier: "S2", sortTime: "2026-07-06T08:00:00Z" }),
      item({ id: "new", kind: "dose", tier: "S2", sortTime: "2026-07-06T11:00:00Z" }),
    ];
    const { todaySections } = groupAttentionItems(items);
    expect(todaySections[0].items.map((i) => i.id)).toEqual(["new", "old"]);
  });

  it("splits prior-day items into one flat Earlier group, severity-then-recency ordered", () => {
    const items: AttentionItem[] = [
      item({ id: "e-suggest", kind: "suggested-unassign", tier: "S3", dayGroup: "earlier", sortTime: "2026-07-05T10:00:00Z" }),
      item({ id: "e-confirm-old", kind: "dose", tier: "S2", dayGroup: "earlier", sortTime: "2026-07-04T10:00:00Z" }),
      item({ id: "e-confirm-new", kind: "assign-patient", tier: "S2", dayGroup: "earlier", sortTime: "2026-07-05T12:00:00Z" }),
      item({ id: "t", kind: "dose", tier: "S2", dayGroup: "today", sortTime: "2026-07-06T09:00:00Z" }),
    ];
    const { todaySections, earlierItems } = groupAttentionItems(items);
    expect(todaySections.map((s) => s.key)).toEqual(["confirm"]);
    // Confirm (S2) before suggested (S3); within S2, newest first.
    expect(earlierItems.map((i) => i.id)).toEqual(["e-confirm-new", "e-confirm-old", "e-suggest"]);
  });
});

describe("attentionBadgeCount / hasAttention", () => {
  const counts = (over: Partial<AttentionCounts>): AttentionCounts => ({
    confirm: 0,
    suggested: 0,
    messages: 0,
    safety: 0,
    total: 0,
    ...over,
  });

  it("counts confirm + messages, never safety or suggested", () => {
    expect(attentionBadgeCount(counts({ confirm: 4, messages: 1, suggested: 2, safety: 3 }))).toBe(5);
  });

  it("renders the indicator for a safety-only feed (shown, never counted)", () => {
    const safetyOnly = counts({ safety: 1, total: 0 });
    expect(attentionBadgeCount(safetyOnly)).toBe(0);
    expect(hasAttention(safetyOnly)).toBe(true);
  });

  it("hides the indicator only when everything is clear", () => {
    expect(hasAttention(counts({}))).toBe(false);
  });
});

describe("attentionItemRoute", () => {
  it("deep-links a Q&A item to its inbox thread, never a visit", () => {
    const route = attentionItemRoute(item({ id: "q", kind: "qa-pending", tier: "qa", threadId: "thread-1", sessionId: "s-1" }));
    expect(route).toEqual({ type: "qa", threadId: "thread-1" });
  });

  it("routes a session-bound item to its source visit", () => {
    const route = attentionItemRoute(item({ id: "d", kind: "dose", tier: "S2", sessionId: "s-9" }));
    expect(route).toEqual({ type: "session", sessionId: "s-9" });
  });

  it("returns null when there is nowhere to route", () => {
    expect(attentionItemRoute(item({ id: "x", kind: "dose", tier: "S2" }))).toBeNull();
  });
});
