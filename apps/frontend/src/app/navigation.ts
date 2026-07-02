import type { Screen } from "../domain/types";

const SCREEN_HASHES: Screen[] = [
  "active-session",
  "patients",
  "qa-inbox",
  "search",
  "settings",
  "profile",
  "team",
  "insights",
  "plan",
  "switch-clinic",
];

export function screenFromLocation(): Screen {
  if (typeof window === "undefined") return "active-session";
  const hash = window.location.hash.replace(/^#/, "") as Screen;
  return SCREEN_HASHES.includes(hash) && hash !== "active-session" ? hash : "active-session";
}

export function replaceScreenLocation(screen: Screen) {
  if (typeof window === "undefined" || !SCREEN_HASHES.includes(screen)) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${screen}`);
}
