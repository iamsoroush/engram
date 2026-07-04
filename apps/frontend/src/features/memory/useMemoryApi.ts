import React from "react";
import type {
  AftercareTemplate,
  AssignmentSuggestionResponse,
  ClinicMember,
  CreatePatientShareInput,
  DuplicateCheckResponse,
  LastVisitInfo,
  LotLedger,
  LotRecallResult,
  PatientMemoryDetailResponse,
  PatientMemoryFilter,
  PatientMemoryListResponse,
  PatientShare,
  SmartListCounts,
  SmartListKey,
  SmartListResponse,
  SmartPatientSearchResponse,
  WorklistEntry,
  WorklistResponse,
} from "../../domain/appTypes";
import type { CaptureItem, CaptureSession } from "../../domain/types";
import {
  cancelWorklistEntry,
  checkDuplicatePatient,
  createAftercareTemplate,
  createPatientShare,
  createWorklistEntry,
  deleteAftercareTemplate,
  fetchAssignmentSuggestion,
  fetchClinicMembers,
  fetchLastVisit,
  fetchLotLedger,
  fetchLotRecall,
  fetchPatientMemory,
  fetchPatientMemoryDetail,
  fetchSession,
  fetchSessionCaptures,
  fetchSmartList,
  fetchSmartListCounts,
  fetchWorklist,
  listAftercareTemplates,
  markWorklistEntrySeen,
  resolveCaptureFileUrl,
  revokePatientShare,
  searchPatientsSmart,
  updateAftercareTemplate,
} from "../../services/api/client";
import { openQaChannel, type QaThreadSummary } from "../qa/qaClient";
import { useApi } from "../../app/providers/ApiProvider";
import { useCapabilities } from "../../app/providers/CapabilitiesProvider";

// Seam A1/E (frontend-refactor plan §3, increment 6). The Clinical-Memory feature's API surface, bound
// once to the context `apiFetch` and capability-gated internally — so PatientsHome (and the App shell's
// remaining memory consumers) read one hook instead of receiving ~26 `apiFetch`-bound callback props.
// The Pro-only binders resolve to `undefined` for Basic (the old `onFetchX = isPro ? cb : undefined`
// prop-gating now lives at the point of use, seam A3). The returned object is MEMOIZED on
// `apiFetch` + capabilities — a stable identity is load-bearing: these binders feed child effects
// (smart search, gallery, resolvers), so a fresh reference every render would re-fire them.

export type MemoryApi = {
  getPatientMemoryDetail: (patientId: string) => Promise<PatientMemoryDetailResponse>;
  listPatientMemory: (params: {
    query?: string;
    filter: PatientMemoryFilter;
    limit?: number;
    offset?: number;
    clinicianId?: string;
  }) => Promise<PatientMemoryListResponse>;
  smartSearchPatients: (query: string) => Promise<SmartPatientSearchResponse>;
  duplicateCheckPatient: (body: { displayName?: string; nationalId?: string; phone?: string }) => Promise<DuplicateCheckResponse>;
  loadSessionCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  loadSession: (sessionId: string) => Promise<CaptureSession>;
  resolveSourceFile: (endpoint: string) => Promise<string>;
  loadLastVisit: (patientId: string) => Promise<LastVisitInfo>;
  listAftercareTemplates: () => Promise<AftercareTemplate[]>;
  createAftercareTemplate: (draft: Parameters<typeof createAftercareTemplate>[1]) => ReturnType<typeof createAftercareTemplate>;
  updateAftercareTemplate: (id: string, draft: Parameters<typeof updateAftercareTemplate>[2]) => ReturnType<typeof updateAftercareTemplate>;
  deleteAftercareTemplate: (id: string) => ReturnType<typeof deleteAftercareTemplate>;
  createShare: (input: CreatePatientShareInput) => Promise<PatientShare>;
  revokeShare: (id: string) => Promise<PatientShare>;
  loadAssignmentSuggestion: (sessionId: string) => Promise<AssignmentSuggestionResponse>;
  listWorklist: (options?: {
    scope?: "mine" | "clinic";
    status?: "waiting" | "seen" | "cancelled" | "all";
    clinicianId?: string;
  }) => Promise<WorklistResponse>;
  lineUpPatient: (input: { patientId: string; clinicianUserId: string; note?: string }) => Promise<WorklistEntry>;
  markWorklistSeen: (entryId: string, sessionId?: string) => Promise<WorklistEntry>;
  cancelWorklistEntry: (entryId: string) => Promise<WorklistEntry>;
  listClinicMembers: () => Promise<ClinicMember[]>;
  // Pro-gated — `undefined` for Basic (capability seam A3). The consumers treat absence as "hide".
  openQaChannel?: (patientId: string) => Promise<QaThreadSummary>;
  fetchSmartListCounts?: () => Promise<SmartListCounts>;
  fetchSmartList?: (key: SmartListKey) => Promise<SmartListResponse>;
  fetchLotLedger?: () => Promise<LotLedger>;
  fetchLotRecall?: (query: { lot?: string; product?: string }) => Promise<LotRecallResult>;
};

