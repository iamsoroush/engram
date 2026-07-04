"""Capture-domain request schemas."""

from typing import Any

from pydantic import BaseModel


class CaptureUpdate(BaseModel):
    status: str | None = None
    metadata: dict[str, Any] | None = None
