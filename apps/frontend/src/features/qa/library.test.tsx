import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../shared/i18n";
import type { ApiFetch } from "../../domain/appTypes";
import type { LibraryItem } from "./qaClient";
import { LibraryTab, TemplateRow } from "./LibraryTab";

// AES-410 — hermetic render of the Q&A knowledge library, proving the chrome flips with the app
// language (fa vs en) and that verbatim clinical CONTENT (a template's answer) renders as-is.
// renderToStaticMarkup keeps it pure: no DOM, no effects — so the async fetch never resolves and we
// assert the first-paint chrome (section headers + the New-template button) that renders synchronously,
// plus a pure TemplateRow render for the content assertion.

const templateItem: LibraryItem = {
  id: "t1",
  kind: "template",
  status: "active",
  title: "Retinoid start",
  question: "When can I start retinoids?",
  answer: "Start low and slow — twice a week, buffered with moisturiser.",
  language: "en",
  tags: ["retinoid", "aftercare"],
  sourceMessageId: null,
  indexed: true,
  createdAt: null,
  updatedAt: null,
};

// The stub is never actually awaited under renderToStaticMarkup (effects don't run), but it keeps the
// component's contract satisfied and mirrors the real client's canned-Response shape.
const stub: ApiFetch = async () =>
  new Response(
    JSON.stringify({
      templates: [templateItem],
      sentReplies: [],
      counts: { templates: 1, sentRepliesActive: 0, sentRepliesExcluded: 0 },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );

function renderTab(lang: string): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang(lang)}>
      <LibraryTab apiFetch={stub} onToast={() => {}} />
    </AppLangProvider>,
  );
}

describe("LibraryTab — bilingual chrome", () => {
  it("renders the section headers + New-template action in Persian under fa", () => {
    const html = renderTab("fa");
    expect(html).toContain("الگوها"); // qa.library.templates
    expect(html).toContain("پاسخ‌های نمایه‌شده"); // qa.library.sentReplies
    expect(html).toContain("الگوی جدید"); // qa.library.newTemplate
    expect(html).toContain('data-testid="qa-library"');
  });

  it("renders the section headers + New-template action in English under en", () => {
    const html = renderTab("en");
    expect(html).toContain("Templates"); // qa.library.templates
    expect(html).toContain("Indexed replies"); // qa.library.sentReplies
    expect(html).toContain("New template"); // qa.library.newTemplate
    expect(html).toContain('data-testid="qa-library-new"');
  });
});

describe("TemplateRow — verbatim clinical content", () => {
  it("renders a template's answer text as-is, independent of app language", () => {
    const row = (lang: string) =>
      renderToStaticMarkup(
        <AppLangProvider lang={toLang(lang)}>
          <TemplateRow item={templateItem} onEdit={() => {}} onDelete={() => {}} />
        </AppLangProvider>,
      );
    for (const lang of ["fa", "en"]) {
      const html = row(lang);
      expect(html).toContain("Start low and slow — twice a week, buffered with moisturiser.");
      expect(html).toContain('data-testid="qa-template-row"');
    }
  });
});
