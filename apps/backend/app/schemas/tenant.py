"""Tenant/clinic-configuration request schemas: AI model overrides, dev usage jump."""

from pydantic import BaseModel, Field


class AiModelConfigUpdate(BaseModel):
    """Live per-task model overrides. `{task: model_id}`; an empty value clears the override."""

    models: dict[str, str] = Field(default_factory=dict)


class AiUsageDevSetRequest(BaseModel):
    """DEV/TEST ONLY: jump the clinic to this percent of its monthly AI budget."""

    percent: float = 0.0
