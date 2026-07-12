import { describe, expect, it } from "vitest";
import type { AftercareTemplate, PatientSummary } from "../../domain/appTypes";
import type { CaptureItem, CaptureSession, StructuredReportModel } from "../../domain/types";
import {
  captureNotSynced,
  captureOutOfContext,
  filterPatientMatches,
  isLowConfidenceTreatment,
  maskIdentifier,
  maskPhone,
  mergePatientMatches,
  mergeSessionItems,
  preservedReportModelContext,
  safetyFlagKey,
  samePatientSummary,
  treatmentAttributeLines,
  sessionKeptSafetyFlags,
  sessionRejectedSafetyFlags,
  sessionSafetyFlags,
  suggestedAftercareTemplateIds,
  textDirection,
  treatmentLabel,
  workspaceTreatments,
} from "./captureModel";

// Characterization tests for the pure capture-model helpers the refactor leans on — especially the
// report-model preservation rules (frontend-refactor plan §6: "keep a prior synthesized report
// visible while a new one organizes") and the patient/safety selectors the session store will move.

function session(overrides: Partial<CaptureSession> = {}): CaptureSession {
  return {
    id: "session-1",
    label: "Session",
    time: "10:00",
    dateLabel: "Today",
    duration: "5m",
    summary: "",
    status: "processing",
    items: [],
    ...overrides,
  };
}

function item(id: string, overrides: Partial<CaptureItem> = {}): CaptureItem {
  return { id, type: "note", title: "", detail: "", time: "10:00", sourceName: "", ...overrides };
}

/** A report model that IS a Pro synthesis (carries a synthesized section id with blocks). */
function synthesizedModel(): StructuredReportModel {
  return { sections: [{ id: "assessment", title: "Assessment", blocks: [{ type: "paragraph", text: "x" }] }] };
}

describe("preservedReportModelContext", () => {
  it("holds the prior synthesized model while the incoming session is still working (not yet synthesized)", () => {
    const existing = session({ reportModel: synthesizedModel() });
    const incoming = session({ reportModel: null, report: { status: "generating", format: "markdown", title: "", body: "" } });
    const held = preservedReportModelContext(existing, incoming);
    expect(held.reportModel).toBe(existing.reportModel);
  });

  it("returns no override when the existing model is not a synthesis", () => {
    const existing = session({ reportModel: { sections: [{ id: "audio-notes", title: "Audio notes", blocks: [{ type: "paragraph", text: "x" }] }] } });
    const incoming = session({ reportModel: null, report: { status: "generating", format: "markdown", title: "", body: "" } });
    expect(preservedReportModelContext(existing, incoming)).toEqual({});
  });

  it("returns no override once the incoming session carries a fresh synthesis", () => {
    const existing = session({ reportModel: synthesizedModel() });
    const incoming = session({ reportModel: synthesizedModel() });
    expect(preservedReportModelContext(existing, incoming)).toEqual({});
  });

  it("merges (never drops) a just-confirmed carried-forward dose while holding the prior model", () => {
    const existing = session({
      reportModel: synthesizedModel(),
      extractedMetadata: { confirmed_carried_forward: ["botox|forehead"] },
    });
    const incoming = session({
      reportModel: null,
      report: { status: "partial", format: "markdown", title: "", body: "", isStale: true },
      extractedMetadata: { confirmed_carried_forward: ["filler|cheek"] },
    });
    const held = preservedReportModelContext(existing, incoming);
    const confirmed = (held.extractedMetadata as Record<string, unknown>)?.confirmed_carried_forward as string[];
    expect(new Set(confirmed)).toEqual(new Set(["botox|forehead", "filler|cheek"]));
  });
});

describe("mergeSessionItems", () => {
  it("preserves the existing patient context when the incoming session lacks one", () => {
    const existing = session({ patientId: "p1", patientName: "Sara", assignmentSource: "staff", items: [item("a")] });
    const incoming = session({ items: [item("a")] });
    const merged = mergeSessionItems(existing, incoming);
    expect(merged.patientId).toBe("p1");
    expect(merged.patientName).toBe("Sara");
  });

  it("replaces a local item id with the incoming backend item, preserving its local preview url", () => {
    const existing = session({ items: [item("local-capture-1", { sourceUrl: "blob:local" })] });
    const incoming = session({ items: [item("backend-1")] });
    const merged = mergeSessionItems(existing, incoming, "local-capture-1");
    expect(merged.items).toHaveLength(1);
    expect(merged.items[0].id).toBe("backend-1");
    expect(merged.items[0].sourceUrl).toBe("blob:local");
  });

  it("keeps a stale synthesized report when the incoming report is processed and not stale", () => {
    const existing = session({
      report: { status: "processed", format: "markdown", title: "", body: "OLD", isStale: true },
      items: [item("a")],
    });
    const incoming = session({
      report: { status: "processed", format: "markdown", title: "", body: "NEW", isStale: false },
      items: [item("a")],
    });
    expect(mergeSessionItems(existing, incoming).report?.body).toBe("OLD");
  });
});

