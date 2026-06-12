import { API_BASE } from "../../shared/lib/config";

/**
 * Patient-surface read API (AES-401/403).
 *
 * The public share endpoints take no auth — the token in the URL is the capability. The backend
 * serves only the curated snapshot (sections + media + aftercare) and returns 404 for unknown,
 * revoked, or expired tokens with no existence leak. This module is intentionally standalone: the
 * public patient page must never depend on clinic auth/state.
 */

/** A curated section of the report (label + body). Empty-body sections are dropped server-side. */
export interface ShareSection {
  label: string;
  body: string;
}

/** A curated before/after photo. `url` is the public, token-scoped media endpoint. */
export interface ShareMedia {
  captureId: string;
  caption: string | null;
  url: string;
}

/** The aftercare block — a snapshotted template or inline instructions. */
export interface ShareAftercare {
  templateId: string | null;
  name: string;
  body: string;
}

/** The read-only curated payload a patient receives (`GET /share/{token}`). */
export interface SharePayload {
  schemaVersion: string;
  payloadType: string;
  status: "active" | "revoked" | "expired";
  clinic: { name: string | null };
  patientName: string | null;
  title: string | null;
  visitDate: string | null;
  sections: ShareSection[];
  media: ShareMedia[];
  aftercare: ShareAftercare | null;
  createdAt: string | null;
  expiresAt: string | null;
}

/** How a load attempt resolved, so the page can render the right state without leaking existence. */
export type ShareLoadResult =
  | { kind: "ok"; payload: SharePayload }
  | { kind: "unavailable" } // 404: unknown / revoked / expired — one indistinguishable state (AES-403)
  | { kind: "error" }; // network or server failure — retryable, not a verdict on the link

/** Origin (no `/api/v1`) for rebasing token-scoped media when the API lives on another host. */
function apiOrigin(): string {
  if (/^https?:\/\//.test(API_BASE)) return API_BASE.replace(/\/api\/v1\/?$/, "");
  return "";
}

/**
 * Resolve the public media endpoint for a curated photo. Built from the token + captureId so it
 * works whether the API is same-origin (proxy/nginx) or a configured cross-origin host.
 */
export function shareMediaUrl(token: string, captureId: string): string {
  const path = `/share/${encodeURIComponent(token)}/media/${encodeURIComponent(captureId)}`;
  if (/^https?:\/\//.test(API_BASE)) return `${apiOrigin()}/api/v1${path}`;
  return `${API_BASE}${path}`;
}

/**
 * Fetch a patient share by token.
 *
 * Returns a discriminated result rather than throwing so the page can distinguish a deliberately
 * closed link (404 → `unavailable`) from a transient failure (→ `error`). A revoked or expired link
 * is indistinguishable from an unknown one by design (no existence leak).
 */
export async function fetchShare(token: string, signal?: AbortSignal): Promise<ShareLoadResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/share/${encodeURIComponent(token)}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch {
    return { kind: "error" };
  }
  if (response.status === 404) return { kind: "unavailable" };
  if (!response.ok) return { kind: "error" };
  try {
    const payload = (await response.json()) as SharePayload;
    return { kind: "ok", payload };
  } catch {
    return { kind: "error" };
  }
}
