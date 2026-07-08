import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../../shared/i18n";
import type { CaptureSession } from "../../../domain/types";
import { ProLiveReport } from "./LiveReport";

// R1 — a Persian report must render Persian section TITLES even when the tenant's report_language is
// NULL. The section titles ship in English by default; the fix infers the report language from an
// explicit report_language, then the report's own content script, then the app language — so titles
// and (Persian) body never disagree.

function session(sections: Array<{ id: string; title: string; text: string }>): CaptureSession {
  return {
    id: "session-1",
    label: "Session",
    time: "10:00",
    dateLabel: "Today",
    duration: "5m",
    summary: "",
    status: "processed",
    items: [],
    reportModel: {
      sections: sections.map((s) => ({ id: s.id, title: s.title, blocks: [{ type: "paragraph", text: s.text }] })),
    },
  } as unknown as CaptureSession;
}

const stubFile = async () => "";

function render(sess: CaptureSession, props: { reportLanguage?: string | null; appLanguage?: string | null }): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang("en")}>
      <ProLiveReport session={sess} onResolveFile={stubFile} reportLanguage={props.reportLanguage ?? null} appLanguage={props.appLanguage ?? null} />
    </AppLangProvider>,
  );
}

const persianReport = session([{ id: "visit-summary", title: "Visit summary", text: "بیمار برای تزریق فیلر گونه مراجعه کرد و درمان انجام شد." }]);
const englishReport = session([{ id: "visit-summary", title: "Visit summary", text: "Patient presented for cheek filler and treatment was performed." }]);

describe("report section-title language (R1)", () => {
  it("renders Persian titles when report_language is NULL but the body is Persian", () => {
    const html = render(persianReport, { reportLanguage: null, appLanguage: "en" });
    expect(html).toContain("خلاصه ویزیت");
    expect(html).not.toContain("Visit summary");
  });

  it("renders Persian titles when report_language is explicitly fa", () => {
    const html = render(persianReport, { reportLanguage: "fa", appLanguage: "en" });
    expect(html).toContain("خلاصه ویزیت");
  });

  it("falls back to the app language when report_language is NULL and there is no content signal", () => {
    const empty = session([{ id: "visit-summary", title: "Visit summary", text: "" }]);
    // Empty section blocks are filtered out, so there is no content to infer from → app language wins.
    expect(render(empty, { reportLanguage: null, appLanguage: "fa" })).not.toContain("Visit summary");
  });

  it("keeps English titles for an explicit English report even if faced with mixed input", () => {
    const html = render(englishReport, { reportLanguage: "en", appLanguage: "fa" });
    expect(html).toContain("Visit summary");
    expect(html).not.toContain("خلاصه ویزیت");
  });
});
