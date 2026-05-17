from typing import Any

from pydantic import BaseModel, Field


class PatientWrite(BaseModel):
    display_name: str = Field(alias="displayName")
    legal_first_name: str | None = Field(default=None, alias="legalFirstName")
    legal_last_name: str | None = Field(default=None, alias="legalLastName")
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
    date_of_birth: str | None = Field(default=None, alias="dateOfBirth")
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True}


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
    status: str | None = None

    model_config = {"populate_by_name": True}


class CaptureUpdate(BaseModel):
    status: str | None = None
    metadata: dict[str, Any] | None = None


class AssignPatientRequest(BaseModel):
    patient_id: str | None = Field(default=None, alias="patientId")
    reason: str | None = None
    source: str | None = "staff"

    model_config = {"populate_by_name": True}


class AiJobStartRequest(BaseModel):
    celery_task_id: str | None = None
    retry_count: int = 0


class AiJobCompleteRequest(BaseModel):
    output_key: str
    output: dict[str, Any]


class AiJobErrorRequest(BaseModel):
    error_message: str
    celery_task_id: str | None = None
    retry_count: int = 0
