import type { Attribution, CaptureItem, CaptureItemType, CaptureSession } from "./types";

/** AES-905 role-permission presets, ordered low → high (each includes the one below). */
export type RolePreset = "contribute" | "reassign" | "full";
/** Effective per non-owner role preset, e.g. { assistant: "reassign", doctor: "contribute" }. */
export type RolePermissions = Record<string, RolePreset | string>;

export type CaptureDraft = {
  kind: Extract<CaptureItemType, "audio" | "photo" | "note">;
  detail?: string;
  file: Blob;
  filename: string;
  metadata?: Record<string, unknown>;
};

export type PendingCapture = {
  id: string;
  localCaptureId: string;
  localSessionId: string;
  clientCaptureId: string;
  sessionId?: string;
  backendSessionId?: string;
  backendCaptureId?: string;
  tenantId?: string;
  intoNew: boolean;
  retryCount: number;
  createdAt: number;
  draft: CaptureDraft;
  item: CaptureItem;
  session: CaptureSession;
};

export type PendingOperationType = "sessionTitle" | "patientAssignment" | "sessionProcessing";

export type PendingOperationStatus = "pending" | "syncing" | "failed";

export type PendingOperation = {
  id: string;
  type: PendingOperationType;
  localSessionId?: string;
  backendSessionId?: string;
  localPatientId?: string;
  backendPatientId?: string;
  tenantId?: string;
  payload: Record<string, unknown>;
  retryCount: number;
  status: PendingOperationStatus;
  createdAt: number;
  updatedAt: number;
  lastError?: string;
};

export type SyncHealth = {
  online: boolean;
  backendReachable: boolean | null;
  pendingCaptures: number;
  pendingOperations: number;
  syncing: boolean;
  lastError?: string;
};

export type Persona = "doctor" | "assistant" | "admin" | "patient-preview" | "therapist-b";

// Dev-login tenant selector: aesthetics Pro/Basic, or the single-plan therapy demo tenant.
export type DevTier = "pro" | "basic" | "therapy";

export type AuthUser = {
  id: string;
  email: string;
  displayName: string | null;
  persona?: Persona | string | null;
};

export type AuthTenant = {
  id: string;
  name: string;
  tier?: "basic" | "pro" | string;
  transcriptionLanguage?: string;
  reportLanguage?: string | null;
  /** App UI language + date calendar (Jalali when Persian); distinct from reportLanguage. */
  appLanguage?: string;
  matchStrictness?: "strict" | "balanced" | "lenient" | string;
  /** Story C (decision 2): include commercial brand names in a curated share's treatment line. */
  shareIncludeBrands?: boolean;
  /** A0 — vertical ("clinic" today) + the presentation label for its work-unit ("Session"). */
  vertical?: string;
  encounterLabel?: string;
  /** AES-905 — effective per non-owner role presets (defaults merged with tenant overrides). */
  rolePermissions?: RolePermissions;
};

export type AuthMembership = {
  tenantId: string;
  role: string;
};

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
  tenant: AuthTenant;
  memberships: AuthMembership[];
};

export type StoredAuthProfile = Pick<AuthSession, "refreshToken" | "user" | "tenant" | "memberships">;

export type ApiFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type PatientSummary = {
  id: string;
  displayName: string;
  nationalId?: string | null;
  phone?: string | null;
  lastVisit?: string | null;
};

export type PatientMemoryFilter = "recent" | "active" | "all" | "needs-input";

// Live per-task AI model selection (Settings → AI models). Blank model = worker env default.
export type AiModelTask = { task: string; label: string; model: string };
export type AiModelConfig = { tasks: AiModelTask[] };

export type PatientMemoryRow = {
  patientId: string;
  displayName: string;
  summary: string;
  summarySource: string;
  // Mock patient-memory lifecycle: "ready" once the (tier-aware) summary is generated,
  // "updating" while a recent change is being processed.
  memoryStatus?: "ready" | "updating" | string;
  memoryUpdatedAt?: string | null;
  generatedSummary?: string | null;
  ruleBasedSummary?: string | null;
  metadataSentence?: string | null;
  latestSessionMetadata?: {
    sessionId?: string | null;
    title?: string | null;
    status?: string | null;
    summary?: string | null;
    captureCount: number;
    capturedAt?: string | null;
    updatedAt?: string | null;
  } | null;
  latestSessionId?: string | null;
  activeSessionId?: string | null;
  activeSessionCount: number;
  sessionCount: number;
  complete: boolean;
  needsInput: boolean;
  needsInputItems?: Array<{
    id: string;
    sessionId?: string | null;
    kind: string;
    label?: string | null;
    reason?: string | null;
    createdAt?: string | null;
  }>;
  latestVisitAt?: string | null;
  updatedAt?: string | null;
};

export type PatientMemoryListResponse = {
  items: PatientMemoryRow[];
  limit: number;
  offset: number;
  total: number;
};

