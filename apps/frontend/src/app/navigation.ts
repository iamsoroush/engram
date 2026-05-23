import type { Screen } from "../domain/types";

export function screenFromLocation(): Screen {
  if (typeof window === "undefined") return "active-session";
  const hash = window.location.hash.replace(/^#/, "");
  if (hash === "patients") return "patients";
  if (hash === "search") return "search";
  return "active-session";
}

export function replaceScreenLocation(screen: Screen) {
  if (typeof window === "undefined" || !["active-session", "patients", "search"].includes(screen)) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${screen}`);
}

export function shouldOpenCameraDirectly() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}
