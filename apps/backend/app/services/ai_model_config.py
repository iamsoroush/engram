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
    ("patient_memory", "Patient summary + history (Pro)"),
    ("qa_draft", "Patient Q&A reply draft (Pro)"),
    ("report_synthesis", "Report synthesis + treatments (Pro)"),
]
_VALID_TASKS = {task for task, _ in AI_MODEL_TASKS}


def _task_entry(value: Any) -> tuple[str | None, str | None]:
    """Read a task's override as (model, reasoningEffort) from a bare string or a richer object.

    A task value may be a plain model id (legacy) or `{model, reasoningEffort}` — the richer shape
    carries the per-task quality knob (Story A's config plumbing, decoupled from its super-admin gate).
    """
    if isinstance(value, str):
        model = value.strip()
        return (model or None, None)
    if isinstance(value, dict):
        model = value.get("model")
        effort = value.get("reasoningEffort")
        return (
            model.strip() if isinstance(model, str) and model.strip() else None,
            effort.strip() if isinstance(effort, str) and effort.strip() else None,
        )
    return (None, None)


def get_ai_model_overrides(db: DbSession) -> dict[str, str]:
    """Return `{task: model_id}` for the tasks that have a non-empty model override set."""
    row = db.get(AppConfig, AI_MODELS_KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    overrides: dict[str, str] = {}
    for task in _VALID_TASKS:
        model, _ = _task_entry(value.get(task))
        if model:
            overrides[task] = model
    return overrides


def ai_models_worker_payload(db: DbSession) -> dict[str, Any]:
    """Build the live `aiModels` payload for a worker job.

    Each task maps to a bare model string (legacy/back-compat) OR a `{model, reasoningEffort}` object
    when an effort is configured. The worker's `resolve_model` / `resolve_reasoning_effort` accept
    both. Only the model id + effort are live here; the gateway URL/key stay in the worker env.
    """
    row = db.get(AppConfig, AI_MODELS_KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    payload: dict[str, Any] = {}
    for task in _VALID_TASKS:
        model, effort = _task_entry(value.get(task))
        if effort:
            payload[task] = {"model": model or "", "reasoningEffort": effort}
        elif model:
            payload[task] = model
    return payload


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
        existing = current.get(task)
        # Preserve a separately-configured reasoningEffort (the richer task shape) when the picker
        # only changes the model — the effort is a distinct knob, not cleared by a model edit.
        if isinstance(existing, dict) and existing.get("reasoningEffort"):
            if cleaned:
                current[task] = {**existing, "model": cleaned}
            else:
                current[task] = {"reasoningEffort": existing["reasoningEffort"]}
        elif cleaned:
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
