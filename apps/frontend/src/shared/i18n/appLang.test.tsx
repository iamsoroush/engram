import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { formatDate, setAppLanguage } from "../lib/datetime";
import { AppLangProvider, toLang, translate, useT } from "./index";

// A2 — prove the authed-app language wiring: AppLangProvider(lang) → useT() → t() output flips with
// the app language, falling back to English for anything unsupported. We render a tiny consumer through
// the REAL provider + hook (not the pure translate() helper) so the test exercises the actual seam the
// app uses. renderToStaticMarkup keeps it pure: no DOM, no shipped test scaffolding.

function Probe() {
  const t = useT();
  return <span>{t("common.back")}</span>;
}

function renderWith(appLanguage: string | null | undefined): string {
  return renderToStaticMarkup(
    <AppLangProvider lang={toLang(appLanguage)}>
      <Probe />
    </AppLangProvider>,
  );
}

describe("AppLangProvider + useT", () => {
  it("renders chrome in Persian when the app language is fa", () => {
    expect(renderWith("fa")).toContain("بازگشت");
  });

  it("renders chrome in English when the app language is en", () => {
    expect(renderWith("en")).toContain("Back");
  });

  it("falls back to English for ar / null / undefined / unknown app languages", () => {
    expect(renderWith("ar")).toContain("Back");
    expect(renderWith(null)).toContain("Back");
    expect(renderWith(undefined)).toContain("Back");
    expect(renderWith("klingon")).toContain("Back");
  });
});

describe("Jalali date formatting follows the app language (A3 non-regression)", () => {
  // The locale-aware formatter is untouched by S1; this guards that moving setAppLanguage into the
  // provider didn't break the calendar/digits. The Evaluator's e2e asserts a date rendered in-shell.
  const iso = "2026-06-20T08:30:00.000Z";
  afterEach(() => setAppLanguage("en")); // module-global; reset so tests stay order-independent

  it("renders Persian (Jalali) digits under fa", () => {
    setAppLanguage("fa");
    expect(formatDate(iso, { month: "short", day: "numeric" })).toMatch(/[۰-۹]/);
  });

  it("renders Latin digits (no Persian) under en", () => {
    setAppLanguage("en");
    const out = formatDate(iso, { month: "short", day: "numeric" });
    expect(out).toMatch(/[0-9]/);
    expect(out).not.toMatch(/[۰-۹]/);
  });
});

describe("mixed-digit policy (S6): only NUMERIC t() values get Persian digits under fa", () => {
  // Surgically scoped so DATA + Latin tokens are never corrupted (Evaluator amendment 3).
  it("converts numeric interpolation values to Persian digits under fa", () => {
    expect(translate("fa", "qa.visitCount", { n: 12 })).toBe("۱۲ ویزیت");
  });

  it("leaves STRING interpolation values untouched under fa (names, Latin tokens with digits)", () => {
    // tier token "MVP v2" passed as a string var keeps Western digits — no "MVP v۲" corruption.
    expect(translate("fa", "capture.toastSwitchedTier", { tier: "Pro" })).toBe("به Pro تغییر یافت.");
    expect(translate("fa", "qa.routedTo", { name: "Clinic 2" })).toBe("ارجاع‌شده به Clinic 2.");
  });

  it("does NOT convert digits under en (numeric value stays Western)", () => {
    expect(translate("en", "qa.visitCount", { n: 12 })).toBe("12 visit");
  });
});

describe("toLang", () => {
  it("maps fa and fa-* (any case) to Persian", () => {
    expect(toLang("fa")).toBe("fa");
    expect(toLang("fa-IR")).toBe("fa");
    expect(toLang("FA")).toBe("fa");
  });

  it("maps everything else (en, ar, empty, null, garbage) to English", () => {
    expect(toLang("en")).toBe("en");
    expect(toLang("ar")).toBe("en");
    expect(toLang("")).toBe("en");
    expect(toLang(null)).toBe("en");
    expect(toLang(undefined)).toBe("en");
    expect(toLang("nonsense")).toBe("en");
  });
});