describe("safety flag selectors", () => {
  const flagsMeta = {
    safety_flags: [
      { kind: "allergy", text: "Lidocaine" },
      { kind: "contraindication", text: "Pregnancy" },
      { kind: "not-a-kind", text: "ignored" },
    ],
  };

  it("keys a safety flag identically to the backend convention (kind|normalized text)", () => {
    expect(safetyFlagKey("allergy", "  Lidocaine  ")).toBe("allergy|lidocaine");
  });

  it("parses only known safety-flag kinds", () => {
    const flags = sessionSafetyFlags(session({ extractedMetadata: flagsMeta }));
    expect(flags.map((f) => f.kind)).toEqual(["allergy", "contraindication"]);
  });

  it("carries the normalized label through, defaulting to null (AES-1801)", () => {
    const meta = {
      safety_flags: [
        { kind: "allergy", label: " حساسیت به لیدوکائین ", text: "بیمار به لیدوکائین حساسیت داره" },
        { kind: "consent", text: "رضایت‌نامه گرفته شد" }, // no label → null
      ],
    };
    const flags = sessionSafetyFlags(session({ extractedMetadata: meta }));
    expect(flags[0].label).toBe("حساسیت به لیدوکائین"); // trimmed passthrough
    expect(flags[1].label).toBeNull();
  });

  it("excludes rejected flags from the kept set", () => {
    const meta = { ...flagsMeta, rejected_safety_flags: [safetyFlagKey("allergy", "Lidocaine")] };
    const kept = sessionKeptSafetyFlags(session({ extractedMetadata: meta }));
    expect(kept.map((f) => f.text)).toEqual(["Pregnancy"]);
    expect(sessionRejectedSafetyFlags(session({ extractedMetadata: meta }))).toEqual(["allergy|lidocaine"]);
  });
});

describe("treatments", () => {
  it("shapes treatments from metadata, dropping entries with neither area nor product", () => {
    const meta = {
      treatments: [
        { area: "Forehead", product: "Botox", brand: "Dysport", quantity: 20, unit: "u", lot: "L1" },
        { brand: "orphan" },
      ],
    };
    const treatments = workspaceTreatments(session({ extractedMetadata: meta }));
    expect(treatments).toHaveLength(1);
    expect(treatmentLabel(treatments[0])).toBe("Forehead: Botox (Dysport) — 20 u · lot L1");
  });

  it("flags a low-confidence treatment", () => {
    expect(isLowConfidenceTreatment({ confidence: 0.4 } as never)).toBe(true);
    expect(isLowConfidenceTreatment({ confidence: 0.9 } as never)).toBe(false);
  });

  it("renders only genuine technique attributes as lines, never status/uncertainty keys (R2)", () => {
    const lines = treatmentAttributeLines({
      attributes: {
        needleGauge: "30G",
        depth: "deep",
        // Status / semantic keys schema-v3 lets the model drop into `attributes` — must NOT leak.
        planned_vs_performed: "نامشخص",
        low_confidence: true,
        uncertaintyReason: "ambiguous_quantity",
      },
    } as never);
    expect(lines).toEqual(["needle gauge: 30G", "depth: deep"]);
    expect(lines.join(" ")).not.toContain("planned");
    expect(lines.join(" ")).not.toContain("نامشخص");
    expect(lines.join(" ")).not.toContain("low_confidence");
  });

  it("returns no attribute lines when there are no technique attributes", () => {
    expect(treatmentAttributeLines({ attributes: { planned_vs_performed: "x" } } as never)).toEqual([]);
    expect(treatmentAttributeLines({} as never)).toEqual([]);
  });
});

describe("aftercare matching", () => {
  const templates: AftercareTemplate[] = [
    { id: "t-botox", name: "Botox aftercare", procedureType: "botox", isActive: true } as AftercareTemplate,
    { id: "t-laser", name: "Laser aftercare", procedureType: "laser", isActive: true } as AftercareTemplate,
  ];

  it("matches templates to the procedures actually performed (cross-language synonyms)", () => {
    const ids = suggestedAftercareTemplateIds(templates, [{ product: "بوتاکس", brand: null } as never]);
    expect(ids.has("t-botox")).toBe(true);
    expect(ids.has("t-laser")).toBe(false);
  });

  it("returns an empty set when nothing was detected", () => {
    expect(suggestedAftercareTemplateIds(templates, []).size).toBe(0);
  });
});

describe("patient match helpers", () => {
  const sara: PatientSummary = { id: "p1", displayName: "Sara", nationalId: "1234567890" };
  const nima: PatientSummary = { id: "p2", displayName: "Nima", nationalId: "0987654321" };

  it("filters by name, national id, or phone", () => {
    expect(filterPatientMatches([sara, nima], "sar").map((p) => p.id)).toEqual(["p1"]);
    expect(filterPatientMatches([sara, nima], "").length).toBe(2);
  });

  it("dedupes when merging two match lists", () => {
    expect(mergePatientMatches([sara], [sara, nima]).map((p) => p.id)).toEqual(["p1", "p2"]);
  });

  it("treats patients with the same id, name, or national id as the same", () => {
    expect(samePatientSummary(sara, { ...sara, displayName: "Different" })).toBe(true);
    expect(samePatientSummary(sara, nima)).toBe(false);
  });
});

describe("misc pure helpers", () => {
  it("masks identifiers and phones", () => {
    expect(maskIdentifier("1234567890")).toBe("1234....7890");
    expect(maskPhone("09123456789")).toBe("0912345....");
  });

  it("detects predominant text direction", () => {
    expect(textDirection("سلام دنیا")).toBe("rtl");
    expect(textDirection("hello world")).toBe("ltr");
  });

  it("treats unsynced capture statuses as not-synced", () => {
    expect(captureNotSynced("saved")).toBe(true);
    expect(captureNotSynced("syncing")).toBe(true);
    expect(captureNotSynced("processed")).toBe(false);
  });

  it("reads a staff 'mark relevant' override as back-in-context", () => {
    expect(captureOutOfContext(item("a", { metadata: { out_of_context: { present: true } } }))).toBe(true);
    expect(
      captureOutOfContext(item("a", { metadata: { out_of_context: { present: true, overridden_by_staff: true } } })),
    ).toBe(false);
  });
});
