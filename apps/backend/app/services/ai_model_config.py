"""Live, global per-task AI model selection.

Each AI task can run on a different model. The selection is a single global `app_config` row
(`ai_models` → `{task: model_id}`), read when the backend builds each worker job payload — so a
change takes effect on the **next** AI request with no restart. Only the model id is live here; the
gateway URL/key stay in the worker's env. A blank/absent override means "use the worker's env
default for that task".
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.models import AppConfig

AI_MODELS_KEY = "ai_models"

# The tasks whose model is live-selectable, with human labels for the settings UI. Keys must match
# the worker's `gateway_settings_for(task)` task names (+ `patient_memory` for the combined job).
AI_MODEL_TASKS: list[tuple[str, str]] = [
    ("transcription", "Audio transcription + intent"),
    ("caption", "Photo caption (Pro)"),
    ("note_decoration", "Note decoration (Pro)"),
    ("patient_memory", "Patient summary + history (Pro)"),
]
_VALID_TASKS = {task for task, _ in AI_MODEL_TASKS}


def get_ai_model_overrides(db: DbSession) -> dict[str, str]:
    """Return `{task: model_id}` for the tasks that have a non-empty override set."""
    row = db.get(AppConfig, AI_MODELS_KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    overrides: dict[str, str] = {}
    for task in _VALID_TASKS:
        model = value.get(task)
        if isinstance(model, str) and model.strip():
            overrides[task] = model.strip()
    return overrides


def set_ai_model_overrides(
    db: DbSession,
    updates: dict[str, str],
    *,
    user_id: uuid.UUID | None = None,
) -> dict[str, str]:
    """Merge model overrides for known tasks. An empty/whitespace value clears an override.

    Commits and returns the resulting override map.
    """
    row = db.get(AppConfig, AI_MODELS_KEY)
    current: dict[str, Any] = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    for task, model in (updates or {}).items():
        if task not in _VALID_TASKS:
            continue
        cleaned = (model or "").strip()
        if cleaned:
            current[task] = cleaned
        else:
            current.pop(task, None)
    if row is None:
        row = AppConfig(key=AI_MODELS_KEY, value=current, updated_by_user_id=user_id)
        db.add(row)
    else:
        row.value = current
        row.updated_by_user_id = user_id
    db.commit()
    return get_ai_model_overrides(db)


def ai_model_settings_payload(db: DbSession) -> dict[str, Any]:
    """Shape the model config for the settings UI: every task + its override (blank = env default)."""
    overrides = get_ai_model_overrides(db)
    return {
        "tasks": [
            {"task": task, "label": label, "model": overrides.get(task, "")}
            for task, label in AI_MODEL_TASKS
        ]
    }
