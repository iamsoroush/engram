"""Patient-share request schemas (AES-303/304/403)."""

from pydantic import BaseModel, Field


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
