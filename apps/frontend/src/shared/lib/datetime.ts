// App-wide date/time formatting that follows the clinic's language. When the language is Persian we
// format with the `fa-IR` locale, which makes Intl use the Jalali (Shamsi) calendar with Persian
// month names and Persian digits automatically — so "Jun 20" renders as «۳۰ خرداد». Set once from
// the auth'd tenant's report language; every formatter reads this single source.
let appLanguage = "en";

export function setAppLanguage(language?: string | null): void {
  appLanguage = (language || "en").toLowerCase();
}

/** True when the app is in Persian (Jalali) mode. */
export function isPersianLocale(): boolean {
  return appLanguage.startsWith("fa");
}

function localeTag(): string {
  return isPersianLocale() ? "fa-IR" : "en";
}

/** Locale-aware Intl.DateTimeFormat (Jalali when Persian). */
export function appDateTimeFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(localeTag(), options);
}

/** Format an ISO/Date value (empty string for null/invalid). Defaults to a short month+day. */
export function formatDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" },
): string {
  if (value == null || value === "") return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return appDateTimeFormat(options).format(date);
}

/** Format a clock time (24h, Persian digits when Persian). */
export function formatTime(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hour12: false },
): string {
  return formatDate(value, options);
}
