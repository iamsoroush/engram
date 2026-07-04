"""Session-domain request schemas: session CRUD, save, and the therapy sub-plane."""

from typing import Any

from pydantic import BaseModel, Field


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
