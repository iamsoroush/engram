import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda values: [item.value for item in values])


class TenantStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    archived = "archived"


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    invited = "invited"


class MembershipRole(str, enum.Enum):
    # ``owner`` is the clinic's founding user (created by self-serve sign-up): a full superset that
    # can both capture (like staff) and administer the tenant (like admin), and is always ``full`` in
    # the multi-seat permission model. Additive — it never changes doctor/assistant/admin semantics.
    owner = "owner"
    doctor = "doctor"
    assistant = "assistant"
    admin = "admin"
    patient = "patient"


class MembershipStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    invited = "invited"


class PatientStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class PatientUserLinkStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class SessionStatus(str, enum.Enum):
    draft = "draft"
    unassigned = "unassigned"
    needs_review = "needs_review"
    processing = "processing"
    organized = "organized"
    reviewing = "reviewing"
    verified = "verified"
    reopened = "reopened"
    failed = "failed"


class OrganizationSource(str, enum.Enum):
    none = "none"
    staff = "staff"
    ai_engine = "ai-engine"


class CaptureType(str, enum.Enum):
    audio = "audio"
    photo = "photo"
    note = "note"


class CaptureStatus(str, enum.Enum):
    received = "received"
    processing = "processing"
    processed = "processed"
    needs_attention = "needs_attention"
    deleted = "deleted"


class ArtifactKind(str, enum.Enum):
    source = "source"
    transcript = "transcript"
    ocr_text = "ocr_text"
    thumbnail = "thumbnail"
    summary = "summary"
    normalized_note = "normalized_note"
    other = "other"


class AiJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    completed = "completed"
    failed = "failed"


