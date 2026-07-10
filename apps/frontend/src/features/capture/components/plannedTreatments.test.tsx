import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../../shared/i18n";
import type { CaptureSession } from "../../../domain/types";
import { ProLiveReport } from "./LiveReport";

// G7 — a PLANNED treatment (future-tense / stated intent) renders under Plan & follow-up as a calm
// "Planned" line, never in the treatment-performed table; PERFORMED treatments render as performed.

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

function render(sess: CaptureSession, lang: "en" | "fa" = "en"): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang(lang)}>
      <ProLiveReport session={sess} onResolveFile={async () => ""} canEditTreatments currentUserId="u1" />
    </AppLangProvider>,
  );
}

const mixed = session({
  treatments: [
    { treatmentKey: "t|forehead|botox|c1", area: "forehead", product: "botox", quantityText: "20 units", status: "performed", sourceCaptureIds: ["c1"], carriedForward: false },
    { treatmentKey: "t|lips|gel|c2", area: "lips", product: "lip-gel-plan", quantityText: "1 cc", status: "planned", sourceCaptureIds: ["c2"], carriedForward: false },
  ],
});

describe("planned vs performed treatments (G7)", () => {
  it("renders a planned treatment under a Planned line, not in the performed table", () => {
    const html = render(mixed);
    expect(html).toContain("report-planned-treatments");
    expect(html).toContain("lip-gel-plan"); // the planned item is shown (under Plan & follow-up)
    expect(html).toContain(">Planned<"); // the localized chrome label
    // The planned item is NOT inside the performed treatments list markup:
    const performedBlock = html.split("report-planned-treatments")[0];
    expect(performedBlock).not.toContain("lip-gel-plan");
    // The performed treatment still renders as performed:
    expect(performedBlock).toContain("botox");
  });

  it("localizes the Planned label to Persian", () => {
    const html = render(mixed, "fa");
    expect(html).toContain("برنامه‌ریزی‌شده");
  });

  it("shows no planned block when every treatment is performed", () => {
    const html = render(session({ treatments: [{ treatmentKey: "k", area: "forehead", product: "botox", status: "performed", sourceCaptureIds: ["c1"], carriedForward: false }] }));
    expect(html).not.toContain("report-planned-treatments");
  });
});
