"""Patient-domain request/response schemas: patient CRUD, duplicate guard, memory, assignment."""

from typing import Any

from pydantic import BaseModel, Field


class PatientWrite(BaseModel):
    display_name: str = Field(alias="displayName")
    legal_first_name: str | None = Field(default=None, alias="legalFirstName")
    legal_last_name: str | None = Field(default=None, alias="legalLastName")
    national_id: str | None = Field(default=None, alias="nationalId")
    date_of_birth: str | None = Field(default=None, alias="dateOfBirth")
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True}


class PatientPatch(BaseModel):
    display_name: str | None = Field(default=None, alias="displayName")
    legal_first_name: str | None = Field(default=None, alias="legalFirstName")
    legal_last_name: str | None = Field(default=None, alias="legalLastName")
    national_id: str | None = Field(default=None, alias="nationalId")
    date_of_birth: str | None = Field(default=None, alias="dateOfBirth")
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True}


class PatientIdentifyingContext(BaseModel):
    date_of_birth: str | None = Field(default=None, alias="dateOfBirth")
    sex: str | None = None
    phone: str | None = None
    national_id: str | None = Field(default=None, alias="nationalId")

    model_config = {"populate_by_name": True}


class PatientLatestSessionMetadata(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    title: str | None = None
    status: str | None = None
    summary: str | None = None
    capture_count: int = Field(default=0, alias="captureCount")
    captured_at: str | None = Field(default=None, alias="capturedAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class NeedsInputItem(BaseModel):
    """One critical human-decision item attached to a patient (the source of truth for both the
    patient-card needs-input badge and the Needs input tab). `kind` ∈ assign-patient |
    choose-patient | resolve-conflict | verify."""

    id: str
    kind: str
    session_id: str | None = Field(default=None, alias="sessionId")
    reason: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")

    model_config = {"populate_by_name": True}


class PatientMemoryRow(BaseModel):
    patient_id: str = Field(alias="patientId")
    display_name: str = Field(alias="displayName")
    identifying_context: PatientIdentifyingContext | None = Field(default=None, alias="identifyingContext")
    summary: str
    summary_source: str = Field(alias="summarySource")
    generated_summary: str | None = Field(default=None, alias="generatedSummary")
    rule_based_summary: str | None = Field(default=None, alias="ruleBasedSummary")
    metadata_sentence: str | None = Field(default=None, alias="metadataSentence")
    # Mock patient-memory lifecycle: "ready" once the canned summary is generated, "updating" while
    # a recent change is being (mock-)processed. `summary` carries the tier-aware memory text.
    memory_status: str = Field(default="ready", alias="memoryStatus")
    memory_updated_at: str | None = Field(default=None, alias="memoryUpdatedAt")
    latest_session_metadata: PatientLatestSessionMetadata | None = Field(default=None, alias="latestSessionMetadata")
    latest_session_id: str | None = Field(default=None, alias="latestSessionId")
    active_session_id: str | None = Field(default=None, alias="activeSessionId")
    active_session_count: int = Field(alias="activeSessionCount")
    session_count: int = Field(alias="sessionCount")
    complete: bool
    needs_input: bool = Field(alias="needsInput")
    needs_input_items: list[NeedsInputItem] = Field(default_factory=list, alias="needsInputItems")
    latest_visit_at: str | None = Field(default=None, alias="latestVisitAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class PatientMemoryListResponse(BaseModel):
    items: list[PatientMemoryRow]
    limit: int
    offset: int
    total: int


class PatientMemorySession(BaseModel):
    session_id: str = Field(alias="sessionId")
    title: str | None = None
    status: str
    summary: str
    generated_summary: str | None = Field(default=None, alias="generatedSummary")
    rule_based_summary: str | None = Field(default=None, alias="ruleBasedSummary")
    capture_count: int = Field(alias="captureCount")
    complete: bool
    needs_input: bool = Field(alias="needsInput")
    # Author attribution on the timeline (AES-901).
    created_by_user_id: str | None = Field(default=None, alias="createdByUserId")
    created_by: dict[str, Any] | None = Field(default=None, alias="createdBy")
    group_label: str = Field(alias="groupLabel")
    sort_date: str | None = Field(default=None, alias="sortDate")
    captured_at: str | None = Field(default=None, alias="capturedAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class PatientMemorySessionGroup(BaseModel):
    label: str
    sessions: list[PatientMemorySession]


class PatientMemoryHistorySection(BaseModel):
    label: str
    body: str


class PatientMemoryHistory(BaseModel):
    """The richer patient-history brief shown atop the timeline. Pro fills `sections`
    (Story so far / Worth remembering / Right now); Basic fills `visits` (a structural recap)."""

    mode: str  # "pro" | "basic"
    status: str = "ready"  # "ready" | "updating" (mirrors PatientMemoryRow.memoryStatus)
    snapshot: str
    sections: list[PatientMemoryHistorySection] = Field(default_factory=list)
    visits: list[str] = Field(default_factory=list)
    source: str
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class PatientMemoryDetailResponse(BaseModel):
    patient: PatientMemoryRow
    sessions: list[PatientMemorySession]
    groups: list[PatientMemorySessionGroup]
    history: PatientMemoryHistory | None = None
    # Pro line-up projection (storySoFar/rightNow/flags/hero/sinceLastVisit/status). Built by the
    # service; passthrough dict so the session context card can surface the curated brief.
    lineupCard: dict[str, Any] | None = None
    # Cross-visit clinical safety flags (allergy/contraindication/consent): [{key, kind, text}].
    safetyFlags: list[dict[str, Any]] = Field(default_factory=list)


class DuplicateCheckRequest(BaseModel):
    """Duplicate-patient guard input (AES-205): the identity being entered at create time."""

    display_name: str | None = Field(default=None, alias="displayName")
    national_id: str | None = Field(default=None, alias="nationalId")
    phone: str | None = None
    email: str | None = None

    model_config = {"populate_by_name": True}


class AssignPatientRequest(BaseModel):
    patient_id: str | None = Field(default=None, alias="patientId")
    reason: str | None = None
    source: str | None = "staff"
    # The capture that justifies this (re)assignment — set when applying a per-capture
    # `Suggested: reassign` so the assignment is attributed to that capture (its suggestion chip
    # clears), and the prior basis capture becomes a switchable alternate.
    basis_capture_id: str | None = Field(default=None, alias="basisCaptureId")

    model_config = {"populate_by_name": True}