class AiJobType(str, enum.Enum):
    capture_process = "capture_process"
    audio_capture_process = "audio_capture_process"
    text_capture_process = "text_capture_process"
    image_capture_process = "image_capture_process"
    session_organize = "session_organize"
    # Combined patient summary + history (Pro). Patient-scoped (uses `patient_id`, not capture/session).
    patient_memory = "patient_memory"
    # Post-session patient↔clinic Q&A reply draft (Pro, AES-402). Patient-scoped (uses `patient_id`);
    # the target Q&A message/thread is carried in `AiJob.result_metadata` so no ai_jobs schema change
    # is needed. See `app/services/qa.py`.
    qa_draft = "qa_draft"
    # Voice edit of a Q&A reply (Pro, AES-402): the doctor's spoken note revises the current draft or
    # replaces it with a new reply — the job classifies which. Patient-scoped like `qa_draft`; the
    # audio object key + current draft live in `AiJob.result_metadata`.
    qa_revise = "qa_revise"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[TenantStatus] = mapped_column(
        pg_enum(TenantStatus, "tenant_status"), nullable=False, default=TenantStatus.active
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pro")
    # Language preferences: transcription "auto" = transcribe verbatim in the spoken
    # language/script; report_language NULL = follow the report template's default.
    transcription_language: Mapped[str] = mapped_column(String(20), nullable=False, server_default="auto")
    report_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # App UI language + date calendar (Jalali when Persian). Distinct from report_language, which
    # scopes only generated report/share content. Default English.
    app_language: Mapped[str] = mapped_column(String(20), nullable=False, server_default="en")
    # Fuzzy-match auto-apply line (H3): "strict" = deterministic matches only (default,
    # preserves prior behavior); "balanced"/"lenient" auto-apply a single high-confidence
    # fuzzy match on an explicit reassignment instruction (high/lower threshold).
    match_strictness: Mapped[str] = mapped_column(String(20), nullable=False, server_default="strict")
    # Story C (decision 2): may a curated patient share's plain-words treatment line include commercial
    # brand names? Default off (generic category only). Dose tables + lots stay always-withheld.
    share_include_brands: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Post-session Q&A routing policy (Pro, AES-402; foundation §7). "ai_default" = a new patient
    # Q&A thread auto-routes to the patient's treating doctor (most recent/frequent); "manual" = the
    # thread starts unrouted and staff route it. Manual re-route is always available either way.
    qa_routing_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ai_default")
    # Vertical (A0): the kind of clinic/lab this tenant runs. The report-required work-unit
    # (today's Session) is the generic Encounter; its presentation label and per-type
    # `Session.attributes` are derived from this. "clinic" for v1; "radiology"/"pathology" later.
    vertical: Mapped[str] = mapped_column(String(40), nullable=False, server_default="clinic")
    # Multi-seat role permissions (AES-905): per non-owner role preset
    # ("contribute" | "reassign" | "full"), e.g. {"assistant": "reassign"}. Permissive,
    # tenant-configurable; empty/missing keys fall back to the permissive defaults in
    # ``services.permissions``. The session owner and admins are always "full" and are not
    # stored here. JSONB (not an enum) to match tier/match_strictness/vertical.
    role_permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    memberships: Mapped[list["TenantMembership"]] = relationship(back_populates="tenant")
    patients: Mapped[list["Patient"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(240))
    auth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), nullable=False, default=UserStatus.active
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    memberships: Mapped[list["TenantMembership"]] = relationship(back_populates="user")


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_id_user_id"),
        Index("ix_tenant_memberships_tenant_id_role", "tenant_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(pg_enum(MembershipRole, "membership_role"), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        pg_enum(MembershipStatus, "membership_status"), nullable=False, default=MembershipStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_tenant_id_display_name", "tenant_id", "display_name"),
        Index("ix_patients_tenant_id_date_of_birth", "tenant_id", "date_of_birth"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    legal_first_name: Mapped[str | None] = mapped_column(String(120))
    legal_last_name: Mapped[str | None] = mapped_column(String(120))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(40))
    phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(320))
    notes: Mapped[str | None] = mapped_column(Text)
    # Mock patient-memory intelligence (placeholder for a future AI job): the tier-aware card
    # `summary` + its refresh lifecycle. JSONB blob shaped like
    # {status: "ready"|"updating", mode: "pro"|"basic", summary, source, updated_at,
    # updating_since, ready_at}. NULL = never generated yet (read paths fall back to the
    # deterministic rule-based summary). The richer `history` is generated on read, not stored.
    memory: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[PatientStatus] = mapped_column(
        pg_enum(PatientStatus, "patient_status"), nullable=False, default=PatientStatus.active
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    tenant: Mapped[Tenant] = relationship(back_populates="patients")
    identifiers: Mapped[list["PatientIdentifier"]] = relationship(back_populates="patient")


class PatientUserLink(Base):
    __tablename__ = "patient_user_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id", name="uq_patient_user_links_tenant_id_patient_id"),
        UniqueConstraint("tenant_id", "user_id", name="uq_patient_user_links_tenant_id_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[PatientUserLinkStatus] = mapped_column(
        pg_enum(PatientUserLinkStatus, "patient_user_link_status"),
        nullable=False,
        default=PatientUserLinkStatus.active,
    )
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientIdentifier(Base):
    __tablename__ = "patient_identifiers"
    __table_args__ = (
        Index("ix_patient_identifiers_tenant_id_type_normalized", "tenant_id", "identifier_type", "normalized_value"),
        Index("ix_patient_identifiers_patient_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(80), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    identifier_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    patient: Mapped[Patient] = relationship(back_populates="identifiers")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_tenant_id_status_updated_at", "tenant_id", "status", "updated_at"),
        Index("ix_sessions_tenant_id_patient_id", "tenant_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, "session_status"), nullable=False, default=SessionStatus.unassigned
    )
    title: Mapped[str | None] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    generated_summary: Mapped[str | None] = mapped_column(Text)
    generated_report: Mapped[str | None] = mapped_column(Text)
    report_model: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extracted_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Per-vertical extension point (A0): reserved for the second vertical's typed fields
    # (radiology: accession/modality/body_part; pathology: specimen_id/stain). Empty for clinics.
    # Kept separate from extracted_metadata (which holds AI/processing output).
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    report_template_key: Mapped[str | None] = mapped_column(String(120))
    organization_source: Mapped[OrganizationSource] = mapped_column(
        pg_enum(OrganizationSource, "organization_source"), nullable=False, default=OrganizationSource.none
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    review_started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppConfig(Base):
    """Global (non-tenant) operational key/value config, editable at runtime.

    Powers live per-task AI model selection (key ``ai_models`` → ``{task: model_id}``). The backend
    reads it when it builds each worker job payload, so changing a model takes effect on the next AI
    request without a restart. Gateway URL/keys stay in the worker's env; only the model id is live.
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )


class Capture(Base):
    __tablename__ = "captures"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "created_by_user_id",
            "client_capture_id",
            name="uq_captures_tenant_id_created_by_user_id_client_capture_id",
        ),
        Index("ix_captures_tenant_id_session_id", "tenant_id", "session_id"),
        Index("ix_captures_tenant_id_patient_id", "tenant_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    capture_type: Mapped[CaptureType] = mapped_column(pg_enum(CaptureType, "capture_type"), nullable=False)
    status: Mapped[CaptureStatus] = mapped_column(
        pg_enum(CaptureStatus, "capture_status"), nullable=False, default=CaptureStatus.received
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"))
    client_capture_id: Mapped[str] = mapped_column(String(120), nullable=False)
    capture_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )


class AiJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        Index("ix_ai_jobs_tenant_id_status_created_at", "tenant_id", "status", "created_at"),
        Index("ix_ai_jobs_tenant_id_session_id", "tenant_id", "session_id"),
        Index("ix_ai_jobs_status_next_retry_at", "status", "next_retry_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    capture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("captures.id", ondelete="CASCADE"))
    # Patient-scoped jobs (patient_memory) reference the patient instead of a capture/session.
    patient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    job_type: Mapped[AiJobType] = mapped_column(pg_enum(AiJobType, "ai_job_type"), nullable=False)
    status: Mapped[AiJobStatus] = mapped_column(
        pg_enum(AiJobStatus, "ai_job_status"), nullable=False, default=AiJobStatus.queued
    )
    generated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="ai-engine")
    input_artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_reason: Mapped[str | None] = mapped_column(String(120))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_artifacts_bucket_object_key"),
        Index("ix_artifacts_tenant_id_capture_id", "tenant_id", "capture_id"),
        Index("ix_artifacts_tenant_id_session_id", "tenant_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    capture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("captures.id", ondelete="SET NULL"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_jobs.id", ondelete="SET NULL"))
    artifact_kind: Mapped[ArtifactKind] = mapped_column(pg_enum(ArtifactKind, "artifact_kind"), nullable=False)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    generated_by: Mapped[str | None] = mapped_column(String(80))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_audit_events_tenant_id_target", "tenant_id", "target_type", "target_id"),
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(120))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AftercareTemplate(Base):
    """A reusable, per-procedure aftercare instruction template (aesthetics-Basic, AES-702).

    Deterministic content managed in Settings; selectable + editable per send when a curated
    patient share is created (AES-304). ``procedure_type`` is a free-form clinic label
    (e.g. ``botox``/``filler``); ``None`` is a general template.
    """

    __tablename__ = "aftercare_templates"
    __table_args__ = (
        Index("ix_aftercare_templates_tenant_id_procedure_type", "tenant_id", "procedure_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    procedure_type: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )


class PatientShare(Base):
    """A tokenized, revocable clinic→patient share of CURATED content (the patient surface).

    The shared primitive of [foundation §4]: a single clinic→patient channel. The Basic payload
    (``report_aftercare``) carries a curated, read-only snapshot — selected sections + media refs +
    aftercare — in ``content``. Storing a snapshot is the withholding contract (AES-403): raw
    captures, internal notes, lots, national ID, and other visits are never copied in, so the public
    read can only ever return what staff explicitly curated. The Pro Q&A payload lands later.
    """

    __tablename__ = "patient_shares"
    __table_args__ = (
        UniqueConstraint("token", name="uq_patient_shares_token"),
        Index("ix_patient_shares_tenant_id_patient_id", "tenant_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="report_aftercare")
    # "active" | "revoked" — String (not an enum type) to match tier/match_strictness/vertical.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class WorklistEntry(Base):
    """A soft "line a patient up for a clinician" entry — the multi-seat worklist (AES-903).

    Reception (or any staff) pre-assigns a patient to a clinician; that clinician sees them under
    "Today / up next" and taps through to the patient (history + before/after) to start a session.
    It is a *convenience lane*, never a gate: capture-first still starts a fresh session from the
    footer regardless of any worklist entry. Status is a plain String ("waiting" | "seen" |
    "cancelled") to match tier/vertical/share-status — no enum DDL. A soft list, NOT a scheduler:
    there is no time slot, only ordering by creation.
    """

    __tablename__ = "worklist_entries"
    __table_args__ = (
        Index("ix_worklist_entries_tenant_clinician_status", "tenant_id", "clinician_user_id", "status"),
        Index("ix_worklist_entries_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    # The clinician this patient is lined up for (whose "up next" list it appears on).
    clinician_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="waiting")
    note: Mapped[str | None] = mapped_column(Text)
    # The session created when the clinician started seeing this patient (set on "seen").
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QaThread(Base):
    """A post-session patient↔clinic Q&A channel (Pro payload of the patient surface; AES-402).

    The shared clinic→patient primitive ([foundation §4]): a single long-lived, tokenized,
    revocable thread per patient. The patient reaches it via ``token`` (the capability) with no
    login and sees ONLY their own questions + the doctor-verified replies (AES-403); drafts,
    routing, and every other patient are withheld. A thread routes to a treating doctor
    (``assigned_doctor_user_id``) per the tenant's ``qa_routing_mode``; ``routing_source`` records
    how (``ai_default`` / ``manual`` / ``unrouted``). Messages live in ``QaMessage``.
    """

    __tablename__ = "qa_threads"
    __table_args__ = (
        UniqueConstraint("token", name="uq_qa_threads_token"),
        # One Q&A channel per patient — created/reused idempotently.
        UniqueConstraint("tenant_id", "patient_id", name="uq_qa_threads_tenant_id_patient_id"),
        Index("ix_qa_threads_tenant_id_assigned_doctor", "tenant_id", "assigned_doctor_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    # "active" | "revoked" — plain String to match patient_shares / tier / vertical (no enum DDL).
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    assigned_doctor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # "ai_default" (auto-routed to the treating doctor) | "manual" (re-routed by staff) | "unrouted".
    routing_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ai_default")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class QaMessage(Base):
    """One message in a Q&A thread: a patient question or a doctor-verified reply (AES-402).

    A patient question carries the AI-drafted ``draft`` (the doctor's *suggested reply*, never shown
    to the patient) until a doctor approves it; sending creates a separate ``role="doctor"`` reply
    linked back via ``in_reply_to_id`` and flips the question's ``status`` to ``answered``. The draft
    is produced by a backend-owned ``qa_draft`` AI job (``draft_job_id``); a stale/failed draft is
    silent and self-healing, never a needs-input item.
    """

    __tablename__ = "qa_messages"
    __table_args__ = (
        Index("ix_qa_messages_tenant_id_thread_id", "tenant_id", "thread_id"),
        Index("ix_qa_messages_tenant_id_role_status", "tenant_id", "role", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_threads.id", ondelete="CASCADE"), nullable=False)
    # "patient" (a question) | "doctor" (a verified, sent reply).
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Question lifecycle: "pending" → "answered" | "dismissed". A doctor reply is "sent".
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    in_reply_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("qa_messages.id", ondelete="SET NULL"))
    # AI-suggested reply for a patient question (doctor-only; withheld from the patient surface).
    draft: Mapped[str | None] = mapped_column(Text)
    # "none" | "pending" (draft job in flight) | "ready" | "failed".
    draft_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="none")
    draft_source: Mapped[str | None] = mapped_column(String(80))
    draft_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )


class AiFeedbackEvent(Base):
    """A harvested AI-quality signal: a staff CORRECTION of an AI output, or a thumbs RATING.

    The eval golden-set harvester (``docs/ai_engine/eval-epic.md`` §1b): every production correction
    of an AI output (transcript / caption / treatment / patient-match) and every report/brief rating is
    logged here as a candidate eval case, so MVP user testing seeds the golden set instead of relying on
    remembered bugs. Append-only, cheap, non-blocking — a correction row is written in the *same*
    transaction as the edit it records (like ``AuditEvent``), never breaking the primary action.

    ``kind`` ∈ ``correction`` (staff edited/overrode an AI output) | ``confirmation`` (staff confirmed
    an AI suggestion — a positive case) | ``rating`` (a report/brief thumbs). ``ai_output_type`` ∈
    ``transcript`` | ``caption`` | ``treatment`` | ``patient_match`` | ``report`` | ``brief``.

    PII posture: the before/after AI-output *text* is stored verbatim because it IS the eval target
    (a transcript's confusable name is the case). Structured patient PII (names, national id, phone,
    DOB, address) never enters ``context`` — it is scrubbed by ``services.feedback.scrub_context``.
    """

    __tablename__ = "ai_feedback_events"
    __table_args__ = (
        Index("ix_ai_feedback_events_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_ai_feedback_events_tenant_id_kind_output", "tenant_id", "kind", "ai_output_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_output_type: Mapped[str] = mapped_column(String(40), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    capture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("captures.id", ondelete="SET NULL"))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    # The AI's output before the correction (verbatim — the eval target) and the human-corrected value.
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    # Thumbs rating for kind="rating": +1 up / -1 down. NULL for corrections/confirmations.
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    # Minimal, PII-scrubbed context (job_type, confidence, source, key, model…). Never raw patient PII.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuthRefreshToken(Base):
    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("jti", name="uq_auth_refresh_tokens_jti"),
        Index("ix_auth_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    jti: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
