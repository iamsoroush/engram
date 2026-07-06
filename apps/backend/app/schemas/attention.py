"""Attention roll-up (Close-the-day) response schema — a superset of the needs-input decision set."""

from pydantic import BaseModel, Field


class AttentionItem(BaseModel):
    """One severity-tiered attention signal, rendered in place at its source and in the sweep.

    ``kind`` is the stable identity the frontend maps to a localized chrome label; ``tier`` is one of
    ``S1`` (safety, shown-not-counted) / ``S2`` (confirm) / ``S3`` (suggested) / ``qa`` (messages).
    ``reason`` + ``patientName`` are verbatim clinical content in the report language (never
    translated). ``dayGroup`` is ``today`` or ``earlier`` (the carry-over group).
    """

    id: str
    kind: str
    tier: str
    session_id: str | None = Field(default=None, alias="sessionId")
    patient_id: str | None = Field(default=None, alias="patientId")
    patient_name: str | None = Field(default=None, alias="patientName")
    clinician_id: str | None = Field(default=None, alias="clinicianId")
    thread_id: str | None = Field(default=None, alias="threadId")
    reason: str | None = None
    key: str | None = None
    sort_time: str | None = Field(default=None, alias="sortTime")
    day_group: str = Field(alias="dayGroup")

    model_config = {"populate_by_name": True}


class AttentionCounts(BaseModel):
    confirm: int
    suggested: int
    messages: int
    safety: int
    total: int


class AttentionResponse(BaseModel):
    schema_version: str = Field(alias="schemaVersion")
    scope: str
    counts: AttentionCounts
    highest_tier: str | None = Field(default=None, alias="highestTier")
    items: list[AttentionItem]

    model_config = {"populate_by_name": True}
