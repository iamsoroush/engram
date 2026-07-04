"""Worklist request schemas (AES-903)."""

from pydantic import BaseModel, Field


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
