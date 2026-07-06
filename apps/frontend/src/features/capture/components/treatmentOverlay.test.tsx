import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../../shared/i18n";
import type { CaptureSession } from "../../../domain/types";
import { ProLiveReport } from "./LiveReport";

// AES-1102..1105 — the user-authored treatment overlay UI: an edited field flips to a human-owned
// presentation ("Edited by you" + the AI value preserved as the provenance/reconcile subline), editing
// a carried-forward dose auto-satisfies its confirm blocker (Q4), and a parked orphan surfaces a chip.

function session(extractedMetadata: Record<string, unknown>): CaptureSession {
  return {
    id: "session-1",
    label: "Session",
    time: "10:00",
    dateLabel: "Today",
    duration: "5m",
    summary: "",
    status: "processed",
    items: [],
    extractedMetadata,
    reportModel: null,
  } as unknown as CaptureSession;
}

const stubFile = async () => "";

function render(sess: CaptureSession, currentUserId = "u1"): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang("en")}>
      <ProLiveReport
        session={sess}
        onResolveFile={stubFile}
        onConfirmCarriedForward={async () => {}}
        canEditTreatments
        currentUserId={currentUserId}
        onEditTreatmentField={() => {}}
        onRevertTreatmentField={() => {}}
      />
    </AppLangProvider>,
  );
}

const editedDoseSession = session({
  treatments: [
    {
      treatmentKey: "t|cheeks|voluma|c1",
      area: "cheeks",
      product: "voluma",
      quantityText: "24 units",
      carriedForward: true,
      overlayEditedFields: ["quantity"],
      sourceCaptureIds: ["c1"],
    },
  ],
  treatment_overlay: [
    { treatmentKey: "t|cheeks|voluma|c1", field: "quantity", value: "24 units", aiValue: "20 units", editedByUserId: "u1", op: "edit" },
  ],
  treatment_review: [{ category: "carried_forward", key: "cheeks|voluma", reason: "confirm the dose", sourceCaptureIds: ["c1"] }],
});

describe("treatment overlay — edited field presentation", () => {
  it("flips an edited field to 'Edited by you' and keeps the AI value visible (never overwritten)", () => {
    const html = render(editedDoseSession);
    expect(html).toContain("Edited by you"); // human-owned marker
    expect(html).toContain("24 units"); // the human value leads
    expect(html).toContain("20 units"); // the AI value preserved as provenance/reconcile
    expect(html).toContain("Use AI"); // one-tap adopt (Revert-to-AI / Use-AI)
  });

  it("attributes a colleague's edit distinctly from the viewer's own", () => {
    expect(render(editedDoseSession, "someone-else")).toContain("Edited by a colleague");
  });

  it("auto-satisfies the carried-forward confirm when the dose was edited (Q4) — no 'Confirm dose'", () => {
    expect(render(editedDoseSession)).not.toContain("Confirm dose");
  });

  it("still asks to confirm a carried-forward dose that was NOT edited", () => {
    const notEdited = session({
      treatments: [{ treatmentKey: "t|cheeks|voluma|c1", area: "cheeks", product: "voluma", quantityText: "20 units", carriedForward: true }],
      treatment_review: [{ category: "carried_forward", key: "cheeks|voluma", reason: "confirm the dose" }],
    });
    expect(render(notEdited)).toContain("Confirm dose");
  });

  it("surfaces a parked overlay orphan as a review chip (a lost edit is never silent)", () => {
    const withOrphan = session({
      treatments: [{ treatmentKey: "t|forehead|botox|c2", area: "forehead", product: "botox" }],
      treatment_overlay_orphans: [{ treatmentKey: "t|cheeks|voluma|c1", field: "lot", value: "D-4471", aiValue: "AI-000", parked: true }],
    });
    const html = withOrphan ? render(withOrphan) : "";
    expect(html).toContain("Parked edits");
    expect(html).toContain("D-4471");
  });
});
