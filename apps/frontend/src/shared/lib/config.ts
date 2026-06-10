export const configuredApiBase = import.meta.env.VITE_API_URL || "/api/v1";
export const API_BASE =
  typeof window !== "undefined" && window.location.hostname !== "localhost" && configuredApiBase.includes("localhost")
    ? "/api/v1"
    : configuredApiBase;

export const DEV_AUTH_STORAGE_KEY = "notari-dev-auth";
export const IS_DEV = import.meta.env.DEV;
