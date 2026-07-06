// Pure, framework-free helpers for the unified finder (AES-1201/1203/1204). Kept out of the overlay
// component so the lot-detection + offline-fallback + today's-visits logic is unit-testable without a
// DOM or effects — the same discipline the memory model uses.
import type { LotLedger } from "../../domain/appTypes";
import type { CaptureSession } from "../../domain/types";

/** A lot- or product-shaped hit from the ledger that surfaces a recall action in the finder. */
export type FinderLotSuggestion = {
  kind: "lot" | "product";
  value: string;
  sub: string | null;
  patientCount: number;
};

/** Separator-insensitive core so "d4471" / "d 4471" both resolve to "D-4471" (mirrors the Lists lot
 *  lookup). NOTE this is only for *finding* a candidate lot — the recall itself stays exact-match
 *  server-side (`D-4471 ≠ D4471`), so a near-miss is never silently folded into a recall cohort. */
export function lotCore(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * Lot/product suggestions from the loaded ledger for a query — the exact separator/case-insensitive
 * contract the Pro Lists lookup uses, so the finder's "Recall lot" action matches the Lists tab. The
 * recall action appears *above* patient results (it never replaces them), so a spurious substring hit
 * is harmless. Returns [] when the ledger is absent (Basic / not loaded) or nothing matches.
 */
export function lotSuggestions(ledger: LotLedger | null | undefined, query: string): FinderLotSuggestion[] {
  if (!ledger) return [];
  const needle = query.trim().toLowerCase();
  if (needle.length < 2) return [];
  const core = lotCore(needle);
  const matches = (...fields: Array<string | null | undefined>): boolean =>
    fields.some((field) => {
      const value = (field || "").toLowerCase();
      return value.includes(needle) || (core.length >= 2 && lotCore(value).includes(core));
    });
  const lots: FinderLotSuggestion[] = ledger.lots
    .filter((entry) => matches(entry.lot, entry.brand, entry.product))
    .map((entry) => ({ kind: "lot", value: entry.lot, sub: entry.brand || entry.product || null, patientCount: entry.patientCount }));
  const products: FinderLotSuggestion[] = ledger.products
    .filter((entry) => matches(entry.name))
    .map((entry) => ({ kind: "product", value: entry.name, sub: null, patientCount: entry.patientCount }));
  return [...lots, ...products].slice(0, 6);
}

/**
 * The preserved offline fallback: a local substring filter over the sessions already loaded in the
 * client (verbatim the old top-nav Search behavior). Used only when offline — online the finder always
 * hits the backend so unloaded patients are findable.
 */
export function localSessionMatches(sessions: CaptureSession[], query: string): CaptureSession[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return sessions.filter((session) =>
    [
      session.label,
      session.summary,
      session.patientName,
      session.reviewReason,
      ...session.items.flatMap((item) => [item.title, item.detail, item.sourceName, item.patientName]),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(normalized),
  );
}

function sessionTimeMs(session: CaptureSession): number {
  const value = session.capturedAt || session.createdAt || session.updatedAt;
  const ms = value ? new Date(value).getTime() : NaN;
  return Number.isNaN(ms) ? 0 : ms;
}

/**
 * The pre-query "Today's visits" grain: sessions captured on the same calendar day as `nowMs`, most
 * recent first. Sourced from the already-loaded session list so it renders instantly and works offline.
 */
export function todaysVisits(sessions: CaptureSession[], nowMs: number, limit = 6): CaptureSession[] {
  const now = new Date(nowMs);
  const isToday = (iso?: string | null): boolean => {
    if (!iso) return false;
    const date = new Date(iso);
    return (
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate()
    );
  };
  return sessions
    .filter((session) => isToday(session.capturedAt) || isToday(session.createdAt) || isToday(session.updatedAt))
    .sort((left, right) => sessionTimeMs(right) - sessionTimeMs(left))
    .slice(0, limit);
}
