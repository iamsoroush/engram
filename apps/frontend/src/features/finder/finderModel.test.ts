import { describe, expect, it } from "vitest";
import type { LotLedger } from "../../domain/appTypes";
import type { CaptureSession } from "../../domain/types";
import { localSessionMatches, lotCore, lotSuggestions, todaysVisits } from "./finderModel";

// AES-1203/1204 — pure finder logic: lot detection (separator-insensitive, mirrors the Lists lookup),
// the preserved offline local-substring fallback, and the instant "Today's visits" grain.

function session(partial: Partial<CaptureSession>): CaptureSession {
  return {
    id: "s1",
    label: "Visit",
    time: "",
    dateLabel: "",
    duration: "",
    summary: "",
    status: "processing",
    items: [],
    ...partial,
  } as CaptureSession;
}

const ledger: LotLedger = {
  lots: [
    { lot: "D-4471", product: "Dysport", brand: "Dysport", patientCount: 3, visitCount: 4 },
    { lot: "R-9080", product: "Restylane", brand: "Restylane", patientCount: 1, visitCount: 1 },
  ],
  products: [{ name: "Dysport", kind: "brand", patientCount: 3, visitCount: 4 }],
};

describe("lotCore", () => {
  it("strips separators/case for candidate matching", () => {
    expect(lotCore("D-4471")).toBe("d4471");
    expect(lotCore("d 4471")).toBe("d4471");
    expect(lotCore("d.4471")).toBe("d4471");
  });
});

describe("lotSuggestions", () => {
  it("finds a lot separator-insensitively (d4471 / d 4471 → D-4471)", () => {
    for (const q of ["d4471", "d 4471", "D-4471", "d.4471"]) {
      const hits = lotSuggestions(ledger, q);
      expect(hits.some((h) => h.kind === "lot" && h.value === "D-4471")).toBe(true);
    }
  });

  it("matches a lot by its brand/product too, and surfaces the product grain", () => {
    const hits = lotSuggestions(ledger, "dysport");
    expect(hits.some((h) => h.kind === "lot" && h.value === "D-4471")).toBe(true);
    expect(hits.some((h) => h.kind === "product" && h.value === "Dysport")).toBe(true);
  });

  it("returns [] with no ledger (Basic / not loaded) or a too-short query", () => {
    expect(lotSuggestions(null, "d4471")).toEqual([]);
    expect(lotSuggestions(ledger, "d")).toEqual([]);
    expect(lotSuggestions(ledger, "  ")).toEqual([]);
  });

  it("does not match an unrelated lot from a long numeric (patient-phone-shaped) query", () => {
    expect(lotSuggestions(ledger, "09123344719")).toEqual([]);
  });
});

describe("localSessionMatches (offline fallback)", () => {
  const sessions: CaptureSession[] = [
    session({ id: "a", label: "Follow-up", patientName: "سارا کریمی", summary: "botox forehead" }),
    session({ id: "b", label: "Consult", patientName: "Reza", summary: "filler cheek" }),
  ];

  it("substring-matches across label/summary/patientName (Persian + latin)", () => {
    expect(localSessionMatches(sessions, "سارا").map((s) => s.id)).toEqual(["a"]);
    expect(localSessionMatches(sessions, "filler").map((s) => s.id)).toEqual(["b"]);
    expect(localSessionMatches(sessions, "").length).toBe(0);
    expect(localSessionMatches(sessions, "nomatch").length).toBe(0);
  });
});

describe("todaysVisits", () => {
  it("keeps only sessions captured today, most recent first, capped", () => {
    // Local-time construction (no trailing Z) so the calendar-day comparison is timezone-robust in CI.
    const now = new Date(2026, 6, 6, 15, 0, 0).getTime();
    const sessions: CaptureSession[] = [
      session({ id: "old", capturedAt: "2026-07-01T10:00:00" }),
      session({ id: "early", capturedAt: "2026-07-06T08:00:00" }),
      session({ id: "late", capturedAt: "2026-07-06T14:00:00" }),
    ];
    expect(todaysVisits(sessions, now).map((s) => s.id)).toEqual(["late", "early"]);
    expect(todaysVisits(sessions, now, 1).map((s) => s.id)).toEqual(["late"]);
  });
});
