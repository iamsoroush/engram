"""Aftercare-template request schemas (AES-702)."""

from pydantic import BaseModel, Field


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
