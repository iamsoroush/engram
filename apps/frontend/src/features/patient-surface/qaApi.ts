import { API_BASE } from "../../shared/lib/config";

/**
 * Public post-session Q&A API (AES-402/403).
 *
 * The Pro payload of the patient surface: a tokenized Q&A thread. Like the share endpoints these
 * take no auth — the token in the URL is the capability — and the backend serves the patient ONLY
 * their own questions + the doctor-verified replies (drafts and clinic internals are withheld). A
 * revoked/unknown token returns 404 with no existence leak. Standalone by design: the public page
 * never depends on clinic auth/state.
 */

/** A doctor-verified reply to a question (only ever present once a clinician approved + sent it). */
export interface QaReply {
  text: string;
  repliedAt: string | null;
  byline: string;
  verified: boolean;
}

/** One exchange: the patient's question and its reply (if the clinic has replied yet). */
export interface QaExchange {
  id: string;
  question: string;
  askedAt: string | null;
  status: "answered" | "awaiting" | "closed";
  reply: QaReply | null;
}

/** The read-only Q&A thread a patient sees (`GET /qa/{token}`). */
export interface QaThreadPayload {
  schemaVersion: string;
  payloadType: string;
  status: "active";
  clinic: { name: string | null };
  patientName: string | null;
  /** The clinic's language (e.g. "fa"), so the page localizes its chrome to match the content. */
  language: string | null;
  exchanges: QaExchange[];
}

/** How a load attempt resolved, so the page can render the right state without leaking existence. */
export type QaLoadResult =
  | { kind: "ok"; payload: QaThreadPayload }
  | { kind: "unavailable" } // 404: unknown / revoked — one indistinguishable state (AES-403)
  | { kind: "error" }; // network or server failure — retryable

/** Fetch the patient's Q&A thread by token. Discriminated result (no existence leak on 404). */
export async function fetchQaThread(token: string, signal?: AbortSignal): Promise<QaLoadResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/qa/${encodeURIComponent(token)}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch {
    return { kind: "error" };
  }
  if (response.status === 404) return { kind: "unavailable" };
  if (!response.ok) return { kind: "error" };
  try {
    const payload = (await response.json()) as QaThreadPayload;
    return { kind: "ok", payload };
  } catch {
    return { kind: "error" };
  }
}

/** Post a new patient question. The clinic drafts + verifies a reply before it appears in the thread. */
export async function askQuestion(token: string, question: string): Promise<{ ok: boolean }> {
  try {
    const response = await fetch(`${API_BASE}/qa/${encodeURIComponent(token)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    return { ok: response.ok };
  } catch {
    return { ok: false };
  }
}
