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


class TherapyFormatRequest(BaseModel):
    """Switch the therapy shareable-plane note format (DAP/SOAP/BIRP)."""

    format: str = Field(pattern="^(dap|soap|birp)$")


class TherapyReleaseRequest(BaseModel):
    """Explicitly release (or withdraw) the shareable therapy summary to the client."""

    released: bool = True


class TherapyRiskRequest(BaseModel):
    """Clinician-confirm (or clear) a dated risk flag (assisted detection only suggests)."""

    active: bool = True
    level: str | None = None
    note: str | None = None


class TherapyReflectionsRequest(BaseModel):
    """Private-plane reflections text (therapist-only; never exported)."""

    reflections: str | None = None


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


class FeedbackCreate(BaseModel):
    """A client-supplied AI-quality signal — the report/brief thumbs rating (eval-epic §1b).

    Staff corrections of transcript/caption/treatment/patient-match are harvested server-side; this
    endpoint carries the lightweight rating (``kind="rating"``, ``rating`` = +1/-1) and any other
    client signal. ``context`` is PII-scrubbed before it is stored.
    """

    kind: str | None = "rating"
    ai_output_type: str | None = Field(default="report", alias="aiOutputType")
    before: str | None = None
    after: str | None = None
    rating: int | None = None
    comment: str | None = None
    session_id: str | None = Field(default=None, alias="sessionId")
    capture_id: str | None = Field(default=None, alias="captureId")
    patient_id: str | None = Field(default=None, alias="patientId")
    context: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class DuplicateCheckRequest(BaseModel):
    """Duplicate-patient guard input (AES-205): the identity being entered at create time."""

    display_name: str | None = Field(default=None, alias="displayName")
    national_id: str | None = Field(default=None, alias="nationalId")
    phone: str | None = None
    email: str | None = None

    model_config = {"populate_by_name": True}


class AftercareTemplateWrite(BaseModel):
    """Create an aftercare template (AES-702)."""

    name: str
    procedure_type: str | None = Field(default=None, alias="procedureType")
    body: str
    is_active: bool = Field(default=True, alias="isActive")

    model_config = {"populate_by_name": True}


class AftercareTemplatePatch(BaseModel):
    """Patch an aftercare template (only provided keys change)."""

    name: str | None = None
    procedure_type: str | None = Field(default=None, alias="procedureType")
    body: str | None = None
    is_active: bool | None = Field(default=None, alias="isActive")

    model_config = {"populate_by_name": True}


class PatientShareSectionInput(BaseModel):
    """One curated text section in a patient share."""

    label: str = ""
    body: str = ""

    model_config = {"populate_by_name": True}


class PatientShareMediaInput(BaseModel):
    """One curated photo reference (must be the patient's own photo capture)."""

    capture_id: str = Field(alias="captureId")
    caption: str | None = None

    model_config = {"populate_by_name": True}


class PatientShareAftercareInput(BaseModel):
    """Aftercare block for a share: snapshot a template by id, or pass inline name+body."""

    template_id: str | None = Field(default=None, alias="templateId")
    name: str | None = None
    body: str | None = None

    model_config = {"populate_by_name": True}


class PatientShareCreate(BaseModel):
    """Create a curated, tokenized patient share (AES-303/304/403)."""

    patient_id: str = Field(alias="patientId")
    session_id: str | None = Field(default=None, alias="sessionId")
    title: str | None = None
    sections: list[PatientShareSectionInput] = Field(default_factory=list)
    media: list[PatientShareMediaInput] = Field(default_factory=list)
    aftercare: PatientShareAftercareInput | None = None
    # Story C (decision 2): include a plain-words "what we did" treatment line, derived server-side
    # from the session's treatments (area + category; brand only if the clinic opted in; never
    # dose/lot). Off by default — the doctor opts in per share.
    include_treatments: bool = Field(default=False, alias="includeTreatments")
    expires_in_days: int | None = Field(default=None, alias="expiresInDays", ge=1, le=365)

    model_config = {"populate_by_name": True}


class WorklistEntryCreate(BaseModel):
    """Line a patient up for a clinician (AES-903)."""

    patient_id: str = Field(alias="patientId")
    clinician_user_id: str = Field(alias="clinicianUserId")
    note: str | None = None

    model_config = {"populate_by_name": True}


class WorklistEntryResolve(BaseModel):
    """Mark a worklist entry seen — optionally linking the session the clinician started."""

    session_id: str | None = Field(default=None, alias="sessionId")

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
