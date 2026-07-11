import { describe, expect, it } from "vitest";
import type { CaptureSession, ReportVersionDetail, ReportVersionSummary } from "../../../domain/types";
import { buildReportVersionPreviewSession, reportVersionRemovedCaptures, reportVersionTriggerLabel } from "./reportHistoryModel";

// A stub translate: echoes the key (with :count when interpolated) so we assert the MAPPING, not the catalog.
const t = (key: string, vars?: Record<string, string | number>) => (vars?.count != null ? `${key}:${vars.count}` : key);

function version(overrides: Partial<ReportVersionSummary> = {}): ReportVersionSummary {
  return {
    id: "v1",
    captureSetHash: "h",
    captureCount: 1,
    captureIds: [],
    generatedAt: "2026-07-11T10:00:00Z",
    createdAt: "2026-07-11T10:00:00Z",
    generatedBy: "ai-engine",
    isCurrent: false,
    restorable: true,
    trigger: { kind: "report_updated" },
    ...overrides,
  };
}

describe("reportVersionTriggerLabel", () => {
  it("maps a known kind to its trigger key", () => {
    expect(reportVersionTriggerLabel({ kind: "photo_added" }, t)).toBe("capture.history.trigger.photo_added");
    expect(reportVersionTriggerLabel({ kind: "first_report" }, t)).toBe("capture.history.trigger.first_report");
  });

  it("passes count through for count-bearing kinds", () => {
    expect(reportVersionTriggerLabel({ kind: "captures_added", count: 3 }, t)).toBe("capture.history.trigger.captures_added:3");
  });

  it("falls back to report_updated for an unknown kind", () => {
    expect(reportVersionTriggerLabel({ kind: "not_a_real_kind" }, t)).toBe("capture.history.trigger.report_updated");
  });
});

describe("reportVersionRemovedCaptures", () => {
  const live = {
    id: "s1",
    items: [
      { id: "c1", type: "audio", status: "processed" },
      { id: "c2", type: "photo", status: "processed" },
      { id: "local-capture-x", type: "note", status: "saved" },
    ],
  } as unknown as CaptureSession;

  it("returns the synced captures the version never knew", () => {
    const removed = reportVersionRemovedCaptures(live, version({ captureIds: ["c1"] }));
    expect(removed.map((c) => c.id)).toEqual(["c2"]); // c1 is known; local- is never restore-removed
  });

  it("returns none when the version already knows every synced capture", () => {
    expect(reportVersionRemovedCaptures(live, version({ captureIds: ["c1", "c2"] }))).toEqual([]);
  });
});

describe("buildReportVersionPreviewSession", () => {
  const live = {
    id: "s1",
    label: "Visit",
    patientId: "p1",
    patientName: "Sara",
    createdAt: "2026-07-11T09:00:00Z",
    updatedAt: "2026-07-11T09:30:00Z",
    items: [],
    // Live overlay (user decisions) + a current-treatments artifact that the version must override.
    extractedMetadata: { rejected_safety_flags: ["allergy|x"], treatments: [{ area: "current" }] },
  } as unknown as CaptureSession;

  const detail: ReportVersionDetail = {
    version: version({ id: "vOld", generatedAt: "2026-07-11T08:00:00Z" }),
    report: {
      summary: "old summary",
      generatedSummary: null,
      generatedReport: "old report body",
      reportModel: { sections: [{ id: "s", title: "Summary", blocks: [] }] } as never,
      reportTemplateKey: null,
      extractedMetadata: { treatments: [{ area: "old-version" }], safety_flags: [{ kind: "allergy", text: "y" }] },
    },
  };

  it("uses the version's report content", () => {
    const preview = buildReportVersionPreviewSession(live, detail);
    expect(preview.generatedReport).toBe("old report body");
    expect(preview.reportModel?.sections?.[0]?.title).toBe("Summary");
  });

  it("lets version artifacts win but keeps the live user-state overlay on top", () => {
    const preview = buildReportVersionPreviewSession(live, detail);
    const meta = preview.extractedMetadata as Record<string, unknown>;
    // Version's treatments override the live/current ones...
    expect(meta.treatments).toEqual([{ area: "old-version" }]);
    // ...but the user's rejection (an overlay key, absent from the version) survives — never time-traveled away.
    expect(meta.rejected_safety_flags).toEqual(["allergy|x"]);
  });
});
