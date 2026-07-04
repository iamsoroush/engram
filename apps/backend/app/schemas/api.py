"""Backward-compatible aggregator for the per-domain API schemas.

The request/response models now live in per-domain modules under ``app/schemas/`` (mirroring the
router split). This module re-exports them so existing ``from app.schemas.api import X`` imports keep
working; new code should import from the domain module directly (e.g.
``from app.schemas.patients import PatientWrite``).
"""

from app.schemas.ai_jobs import (
    AiJobCompleteRequest,
    AiJobErrorRequest,
    AiJobProgressRequest,
    AiJobStartRequest,
)
from app.schemas.aftercare import AftercareTemplatePatch, AftercareTemplateWrite
from app.schemas.captures import CaptureUpdate
from app.schemas.feedback import FeedbackCreate
from app.schemas.patients import (
    AssignPatientRequest,
    DuplicateCheckRequest,
    NeedsInputItem,
    PatientIdentifyingContext,
    PatientLatestSessionMetadata,
    PatientMemoryDetailResponse,
    PatientMemoryHistory,
    PatientMemoryHistorySection,
    PatientMemoryListResponse,
    PatientMemoryRow,
    PatientMemorySession,
    PatientMemorySessionGroup,
    PatientPatch,
    PatientWrite,
)
from app.schemas.shares import (
    PatientShareAftercareInput,
    PatientShareCreate,
    PatientShareMediaInput,
    PatientShareSectionInput,
)
from app.schemas.sessions import (
    SessionCreate,
    SessionSaveRequest,
    SessionUpdate,
    TherapyFormatRequest,
    TherapyReflectionsRequest,
    TherapyReleaseRequest,
    TherapyRiskRequest,
)
from app.schemas.tenant import AiModelConfigUpdate, AiUsageDevSetRequest
from app.schemas.worklist import WorklistEntryCreate, WorklistEntryResolve

__all__ = [
    "AftercareTemplatePatch",
    "AftercareTemplateWrite",
    "AiJobCompleteRequest",
    "AiJobErrorRequest",
    "AiJobProgressRequest",
    "AiJobStartRequest",
    "AiModelConfigUpdate",
    "AiUsageDevSetRequest",
    "AssignPatientRequest",
    "CaptureUpdate",
    "DuplicateCheckRequest",
    "FeedbackCreate",
    "NeedsInputItem",
    "PatientIdentifyingContext",
    "PatientLatestSessionMetadata",
    "PatientMemoryDetailResponse",
    "PatientMemoryHistory",
    "PatientMemoryHistorySection",
    "PatientMemoryListResponse",
    "PatientMemoryRow",
    "PatientMemorySession",
    "PatientMemorySessionGroup",
    "PatientPatch",
    "PatientShareAftercareInput",
    "PatientShareCreate",
    "PatientShareMediaInput",
    "PatientShareSectionInput",
    "PatientWrite",
    "SessionCreate",
    "SessionSaveRequest",
    "SessionUpdate",
    "TherapyFormatRequest",
    "TherapyReflectionsRequest",
    "TherapyReleaseRequest",
    "TherapyRiskRequest",
    "WorklistEntryCreate",
    "WorklistEntryResolve",
]