export function useMemoryApi(): MemoryApi {
  const apiFetch = useApi();
  const { canUseQa, canUseSmartLists } = useCapabilities();
  return React.useMemo<MemoryApi>(
    () => ({
      getPatientMemoryDetail: (patientId) => fetchPatientMemoryDetail(apiFetch, patientId),
      listPatientMemory: (params) => fetchPatientMemory(apiFetch, params),
      smartSearchPatients: (query) => searchPatientsSmart(apiFetch, query),
      duplicateCheckPatient: (body) => checkDuplicatePatient(apiFetch, body),
      loadSessionCaptures: (sessionId) => fetchSessionCaptures(apiFetch, sessionId),
      loadSession: (sessionId) => fetchSession(apiFetch, sessionId),
      resolveSourceFile: (endpoint) => resolveCaptureFileUrl(apiFetch, endpoint),
      loadLastVisit: (patientId) => fetchLastVisit(apiFetch, patientId),
      listAftercareTemplates: () => listAftercareTemplates(apiFetch),
      createAftercareTemplate: (draft) => createAftercareTemplate(apiFetch, draft),
      updateAftercareTemplate: (id, draft) => updateAftercareTemplate(apiFetch, id, draft),
      deleteAftercareTemplate: (id) => deleteAftercareTemplate(apiFetch, id),
      createShare: (input) => createPatientShare(apiFetch, input),
      revokeShare: (id) => revokePatientShare(apiFetch, id),
      loadAssignmentSuggestion: (sessionId) => fetchAssignmentSuggestion(apiFetch, sessionId),
      listWorklist: (options) => fetchWorklist(apiFetch, options),
      lineUpPatient: (input) => createWorklistEntry(apiFetch, input),
      markWorklistSeen: (entryId, sessionId) => markWorklistEntrySeen(apiFetch, entryId, sessionId),
      cancelWorklistEntry: (entryId) => cancelWorklistEntry(apiFetch, entryId),
      listClinicMembers: () => fetchClinicMembers(apiFetch),
      openQaChannel: canUseQa ? (patientId) => openQaChannel(apiFetch, patientId) : undefined,
      fetchSmartListCounts: canUseSmartLists ? () => fetchSmartListCounts(apiFetch) : undefined,
      fetchSmartList: canUseSmartLists ? (key) => fetchSmartList(apiFetch, key) : undefined,
      fetchLotLedger: canUseSmartLists ? () => fetchLotLedger(apiFetch) : undefined,
      fetchLotRecall: canUseSmartLists ? (query) => fetchLotRecall(apiFetch, query) : undefined,
    }),
    [apiFetch, canUseQa, canUseSmartLists],
  );
}
