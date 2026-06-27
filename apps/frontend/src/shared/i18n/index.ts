import React from "react";
import { setAppLanguage } from "../lib/datetime";
import { LANGS, MESSAGES, type Lang } from "./messages";

export { LANGS, LANG_LABEL, MESSAGES } from "./messages";
export type { Lang } from "./messages";

const STORAGE_KEY = "engram-ui-lang";

/** Text direction for a language (Persian is RTL). */
export function dirFor(lang: Lang): "rtl" | "ltr" {
  return lang === "fa" ? "rtl" : "ltr";
}

function isLang(value: unknown): value is Lang {
  return value === "fa" || value === "en";
}

/** Initial UI language for the public surfaces: stored choice → browser language → Persian (Iran-first). */
export function detectInitialLang(): Lang {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (isLang(stored)) return stored;
    } catch {
      // ignore storage access errors (private mode, etc.)
    }
    const nav = window.navigator?.language?.toLowerCase() ?? "";
    if (nav.startsWith("en")) return "en";
  }
  return "fa";
}

function persistLang(lang: Lang): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // non-fatal
  }
}

/** Reflect the language on <html> so direction + lang apply page-wide (background, scrollbars, etc.). */
export function applyDocumentLang(lang: Lang): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lang;
  document.documentElement.dir = dirFor(lang);
}

/** Reset <html> to the authenticated app's defaults (English LTR — the app UI is not yet translated). */
export function resetDocumentToAppDefault(): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = "en";
  document.documentElement.dir = "ltr";
}

/** Translate a key in a language, filling `{var}` placeholders. Falls back to English, then the key. */
export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const template = MESSAGES[lang]?.[key] ?? MESSAGES.en[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

export type Translator = (key: string, vars?: Record<string, string | number>) => string;

/**
 * Language for the AUTHENTICATED clinic app. English-only for now (see messages.ts) — but new authed
 * chrome must still go through the catalog so it is translatable, not a hardcoded regression for the
 * Persian-UI work. When the authed app is wired to a live language, this is the single swap point.
 */
export const APP_LANG: Lang = "en";

/**
 * Translator for the authenticated app. Resolves against {@link APP_LANG} today, but every key it
 * reads lives in the shared catalog in both en + fa, so the Persian copy is already in place. Use this
 * for NEW authed chrome instead of hardcoding literals; clinical content (report-language text such as
 * a safety flag's body) is NOT chrome and is rendered verbatim, never through a translator.
 */
export function appT(key: string, vars?: Record<string, string | number>): string {
  return translate(APP_LANG, key, vars);
}

export interface UiLang {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  t: Translator;
  dir: "rtl" | "ltr";
}

/**
 * UI-language state for the public / first-run surfaces. Persists the choice, reflects it on <html>,
 * and returns a bound translator. Use only on unauthenticated surfaces; the authed app reads the
 * tenant's app language for date formatting separately.
 */
export function useUiLang(): UiLang {
  const [lang, setLangState] = React.useState<Lang>(() => detectInitialLang());

  React.useEffect(() => {
    applyDocumentLang(lang);
  }, [lang]);

  const setLang = React.useCallback((next: Lang) => {
    persistLang(next);
    setLangState(next);
  }, []);

  const toggleLang = React.useCallback(() => {
    setLangState((current) => {
      const next: Lang = current === "fa" ? "en" : "fa";
      persistLang(next);
      return next;
    });
  }, []);

  const t = React.useCallback<Translator>((key, vars) => translate(lang, key, vars), [lang]);

  return { lang, setLang, toggleLang, t, dir: dirFor(lang) };
}

// ---------------------------------------------------------------------------
// Authenticated-app language seam
//
// The public surfaces own their UI language locally (`useUiLang` + localStorage). The AUTHENTICATED
// app instead follows the tenant's APP language (`auth.tenant.appLanguage`) — distinct from
// `reportLanguage`, which scopes only clinical CONTENT. `AppLangProvider` is the single source that
// drives `t()` (chrome) + the document direction for every authed surface.
// ---------------------------------------------------------------------------

/** Layout effect in the browser; a passive effect under SSR/test renderers that have no DOM. */
const useIsomorphicLayoutEffect = typeof window !== "undefined" ? React.useLayoutEffect : React.useEffect;

/**
 * Normalize a tenant's stored app-language string to a supported UI language. Total + deterministic,
 * never throws: `fa`/`fa-*` → Persian; everything else (`en`, `ar` (ships later), null, garbage) →
 * English, the safe default. New languages get a branch here, not a second seam.
 */
export function toLang(value: string | null | undefined): Lang {
  return typeof value === "string" && value.toLowerCase().startsWith("fa") ? "fa" : "en";
}

/** App-language bundle for authed components: the active language, a bound translator, and direction. */
export interface AppLang {
  lang: Lang;
  t: Translator;
  dir: "rtl" | "ltr";
}

const AppLangContext = React.createContext<AppLang | null>(null);

/**
 * App-language context for the AUTHENTICATED app. Provides `t()` (chrome only — never clinical
 * content) and reflects the tenant's app language on `<html>` (dir + lang). This is the SOLE authority
 * that writes `<html dir/lang>` on authed surfaces: on login it overrides whatever the public shell
 * (`useUiLang` + `engram-ui-lang` localStorage) left there. Date/Jalali formatting is kept in lockstep
 * via `setAppLanguage`, set during render (before children render) so the first authed paint already
 * formats dates in the correct calendar — no flash.
 */
export function AppLangProvider({ lang, children }: { lang: Lang; children: React.ReactNode }): React.ReactElement {
  setAppLanguage(lang);

  const value = React.useMemo<AppLang>(
    () => ({ lang, t: (key, vars) => translate(lang, key, vars), dir: dirFor(lang) }),
    [lang],
  );

  // Apply direction + lang to <html> before paint, so RTL/LTR is correct on the first authed frame
  // and any leftover public-surface direction is overridden cleanly (no stale dir, no flash).
  useIsomorphicLayoutEffect(() => {
    applyDocumentLang(lang);
  }, [lang]);

  return React.createElement(AppLangContext.Provider, { value }, children);
}

/** App-language bundle ({ lang, t, dir }) for authed components. Throws if used outside the provider. */
export function useAppLang(): AppLang {
  const ctx = React.useContext(AppLangContext);
  if (!ctx) {
    throw new Error("useAppLang must be used within <AppLangProvider> (authenticated app).");
  }
  return ctx;
}

/** Bound translator for authed components — sugar for `useAppLang().t`. */
export function useT(): Translator {
  return useAppLang().t;
}
