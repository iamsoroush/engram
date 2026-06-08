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


class AiModelConfigUpdate(BaseModel):
    """Live per-task model overrides. `{task: model_id}`; an empty value clears the override."""

    models: dict[str, str] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    patient_id: str | None = Field(default=None, alias="patientId")
    title: str | None = None
    summary: str | None = None
    captured_at: str | None = Field(default=None, alias="capturedAt")

    model_config = {"populate_by_name": True}


class SessionUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    generated_summary: str | None = Field(default=None, alias="generatedSummary")
    generated_report: str | None = Field(default=None, alias="generatedReport")
    report_model: dict[str, Any] | None = Field(default=None, alias="reportModel")
    report: dict[str, Any] | None = None
    summaries: dict[str, Any] | None = None
    findings: list[dict[str, Any]] | None = None
    processing_status: dict[str, Any] | None = Field(default=None, alias="processingStatus")
    extracted_metadata: dict[str, Any] | None = Field(default=None, alias="extractedMetadata")
    status: str | None = None

    model_config = {"populate_by_name": True}


class SessionSaveRequest(BaseModel):
    report_template_key: str | None = Field(default=None, alias="reportTemplateKey")

    model_config = {"populate_by_name": True}


class CaptureUpdate(BaseModel):
    status: str | None = None
    metadata: dict[str, Any] | None = None


class AssignPatientRequest(BaseModel):
    patient_id: str | None = Field(default=None, alias="patientId")
    reason: str | None = None
    source: str | None = "staff"
    # The capture that justifies this (re)assignment — set when applying a per-capture
    # `Suggested: reassign` so the assignment is attributed to that capture (its suggestion chip
    # clears), and the prior basis capture becomes a switchable alternate.
    basis_capture_id: str | None = Field(default=None, alias="basisCaptureId")

    model_config = {"populate_by_name": True}


class AiJobStartRequest(BaseModel):
    celery_task_id: str | None = None
    retry_count: int = 0


class AiJobCompleteRequest(BaseModel):
    output_key: str
    output: dict[str, Any]


class AiJobProgressRequest(BaseModel):
    output_key: str
    output: dict[str, Any]
    stage: str | None = None


class AiJobErrorRequest(BaseModel):
    error_message: str
    celery_task_id: str | None = None
    retry_count: int = 0
    retry_reason: str | None = None
