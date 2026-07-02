import type { ApiFetch } from "../../domain/appTypes";
import { API_BASE } from "../../shared/lib/config";

/**
 * Client for the owner/admin Insights endpoints (`/api/v1/insights/*`). All responses are
 * pre-aggregated server-side, so the screen renders them with no heavy reshaping. `/treatments`
 * returns 403 on Basic — callers map that to the Pro upsell (errors carry `.status`).
 */

export type RangeKey = "this-week" | "this-month" | "last-3-months" | "this-year" | "custom";
export type RangeParams = { range: RangeKey; from?: string; to?: string };

export type Delta = { current: number; previous: number; pct: number | null };

export interface OverviewResponse {
  range: string;
  kpis: { visits: Delta; newPatients: Delta; activePatients: Delta; captures: Delta };
  activitySeries: Array<{ date: string; visits: number; captures: number; newPatients: number }>;
  newVsReturning: { new: number; returning: number; repeatRate: number | null };
  busyHeatmap: number[][];
  needsAttention: { unassignedCaptures: number; awaitingReview: number; failed: number };
}

export interface TeamMemberStat {
  userId: string;
  name: string | null;
  role: string;
  lastActiveAt: string | null;
  visits: number;
  patients: number;
  captures: number;
  share: number;
}
export interface TeamResponse {
  range: string;
  members: TeamMemberStat[];
}

export interface PatientsResponse {
  range: string;
  totalActive: number;
  recency: { active: number; lapsing: number; lapsed: number; neverVisited: number };
  ageHistogram: Array<{ band: string; count: number }>;
  sexSplit: { female: number; male: number; other: number; unknown: number };
  growth: { baseline: number; buckets: Array<{ date: string; newPatients: number }> };
}

export interface TreatmentsResponse {
  range: string;
  topTreatments: Array<{ name: string; count: number }>;
  topProducts: Array<{ name: string; count: number }>;
  byArea: Array<{ name: string; count: number }>;
  consumption: Array<{ unit: string; total: number; count: number }>;
  mixKeys: string[];
  mixSeries: Array<{ date: string } & Record<string, number>>;
}

function query(params: RangeParams): string {
  const q = new URLSearchParams({ range: params.range });
  if (params.from) q.set("from", params.from);
  if (params.to) q.set("to", params.to);
  return q.toString();
}

async function getJson<T>(apiFetch: ApiFetch, path: string): Promise<T> {
  const response = await apiFetch(`${API_BASE}/insights/${path}`);
  if (!response.ok) {
    const error = new Error("Could not load insights") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return (await response.json()) as T;
}

export const fetchOverview = (apiFetch: ApiFetch, params: RangeParams) =>
  getJson<OverviewResponse>(apiFetch, `overview?${query(params)}`);
export const fetchTeamInsights = (apiFetch: ApiFetch, params: RangeParams) =>
  getJson<TeamResponse>(apiFetch, `team?${query(params)}`);
export const fetchPatientInsights = (apiFetch: ApiFetch, params: RangeParams) =>
  getJson<PatientsResponse>(apiFetch, `patients?${query(params)}`);
export const fetchTreatmentInsights = (apiFetch: ApiFetch, params: RangeParams) =>
  getJson<TreatmentsResponse>(apiFetch, `treatments?${query(params)}`);
