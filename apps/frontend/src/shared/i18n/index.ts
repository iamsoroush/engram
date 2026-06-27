import React from "react";
import { LANGS, MESSAGES, type Lang } from "./messages";

export { LANGS, LANG_LABEL, MESSAGES } from "./messages";
export type { Lang } from "./messages";

const STORAGE_KEY = "memara-ui-lang";

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
