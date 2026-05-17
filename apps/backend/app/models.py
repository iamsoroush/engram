import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
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
    fake_processing = "fake-processing"


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


class FakeJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    completed = "completed"
    failed = "failed"


class FakeJobType(str, enum.Enum):
    capture_process = "capture_process"
    audio_capture_process = "audio_capture_process"
    text_capture_process = "text_capture_process"
    image_capture_process = "image_capture_process"
    session_organize = "session_organize"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[TenantStatus] = mapped_column(
        pg_enum(TenantStatus, "tenant_status"), nullable=False, default=TenantStatus.active
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


class FakeJob(Base):
    __tablename__ = "fake_jobs"
    __table_args__ = (
        Index("ix_fake_jobs_tenant_id_status_created_at", "tenant_id", "status", "created_at"),
        Index("ix_fake_jobs_tenant_id_session_id", "tenant_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    capture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("captures.id", ondelete="CASCADE"))
    job_type: Mapped[FakeJobType] = mapped_column(pg_enum(FakeJobType, "fake_job_type"), nullable=False)
    status: Mapped[FakeJobStatus] = mapped_column(
        pg_enum(FakeJobStatus, "fake_job_status"), nullable=False, default=FakeJobStatus.queued
    )
    generated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="fake-processing")
    input_artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
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
    fake_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fake_jobs.id", ondelete="SET NULL"))
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