export type PatientMemoryTimelineSession = {
  sessionId: string;
  title?: string | null;
  status: string;
  summary: string;
  generatedSummary?: string | null;
  ruleBasedSummary?: string | null;
  captureCount: number;
  complete: boolean;
  needsInput: boolean;
  /** AES-901 — who ran this visit (for "by X" on the timeline). */
  createdByUserId?: string | null;
  createdBy?: Attribution | null;
  groupLabel: string;
  sortDate?: string | null;
  capturedAt?: string | null;
  updatedAt?: string | null;
};

export type PatientMemorySessionGroup = {
  label: string;
  sessions: PatientMemoryTimelineSession[];
};

export type PatientMemoryHistorySection = {
  label: string;
  body: string;
};

// The richer "patient history" brief shown atop the timeline. Pro fills `sections`
// (Story so far / Worth remembering / Right now); Basic fills `visits` (a structural recap).
export type PatientMemoryHistory = {
  mode: "pro" | "basic" | string;
  status: "ready" | "updating" | string;
  snapshot: string;
  sections: PatientMemoryHistorySection[];
  visits: string[];
  source: string;
  updatedAt?: string | null;
};

// A surfaced clinical flag on the line-up card (allergy/consent/preference/caution).
export type LineupCardFlag = {
  kind: "allergy" | "consent" | "preference" | "caution" | string;
  label: string;
};

// The deterministic hero photo for the line-up card (most recent clear after-photo of the primary
// area, else the latest photo). Endpoints resolve to the file via the capture content route.
export type LineupCardHero = {
  captureId: string;
  fileEndpoint: string;
  contentEndpoint: string;
  capturedAt: string | null;
  caption: string | null;
};

// The compact, glanceable line-up card (Pro only) shown in the worklist recap: ≤2 short paragraphs
// (story so far / right now), a deterministic hero photo, a "since last visit" delta, and flags.
export type LineupCard = {
  storySoFar: string;
  rightNow: string;
  flags: LineupCardFlag[];
  sinceLastVisit: string | null;
  hero: LineupCardHero | null;
  status: "ready" | "updating" | string;
  updatedAt?: string | null;
};

export type PatientMemoryDetailResponse = {
  patient: PatientMemoryRow;
  sessions: PatientMemoryTimelineSession[];
  groups: PatientMemorySessionGroup[];
  history?: PatientMemoryHistory | null;
  // Compact line-up card for the worklist recap (Pro; null for Basic / no captures).
  lineupCard?: LineupCard | null;
};

// --- Aesthetics-Basic deterministic services (docs/backend/aes-basic-api.md) ---

/** AES-204 — one ranked, match-annotated smart-search result (all patient fields + metadata). */
export type SmartPatientMatch = PatientSummary & {
  email?: string | null;
  status?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  /** 0–1, or null on the blank-query "recent" list. */
  score: number | null;
  /** national_id | phone | email | name | name_prefix | name_fuzzy | contact_partial */
  matchedOn: string[];
  reason: string;
};

export type SmartPatientSearchResponse = {
  query: string;
  total: number;
  items: SmartPatientMatch[];
};

/** AES-205 — a likely-existing patient surfaced by the duplicate guard at create time. */
export type DuplicateCandidate = {
  patientId: string;
  displayName: string;
  confidence: number;
  matchedOn: string[];
  reason: string;
  risks: string[];
};

export type DuplicateCheckResponse = {
  hasLikelyDuplicate: boolean;
  candidates: DuplicateCandidate[];
};

/** AES-301 — a deterministic "Assign to …?" suggestion for an unassigned visit. */
export type AssignmentSuggestionCandidate = {
  patientId: string;
  displayName: string;
  /** active_patient (a visit open right now) | recent_patient (most recently seen). */
  basis: string;
  reason: string;
  lastVisitAt: string | null;
};

export type AssignmentSuggestionResponse = {
  sessionId: string;
  alreadyAssigned: boolean;
  suggestion: AssignmentSuggestionCandidate | null;
  candidates: AssignmentSuggestionCandidate[];
};

/** AES-106/203 — a photo from the prior visit (before/after; untagged in Basic). */
export type LastVisitMedia = {
  captureId: string;
  type: string;
  fileEndpoint: string;
  contentEndpoint: string;
  capturedAt: string | null;
  caption?: string | null;
};

export type LastVisitInfo = {
  patientId: string;
  hasPriorVisit: boolean;
  visit: {
    sessionId: string;
    title: string;
    status: string;
    capturedAt: string | null;
    updatedAt: string | null;
    captureCount: number;
    note: string | null;
    noteSource: string | null;
    media: LastVisitMedia[];
    /** Playable voice memos from the prior visit (digest); count for the headline. */
    audio?: LastVisitMedia[];
    audioCount?: number;
  } | null;
  /** Deterministic "same as last time" pre-fill; null if the prior visit has no typed note. */
  sameAsLastTime: {
    note: string;
    fromSessionId: string;
    fromVisitAt: string | null;
    label: string;
  } | null;
};

