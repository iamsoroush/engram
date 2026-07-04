"""AI-quality feedback request schema (eval-epic §1b)."""

from typing import Any

from pydantic import BaseModel, Field


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
