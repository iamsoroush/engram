import { describe, expect, it } from "vitest";
import type { AttentionCounts, AttentionItem } from "../../../domain/appTypes";
import {
  attentionBadgeCount,
  attentionItemRoute,
  groupAttentionItems,
  groupConfirmVisits,
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

describe("groupConfirmVisits", () => {
  it("collapses a visit's ≥2 confirmations into one group, keeping the patient name", () => {
    const items: AttentionItem[] = [
      item({ id: "d1", kind: "review-treatment", tier: "S2", sessionId: "v1", patientName: "سورنا معاضد" }),
      item({ id: "d2", kind: "review-treatment", tier: "S2", sessionId: "v1", patientName: "سورنا معاضد" }),
      item({ id: "d3", kind: "verify", tier: "S2", sessionId: "v1", patientName: "سورنا معاضد" }),
    ];
    const units = groupConfirmVisits(items);
    expect(units).toHaveLength(1);
    expect(units[0]).toMatchObject({ type: "group", sessionId: "v1", patientName: "سورنا معاضد" });
    if (units[0].type === "group") expect(units[0].items).toHaveLength(3);
  });

  it("keeps a lone confirmation and non-confirm items as single rows, in order", () => {
    const items: AttentionItem[] = [
      item({ id: "solo", kind: "dose", tier: "S2", sessionId: "v1" }),
      item({ id: "sug", kind: "suggested-unassign", tier: "S3", sessionId: "v2" }),
      item({ id: "qa", kind: "qa-pending", tier: "qa", sessionId: "v3", threadId: "t1" }),
    ];
    const units = groupConfirmVisits(items);
    expect(units.map((u) => u.type)).toEqual(["single", "single", "single"]);
  });

  it("groups per visit (session), not per patient — same name, two visits → two groups", () => {
    const items: AttentionItem[] = [
      item({ id: "a1", kind: "review-treatment", tier: "S2", sessionId: "v1", patientName: "Sorna" }),
      item({ id: "a2", kind: "review-treatment", tier: "S2", sessionId: "v1", patientName: "Sorna" }),
      item({ id: "b1", kind: "review-treatment", tier: "S2", sessionId: "v2", patientName: "Sorna" }),
      item({ id: "b2", kind: "review-treatment", tier: "S2", sessionId: "v2", patientName: "Sorna" }),
    ];
    const groups = groupConfirmVisits(items).filter((u) => u.type === "group");
    expect(groups.map((g) => (g.type === "group" ? g.sessionId : null))).toEqual(["v1", "v2"]);
  });

  it("falls back to a null name for an unnamed (unassigned) visit's confirmations", () => {
    const items: AttentionItem[] = [
      item({ id: "u1", kind: "review-treatment", tier: "S2", sessionId: "v9" }),
      item({ id: "u2", kind: "review-treatment", tier: "S2", sessionId: "v9" }),
    ];
    const [unit] = groupConfirmVisits(items);
    expect(unit).toMatchObject({ type: "group", patientName: null });
  });

  it("does not group confirmations that lack a sessionId", () => {
    const items: AttentionItem[] = [
      item({ id: "n1", kind: "dose", tier: "S2" }),
      item({ id: "n2", kind: "dose", tier: "S2" }),
    ];
    expect(groupConfirmVisits(items).map((u) => u.type)).toEqual(["single", "single"]);
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