/** One prior visit in the cross-visit photo strip (deterministic, newest-first). */
export type SessionRecentVisit = {
  sessionId: string;
  title: string;
  capturedAt: string | null;
  photoCount: number;
  photos: LastVisitMedia[];
};

/**
 * Deterministic patient context for the session/assignment surface (both tiers, zero AI).
 * The Basic card renders this directly; Pro layers intelligent Job-4 blocks on top and falls back
 * to it. From GET /patients/{id}/session-context.
 */
export type SessionContext = {
  patientId: string;
  /** The last-visit digest (full prior visit). */
  lastVisit: LastVisitInfo;
  /** Cross-visit photo strip for eyeball progress (bounded). */
  recentVisits: SessionRecentVisit[];
  /** Number of real prior visits (the strip is bounded; this counts all). */
  totalPriorVisits: number;
  /** The in-progress visit's 1-based number in this patient's history. */
  visitOrdinal: number;
  /** Patient-pinned key facts (allergies/preferences) surfaced at top; null if none. */
  keyFacts: string | null;
};

/** AES-702 — a per-procedure deterministic aftercare instruction template. */
export type AftercareTemplate = {
  id: string;
  tenantId?: string | null;
  name: string;
  procedureType: string | null;
  body: string;
  isActive: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export type AftercareTemplateDraft = {
  name: string;
  procedureType?: string | null;
  body: string;
  isActive?: boolean;
};

// AES-303/304/403/401 — the patient-facing curated share.
export type ShareSectionInput = { label: string; body: string };
export type ShareMediaInput = { captureId: string; caption?: string };

export type CreatePatientShareInput = {
  patientId: string;
  sessionId?: string;
  title: string;
  sections: ShareSectionInput[];
  media: ShareMediaInput[];
  aftercare?: { templateId?: string; name?: string; body?: string } | null;
  /** Story C: include a plain-words "what we did" line (derived server-side; generic by default). */
  includeTreatments?: boolean;
  expiresInDays?: number;
};

export type PatientSharePreview = {
  payloadType: string;
  status: string;
  clinic: { name: string };
  patientName: string;
  title: string;
  visitDate: string | null;
  sections: ShareSectionInput[];
  media: Array<{ captureId: string; caption: string | null; url: string }>;
  aftercare: { templateId: string | null; name: string; body: string } | null;
  createdAt: string | null;
  expiresAt: string | null;
};

export type PatientShare = {
  id: string;
  patientId: string;
  sessionId: string | null;
  token: string;
  publicPath: string;
  payloadType: string;
  status: string;
  title: string;
  mediaCount: number;
  createdAt: string | null;
  updatedAt: string | null;
  expiresAt: string | null;
  revokedAt: string | null;
  preview?: PatientSharePreview | null;
};

// --- E9 multi-seat: worklist + clinic directory (AES-903) ---

/** One active staff member of the clinic (for the worklist line-up picker + name display). */
export type ClinicMember = {
  userId: string;
  displayName: string;
  role: string;
  isClinician: boolean;
};

/** A soft "line a patient up for a clinician" worklist entry (AES-903). */
export type WorklistEntry = {
  id: string;
  status: "waiting" | "seen" | "cancelled" | string;
  note: string | null;
  patientId: string;
  patientName: string | null;
  clinicianUserId: string;
  clinician: Attribution | null;
  /** Who lined this patient up (AES-901 attribution on the worklist). */
  linedUpBy: Attribution | null;
  sessionId: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  resolvedAt: string | null;
};

export type WorklistResponse = {
  scope: "mine" | "clinic" | string;
  clinicianId: string | null;
  status: string;
  items: WorklistEntry[];
};

export type PatientAssignmentDraft = {
  patientId?: string;
  displayName: string;
  nationalId?: string;
  /** Demographic fields carried when creating a new patient from the unified create form (B3). */
  phone?: string;
  dateOfBirth?: string;
  sex?: string;
  notes?: string;
  unassign?: boolean;
  /** The capture that justifies this (re)assignment — set when applying a per-capture suggestion. */
  basisCaptureId?: string;
};

export type CachedCapture = {
  id: string;
  blob: Blob;
  sourceName: string;
  contentType: string;
  size: number;
  createdAt: number;
  lastAccessedAt: number;
};

export type IdMapping = {
  id: string;
  kind: "capture" | "session";
  localId: string;
  backendId: string;
  tenantId: string;
  createdAt: number;
};

export type StoredWorkspaceState = {
  schemaVersion: 1;
  tenantId?: string;
  screen: string;
  activeSession: CaptureSession | null;
  selectedSessionId: string;
  assignmentSessionId: string;
  pendingCaptureKind: CaptureDraft["kind"] | null;
  updatedAt: number;
};
