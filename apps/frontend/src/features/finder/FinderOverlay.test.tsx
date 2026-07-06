import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../shared/i18n";
import type { SyncHealth } from "../../domain/appTypes";
import type { CaptureSession } from "../../domain/types";
import type { MemoryApi } from "../memory/useMemoryApi";
import { FinderOverlay } from "./FinderOverlay";

// AES-1201/1204 — hermetic first-paint render of the finder overlay: proves the chrome flips with the
// app language (fa vs en, RTL-ready) while verbatim clinical CONTENT (patient names, visit labels)
// renders as-is. renderToStaticMarkup runs no effects, so the async recent/ledger loads never fire —
// we assert the synchronous chrome + the "Today's visits" grain (computed from the sessions prop).

const online: SyncHealth = { online: true, backendReachable: true, pendingCaptures: 0, pendingOperations: 0, syncing: false };
const offline: SyncHealth = { ...online, online: false, backendReachable: false };

// A minimal MemoryApi stub — its async binders are never awaited under static markup (no effects run).
const memoryApi = {
  listPatientMemory: async () => ({ items: [], limit: 6, offset: 0, total: 0 }),
  smartSearchPatients: async () => ({ query: "", total: 0, items: [] }),
} as unknown as MemoryApi;

const today: CaptureSession = {
  id: "s-today",
  label: "Follow-up",
  time: "",
  dateLabel: "",
  duration: "",
  summary: "botox review",
  status: "processing",
  items: [],
  patientName: "سارا کریمی",
  // Captured now, so the finder's "Today's visits" grain includes it on first paint.
  capturedAt: new Date().toISOString(),
};

function render(lang: string, sync: SyncHealth): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang(lang)}>
      <FinderOverlay
        onClose={() => {}}
        memoryApi={memoryApi}
        sessions={[today]}
        syncHealth={sync}
        onOpenPatient={() => {}}
        onOpenSession={() => {}}
      />
    </AppLangProvider>,
  );
}

describe("FinderOverlay — bilingual chrome", () => {
  it("renders the placeholder + hint + today's-visits grain in Persian under fa", () => {
    const html = render("fa", online);
    expect(html).toContain("جستجوی بیمار، ویزیت، یا شمارهٔ لات…"); // finder.placeholder
    expect(html).toContain("ویزیت‌های امروز"); // finder.group.visits
    expect(html).toContain('role="dialog"');
  });

  it("renders the placeholder + hint + today's-visits grain in English under en", () => {
    const html = render("en", online);
    expect(html).toContain("Search patients, visits, or a lot number…"); // finder.placeholder
    expect(html).toContain("visits"); // finder.group.visits (apostrophe is HTML-escaped in markup)
    expect(html).toContain("Search by name, phone, or national ID"); // finder.hint
  });

  it("shows the offline note when offline (the preserved 'limited' fallback cue)", () => {
    const en = render("en", offline);
    // Apostrophe in "You're" is HTML-escaped, so assert the un-apostrophed tail + the marker class.
    expect(en).toContain("offline. Patient search may be limited.");
    expect(en).toContain("finder-offline");
    const fa = render("fa", offline);
    expect(fa).toContain("finder-offline");
  });
});

describe("FinderOverlay — verbatim clinical content", () => {
  it("renders a visit's patient name + label as-is, independent of app language", () => {
    for (const lang of ["fa", "en"]) {
      const html = render(lang, online);
      expect(html).toContain("سارا کریمی"); // patient name — clinical content, never translated
      expect(html).toContain("Follow-up"); // visit label
    }
  });
});
