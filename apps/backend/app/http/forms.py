"""Multipart form-field parsing shared by the capture-upload routes."""

import json
from typing import Any

from fastapi import HTTPException


def parse_metadata_form(metadata: str | None) -> dict[str, Any] | None:
    """Parse the optional ``metadata`` multipart field into a dict.

    Returns ``None`` when the field is absent/empty. Raises ``400`` when it is present but not a
    JSON object. Used by both capture-upload routes.
    """
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed
